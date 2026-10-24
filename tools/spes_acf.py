"""Validate AW87xxx ACF metadata offline; never emit or apply register writes.

Layout: MiCode/vendor_qcom_opensource_audio-kernel, spes-r-oss,
054e4f359514ddd1509095b15ad9f8e1607086a4, aw_acf_bin.{h,c}.
"""
import argparse
import json
import struct
from pathlib import Path


def crc8(data):
    crc = 0
    for byte in data:
        for _ in range(8):
            crc = ((crc >> 1) ^ 0x8c) if (crc ^ byte) & 1 else crc >> 1
            byte >>= 1
    return crc


def inspect(blob):
    if len(blob) < 80:
        raise ValueError('truncated ACF header')
    magic = struct.unpack_from('<I', blob)[0]
    size, count, offset, version = struct.unpack_from('<4I', blob, 52)
    if magic != 0x0a15f908 or version not in (1, 0x01000000):
        raise ValueError('unsupported ACF magic/version')
    entry_size = 64 if version == 1 else 96
    if not count or size != count * entry_size or offset != 80 or offset + size > len(blob):
        raise ValueError('invalid ACF table bounds')
    entries, ranges = [], []
    for i in range(count):
        pos = offset + i * entry_size
        kind, name, index, bus, addr, profile, dtype, length, start, checksum = struct.unpack_from('<I16s4H4I', blob, pos)
        end = start + length
        if not length or start < offset + size or end > len(blob):
            raise ValueError('invalid ACF payload bounds')
        if crc8(blob[start:end]) != checksum:
            raise ValueError('ACF payload CRC mismatch')
        ranges.append((start, end))
        entries.append(dict(type=kind, device=name.split(b'\0', 1)[0].decode('ascii'),
                            index=index, bus=bus, address=addr, profile=profile,
                            data_type=dtype, size=length, offset=start, crc=checksum))
    cursor = offset + size
    for start, end in sorted(ranges):
        if start != cursor:
            raise ValueError('overlapping or unaccounted ACF bytes')
        cursor = end
    if cursor != len(blob):
        raise ValueError('trailing ACF bytes')
    return dict(version=version, entries=entries)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('acf', type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.acf.read_bytes()), indent=2))
