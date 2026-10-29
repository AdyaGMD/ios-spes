"""Exercise actual patched allocator/page-table code beyond the old 512 MiB limit."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_gpu_upstream_ports import patched_source

class AddressSpaceTests(unittest.TestCase):
    def test_two_gibibytes_and_reserved_mappings(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            source, = patched_source(d, ['bsd/dev/spes_gpu_backend.h'])
            code = source[:source.index('bool redwood_gpu_mapped(void)')]
            code += source[source.index('bool redwood_gpu_unmap('):source.index('void redwood_gpu_to_memory(')]
            code += source[source.index('static bool spes_gpu_address_space('):source.index('static bool spes_gpu_backend_start(')]
            prefix = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
typedef uintptr_t vm_offset_t;
typedef uintptr_t addr64_t;
#define PAGE_SIZE 16384
#define PAGE_MASK 16383
#define KMA_DATA 1
#define KMA_ZERO 2
#define KMA_PERMANENT 4
#define VM_KERN_MEMORY_IOKIT 1
#define KERN_SUCCESS 0
static int kernel_map,kernel_pmap;
static void *allocations[1100];
static unsigned allocated;
static bool fail_alloc;
static int kmem_alloc_contig(int k,vm_offset_t *p,size_t n,unsigned m,int a,int b,int f,int t){
 if(fail_alloc)return 1;
 assert(allocated<1100);allocations[allocated++]=calloc(1,n);
 *p=(uintptr_t)allocations[allocated-1];return 0;
}
static uint64_t pmap_find_phys(int p,addr64_t v){return (0x100000000ull+allocated*16384)>>14;}
#define ptoa_64(p) ((p)<<14)
static void to_memory(vm_offset_t p,size_t n){}
static void touch_wr(vm_offset_t p,uint32_t r,uint32_t v){}
static uint32_t touch_rd(vm_offset_t p,uint32_t r){return 0;}
static bool spes_gpu_tlb_sync(vm_offset_t p,uint32_t c){return true;}
void RedwoodGPUStart(void){}
'''
            suffix = r'''
int main(void){
 uint64_t root[512]={0};root[0]=0x12345003;root[1]=0x12346003;
 assert(!spes_gpu_address_space(NULL));
 root[2]=3;assert(!spes_gpu_address_space(root));root[2]=0;
 root[3]=3;assert(!spes_gpu_address_space(root));root[3]=0;
 fail_alloc=true;assert(!spes_gpu_address_space(root));assert(!root[2]&&!root[3]);fail_alloc=false;
 assert(spes_gpu_address_space(root));
 assert(root[0]==0x12345003 && root[1]==0x12346003);
 assert(root[2] && root[3]==root[2]+4096);
 for(unsigned i=4;i<512;i++)assert(root[i]==0);
 sg.ready=true;
 uint64_t addresses[128];
 for(unsigned i=0;i<128;i++){
  addresses[i]=redwood_gpu_address(16ull<<20);
  assert(addresses[i]==0x80000000ull+(uint64_t)i*(16ull<<20));
 }
 assert(!redwood_gpu_address(4096));
 assert(!spes_gpu_leaf(0x7ffff000,false));assert(!spes_gpu_leaf(0x100000000ull,false));
 assert(redwood_gpu_map(addresses[0],0x100000000ull,false));
 assert(redwood_gpu_map(0xbffff000ull,0x100004000ull,false));
 assert(redwood_gpu_map(0xc0000000ull,0x100008000ull,true));
 assert(redwood_gpu_map(0xfffff000ull,0x10000c000ull,false));
 assert(sg.l2[0] && sg.l2[511] && sg.l2[512] && sg.l2[1023]);
 assert((*spes_gpu_leaf(0xc0000000ull,false)&0x80)!=0);
 assert(!redwood_gpu_map(0x100000000ull,0x100010000ull,false));
 assert(!redwood_gpu_map(addresses[0],0x100010000ull,false));
 for(unsigned i=0;i<128;i++){
  assert(redwood_gpu_unmap(addresses[i],16ull<<20));
  redwood_gpu_address_free(addresses[i],16ull<<20);
 }
 assert(redwood_gpu_address(SPES_GPU_SIZE)==SPES_GPU_BASE);
 assert(!redwood_gpu_address(4096));
 assert(!redwood_gpu_address(UINT64_MAX));
 assert(!spes_gpu_address_space(root));
 assert(root[0]==0x12345003 && root[1]==0x12346003);
 for(unsigned i=0;i<allocated;i++)free(allocations[i]);
}
'''
            c=d/'test.c';c.write_text(prefix+code+suffix)
            subprocess.run(['clang','-Wno-format','-fsanitize=address,undefined','-g',str(c),'-o',str(d/'test')],check=True,capture_output=True)
            subprocess.run([str(d/'test')],check=True,capture_output=True)
