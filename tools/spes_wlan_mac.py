#!/usr/bin/env python3
"""Print a stable per-phone Wi-Fi MAC for boot-arg wlan_mac=, from a live FDT.

The address is locally administered and unicast (first byte xxxxxx10), derived by
SHA-256 from androidboot.serialno in /chosen/bootargs. The serial number itself is
never printed. Exits 1 (prints nothing) when the FDT has no serial number.
"""
import hashlib
import struct
import sys


def chosen_bootargs(blob):
    if blob[:4] != b'\xd0\x0d\xfe\xed':
        return ''
    off_struct, off_str = struct.unpack('>II', blob[8:16])
    p, path = off_struct, []
    while p + 4 <= len(blob):
        tok = struct.unpack('>I', blob[p:p + 4])[0]
        p += 4
        if tok == 1:
            end = blob.index(b'\0', p)
            path.append(blob[p:end].decode('latin1'))
            p = (end + 4) & ~3
        elif tok == 2:
            path.pop()
        elif tok == 3:
            length, nameoff = struct.unpack('>II', blob[p:p + 8])
            p += 8
            value = blob[p:p + length]
            p = (p + length + 3) & ~3
            name = blob[off_str + nameoff:blob.index(b'\0', off_str + nameoff)]
            if path and path[-1] == 'chosen' and name == b'bootargs':
                return value.rstrip(b'\0').decode('latin1')
        elif tok == 9:
            break
    return ''


def mac_for(serial):
    h = hashlib.sha256(b'spes-wlan-mac:' + serial.encode()).digest()
    mac = bytearray(h[:6])
    mac[0] = (mac[0] & 0xfc) | 0x02         # locally administered, unicast
    return ':'.join('%02x' % b for b in mac)


def main():
    blob = open(sys.argv[1], 'rb').read()
    for arg in chosen_bootargs(blob).split():
        if arg.startswith('androidboot.serialno=') and len(arg) > len('androidboot.serialno='):
            print(mac_for(arg.split('=', 1)[1]))
            return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
