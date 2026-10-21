import runpy,struct,unittest
from pathlib import Path
Fat16=runpy.run_path(str(Path(__file__).resolve().parents[1]/'tools/map-modem-fat16.py'))['Fat16']

def volume():
    b=bytearray(4132*512)
    b[510:512]=b'\x55\xaa';struct.pack_into('<H',b,11,512);b[13]=1
    struct.pack_into('<H',b,14,1);b[16]=2
    struct.pack_into('<H',b,17,16);struct.pack_into('<H',b,19,4132)
    struct.pack_into('<H',b,22,17)
    for off in (512,18*512):
        struct.pack_into('<HHHHH',b,off,0xfff8,0xffff,4,0,0xffff)
    off=35*512;b[off:off+11]=b'MODEM   MDT';b[off+11]=32
    struct.pack_into('<H',b,off+26,2);struct.pack_into('<I',b,off+28,600)
    b[36*512:37*512]=b'A'*512;b[38*512:38*512+88]=b'B'*88
    return b

class ModemFatTests(unittest.TestCase):
    def test_fragmented_file_extents(self):
        f=Fat16(volume()).files()['modem.mdt']
        self.assertEqual(f['size'],600)
        self.assertEqual(f['extents'],[{'offset':36*512,'length':512},{'offset':38*512,'length':88}])
    def test_cycle_rejected(self):
        b=volume()
        for off in (512,18*512):struct.pack_into('<H',b,off+4*2,2)
        with self.assertRaisesRegex(ValueError,'cyclic'):Fat16(b).files()
    def test_fat_disagreement_rejected(self):
        b=volume();b[512+4]=3
        with self.assertRaisesRegex(ValueError,'disagree'):Fat16(b)
    def test_truncated_volume_rejected(self):
        with self.assertRaisesRegex(ValueError,'truncated'):Fat16(volume()[:-512])

if __name__=='__main__':unittest.main()
