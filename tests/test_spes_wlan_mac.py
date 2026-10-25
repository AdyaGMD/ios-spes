"""The per-phone Wi-Fi MAC: format, stability, and no serial number in the output."""
import importlib.util
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('spes_wlan_mac', ROOT / 'tools/spes_wlan_mac.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fdt_with_bootargs(bootargs):
    strings = b'bootargs\0'
    value = bootargs.encode() + b'\0'
    struct_block = struct.pack('>I', 1) + b'\0\0\0\0'                  # root node ""
    struct_block += struct.pack('>I', 1) + b'chosen\0\0'               # chosen (padded)
    struct_block += struct.pack('>III', 3, len(value), 0) + value + b'\0' * ((4 - len(value) % 4) % 4)
    struct_block += struct.pack('>II', 2, 2) + struct.pack('>I', 9)
    off_struct = 40
    off_str = off_struct + len(struct_block)
    header = struct.pack('>IIIIIIIIII', 0xd00dfeed, off_str + len(strings), off_struct, off_str, 40, 17, 16, 0,
                         len(strings), len(struct_block))
    return header + struct_block + strings


class WlanMacTests(unittest.TestCase):
    def test_locally_administered_unicast_and_stable(self):
        a = mod.mac_for('ABCDEF123456')
        self.assertEqual(a, mod.mac_for('ABCDEF123456'))
        self.assertNotEqual(a, mod.mac_for('ABCDEF123457'))
        self.assertRegex(a, r'^[0-9a-f]{2}(:[0-9a-f]{2}){5}$')
        self.assertEqual(int(a[:2], 16) & 3, 2)

    def test_reads_serial_from_chosen_bootargs(self):
        blob = fdt_with_bootargs('console=ttyMSM0 androidboot.serialno=ABCDEF123456 panel_info=1')
        self.assertEqual(mod.chosen_bootargs(blob).split()[1], 'androidboot.serialno=ABCDEF123456')

    def test_no_fdt_no_serial(self):
        self.assertEqual(mod.chosen_bootargs(b'not an fdt'), '')
        self.assertEqual(mod.chosen_bootargs(fdt_with_bootargs('console=ttyMSM0')).split(), ['console=ttyMSM0'])


if __name__ == '__main__':
    unittest.main()
