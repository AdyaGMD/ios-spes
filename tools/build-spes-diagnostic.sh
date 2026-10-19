#!/bin/bash
# Build an entirely RAM-backed XNU/PID-1 diagnostic image. Never flashes a phone.
set -euo pipefail
if [ "$#" -ne 2 ]; then
    echo "usage: $0 KERNEL LIVE_FDT" >&2
    exit 2
fi
kernel=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1")
live_fdt=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$2")
cd "$(dirname "$0")/.."
[ -f "$kernel" ] && [ -f "$live_fdt" ] || { echo 'Kernel or live FDT missing' >&2; exit 1; }
mkdir -p shim/out
python3 tools/mkadt.py shim/out/spes.adt --device spes --memory-dtb "$live_fdt"
clang -target arm64-apple-ios16.0 -mcpu=cortex-a53 -c tools/sweet-init.S -o shim/out/spes-init.o
python3 tools/mkinit.py shim/out/spes-init.o shim/out/spes-init
python3 tools/mkpayload.py "$kernel" shim/out/spes.adt shim/out/spes-diagnostic.payload \
    --ramdisk shim/out/spes-init \
    --cmdline 'debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress rd=md0 ufsrw=0 rootrw=0 sweetlog=0 sweettouch=0 sweetkeys=0 sweethw=0 sweetfb_stayon=1'
BOOT_HEADER_VERSION=3 shim/build.sh out/spes-diagnostic.payload
cp shim/out/shim-boot.img shim/out/spes-diagnostic.img
shasum -a 256 shim/out/spes-diagnostic.img > shim/out/spes-diagnostic.img.sha256
printf '%s\n' 'Built shim/out/spes-diagnostic.img; nothing sent to the phone.'
