"""Exercise the actual persistent backend with mocked hardware, not a live device."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

class BackendTests(unittest.TestCase):
    def test_mapping_ownership_and_failure_retention(self):
        source=(ROOT/'xnu/graphics/spes_gpu_backend.h').read_text().replace('__asm__ volatile("dsb sy" ::: "memory");','')
        prefix=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
typedef uintptr_t vm_offset_t;
typedef size_t vm_size_t;
typedef uintptr_t addr64_t;
#define PAGE_SIZE 16384
#define PAGE_MASK 16383
#define KMA_DATA 1
#define KMA_ZERO 2
#define KMA_PERMANENT 4
#define VM_KERN_MEMORY_IOKIT 1
#define KERN_SUCCESS 0
static int kernel_map, kernel_pmap;
static bool sync_ok=true, retire_ok=true;
static unsigned starts, allocs;
static uint32_t rptr, captured[266], captured_count;
static uint32_t *fence_word;
static bool complete=true;
static int kmem_alloc_contig(int k,vm_offset_t *p,size_t n,unsigned mask,int a,int b,int f,int tag) {
 (void)k;(void)mask;(void)a;(void)b;(void)f;(void)tag;
 *p=(uintptr_t)calloc(1,n);++allocs;return *p?0:1;
}
static uint64_t pmap_find_phys(int p,addr64_t v){(void)p;(void)v;return (0x100000000ULL+allocs*16384)>>14;}
#define ptoa_64(p) ((p)<<14)
static void to_memory(vm_offset_t p,vm_size_t n){(void)p;(void)n;}
static bool spes_gpu_tlb_sync(vm_offset_t s,uint32_t c){(void)s;(void)c;return sync_ok;}
static void touch_wr(vm_offset_t g,uint32_t r,uint32_t v){(void)g;if(r==0x201c){rptr=v;if(complete && captured_count)*fence_word=captured[captured_count-1];}}
static uint32_t touch_rd(vm_offset_t g,uint32_t r){(void)g;(void)r;return rptr;}
static void touch_wait(unsigned n){(void)n;}
static bool spes_gpu_retire(vm_offset_t g,vm_offset_t s,uint32_t c,uint32_t t,const char *tag){
 (void)g;(void)s;(void)c;(void)t;(void)tag;return retire_ok;
}
static bool spes_gpu_ring_append(volatile uint32_t *r,uint32_t *tail,uint32_t head,const uint32_t *p,uint32_t n){
 (void)head;assert(n<=266);memcpy(captured,p,n*4);captured_count=n;for(unsigned i=0;i<n;++i){r[*tail]=p[i];*tail=(*tail+1)&2047;}return true;
}
void RedwoodGPUStart(void){++starts;}
'''
        suffix=r'''
int main(void){
 uint64_t l2[512]={0};uint8_t *dma=calloc(1,65536);
 fence_word=&((uint32_t *)(dma+0xc000))[9];*fence_word=2048;
 assert(spes_gpu_backend_start(1,2,0x8000,(uintptr_t)dma,l2,1116));
 assert(starts==1 && redwood_gpu_ready());
 assert(!redwood_gpu_address(0) && !redwood_gpu_address(1) && !redwood_gpu_address(UINT64_MAX));
 uint64_t a=redwood_gpu_address(12<<20),b=redwood_gpu_address(4096);
 assert(a==0x20000000 && b==a+(12<<20));
 assert(!redwood_gpu_map(a,0,true));
 assert(!redwood_gpu_map(a,0x100000001ULL,false));
 assert(!redwood_gpu_map(a+(12<<20)+4096,0x100000000ULL,false));
 assert(redwood_gpu_map(a,0x100000000ULL,false));
 assert(redwood_gpu_map(a+(4<<20),0x100004000ULL,true));
 assert(l2[256] && l2[258]);
 assert(!redwood_gpu_map(a,0x100008000ULL,false));
 assert((*spes_gpu_leaf(a+(4<<20),false)&0x80)!=0);
 assert(redwood_gpu_mapped());
 uint64_t ib[64];uint32_t words[64];
 for(unsigned i=0;i<64;++i){ib[i]=a;words[i]=4;}
 assert(!redwood_gpu_submit(ib,words,65));
 assert(redwood_gpu_submit(ib,words,64)==2049);
 assert(captured_count==266 && captured[4]==0x70bf8003);
 assert(captured[260]==0x70268000 && captured[263]==0x011f0024);
 assert(*fence_word==2049 && redwood_gpu_done(2049));
 ib[0]=a+4096;assert(!redwood_gpu_submit(ib,words,1)); /* unmapped */
 ib[0]=a;words[0]=0x100000;assert(!redwood_gpu_submit(ib,words,1));

 redwood_gpu_address_free(a,12<<20);
 assert(spes_gpu_owner(a,4096)>=0); /* mapped buffers cannot be freed */
 assert(!redwood_gpu_unmap(a,4096));
 assert(redwood_gpu_unmap(a,12<<20));
 redwood_gpu_address_free(a,12<<20);
 assert(spes_gpu_owner(a,4096)<0);
 uint64_t c=redwood_gpu_address(12<<20);assert(c==a);
 assert(redwood_gpu_map(c,0x100008000ULL,false));
 sync_ok=false;
 assert(!redwood_gpu_unmap(c,12<<20));
 assert(!redwood_gpu_ready() && sg.faulted);
 assert(spes_gpu_owner(c,4096)>=0);
 assert(!redwood_gpu_address(4096));
 redwood_gpu_address_free(c,12<<20);assert(spes_gpu_owner(c,4096)>=0);
 uint64_t value;assert(redwood_gpu_parameter(2,&value) && value==135168);
 assert(redwood_gpu_parameter(0x12,&value) && value==7);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            c=Path(d)/'backend.c';exe=Path(d)/'backend';c.write_text(prefix+source+suffix)
            subprocess.run(['clang','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(c),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True,capture_output=True)
