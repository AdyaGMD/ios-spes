#!/bin/bash
# Build a guarded EAGL bridge; never modify the device or installed root here.
set -euo pipefail
[[ $# == 2 ]] || { echo 'usage: build-spes-eagl-macos.sh HACKIOS_USERLAND IOS_SDK' >&2; exit 2; }
repo=$(cd "$1" && pwd)
sdk=$(cd "$2" && pwd)
root=$(cd "$(dirname "$0")/.." && pwd)
[[ $(git -C "$repo" rev-parse HEAD) == 906425b75e02b4f99eb5d7bb1ef7c9583472d772 ]] || exit 1
src="$repo/userland/src"
out="$root/research/mesa-build/out"
python3 "$repo/userland/mkeagl.py" "$src/eagl_slots.txt" "$out/gl.xml" "$out/exported-gl.txt" "$src/eagl.c" > "$out/eagl_gen.h"
python3 - "$src/eagl.c" "$out/eagl-spes.c" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
a='__attribute__((constructor)) static void\ninstall(void)\n{'
b='extern int spes_gl_preflight(void);\n'+a+'\n\tif (!spes_gl_preflight()) return;'
assert s.count(a)==1
Path(sys.argv[2]).write_text(s.replace(a,b))
PY
patch -s "$out/eagl-spes.c" < "$root/tools/eagl-attach-gpu.patch"
/usr/bin/clang -target arm64-apple-ios16.0 -mcpu=cortex-a53 -isysroot "$sdk" \
 -O2 -dynamiclib -install_name /redwood/lib/libredwood-gl.dylib \
 -DGL_GLEXT_PROTOTYPES -I"$out" -I"$src" -I"$root/research/mesa-build/mesa-25.0.7/include" \
 -framework CoreFoundation -framework IOKit -framework IOSurface -lobjc \
 "$out/eagl-spes.c" "$src/gl_osmesa.c" "$root/xnu/graphics/spes_gl_preflight.c" \
 "$out/libOSMesa.8.dylib" -o "$out/libredwood-gl.dylib"
codesign --force --sign - "$out/libOSMesa.8.dylib" "$out/libredwood-gl.dylib"
codesign --verify "$out/libOSMesa.8.dylib"
codesign --verify "$out/libredwood-gl.dylib"
shasum -a 256 "$out/libOSMesa.8.dylib" "$out/libredwood-gl.dylib" > "$out/SHA256SUMS"
echo "Built guarded EAGL bridge; hardware rendering remains unverified."
