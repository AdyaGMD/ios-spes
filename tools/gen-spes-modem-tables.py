#!/usr/bin/env python3
"""Generate C tables for SpesModem from research/spes-modem-map.json.
"""
import json
import sys

def main():
    map_file = "research/spes-modem-map.json"
    with open(map_file, "r") as f:
        data = json.load(f)

    files = data["files"]
    print(f"/* Auto-generated from {map_file}: {len(files)} files */")

    # 1. fw_files: modem.bNN and modem.mdt
    modem_files = []
    for path, info in sorted(files.items()):
        name = path.replace("image/", "")
        if name.startswith("modem.b") or name == "modem.mdt":
            ext = info["extents"][0]
            modem_files.append((name, ext["offset"], info["size"], info["crc32"]))

    print("\n/* Stock spes modem_a split ELF firmware segments */")
    print("static const struct { const char *name; uint32_t off, size, crc; } fw_files[] = {")
    for name, off, size, crc in modem_files:
        print(f'\t{{ "{name}", 0x{off:x}, 0x{size:x}, 0x{crc} }},')
    print("};")

    # 2. fw_ext and fw_all for TFTP
    # Extents table
    print("\n/* TFTP firmware file extents */")
    ext_list = []
    file_list = []
    
    # Sort files deterministically
    for path, info in sorted(files.items()):
        ext_idx = len(ext_list)
        ext_count = len(info["extents"])
        for ext in info["extents"]:
            ext_list.append((ext["offset"], ext["length"]))
        file_list.append((path, info["size"], ext_idx, ext_count))

    print(f"static const struct {{ uint32_t off, len; }} fw_ext[{len(ext_list)}] = {{")
    for off, length in ext_list:
        print(f"\t{{ 0x{off:x}, 0x{length:x} }},")
    print("};")

    print(f"\nstatic const struct {{ const char *path; uint32_t len; uint16_t ext, next; }} fw_all[{len(file_list)}] = {{")
    for path, size, ext_idx, ext_count in file_list:
        print(f'\t{{ "{path}", 0x{size:x}, {ext_idx}, {ext_count} }},')
    print("};")

if __name__ == "__main__":
    main()
