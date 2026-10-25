#!/bin/bash
# Build HackiOS's RedwoodAudio.driver (CoreAudio HAL plug-in for mediaserverd) from source;
# never modify the device or installed root here. It writes /dev/redwood-audio (SpesAudio 0152).
set -euo pipefail
[[ $# == 3 ]] || { echo 'usage: build-spes-audio-hal.sh HACKIOS_USERLAND IOS_SDK OUTDIR' >&2; exit 2; }
repo=$(cd "$1" && pwd)
sdk=$(cd "$2" && pwd)
[[ $(git -C "$repo" rev-parse HEAD) == 906425b75e02b4f99eb5d7bb1ef7c9583472d772 ]] || exit 1
out="$3/RedwoodAudio.driver"
mkdir -p "$out"
/usr/bin/clang -target arm64-apple-ios16.0 -mcpu=cortex-a53 -isysroot "$sdk" -O2 -bundle \
 -framework CoreFoundation -I"$repo/userland/src" "$repo/userland/src/audio_plugin.c" -o "$out/RedwoodAudio"
cp "$repo/userland/src/audio_plugin.plist" "$out/Info.plist"
codesign --force --sign - "$out/RedwoodAudio"
codesign --verify "$out/RedwoodAudio"
shasum -a 256 "$out/RedwoodAudio" "$out/Info.plist"
echo "Install as /System/Library/Audio/Plug-Ins/HAL/RedwoodAudio.driver (root write: ask first)."
