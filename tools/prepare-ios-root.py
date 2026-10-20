#!/usr/bin/env python3
"""Link cryptex contents and seed local state in a mounted iOS image.

Used by mkiosroot-macos.sh. Requires root; never opens a phone device.
"""
import os
from pathlib import Path
import plistlib
import stat
import sys


def safe_parent(root, relative):
    parent = root
    for part in relative.parts[:-1]:
        parent = parent / part
        if parent.is_symlink():
            raise ValueError(f'refusing destination symlink traversal: {parent}')
        parent.mkdir(exist_ok=True)
    return root / relative


def prepare(root):
    root = root.resolve(strict=True)
    version = root / 'System/Library/CoreServices/SystemVersion.plist'
    with version.open('rb') as f:
        info = plistlib.load(f)
    if (info.get('ProductVersion'), info.get('ProductBuildVersion')) != ('16.7.16', '20H392'):
        raise ValueError('root tweaks require iOS 16.7.16 build 20H392')
    for cryptex in ('OS', 'App'):
        source = root / 'private/preboot/Cryptexes' / cryptex
        for directory, dirs, files in os.walk(source, followlinks=False):
            for name in files + [d for d in dirs if (Path(directory) / d).is_symlink()]:
                src = Path(directory) / name
                rel = src.relative_to(source)
                dst = root / rel
                if os.path.lexists(dst):
                    continue
                dst = safe_parent(root, rel)
                if src.is_symlink():
                    os.symlink(os.readlink(src), dst)
                    st = src.lstat()
                    os.lchown(dst, st.st_uid, st.st_gid)
                elif stat.S_ISREG(src.stat().st_mode):
                    os.link(src, dst)
                else:
                    raise ValueError(f'unsupported cryptex entry: {src}')
    for rel, mode in [('private/var/db/diagnostics', 0o751),
                      ('private/var/db/uuidtext', 0o755),
                      ('private/var/db/diagnostics/timesync', 0o755)]:
        path = safe_parent(root, Path(rel) / '.migrated').parent
        os.chown(path, 272, 272)
        path.chmod(mode)
        marker = path / '.migrated'
        if marker.is_symlink():
            raise ValueError(f'refusing symlink: {marker}')
        marker.touch()
        os.chown(marker, 272, 272)
        marker.chmod(0o644)
    keybag = safe_parent(root, Path('private/var/keybags/systembag.kb'))
    keybag.parent.chmod(0o700)
    os.chown(keybag.parent, 0, 0)
    if os.path.lexists(keybag):
        raise ValueError('refusing to overwrite existing system keybag')
    with keybag.open('xb') as f:
        plistlib.dump({'KeyBagKeys': b'SWEET'}, f)
    os.chown(keybag, 0, 0)
    keybag.chmod(0o600)


if __name__ == '__main__':
    if len(sys.argv) != 2 or os.geteuid() != 0:
        sys.exit('usage (as root): prepare-ios-root.py MOUNTED_IMAGE_ROOT')
    prepare(Path(sys.argv[1]))
