"""Execute the probe's actual table/packet construction on the host, no MMIO."""
import ctypes
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GPUProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patch = (ROOT / 'xnu/patches/0098-spes-glink-rpm-transport.patch').read_text()
        src = '\n'.join(x[1:] for x in patch.splitlines() if x.startswith('+') and not x.startswith('+++'))
        tables = src[src.index('uint64_t *l1 ='):src.index('to_memory(pt_va,')]
        init = src[src.index('uint32_t w = 0;', src.index('Step 20:')):]
        init = init[:init.index('__asm__')]
        render = src[src.index('/* 1. CP_SET_SECURE_MODE'):]
        render = render[:render.index('__asm__')]
        code = '#include <stdint.h>\n#include <stddef.h>\n#define LOG_CP(tag) ((void)0)\n'
        code += 'void tables(uint64_t *buf) { uintptr_t pt_va=(uintptr_t)buf; uint64_t pt_pa=0x100000000ULL, rb_pa=0x5ca08000, sqe_pa=0x5ca00000, fence_pa=0x5ca0c000;\n' + tables + '\n}\n'
        display = src[src.index('/* BEGIN DISPLAY PACKETS */'):src.index('/* END DISPLAY PACKETS */')]
        indirect = src[src.index('/* BEGIN IB PACKETS */'):src.index('/* END IB PACKETS */')]
        code += 'unsigned packets(uint32_t *rb) { uint32_t color=0xff00ff00, ib[4];\n' + init + '\nwhile(w<32) rb[w++]=0x70108000u;\n' + render + '\n' + display + '\n' + indirect + '\n(void)ib; return w; }\n'
        cls.tmp = tempfile.TemporaryDirectory()
        c = Path(cls.tmp.name)/'probe.c'; lib=Path(cls.tmp.name)/'probe.dylib'
        c.write_text(code)
        subprocess.run(['clang','-shared','-fPIC','-Wall','-Wextra','-Werror',str(c),'-o',str(lib)],check=True,capture_output=True)
        cls.lib=ctypes.CDLL(str(lib))
        cls.lib.tables.argtypes=[ctypes.POINTER(ctypes.c_uint64)]
        cls.lib.packets.argtypes=[ctypes.POINTER(ctypes.c_uint32)]
        cls.lib.packets.restype=ctypes.c_uint

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_packet_parity_and_boundaries(self):
        buf=(ctypes.c_uint32*2048)(); count=self.lib.packets(buf); pos=0
        while pos<count:
            h=buf[pos]; kind=h>>28
            self.assertIn(kind,(4,7),f'bad header at {pos}: {h:#x}')
            if kind==7:
                n=h&0x3fff; op=(h>>16)&0x7f
                self.assertEqual((h>>15)&1,1-(n.bit_count()%2),f'count parity at {pos}')
                self.assertEqual((h>>23)&1,1-(op.bit_count()%2),f'opcode parity at {pos}')
            else:
                n=h&0x7f; reg=(h>>8)&0x3ffff
                self.assertEqual((h>>7)&1,1-(n.bit_count()%2))
                self.assertEqual((h>>27)&1,1-(reg.bit_count()%2))
            self.assertLessEqual(pos+1+n,count)
            pos+=1+n
        self.assertEqual(pos,count)

    def test_page_walk_reaches_real_targets(self):
        buf=(ctypes.c_uint64*4096)(); self.lib.tables(buf)
        def walk(va):
            table=0
            for shift in (30,21,12):
                entry=buf[table+((va>>shift)&511)]
                if not entry&1:return None
                self.assertEqual(entry&3,3)
                pa=entry&0x0000fffffffff000
                if shift==12:return pa+(va&4095)
                self.assertGreaterEqual(pa,0x100000000)
                self.assertLess(pa,0x100008000)
                table=(pa-0x100000000)//8
        for va,pa in [(0x1000000,0x5ca08000),(0x1100000,0x5ca00000),
                      (0x11f0010,0x5ca0c010),(0x10001000,0x5ca0d000),(0x11f0024,0x5ca0c024),(0x5c069000,0x5c069000),
                      (0x5ca0ffff,0x5ca0ffff)]:
            self.assertEqual(walk(va),pa,hex(va))
        self.assertIsNone(walk(0x5ca10000),'must not expose DMA memory beyond allocation')

    def test_display_packets_stay_in_ring_and_mapped_framebuffer(self):
        buf=(ctypes.c_uint32*2048)(); count=self.lib.packets(buf)
        self.assertEqual(count, 32+2+16*67+10)
        pos=34
        for row in range(16):
            self.assertEqual((buf[pos]>>16)&0x7f,0x3d)
            self.assertEqual(buf[pos]&0x3fff,66)
            self.assertEqual(buf[pos+1],0x5c000000+(360+row)*4320+64*4)
            self.assertEqual(buf[pos+2],0)
            self.assertLess(buf[pos+1]+64*4,0x5c200000)
            self.assertTrue(all(buf[pos+3+i]==0xff00ff00 for i in range(64)))
            pos+=67
        self.assertLessEqual(count,2048)

    def test_retirement_rejects_faults_and_timeouts(self):
        patch=(ROOT/'xnu/patches/0098-spes-glink-rpm-transport.patch').read_text()
        src='\n'.join(l[1:] for l in patch.splitlines() if l.startswith('+'))
        helper=src[src.index('static bool\nspes_gpu_retire'):src.index('static void\nspes_glink_rpm_probe')]
        prefix=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
typedef uintptr_t vm_offset_t;
static int scenario, waits;
static void touch_wait(unsigned ms) { waits+=ms; }
static uint32_t touch_rd(vm_offset_t base, uint32_t off) {
 if(base==1) {
  if(off==0x2018) return scenario==1 ? 33 : 34;
  if(off==0x208c && scenario==2) return 0x80;
  if(off==0x2084 && scenario==3) return 1;
  if(off==0x804 && scenario==4) return 0x80;
 } else {
  if(off==0x48 && scenario==5) return 1;
  if(off==0x8058) return scenario==6 ? 0x402 : 0x400;
 }
 return 0;
}
'''
        suffix='\nint run(int mode) {scenario=mode;waits=0;return spes_gpu_retire(1,2,0x8000,34,"mock") ? 1 : 0;}\n'
        with tempfile.TemporaryDirectory() as d:
            c=Path(d)/'retire.c';lib=Path(d)/'retire.dylib';c.write_text(prefix+helper+suffix)
            subprocess.run(['clang','-shared','-fPIC','-Wall','-Wextra','-Werror',str(c),'-o',str(lib)],check=True,capture_output=True)
            dll=ctypes.CDLL(str(lib));dll.run.argtypes=[ctypes.c_int]
            self.assertEqual(dll.run(0),1) # FSR format bit alone is not a fault
            for fault in range(1,7):self.assertEqual(dll.run(fault),0,fault)

    def test_indirect_submission_and_fence_layout(self):
        buf=(ctypes.c_uint32*2048)(); count=self.lib.packets(buf)
        start=32+2+16*67
        self.assertEqual(list(buf[start:count]), [0x70bf8003,0x10001000,0,4,
            0x70268000,0x70460004,4,0x11f0024,0,1])
