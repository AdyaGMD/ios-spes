#!/usr/bin/env python3
"""Read-only audio/WLAN inventory from a live spes FDT; writes no hardware."""
import argparse,json,re,struct
from pathlib import Path
from spes_memory import parse

def inventory(blob):
 nodes,_=parse(blob)
 if b'qcom,khaje\0' not in nodes.get('',{}).get('compatible',b''):
  raise ValueError('Expected khaje device tree')
 handles={int.from_bytes(p['phandle'],'big'):n for n,p in nodes.items() if 'phandle' in p}
 wanted=re.compile(r'aw87|bolero|rouleur|wcd937|icnss|wlan|adsp|lpass|sound|smp2p|glink|smd-edge|apr',re.I)
 def value(key,b):
  if not b:return True
  if (key in ('compatible','status','model','label','transport','device_type') or key.endswith(('-name','-names','-channels','-routing','-supplies','-label','-dma','-prefix','-edges'))) and b.endswith(b'\0') and b[0] != 0 and all(part and all(32<=c<127 for c in part) for part in b[:-1].split(b'\0')):return b.rstrip(b'\0').decode().split('\0')
  if len(b)%4==0:return [f'0x{x:x}' for x in struct.unpack('>'+str(len(b)//4)+'I',b)]
  return {'hex':b.hex()}
 result={}
 for path,props in nodes.items():
  if not wanted.search(path+' '+props.get('compatible',b'').decode('ascii',errors='replace')):continue
  row={k:value(k,v) for k,v in props.items()}
  refs={}
  for key,b in props.items():
   if key in ('memory-region','interrupt-parent') or key.endswith('-supply') or key.startswith('pinctrl-') and key!='pinctrl-names':
    if len(b)%4==0:
     refs[key]=[handles.get(int.from_bytes(b[i:i+4],'big'),'unresolved') for i in range(0,len(b),4)]
  if refs:row['_references']=refs
  result[path]=row
 return result
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('dtb',type=Path);a=ap.parse_args()
 print(json.dumps(inventory(a.dtb.read_bytes()),indent=2,sort_keys=True))
