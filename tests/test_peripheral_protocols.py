"""Host-execute the same SMEM/WLFW parsers and assignment function as the kernel."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class ProtocolTests(unittest.TestCase):
    def test_native_parsers_and_assignment(self):
        generator = ROOT / 'tools/build-spes-peripheral-patch.py'
        # Load generator to obtain the exact patched translation unit.
        scope = {'__file__': str(generator)}
        exec(compile(generator.read_text(), str(generator), 'exec'), scope)
        source = scope['src']
        start = source.index('static bool\nw_on_msa_info')
        end = source.index('static unsigned w_arrivals', start)
        function = source[start:end]
        harness = r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
#include "spes_smem_read.h"
#include "spes_wlfw_memory.h"
#define LOG(...) ((void)0)
#define WLFW_MSA_BASE 0x51900000u
#define WLFW_MSA_SIZE 0x100000u
#define VMID_MSS_MSA 15
#define VMID_WLAN 24
#define VMID_WLAN_CE 25
static void IOSleep(unsigned) {}
static unsigned assignments, fail_at;
static uint64_t scm_assign(uint64_t, uint64_t, const uint32_t *, unsigned) {
    return ++assignments == fail_at ? 1 : 0;
}
static const uint8_t *qm_find(const uint8_t *p, uint32_t n, uint8_t, uint16_t *l) {
    *l = (uint16_t)n; return p;
}
'''
        harness += function
        harness += r'''
static void put16(uint8_t *p, uint16_t n) { p[0]=n; p[1]=n>>8; }
static void put32(uint8_t *p, uint32_t n) { for (unsigned i=0;i<4;i++)p[i]=n>>(8*i); }
static void region(uint8_t *p, uint32_t a, uint32_t n) { memset(p,0,13);put32(p,a);put32(p+8,n); }
int main() {
    uint8_t v[27]={2}; region(v+1,WLFW_MSA_BASE,0x1000);region(v+14,WLFW_MSA_BASE+0x1000,0x1000);
    assert(spes_msa_regions_valid(v,27,WLFW_MSA_BASE,WLFW_MSA_SIZE));
    assignments=0;fail_at=0;assert(w_on_msa_info(v,27));assert(assignments==2);
    assignments=0;fail_at=1;assert(!w_on_msa_info(v,27));assert(assignments==1);
    assignments=0;fail_at=2;assert(!w_on_msa_info(v,27));assert(assignments==2);
    for(unsigned n=0;n<27;n++)assert(!spes_msa_regions_valid(v,n,WLFW_MSA_BASE,WLFW_MSA_SIZE));
    region(v+14,WLFW_MSA_BASE,0x1000); assignments=0;
    assert(!w_on_msa_info(v,27));assert(assignments==0); // overlap rejected before first assign
    memset(v+14,255,8);assert(!spes_msa_regions_valid(v,27,WLFW_MSA_BASE,WLFW_MSA_SIZE));
    region(v+14,WLFW_MSA_BASE+0x1000,0);assert(!w_on_msa_info(v,27));
    region(v+14,WLFW_MSA_BASE+0x1000,0x1000);v[26]=2;assert(!w_on_msa_info(v,27));
    v[26]=1;assert(spes_msa_regions_valid(v,27,WLFW_MSA_BASE,WLFW_MSA_SIZE));
    uint8_t mem[8192]={};uint8_t *toc=mem+4096,*p=mem+256;
    memcpy(toc,"$TOC",4);put32(toc+4,1);put32(toc+8,1);
    put32(toc+32,256);put32(toc+36,256);put16(toc+46,2);
    memcpy(p,"$PRT",4);put16(p+6,2);put32(p+8,256);put32(p+12,56);put32(p+16,256);
    put16(p+32,0xa5a5);put16(p+34,443);put32(p+36,8);put16(p+40,4);put32(p+48,0x1234);
    uint32_t length,bytes;
    assert(spes_smem_partition_read(mem,sizeof(mem),2,&length)==p && length==256);
    assert(spes_smem_item_read(p,length,443,&bytes)==p+48 && bytes==4);
    assert(!spes_smem_item_read(p,length,429,&bytes));
    put16(p+40,9);assert(!spes_smem_item_read(p,length,443,&bytes));put16(p+40,4);
    put32(p+36,0xffffffff);assert(!spes_smem_item_read(p,length,443,&bytes));
    put32(p+12,257);assert(!spes_smem_partition_read(mem,sizeof(mem),2,&length));
    put32(p+12,56);put32(toc+36,0xffffffff);assert(!spes_smem_partition_read(mem,sizeof(mem),2,&length));
    put32(toc+36,256);put32(toc+8,0xffffffff);assert(!spes_smem_partition_read(mem,sizeof(mem),2,&length));
    assert(!spes_smem_partition_read(mem,100,2,&length));
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)
            (path / 'test.cpp').write_text(harness)
            subprocess.run(['clang++', '-std=c++14', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I', str(ROOT / 'xnu/peripherals'),
                            str(path / 'test.cpp'), '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True)

if __name__ == '__main__': unittest.main()
