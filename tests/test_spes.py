import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import adt
import mkadt
from spes_memory import select_memory


def fdt(banks, reservations=(), dynamic=False):
    names = bytearray(); body = bytearray()
    def token(n): body.extend(struct.pack('>I', n))
    def begin(name):
        token(1); body.extend(name.encode() + b'\0'); body.extend(b'\0' * (-len(body) % 4))
    def prop(name, value):
        offset = len(names); names.extend(name.encode() + b'\0')
        body.extend(struct.pack('>III', 3, len(value), offset) + value)
        body.extend(b'\0' * (-len(body) % 4))
    begin(''); prop('compatible', b'qcom,khaje\0')
    prop('#address-cells', struct.pack('>I', 2)); prop('#size-cells', struct.pack('>I', 2))
    begin('memory'); prop('device_type', b'memory\0'); prop('reg', b''.join(struct.pack('>QQ', *b) for b in banks)); token(2)
    if dynamic:
        begin('reserved-memory'); begin('pool'); prop('size', struct.pack('>Q', 4096)); token(2); token(2)
    token(2); token(9)
    reserve = b''.join(struct.pack('>QQ', *r) for r in reservations) + bytes(16)
    off = 40 + len(reserve); strings = off + len(body)
    return struct.pack('>10I', 0xd00dfeed, strings + len(names), off, strings, 40, 17, 16, 0, len(names), len(body)) + reserve + body + names


class SpesTests(unittest.TestCase):
    def test_stock_placeholder_rejected(self):
        with self.assertRaisesRegex(ValueError, 'live FDT'):
            select_memory(fdt([(0, 0)]))

    def test_actual_bank_used_not_topaz_size(self):
        self.assertEqual(select_memory(fdt([(0x140000000, 0x80000000)])), (0x140000000, 0x80000000))

    def test_reservation_splits_bank(self):
        self.assertEqual(select_memory(fdt([(0x100000000, 0x100000000)], [(0x140000000, 0x10000000)])), (0x150000000, 0xb0000000))

    def test_unknown_dynamic_pool_rejected(self):
        with self.assertRaisesRegex(ValueError, 'dynamic reservation'):
            select_memory(fdt([(0x100000000, 0x80000000)], dynamic=True))

    def test_truncation_rejected(self):
        with self.assertRaises(ValueError):
            select_memory(fdt([(0x100000000, 0x80000000)])[:-1])

    def test_spes_requires_verified_memory(self):
        with self.assertRaises(ValueError): mkadt.build(device='spes')
        with self.assertRaises(ValueError): mkadt.build(device='spes', highmem=True, memory=(0x140000000, 0x80000000))

    def test_spes_adt_roundtrip(self):
        root, _ = adt.parse(adt.serialize(mkadt.build(device='spes', memory=(0x140000000, 0x80000000))))
        children = {c.name:c for c in root.children}
        self.assertIn('spes-platform', children)
        self.assertIn(b'xiaomi,spes\0', root.prop('compatible'))
        self.assertEqual(struct.unpack('<Q', children['chosen'].prop('dram-size'))[0], 0x80000000)
        self.assertEqual([struct.unpack('<I', c.prop('reg'))[0] for c in children['cpus'].children], [0x100,0x101,0x102,0x103])

    def test_topaz_still_available(self):
        root=mkadt.build(highmem=True)
        self.assertNotIn('spes-platform', [c.name for c in root.children])
        self.assertIn(b'xiaomi,topaz\0', root.prop('compatible'))

if __name__ == '__main__': unittest.main()
