#!/bin/bash
# Build the pinned HackiOS Mesa fork for iOS, without modifying the phone/rootfs.
set -euo pipefail
[[ $# == 2 ]] || { echo 'usage: build-spes-mesa-macos.sh HACKIOS_USERLAND IOS_SDK' >&2; exit 2; }
repo=$(cd "$1" && pwd)
sdk=$(cd "$2" && pwd)
root=$(cd "$(dirname "$0")/.." && pwd)
b="$root/research/mesa-build"
[[ $(git -C "$repo" rev-parse HEAD) == 906425b75e02b4f99eb5d7bb1ef7c9583472d772 ]] || { echo 'Unexpected HackiOS userland revision' >&2; exit 1; }
mkdir -p "$b/out"
cd "$b"
printf '%s\n' '592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6  mesa-25.0.7.tar.xz' | shasum -a 256 -c -
if [[ ! -f mesa-25.0.7/.spes-patched ]]; then
 [[ ! -d mesa-25.0.7 ]] || { echo 'Partial source exists; inspect before rebuilding' >&2; exit 1; }
 tar -xJf mesa-25.0.7.tar.xz
 for p in "$repo"/tools/mesa/*.patch; do patch -s -d mesa-25.0.7 -p1 < "$p"; done
 cp -R "$repo/tools/mesa/redwood-drm" mesa-25.0.7/src/redwood-drm
 cp -R "$repo/tools/mesa/air" mesa-25.0.7/src/compiler/air
 touch mesa-25.0.7/.spes-patched
fi
# The spes kernel programs the bank layout read from its live KGSL device tree.
python3 - "$b/mesa-25.0.7/src/freedreno/common/freedreno_dev_info.c" <<'PYBANK'
import sys
from pathlib import Path
p=Path(sys.argv[1]);s=p.read_text()
a="      modified = *orig;"
b=a+"\n      /* SPES: match the kernel's SM6225 bank layout. */\n      if (id->chip_id == 0x06010001) modified.highest_bank_bit = 14;"
if b not in s:
    assert s.count(a)==1
    p.write_text(s.replace(a,b))
PYBANK
export PATH="$b/venv/bin:/opt/homebrew/opt/bison/bin:/opt/homebrew/opt/flex/bin:/opt/homebrew/opt/llvm/bin:$PATH"
cat > cross-macos.ini <<INI
[binaries]
c = ['/usr/bin/clang', '-target', 'arm64-apple-ios16.0', '-mcpu=cortex-a53', '-isysroot', '$sdk']
cpp = ['/usr/bin/clang++', '-target', 'arm64-apple-ios16.0', '-mcpu=cortex-a53', '-isysroot', '$sdk', '-fuse-cxa-atexit']
objc = ['/usr/bin/clang', '-target', 'arm64-apple-ios16.0', '-mcpu=cortex-a53', '-isysroot', '$sdk']
ar = '/usr/bin/ar'
strip = '/usr/bin/strip'
pkg-config = 'false'
[host_machine]
system = 'darwin'
subsystem = 'ios'
cpu_family = 'aarch64'
cpu = 'arm64'
endian = 'little'
[properties]
needs_exe_wrapper = true
INI
[[ -f build-spes/build.ninja ]] || meson setup build-spes mesa-25.0.7 --cross-file cross-macos.ini --wrap-mode=nofallback \
 --prefix=/redwood --libdir=lib --buildtype=release -Db_ndebug=true \
 -Dplatforms= -Dgallium-drivers=softpipe,freedreno -Dfreedreno-kmds=msm -Dvulkan-drivers= \
 -Dglx=disabled -Degl=disabled -Dgbm=disabled -Dosmesa=true -Dllvm=disabled \
 -Dshared-glapi=enabled -Dgles1=disabled -Dgles2=enabled -Dopengl=true \
 -Dzstd=disabled -Dxmlconfig=disabled -Dexpat=disabled -Dshader-cache=disabled -Dvalgrind=disabled \
 -Dlibunwind=disabled -Dglvnd=disabled -Dvideo-codecs= -Dtools= -Dgallium-vdpau=disabled \
 -Dgallium-va=disabled -Dgallium-xa=disabled -Dlmsensors=disabled -Dbuild-tests=false
ninja -C build-spes -j4
cp build-spes/src/gallium/targets/osmesa/libOSMesa.8.dylib out/
install_name_tool -id /redwood/lib/libOSMesa.8.dylib out/libOSMesa.8.dylib
nm -gU out/libOSMesa.8.dylib | awk '$3 ~ /^_gl/ { print substr($3, 2) }' > out/exported-gl.txt
cp mesa-25.0.7/src/mapi/glapi/registry/gl.xml out/
shasum -a 256 out/libOSMesa.8.dylib > out/SHA256SUMS
echo "Built $b/out/libOSMesa.8.dylib; nothing installed on the phone."
