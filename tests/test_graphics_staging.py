import importlib.util
from pathlib import Path
import struct
import unittest
spec=importlib.util.spec_from_file_location('stage',Path(__file__).resolve().parents[1]/'tools/stage-spes-eagl.py')
stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
class StagingTests(unittest.TestCase):
 def sample(self,padding=128):
  b=bytearray(1024);struct.pack_into('<8I',b,0,0xfeedfacf,0x100000c,0,2,1,152,0,0)
  struct.pack_into('<II',b,32,0x19,152);struct.pack_into('<I',b,96,1)
  struct.pack_into('<I',b,152,184+padding)
  b[184+padding:]=b'Z'*(1024-184-padding)
  return bytes(b)
 def test_preserves_sections_and_rejects_duplicate(self):
  old=self.sample();new=stage.add_dependency(old)
  self.assertEqual(old[312:],new[312:]);self.assertEqual(len(old),len(new))
  self.assertEqual(struct.unpack_from('<I',new,184)[0],0x80000018)
  with self.assertRaises(ValueError):stage.add_dependency(new)
 def test_refuses_missing_padding_and_invalid_commands(self):
  with self.assertRaises(ValueError):stage.add_dependency(self.sample(0))
  b=bytearray(self.sample());b[184]=1
  with self.assertRaises(ValueError):stage.add_dependency(b)
  struct.pack_into('<I',b,36,0)
  with self.assertRaises(ValueError):stage.add_dependency(b)
