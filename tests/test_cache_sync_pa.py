"""Regression: cache-mode changes must retain physical address bits above 4 GiB."""
import subprocess,tempfile,unittest
from pathlib import Path
class CacheAddressTests(unittest.TestCase):
 def test_actual_patch_expression_retains_high_physical_bits(self):
  patch=(Path(__file__).resolve().parents[1]/'xnu/patches/0101-spes-cache-sync-high-pa.patch').read_text()
  line=next(s[1:] for s in patch.splitlines() if s.startswith('+\tflush_dcache('))
  source='''#include <stdint.h>
#include <assert.h>
typedef uint32_t ppnum_t;
typedef uint64_t vm_offset_t;
#define PAGE_SHIFT 14
#define PAGE_SIZE (1u<<PAGE_SHIFT)
#define TRUE 1
static uint64_t seen;
static void flush_dcache(uint64_t pa,unsigned count,int phys){assert(count==PAGE_SIZE && phys);seen=pa;}
static void sync_page(ppnum_t pp){'''+line+'''}
int main(void){
uint64_t pages[]={0xffffc000ULL,0x100000000ULL,0x103f18000ULL,0x1341a8000ULL,0x1c7ffc000ULL,0x3fffffffc000ULL};
for(unsigned i=0;i<sizeof(pages)/sizeof(pages[0]);++i){sync_page((ppnum_t)(pages[i]>>14));assert(seen==pages[i]);}
uint32_t old_page=(uint32_t)(0x1341a8000ULL>>14);
assert((uint64_t)(old_page<<14)==0x341a8000ULL);
return 0;}
'''
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'test.c').write_text(source)
   subprocess.run(['clang','-Wall','-Werror','-fsanitize=undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
   subprocess.run([str(p/'test')],check=True)
