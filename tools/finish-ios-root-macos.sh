#!/bin/bash
# Validate and publish an already-built raw HFSX image. No phone access.
set -euo pipefail
[[ $(uname -s) == Darwin && $# == 2 ]] || { echo "usage: $0 BUILT_IMAGE OUTPUT.img" >&2; exit 2; }
py=$(command -v python3)
source_image=$("$py" -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1")
out=$("$py" -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$2")
[[ -f $source_image && ! -L $source_image ]] || { echo 'Expected a regular built image' >&2; exit 1; }
[[ ! -e $out && ! -L $out && ! -e $out.sha256 && ! -L $out.sha256 ]] || { echo 'Output already exists; refusing overwrite' >&2; exit 1; }
"$py" - "$source_image" <<'PY'
import struct,sys
with open(sys.argv[1],'rb') as f:
    f.seek(1024); h=f.read(512)
assert len(h)==512 and h[:2]==b'HX', 'expected raw HFSX at offset 1024'
assert struct.unpack_from('>I',h,4)[0] & (1<<13), 'journal flag missing'
PY
manifest=$(mktemp)
check_disk=''
cleanup() {
    if [[ -n $check_disk ]]; then hdiutil detach "$check_disk" >/dev/null 2>&1 || true; fi
    rm -f "$manifest"
}
trap cleanup EXIT
hdiutil attach -nomount -readonly -plist "$source_image" > "$manifest"
check_disk=$("$py" -c 'import plistlib,sys; p=plistlib.load(open(sys.argv[1],"rb")); ds=[e["dev-entry"] for e in p["system-entities"] if e.get("potentially-mountable")]; assert len(ds)==1; print(ds[0])' "$manifest")
[[ $check_disk =~ ^/dev/disk[0-9]+$ ]] || { echo 'Unexpected virtual disk path' >&2; exit 1; }
# Prefix the basename; avoid escaped pattern replacement on macOS Bash 3.2.
/sbin/fsck_hfs -fn "/dev/r${check_disk#/dev/}"
hdiutil detach "$check_disk"
check_disk=''
# Hard link atomically refuses replacement and preserves the source on failure.
ln "$source_image" "$out"
shasum -a 256 "$out" > "$out.sha256"
if [[ ${SUDO_UID:-} =~ ^[0-9]+$ && ${SUDO_GID:-} =~ ^[0-9]+$ ]]; then
    chown "$SUDO_UID:$SUDO_GID" "$out" "$out.sha256"
fi
rm "$source_image"
echo "Validated and created $out; nothing sent to the phone."
