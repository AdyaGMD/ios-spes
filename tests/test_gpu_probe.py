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
        code += 'unsigned packets(uint32_t *rb) {\n' + init + '\n' + render + '\nreturn w; }\n'
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
        buf=(ctypes.c_uint32*512)(); count=self.lib.packets(buf); pos=0
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
                      (0x11f0010,0x5ca0c010),(0x5c069000,0x5c069000),
                      (0x5ca0ffff,0x5ca0ffff)]:
            self.assertEqual(walk(va),pa,hex(va))
        self.assertIsNone(walk(0x5ca10000),'must not expose DMA memory beyond allocation')
