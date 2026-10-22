#!/bin/bash
# Optimized full iOS boot image builder for Xiaomi Redmi Note 11 (spes).
# Features:
#   - cpus=4: Boots all four Kryo 260 Gold (Cortex-A73) high-performance cores
#   - sweetfb_hz=60: 60 fps display composition refresh
#   - Preserves UFS read-write root (userdata) and persistent logging
set -euo pipefail
if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "usage: $0 KERNEL LIVE_FDT [OUTPUT_NAME]" >&2
    exit 2
fi
name=${3:-spes-ios-smp4}
kernel=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1")
fdt=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$2")
cd "$(dirname "$0")/.."
[[ -f "$kernel" && -f "$fdt" ]] || { echo 'Kernel or live FDT missing' >&2; exit 1; }

mkdir -p shim/out
python3 tools/mkadt.py "shim/out/$name.adt" --device spes --memory-dtb "$fdt"

python3 tools/mkpayload.py "$kernel" "shim/out/$name.adt" "shim/out/$name.payload" \
    --cmdline 'debug=0xc serial=3 cpus=4 keepsyms=1 -enable_kprintf_spam -noprogress rd=ufsroot0 ufsroot=userdata unentitled_ios_sim_launch=1 ignition_level=1 launchd_unsecure_cache=1 wdt_test=no_user_checkin wdt=-1 ufsrw=1 rootrw=1 sweetlog=1 ufslogsecs=10 sweettouch=1 sweettouchdelay=5 sweettouchdiag=3 sweetkeys=0 sweethw=0 sweetfb_stayon=1 sweetfb_noconsole=1 sweetfb_hz=60'

BOOT_HEADER_VERSION=3 shim/build.sh "out/$name.payload"
cp shim/out/shim-boot.img "shim/out/$name.img"
shasum -a 256 "shim/out/$name.img" > "shim/out/$name.img.sha256"
echo "Built shim/out/$name.img (4x Gold CPUs, 60Hz composition, UFS root); nothing sent to phone."
