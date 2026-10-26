#!/bin/bash
# Build the Metal userland for spes (A610), after iOSPlus10's (MIT) NegroniMetal: the ios-flame Metal frontend
# (NWylynko/ios-flame 745c434, MIT) + its bridge over metal2vulkan (steelbrain 720ef1ce, GPL-2.0+/LGPL-3.0+,
# linked statically: keep this script and the sources with any binary handed out) + iOSPlus10's patches, with
# their A730 device answers (flame 0003) turned into A610 ones. Never touches the phone.
#   out: research/metal-build/stage/System/Library/Extensions/NegroniMetal.bundle (+ our Turnip) and the probes.
set -euo pipefail
[[ $# == 5 ]] || { echo 'usage: build-spes-metal-macos.sh IOSPLUS10 IOS_FLAME METAL2VULKAN IOS_SDK TURNIP_DYLIB' >&2; exit 2; }
ip10=$(cd "$1" && pwd); flame=$(cd "$2" && pwd); m2vrepo=$(cd "$3" && pwd); sdk=$(cd "$4" && pwd); turnip=$(cd "$(dirname "$5")" && pwd)/$(basename "$5")
root=$(cd "$(dirname "$0")/.." && pwd); b="$root/research/metal-build"
[[ $(git -C "$ip10" rev-parse --short=7 HEAD) == c0a451f ]] || { echo 'iOSPlus10 not at c0a451f' >&2; exit 1; }
git -C "$flame" cat-file -e 745c4341af86089efb0df851fa8a27fb8face624^{commit}
git -C "$m2vrepo" cat-file -e 720ef1ce9ae2a2068999a8675717418b9416283e^{commit}
export PATH="$HOME/.cargo/bin:/opt/homebrew/opt/llvm/bin:$PATH"
m2v="$b/src/metal2vulkan"; fs="$b/src/flame"; met="$b/src/metal"
if [[ ! -f "$b/src/.patched" ]]; then
  rm -rf "$b/src"; mkdir -p "$m2v" "$fs"
  git -C "$m2vrepo" archive 720ef1ce9ae2a2068999a8675717418b9416283e | tar -x -C "$m2v"
  git -C "$m2v" init -q && git -C "$m2v" add -A && git -C "$m2v" -c user.name=spes -c user.email=spes@local commit -q -m base
  git -C "$flame" archive 745c4341af86089efb0df851fa8a27fb8face624 phone/metal2 phone/turnip/NativeAdrenoABI.h | tar -x -C "$fs"
  for p in "$fs"/phone/metal2/bridge/patches/*.patch; do
    case "$(basename "$p")" in 0006-*) continue ;; esac        # UniXNU and iOSPlus10 leave 0006 out too
    git -C "$m2v" apply --whitespace=nowarn "$p"; echo "m2v: flame $(basename "$p")"
  done
  # iOSPlus10's userland/metal, copied: metalprobe reads recommendedMaxWorkingSetSize, which the iOS 16.5 SDK marks
  # unavailable on iOS (they build with a newer SDK); asked by key instead
  cp -R "$ip10/userland/metal" "$met"
  python3 - "$met/probes/metalprobe.m" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1]); s=p.read_text()
a='(unsigned long long)(d.recommendedMaxWorkingSetSize >> 20)'
assert s.count(a)==1
p.write_text(s.replace(a,'(unsigned long long)([[(id)d valueForKey:@"recommendedMaxWorkingSetSize"] unsignedLongLongValue] >> 20)'))
PY
  for p in "$met"/patches/m2v/*.patch; do git -C "$m2v" apply --whitespace=nowarn "$p"; echo "m2v: iOSPlus10 $(basename "$p")"; done
  # A610 (Mesa freedreno_devices.py GPUId(610): num_ccu 1, cs_shared_mem_size 16 KiB) instead of the A730's 4 and 32 KiB
  sed -e 's/A730 answers/A610 answers/; s/Adreno 730/Adreno 610/; s/FD730: num_ccu 4 = num_sp_cores/FD610: num_ccu 1 = num_sp_cores/' \
      -e 's/"gpuCoreCount")){\*value=4;/"gpuCoreCount")){*value=1;/; s/\*value=32768;/*value=16384;/; s/32 KiB/16 KiB/' \
      -e 's/NegroniMetal A730 answer/NegroniMetal A610 answer/' \
      "$met/patches/flame/0003-negroni-a730-device-answers.patch" > "$b/0003-spes-a610-device-answers.patch"
  grep -q 'value=1;return true' "$b/0003-spes-a610-device-answers.patch" && grep -q 'value=16384' "$b/0003-spes-a610-device-answers.patch"
  for p in "$met"/patches/flame/*.patch; do
    case "$(basename "$p")" in 0003-*) p="$b/0003-spes-a610-device-answers.patch" ;; esac
    patch -s -p1 --batch --no-backup-if-mismatch -d "$fs" < "$p"; echo "flame: $(basename "$p")"
  done
  touch "$b/src/.patched"
fi
# the bridge: a static library over metal2vulkan (iOSPlus10 scripts/metal/build-bridge.sh)
br="$fs/phone/metal2/bridge"; mkdir -p "$b/bridge"
llvm-as -o "$b/bridge/runtime_examples.air" "$m2v/crates/metal2vulkan-validation/fixtures/public/examples/runtime_examples.ll"
llvm-as -o "$b/bridge/function_constant.air" "$m2v/crates/metal2vulkan-validation/fixtures/public/kernel_function_constant_gate_fold.ll"
cat > "$b/bridge/Cargo.toml" <<TOML
[package]
name = "native-metal-bridge"
version = "0.1.0"
edition = "2024"
rust-version = "1.98"
[workspace]
[lib]
crate-type = ["staticlib"]
path = "$br/NativeMetalBridge.rs"
[dependencies]
metal2vulkan = { path = "$m2v/crates/metal2vulkan", features = ["ash"] }
metal2vulkan-runtime = { path = "$m2v/crates/metal2vulkan-runtime" }
libc = "0.2"
sha2 = { version = "0.10", features = ["asm"] }
[profile.release]
panic = "unwind"
debug = 1
TOML
export NMB_FIXTURE_AIR="$b/bridge/runtime_examples.air" NMB_FC_AIR="$b/bridge/function_constant.air"
export IPHONEOS_DEPLOYMENT_TARGET=16.0 SDKROOT="$sdk"
cargo +1.98.0 build --release --manifest-path "$b/bridge/Cargo.toml" --target aarch64-apple-ios --target-dir "$b/bridge/target"
lib="$b/bridge/target/aarch64-apple-ios/release/libnative_metal_bridge.a"
# plug-in and probes (iOSPlus10 userland/metal CMakeLists.txt, ios-arm64.cmake)
export IOS_MIN=16.0 SDK="$sdk"
cmake -S "$met" -B "$b/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_TOOLCHAIN_FILE="$met/cmake/ios-arm64.cmake" \
  -DNMTL_BRIDGE_LIB="$lib" -DNMTL_FLAME_SRC="$fs/phone/metal2" -DNMTL_CLASS=NegroniMTLDevice \
  -DVULKAN_INCLUDE="$root/research/mesa-build/mesa-25.0.7/include"
ninja -C "$b/build"
st="$b/stage"; rm -rf "$st"; bun="$st/System/Library/Extensions/NegroniMetal.bundle"; mkdir -p "$bun" "$st/redwood/bin"
cp "$b/build/NegroniMetal" "$bun/NegroniMetal"
sed -e 's/@NAME@/NegroniMetal/g' -e 's/@CLASS@/NegroniMTLDevice/g' "$met/plugin/Info.plist.in" > "$bun/Info.plist"
echo 'metalprobe m2vtest carenderprobe' > "$bun/clients"
cp "$turnip" "$bun/libvulkan_freedreno.dylib"
for t in metalprobe m2vtest carenderprobe; do cp "$b/build/$t" "$st/redwood/bin/$t"; done
codesign -f -s - "$bun/NegroniMetal" "$bun/libvulkan_freedreno.dylib" "$st/redwood/bin/"*
shasum -a 256 "$bun/NegroniMetal" "$bun/libvulkan_freedreno.dylib" "$st/redwood/bin/"*
echo "Built the Metal userland; nothing installed on the phone."
