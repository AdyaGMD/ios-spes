#!/usr/bin/env python3
"""Split an AIR module (LLVM IR text, llvm-dis output) into one module per entry point, as Apple's metallibs keep
them: metal2vulkan refuses a metallib function whose bitcode holds other entries (Abi(ContainerMismatch), orientprobe
on all38). Keeps the named entry's `define`, every declaration and global, attributes and metadata, drops the other
defines and their !air.kernel/vertex/fragment nodes.

  air-split.py IN.ll FUNCTION OUT.ll
"""
import re
import sys


def main():
    src, name, dst = sys.argv[1:4]
    text = open(src).read()
    lines = text.split('\n')
    out, skip = [], False
    defined = []
    for line in lines:
        m = re.match(r'define .*@([A-Za-z0-9_.$]+)\(', line)
        if m:
            defined.append(m.group(1))
            skip = m.group(1) != name
        if not skip:
            out.append(line)
        if skip and line == '}':
            skip = False
    if name not in defined:
        sys.exit(f'{name} is not defined in {src}')
    gone = [f for f in defined if f != name]
    # metadata nodes naming a removed function, and the entry lists that point at them
    dropped = set()
    kept = []
    for line in out:
        m = re.match(r'^(![0-9]+) = .*', line)
        if m and any(re.search(r'@' + re.escape(f) + r'\b', line) for f in gone):
            dropped.add(m.group(1))
            continue
        kept.append(line)
    res = []
    for line in kept:
        m = re.match(r'^(!air\.(kernel|vertex|fragment)) = !\{(.*)\}$', line)
        if m:
            refs = [r.strip() for r in m.group(3).split(',') if r.strip() and r.strip() not in dropped]
            if not refs:
                continue
            line = f'{m.group(1)} = !{{{", ".join(refs)}}}'
        res.append(line)
    open(dst, 'w').write('\n'.join(res))


if __name__ == '__main__':
    main()
