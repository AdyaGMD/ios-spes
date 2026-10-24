#!/usr/bin/env python3
"""Create reversible changed-block payloads from equal-sized offline root images."""
import argparse,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('output',type=Path)
a=p.parse_args();size=a.before.stat().st_size
if size!=a.after.stat().st_size or size%1048576:p.error('Images must have equal whole-MiB sizes')
if a.output.exists():p.error('Output already exists')
a.output.mkdir(parents=True)
rows=[]
with a.before.open('rb') as old,a.after.open('rb') as new:
 for offset in range(0,size,1048576):
  x,y=old.read(1048576),new.read(1048576)
  if x==y:continue
  stem=f'{offset//1048576:05d}'
  (a.output/(stem+'.before')).write_bytes(x)
  (a.output/(stem+'.after')).write_bytes(y)
  rows.append(dict(block=offset//1048576,before=hashlib.sha256(x).hexdigest(),after=hashlib.sha256(y).hexdigest(),stem=stem))
manifest=dict(size=size,block_size=1048576,changed_bytes=len(rows)*1048576,blocks=rows)
(a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(f'{len(rows)} changed MiB; forward and rollback payloads retained; nothing written to device')
