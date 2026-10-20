#!/bin/bash
# Build an iOS HFSX root locally on macOS. Never accesses a phone.
# sudo tools/mkiosroot-macos.sh OS.dmg SYSTEMOS.dmg APPOS.dmg OUT.img [SIZE]
set -euo pipefail
[[ $(uname -s) == Darwin ]] || { echo 'macOS required' >&2; exit 2; }
[[ $# -ge 4 && $# -le 5 ]] || { echo "usage: $0 OS.dmg SYSTEMOS.dmg APPOS.dmg OUT.img [SIZE]" >&2; exit 2; }
[[ $EUID == 0 ]] || { echo 'Run with sudo to preserve iOS numeric owners and modes.' >&2; exit 1; }
script_dir=$(cd "$(dirname "$0")" && pwd)
py=$(command -v python3)
absolute() { "$py" -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1"; }
os=$(absolute "$1")
sysos=$(absolute "$2")
appos=$(absolute "$3")
out=$(absolute "$4")
size=${5:-16g}
[[ ! -e $out && ! -L $out ]] || { echo "Refusing to overwrite $out" >&2; exit 1; }
for src in "$os" "$sysos" "$appos"; do
    [[ -f $src ]] || { echo "Missing source: $src" >&2; exit 1; }
done
work=$(mktemp -d "$(dirname "$out")/.spes-root.XXXXXX")
mounts=()
cleanup() {
    for ((i=${#mounts[@]}-1; i>=0; i--)); do
        hdiutil detach "${mounts[$i]}" >/dev/null 2>&1 || true
    done
    # Never recursively delete a directory that might still be mounted.
    echo "Build workspace retained at $work" >&2
}
trap cleanup EXIT
mount_image() {
    local source=$1 name=$2 mode=$3
    mkdir "$work/$name"
    hdiutil attach "$source" "$mode" -nobrowse -owners on \
        -mountpoint "$work/$name" -plist > "$work/$name.plist"
    mounts+=("$work/$name")
}
mount_image "$os" os -readonly
mount_image "$sysos" sysos -readonly
mount_image "$appos" appos -readonly
[[ -f $work/os/System/Library/CoreServices/SystemVersion.plist && -f $work/os/sbin/launchd ]] || {
    echo 'Base image is not an expected iOS root' >&2; exit 1;
}
[[ -d $work/sysos/System/Library/Caches/com.apple.dyld ]] || {
    echo 'SystemOS shared cache missing' >&2; exit 1;
}
# UDTO + NONE yields a raw filesystem (no partition map or UDIF trailer).
hdiutil create -size "$size" -type UDTO -layout NONE \
    -fs 'Case-sensitive Journaled HFS+' -volname iOSRoot "$work/root.cdr"
mount_image "$work/root.cdr" root -readwrite
copy_tree() {
    mkdir -p "$2"
    /usr/bin/rsync -aH --numeric-ids "$1/" "$2/"
}
copy_tree "$work/os" "$work/root"
copy_tree "$work/sysos" "$work/root/private/preboot/Cryptexes/OS"
copy_tree "$work/appos" "$work/root/private/preboot/Cryptexes/App"
"$py" "$script_dir/prepare-ios-root.py" "$work/root"
"$py" "$script_dir/sweet-root-tweaks.py" "$work/root"
sync
hdiutil detach "$work/root"
unset 'mounts[3]'
"$script_dir/finish-ios-root-macos.sh" "$work/root.cdr" "$out"
