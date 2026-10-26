#!/bin/bash
# Build Turnip (Mesa freedreno Vulkan) for iOS 16 arm64 for spes's A610, the Vulkan driver of a
# later Metal path (iOSPlus10's NegroniMetal -> metal2vulkan -> Turnip). Never touches the phone.
#   tree:  Mesa 25.0.7 + HackiOS b4c5513 tools/mesa {freedreno-darwin, ir3-*} + iOSPlus10's libdrm
#          stand-in (userland/negronigl/drm, log.c) + their userland/turnip/mesa-patches + the spes
#          bank layout (chip 0x06010001: highest_bank_bit 14, as our GL build).
#   out:   research/turnip-build/libvulkan_freedreno.dylib (ad-hoc signed) + nm/otool checks.
set -euo pipefail
[[ $# == 3 ]] || { echo 'usage: build-spes-turnip-macos.sh HACKIOS_USERLAND IOSPLUS10 IOS_SDK' >&2; exit 2; }
hack=$(cd "$1" && pwd); ip10=$(cd "$2" && pwd); sdk=$(cd "$3" && pwd)
root=$(cd "$(dirname "$0")/.." && pwd)
b="$root/research/turnip-build"; tar="$root/research/mesa-build/mesa-25.0.7.tar.xz"
hc=b4c5513e2df93689895d21fd3b93b723a7bcfdd3; ic=c0a451f
git -C "$hack" cat-file -e "$hc^{commit}"
[[ $(git -C "$ip10" rev-parse --short=7 HEAD) == "$ic" ]] || { echo "iOSPlus10 not at $ic" >&2; exit 1; }
printf '%s\n' "592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6  $tar" | shasum -a 256 -c - >/dev/null
mkdir -p "$b"; src="$b/mesa-25.0.7"
if [[ ! -f "$src/.spes-turnip" ]]; then
  [[ ! -d "$src" ]] || { echo "partial tree $src: inspect, then remove it" >&2; exit 1; }
  tar -xJf "$tar" -C "$b"
  for p in freedreno-darwin ir3-round-default ir3-shift-split ir3-ssbo-subdword; do
    git -C "$hack" show "$hc:tools/mesa/$p.patch" | patch -s --no-backup-if-mismatch -d "$src" -p1
  done
  mkdir -p "$src/src/redwood-drm"
  for f in xf86drm.h negroni_drm.c negroni_drm.h ngl_abi.h; do cp "$ip10/userland/negronigl/drm/$f" "$src/src/redwood-drm/"; done
  cp "$ip10/userland/negronigl/log.c" "$src/src/redwood-drm/log.c"
  echo 'typedef int spes_turnip_redwood_drm_placeholder;' > "$src/src/redwood-drm/redwood_drm.c"
  for p in "$ip10"/userland/turnip/mesa-patches/*.patch; do patch -s --no-backup-if-mismatch -d "$src" -p1 < "$p"; done
  python3 - "$src/src/freedreno/common/freedreno_dev_info.c" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1]);s=p.read_text()
a="      modified = *orig;"
b=a+"\n      /* SPES: match the kernel's SM6225 bank layout. */\n      if (id->chip_id == 0x06010001) modified.highest_bank_bit = 14;"
assert s.count(a)==1
p.write_text(s.replace(a,b))
PY
  find "$src" -name '*.orig' -delete
  touch "$src/.spes-turnip"
fi
export PATH="$root/research/mesa-build/venv/bin:/opt/homebrew/opt/bison/bin:/opt/homebrew/opt/flex/bin:$PATH"
cat > "$b/cross.ini" <<INI
[binaries]
c = ['/usr/bin/clang', '-target', 'arm64-apple-ios16.0', '-mcpu=cortex-a53', '-isysroot', '$sdk']
cpp = ['/usr/bin/clang++', '-target', 'arm64-apple-ios16.0', '-mcpu=cortex-a53', '-isysroot', '$sdk', '-fuse-cxa-atexit']
objc = ['/usr/bin/clang', '-target', 'arm64-apple-ios16.0', '-mcpu=cortex-a53', '-isysroot', '$sdk']
ar = '/usr/bin/ar'
strip = '/usr/bin/strip'
nm = '/usr/bin/nm'
pkg-config = 'false'
[built-in options]
c_args = ['-Wno-error=incompatible-function-pointer-types']
c_link_args = ['-Wl,-ios_version_min,16.0']
cpp_link_args = ['-Wl,-ios_version_min,16.0']
[host_machine]
system = 'darwin'
subsystem = 'ios'
cpu_family = 'aarch64'
cpu = 'arm64'
endian = 'little'
[properties]
needs_exe_wrapper = true
INI
[[ -f "$b/build/build.ninja" ]] || meson setup "$b/build" "$src" --cross-file "$b/cross.ini" --wrap-mode=nofallback \
  --buildtype=release -Db_ndebug=true -Ddefault_library=static \
  -Dplatforms= -Degl=disabled -Dglx=disabled -Dgbm=disabled -Dglvnd=disabled -Dosmesa=false \
  -Dgallium-drivers= -Dvulkan-drivers=freedreno -Dfreedreno-kmds=msm -Dllvm=disabled \
  -Dopengl=false -Dgles1=disabled -Dgles2=disabled -Dshared-glapi=disabled \
  -Dzstd=disabled -Dexpat=disabled -Dxmlconfig=disabled -Dshader-cache=disabled \
  -Dvalgrind=disabled -Dlibunwind=disabled -Dlmsensors=disabled -Dbuild-tests=false \
  -Dperfetto=false -Dgallium-va=disabled -Dgallium-vdpau=disabled -Dgallium-xa=disabled \
  -Dgallium-rusticl=false -Dteflon=false -Dvideo-codecs= -Dtools= -Dhtml-docs=disabled -Dvulkan-layers=
ninja -C "$b/build" -j"$(sysctl -n hw.ncpu)" src/freedreno/vulkan/libvulkan_freedreno.dylib
vk="$b/build/src/freedreno/vulkan/libvulkan_freedreno.dylib"; out="$b/libvulkan_freedreno.dylib"
cp "$vk" "$out"; codesign --force --sign - "$out"
otool -l "$out" | grep -q 'cmd LC_DYLD_CHAINED_FIXUPS' || { echo 'turnip: no chained fixups' >&2; exit 1; }
nm -m "$out" | grep -q dyld_stub_binder && { echo 'turnip: imports dyld_stub_binder' >&2; exit 1; }
for s in _vk_icdGetInstanceProcAddr _vkGetInstanceProcAddr _redwood_drm_note_surface; do
  nm -gU "$out" | awk '{print $3}' | grep -qx "$s" || { echo "turnip: $s not exported" >&2; exit 1; }
done
shasum -a 256 "$out"
echo "Built Turnip for iOS; nothing installed on the phone."
