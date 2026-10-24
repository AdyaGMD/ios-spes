"""Synthetic fixtures only: do not commit phone firmware."""
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from spes_acf import inspect, crc8


def fixture(version=1):
    entry_size = 64 if version == 1 else 96
    data = b'\x01\x02'
    blob = bytearray(80 + entry_size) + data
    struct.pack_into('<I', blob, 0, 0x0a15f908)
    struct.pack_into('<4I', blob, 52, entry_size, 1, 80, version)
    struct.pack_into('<I16s4H4I', blob, 80, 2, b'fixture', 0, 65535, 65535, 0,
                     4, len(data), 80 + entry_size, crc8(data))
    return blob


class ACFTests(unittest.TestCase):
    def test_versions(self):
        for version in (1, 0x01000000):
            self.assertEqual(inspect(fixture(version))['entries'][0]['device'], 'fixture')

    def test_crc_vector(self):
        self.assertEqual(crc8(b'123456789'), 0xa1)

    def test_truncations(self):
        blob = fixture()
        for n in range(len(blob)):
            with self.assertRaises(ValueError):
                inspect(blob[:n])

    def test_corrupt_data(self):
        blob = fixture()
        blob[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'CRC'):
            inspect(blob)

    def test_reject_table_as_payload(self):
        blob = fixture()
        struct.pack_into('<I', blob, 80 + 36, 80)
        with self.assertRaisesRegex(ValueError, 'bounds'):
            inspect(blob)

    def test_trailing_bytes(self):
        with self.assertRaisesRegex(ValueError, 'trailing'):
            inspect(fixture() + b'\0')

    def test_unknown_version(self):
        blob = fixture()
        struct.pack_into('<I', blob, 64, 2)
        with self.assertRaisesRegex(ValueError, 'version'):
            inspect(blob)

if __name__ == '__main__':
    unittest.main()
