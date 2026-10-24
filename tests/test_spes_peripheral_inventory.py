import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('inventory', TOOLS / 'spes-peripheral-inventory.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class InventoryTests(unittest.TestCase):
    def test_binary_cells_do_not_become_strings(self):
        nodes = {'': {'compatible': b'qcom,khaje\0'}, '/soc/aw87': {
            'dev_index': bytes(4), 'reset-gpio': bytes.fromhex('0000006c0000006a00000000'),
            'reg': b'ABC\0', 'compatible': b'awinic,aw87xxx_pa\0'}}
        with patch.object(mod, 'parse', return_value=(nodes, [])):
            row = mod.inventory(b'')['/soc/aw87']
        self.assertEqual(row['dev_index'], ['0x0'])
        self.assertEqual(row['reset-gpio'], ['0x6c', '0x6a', '0x0'])
        self.assertEqual(row['reg'], ['0x41424300'])
        self.assertEqual(row['compatible'], ['awinic,aw87xxx_pa'])

    def test_wrong_board_rejected(self):
        with patch.object(mod, 'parse', return_value=({'': {'compatible': b'other\0'}}, [])):
            with self.assertRaises(ValueError): mod.inventory(b'')

    def test_phandle_reference(self):
        nodes = {'': {'compatible': b'qcom,khaje\0'},
                 '/reserved-memory/adsp': {'phandle': bytes.fromhex('00000078')},
                 '/soc/lpass': {'memory-region': bytes.fromhex('00000078')}}
        with patch.object(mod, 'parse', return_value=(nodes, [])):
            row = mod.inventory(b'')['/soc/lpass']
        self.assertEqual(row['_references']['memory-region'], ['/reserved-memory/adsp'])

if __name__ == '__main__': unittest.main()
