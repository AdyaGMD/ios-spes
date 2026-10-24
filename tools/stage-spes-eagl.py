#!/usr/bin/env python3
"""Stage a backboardd copy with a weak EAGL bridge dependency. Never installs it."""
import argparse
import hashlib
import json
import plistlib
import struct
import subprocess
from pathlib import Path

LIB='/redwood/lib/libredwood-gl.dylib'
def add_dependency(data):
    b=bytearray(data)
    if len(b)<32 or struct.unpack_from('<II',b)!= (0xfeedfacf,0x100000c):
        raise ValueError('Expected thin arm64 Mach-O')
    n,size=struct.unpack_from('<II',b,16)
    end=32+size
    if end>len(b): raise ValueError('Truncated load commands')
    pos=32;first=len(b)
    for _ in range(n):
        if pos+8>end: raise ValueError('Truncated command')
        cmd,length=struct.unpack_from('<II',b,pos)
        if length<8 or length%8 or pos+length>end: raise ValueError('Invalid command size')
        if cmd in (0xc,0x80000018):
            if length<24: raise ValueError('Invalid dylib command')
            off=struct.unpack_from('<I',b,pos+8)[0]
            if off<24 or off>=length: raise ValueError('Invalid dylib name offset')
            if b[pos+off:pos+length].split(b'\0')[0]==LIB.encode():
                raise ValueError('Bridge already present')
        if cmd==0x19:
            if length<72: raise ValueError('Invalid segment')
            ns=struct.unpack_from('<I',b,pos+64)[0]
            if 72+ns*80>length: raise ValueError('Invalid section count')
            for j in range(ns):
                offset=struct.unpack_from('<I',b,pos+72+j*80+48)[0]
                if offset:first=min(first,offset)
        pos+=length
    if pos!=end: raise ValueError('Command count mismatch')
    length=(24+len(LIB)+1+7)&~7
    if end+length>first or end+length>len(b) or any(b[end:end+length]):
        raise ValueError('No zero header padding; refusing to move existing data')
    command=struct.pack('<6I',0x80000018,length,24,0,0,0)+LIB.encode()+b'\0'
    b[end:end+length]=command.ljust(length,b'\0')
    struct.pack_into('<II',b,16,n+1,size+length)
    return bytes(b)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args()
    if a.output.exists():p.error('Output directory exists; use a fresh staging directory')
    original=a.source.read_bytes();changed=add_dependency(original)
    ent=subprocess.run(['codesign','-d','--entitlements',':-',str(a.source)],check=True,capture_output=True).stdout
    plistlib.loads(ent)
    a.output.mkdir(parents=True)
    (a.output/'backboardd.original').write_bytes(original)
    dst=a.output/'backboardd';dst.write_bytes(changed);dst.chmod(0o755)
    e=a.output/'entitlements.plist';e.write_bytes(ent)
    subprocess.run(['codesign','--force','--sign','-','--entitlements',str(e),str(dst)],check=True)
    subprocess.run(['codesign','--verify',str(dst)],check=True)
    got=subprocess.run(['codesign','-d','--entitlements',':-',str(dst)],check=True,capture_output=True).stdout
    if plistlib.loads(got)!=plistlib.loads(ent):raise ValueError('Entitlements changed')
    manifest={'original_sha256':hashlib.sha256(original).hexdigest(),'patched_sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),'dependency':LIB,'installed':False}
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
