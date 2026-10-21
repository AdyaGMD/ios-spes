#!/usr/bin/env python3
"""Read-only FAT16 firmware extent map. No phone access or firmware extraction.
Usage: map-modem-fat16.py MODEM_BACKUP OUTPUT_JSON
Offsets are relative to the partition, never to a whole UFS device.
"""
import hashlib, json, struct, sys, zlib
from pathlib import Path

class Fat16:
    def __init__(self, data):
        self.data = data
        if len(data) < 512 or data[510:512] != b'\x55\xaa':
            raise ValueError('missing FAT boot sector')
        self.bps = struct.unpack_from('<H', data, 11)[0]
        self.spc = data[13]
        self.reserved = struct.unpack_from('<H', data, 14)[0]
        self.nfat = data[16]
        self.roots = struct.unpack_from('<H', data, 17)[0]
        total16 = struct.unpack_from('<H', data, 19)[0]
        self.total = total16 or struct.unpack_from('<I', data, 32)[0]
        self.fatsectors = struct.unpack_from('<H', data, 22)[0]
        if self.bps not in (512,1024,2048,4096) or not self.spc or self.spc & (self.spc-1):
            raise ValueError('unsupported sector/cluster geometry')
        self.root_sector = self.reserved + self.nfat * self.fatsectors
        self.root_sectors = (self.roots * 32 + self.bps-1)//self.bps
        self.data_sector = self.root_sector + self.root_sectors
        self.clusters = (self.total - self.data_sector)//self.spc
        if not (4085 <= self.clusters < 65525) or not self.roots or not self.reserved or self.nfat not in (1,2):
            raise ValueError('expected FAT16')
        if self.total*self.bps > len(data) or self.fatsectors*self.bps < (self.clusters+2)*2:
            raise ValueError('truncated FAT volume')
        self.fat = data[self.reserved*self.bps:(self.reserved+self.fatsectors)*self.bps]
        for i in range(1,self.nfat):
            off=(self.reserved+i*self.fatsectors)*self.bps
            if data[off:off+len(self.fat)] != self.fat: raise ValueError('FAT copies disagree')
        self.cluster_bytes = self.bps*self.spc
        self.visited_dirs=set()

    def chain(self, start):
        seen=set(); chain=[]; cur=start
        while cur < 0xfff8:
            if not 2 <= cur < self.clusters+2 or cur in seen:
                raise ValueError('invalid/cyclic cluster chain')
            seen.add(cur);chain.append(cur)
            cur=struct.unpack_from('<H',self.fat,cur*2)[0]
        return chain

    def offset(self, c):
        return (self.data_sector+(c-2)*self.spc)*self.bps

    def walk(self, directory, prefix=''):
        lfn=[]
        for off in range(0,len(directory),32):
            e=directory[off:off+32]
            if e[0]==0: break
            if e[0]==0xe5: lfn=[];continue
            if e[11]==15:
                lfn.append(e);continue
            short=e[:8].decode('ascii').rstrip(); ext=e[8:11].decode('ascii').rstrip()
            name=short+('.'+ext if ext else '')
            if lfn:
                ordered=sorted(lfn,key=lambda x:x[0]&31)
                checksum=0
                for c in e[:11]: checksum=(((checksum&1)<<7)+(checksum>>1)+c)&255
                if [x[0]&31 for x in ordered] != list(range(1,len(lfn)+1)) or not lfn[0][0]&64 or any(x[13]!=checksum for x in lfn):
                    raise ValueError('invalid long filename')
                raw=b''.join(x[1:11]+x[14:26]+x[28:32] for x in ordered)
                name=raw.decode('utf-16le').split('\0')[0].rstrip('\uffff')
            lfn=[]
            if e[11]&8 or name in ('.','..'):continue
            if '/' in name or '\\' in name:raise ValueError('invalid filename')
            name=name.lower(); path=prefix+name
            start=struct.unpack_from('<H',e,26)[0]; size=struct.unpack_from('<I',e,28)[0]
            chain=self.chain(start) if start else []
            if e[11]&16:
                if not chain or start in self.visited_dirs:raise ValueError('cyclic directory')
                self.visited_dirs.add(start)
                d=b''.join(self.data[self.offset(c):self.offset(c)+self.cluster_bytes] for c in chain)
                yield from self.walk(d,path+'/');continue
            if size > len(chain)*self.cluster_bytes:raise ValueError('short file chain')
            extents=[]; left=size; crc=0; sha=hashlib.sha256()
            for c in chain:
                n=min(left,self.cluster_bytes)
                if not n:break
                o=self.offset(c); b=self.data[o:o+n]; crc=zlib.crc32(b,crc);sha.update(b)
                if extents and extents[-1]['offset']+extents[-1]['length']==o:extents[-1]['length']+=n
                else:extents.append({'offset':o,'length':n})
                left-=n
            yield path,{'size':size,'crc32':f'{crc:08x}','sha256':sha.hexdigest(),'extents':extents}

    def files(self):
        o=self.root_sector*self.bps
        entries=list(self.walk(self.data[o:o+self.roots*32]))
        result={}
        for path, entry in entries:
            if path in result:
                if (entry['size'],entry['sha256']) != (result[path]['size'],result[path]['sha256']):
                    raise ValueError('conflicting duplicate file path')
                continue  # Qualcomm images can carry identical duplicate board data.
            result[path]=entry
        return result

if __name__=='__main__':
    if len(sys.argv)!=3:sys.exit(__doc__)
    data=Path(sys.argv[1]).read_bytes(); fs=Fat16(data); files=fs.files()
    result={'partition_bytes':len(data),'partition_sha256':hashlib.sha256(data).hexdigest(),'files':files}
    with open(sys.argv[2],'x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(f'Mapped {len(files)} files; modem.mdt present: {"image/modem.mdt" in files}')
