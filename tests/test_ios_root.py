import os
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch
import importlib.util

spec = importlib.util.spec_from_file_location('prepare_root', Path(__file__).resolve().parents[1] / 'tools/prepare-ios-root.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class RootPreparationTests(unittest.TestCase):
    def seed(self, root, version='16.7.16'):
        p = root / 'System/Library/CoreServices/SystemVersion.plist'
        p.parent.mkdir(parents=True)
        p.write_bytes(plistlib.dumps({'ProductVersion': version, 'ProductBuildVersion': '20H392'}))
        src = root / 'private/preboot/Cryptexes/OS/usr/lib'
        src.mkdir(parents=True)
        (src / 'test.dylib').write_bytes(b'cache sample')
        (src / 'alias.dylib').symlink_to('test.dylib')
        (root / 'private/preboot/Cryptexes/App').mkdir()
        return src

    def test_hardlinks_and_symlinks_and_keybag(self):
        with tempfile.TemporaryDirectory() as td, patch.object(os, 'chown'), patch.object(os, 'lchown'):
            root = Path(td)
            src = self.seed(root)
            mod.prepare(root)
            dst = root / 'usr/lib/test.dylib'
            self.assertEqual(src.joinpath('test.dylib').stat().st_ino, dst.stat().st_ino)
            self.assertEqual(os.readlink(root / 'usr/lib/alias.dylib'), 'test.dylib')
            keybag = root / 'private/var/keybags/systembag.kb'
            self.assertEqual(plistlib.loads(keybag.read_bytes()), {'KeyBagKeys': b'SWEET'})
            self.assertEqual(keybag.stat().st_mode & 0o777, 0o600)

    def test_destination_cannot_escape_through_symlink(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside:
            root = Path(td)
            self.seed(root)
            (root / 'usr').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'symlink traversal'):
                mod.prepare(root)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_wrong_build_stops_before_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.seed(root, '17.0')
            with self.assertRaisesRegex(ValueError, 'require iOS'):
                mod.prepare(root)
            self.assertFalse((root / 'usr').exists())
