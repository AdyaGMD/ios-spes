#!/usr/bin/env python3
"""Verify a prepared userdata delta in recovery. Writes require --apply."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('delta',type=Path);p.add_argument('--adb',default='adb')
p.add_argument('--apply',action='store_true');p.add_argument('--rollback',action='store_true')
a=p.parse_args();m=json.loads((a.delta/'manifest.json').read_text())
def adb(*args):return subprocess.run([a.adb,*args],check=True,capture_output=True).stdout
def sha(b):return hashlib.sha256(b).hexdigest()
if m['block_size']!=1048576 or m['size']!=17179869184:raise SystemExit('Unexpected volume geometry')
if adb('shell','getprop ro.product.device').strip()!=b'spes':raise SystemExit('Wrong device')
part=adb('shell','readlink -f /dev/block/by-name/userdata').decode().strip()
if part!='/dev/block/sda16':raise SystemExit('Unexpected userdata mapping; re-inspect device')
for line in adb('shell','cat /proc/mounts').decode().splitlines():
 if line.split()[0] in [part,'/dev/block/by-name/userdata']:raise SystemExit('Userdata is mounted')
source,target=('after','before') if a.rollback else ('before','after')
seen=set()
for row in m['blocks']:
 n=row['block'];stem=row['stem']
 if type(n)!=int or not 0<=n<16384 or n in seen or stem!=f'{n:05d}':raise SystemExit('Invalid manifest block')
 seen.add(n)
 for kind in ['before','after']:
  b=(a.delta/(stem+'.'+kind)).read_bytes()
  if len(b)!=1048576 or sha(b)!=row[kind]:raise SystemExit('Payload checksum mismatch')
def read(n):return adb('exec-out',f'dd if=/dev/block/by-name/userdata bs=1048576 skip={n} count=1 2>/dev/null')
pending=[]
for row in m['blocks']:
 current=sha(read(row['block']))
 if a.rollback and current==row[target]:continue
 if current!=row[source]:raise SystemExit(f"Device differs at block {row['block']}; no writes performed")
 pending.append(row)
print(f"Verified all {len(seen)} blocks; {len(pending)} need changes",flush=True)
if not a.apply:
 print('Verification only; no writes performed');sys.exit(0)
for row in pending:
 n=row['block']
 if sha(read(n))!=row[source]:raise SystemExit(f'Device changed at block {n}; stopped')
 adb('push',str(a.delta/(row['stem']+'.'+target)),'/tmp/spes-root-delta-block')
 got=adb('shell','sha256sum /tmp/spes-root-delta-block').decode().split()[0]
 if got!=row[target]:raise SystemExit('Transferred payload checksum mismatch')
 adb('shell',f'dd if=/tmp/spes-root-delta-block of=/dev/block/by-name/userdata bs=1048576 seek={n} count=1 conv=notrunc,fsync')
 if sha(read(n))!=row[target]:raise SystemExit(f'Readback mismatch at block {n}; stopped')
 print(f'Written and verified block {n}',flush=True)
adb('shell','rm /tmp/spes-root-delta-block')
print('All changed blocks installed and readback verified; remain in recovery until boot image is ready')
