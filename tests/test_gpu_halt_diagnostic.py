"""A610 register audit and execution of the diagnostic with mocked MMIO."""
import ctypes
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

PATCH = Path(__file__).resolve().parents[1] / 'xnu/patches/0098-spes-glink-rpm-transport.patch'

class HaltDiagnosticTests(unittest.TestCase):
    def test_a610_register_addresses(self):
        # Independent DWORD constants from pinned Qualcomm a6xx_reg.h.
        expected = {'GBIF_HALT':0x3c45, 'PC_DBG_ECO_CNTL':0x9e00,
                    'RBBM_PERFCTR_CNTL':0x500, 'RBBM_PERFCTR_GPU_BUSY_MASKED':0x50b,
                    'UCHE_FILTER_CNTL':0xe18, 'RBBM_INT_0_MASK':0x38,
                    'UCHE_TRAP_BASE_LO':0xe09, 'UCHE_TRAP_BASE_HI':0xe0a,
                    'UCHE_WRITE_THRU_BASE_LO':0xe07, 'UCHE_WRITE_THRU_BASE_HI':0xe08}
        seen = set()
        for line in PATCH.read_text().splitlines():
            m = re.search(r'touch_wr\(gpu, (0x[0-9a-f]+)u,.*?/\* (?:REG_)?(?:A6XX_)?(\w+)', line)
            if m and m[2] in expected:
                self.assertEqual(int(m[1],16), expected[m[2]]*4, m[2])
                seen.add(m[2])
        self.assertEqual(seen,set(expected))
        self.assertNotRegex(PATCH.read_text(), r'touch_wr\(gpu, 0x2110u,')

    def test_control_and_halt_stop_before_setup(self):
        src='\n'.join(l[1:] for l in PATCH.read_text().splitlines() if l.startswith('+'))
        start=src.index('\t/* Controlled early-halt experiment.')
        end=src.index('\t/* Paired hardware test:',start)
        fragment=src[start:end]
        fragment=fragment.replace('__asm__ volatile ("dsb sy" ::: "memory");','((void)0);')
        prefix=r'''
#include <stdint.h>
#include <stdio.h>
static int mode, writes, waits, reads, continued, badwrite;
static unsigned long gpu;
static int PE_parse_boot_argn(const char *s, int *v, unsigned long n) { (void)s;(void)n;*v=mode;return 1; }
static void touch_wait(unsigned n) { waits+=n; }
static uint32_t touch_rd(unsigned long b, unsigned off) { (void)b;(void)off;reads++;return 0; }
static void touch_wr(unsigned long b,unsigned off,unsigned v) {
 (void)b;writes++;if(off!=0x2020 || v!=3 || waits!=10) badwrite++;
}
static void probe(void) {
'''
        suffix='\ncontinued++;}\nint run(int m) {mode=m;writes=waits=reads=continued=badwrite=0;probe();return writes+waits*10+continued*1000+badwrite*10000;}\n'
        # Suppress the printf without weakening compilation of its format strings.
        with tempfile.TemporaryDirectory() as d:
            c=Path(d)/'test.c';lib=Path(d)/'test.dylib'
            c.write_text(prefix+fragment+suffix)
            subprocess.run(['clang','-shared','-fPIC','-Wall','-Wextra','-Werror',str(c),'-o',str(lib)],check=True,capture_output=True)
            dll=ctypes.CDLL(str(lib));dll.run.argtypes=[ctypes.c_int]
            self.assertEqual(dll.run(1),200) # no writes, 20 ms delay, no fallthrough
            self.assertEqual(dll.run(2),201) # one halt after first 10 ms window
            self.assertEqual(dll.run(99),200) # invalid modes remain diagnostic
