# ios-spes — Redmi Note 11 bring-up

Experimental source port of [MakrSas/ios-topaz](https://github.com/MakrSas/ios-topaz/tree/topaz)
to **Redmi Note 11 (`spes`, SM6225 / Snapdragon 680)**. Target handset: 6 GB
physical RAM, unlocked bootloader. The Android “+2 GB” expansion is not RAM
available to this kernel.

**Status (2026-10-26): iOS 16.7.16 runs on the phone with a GPU-drawn interface,
touch, Wi-Fi, Safari, wallpapers and speaker sound.** Images are still loaded with
`fastboot boot` (nothing is flashed to `boot`). This is an experimental port, not
a daily-use ROM.

| Feature | Status | Notes |
| --- | --- | --- |
| Boot to the home screen | Works | iOS 16.7.16 (20H392, iPhone X identity) from an HFS+ root in `userdata`; about a minute or two to the home screen |
| GPU-drawn interface | Works | Adreno 610 through Mesa freedreno (OpenGL ES) and the HackiOS EAGL bridge; full-screen frames go straight to the display controller |
| Frame pacing | Works, 60 Hz | Vsync follows the panel's own frame counter (patch 0154) |
| 90 Hz | Not working | The panel switches to 90 Hz (patch 0154/0155), but the interface stops drawing and touch fails; images pass `sweetfb_rate=0` |
| Touchscreen | Works | FocalTech `54:52`; read on its interrupt line every 1 ms, every 4 ms while touched (patch 0154) |
| Power and volume buttons | Work | Lock and unlock with display fades |
| Brightness | Works | Slider and fades through an AppleARMBacklight service (patches 0145, 0146, 0154) |
| Wi-Fi | Works | Modem and WLAN firmware boot through TrustZone; iOS joins networks (`modem=1 wifi=1`) |
| Safari / WebKit | Works | Pages render on the GPU |
| Speaker sound | Works | ADSP stream into the WCD937x codec and the two aw87559 amplifiers (patches 0142-0153); HackiOS's RedwoodAudio HAL plug-in with iOS's virtual audio device. Volume is limited on purpose (`spesvol`, default -12 dB) |
| Video playback | Not working | YouTube and other video crash `mediaserverd` in the software H.264 decoder |
| Wallpapers | Partly | Most wallpapers show (patch 0151); the Earth wallpapers need Metal; some library thumbnails look wrong |
| Metal | Not working | No Metal device yet. Turnip (Vulkan) for iOS builds and opens the GPU; the Metal translation layer (metal2vulkan) is the next step |
| Microphone | Not tested | |
| Bluetooth | Not working | Planned |
| Battery and charging | Not working | A placeholder battery service (SweetBattery) satisfies iOS; the real level and charging control are planned |
| Cellular, camera, vibration, USB | Not working | Not started (the USB driver is disabled on spes) |

The iOS HFS+ root is installed in the existing `userdata` partition after
explicit approval to erase Android data. Boot images are still loaded with
`fastboot boot`; bootloaders, recovery, modem and persist are preserved.
Apple filesystem images and device-specific dumps are not distributed here.

## Graphics (2026-10-25)

The GPU stack follows [HackiOS](https://github.com/oosexgang/hackios-xnu-kernel)
(RedwoodGPU service, MiniIOSurface/MiniIOMobileFramebuffer designs, EAGL bridge
over Mesa) and [Topaz](https://github.com/MakrSas/ios-topaz), which runs the same
SM6225 SoC and Adreno 610. Main pieces, all patches in `xnu/patches`:

- **0100/0102**: persistent A610 backend with queued submissions (the caller waits
  for ring space, not for the GPU) and per-surface GPU fences; the framebuffer
  waits for a frame's fence before showing it.
- **0046/0104/0108**: built-in IOSurface with client-memory surfaces, values,
  bulk attachments, and Topaz's release semantics (trap 4 detaches, trap 5 releases).
- **0105/0106**: presenter thread with frame backpressure; published 60 Hz modes.
- **0107**: GPU clock from GPLL0 (nominal 300 MHz); `SPES_GPU_MHZ=19` selects the
  original 19.2 MHz clock.
- **0109**: direct MDP scanout of full-screen surfaces from contiguous RAM
  (SSPP VIG0/CTL0, as in Topaz). It is only enabled when VIG0 is found scanning the
  boot framebuffer; boot-arg `sweetfb_direct=0` turns it off.
- **0111/0112**: display off shows black (a flip to a ready black frame with direct
  scanout); opt-in DSI panel sleep and brightness (`sweetpanel=1`, Topaz 0104/0143).
- `tools/eagl-attach-gpu.patch`: EAGL fills attached display targets on the GPU
  instead of copying them on the CPU.

Wi-Fi uses patch 0099 (modem boot through TrustZone PAS, GLINK/QRTR, WLFW, WMI,
HTT) with 0110 following Topaz on the MSA handover; it is off unless the image
gets `SWEET_EXTRA_ARGS='modem=1 wifi=1'`. The iOS side (en0 and Apple80211 for
wifid, Topaz 0900) is not ported yet.

`tools/build-spes-ios-graphics.sh KERNEL LIVE_FDT` builds the full graphics image
(defaults: `SWEET_CPUS=6`, `SWEET_FB_HZ=60`, `SPES_GPU_MHZ=300`). The Mesa/EAGL
libraries are installed into the iOS root separately. Development history and
logs are in `NOTES.md`.

### GPU bring-up milestone (2026-10-23)

All three stages of GPU initialization and execution are verified on the test handset:
1. **Command Processor execution**: `CP_ME_INIT` retires at RPTR/WPTR `16/16`, followed by `CP_MEM_WRITE` at `32/32`. The GPU writes `0xcafe0001` to its reserved scratch buffer with zero CP errors and zero SMMU fault bits.
2. **TrustZone ZAP authentication & secure transition**: PAS13 microcode authentication succeeds via TZBSP, and `CP_SET_SECURE_MODE(0)` retires cleanly, placing the Adreno 610 in non-secure rendering mode.
3. **Physical framebuffer memory write**: The GPU CP executes 16 `CP_MEM_WRITE` packets writing a 64×16 pixel rectangle into physical display RAM (`0x5c000000`) and retires cleanly, with all 1024/1024 pixels bit-exact verified on readback.

This was verified via temporary RAM-boot using kernel `426b3ad` ([CI 39918190004](https://github.com/AdyaGMD/ios-spes/actions/runs/39918190004)) with the `gpu-display` profile in `tools/build-spes-diagnostic.sh`.

The subsequent `gpu-bridge` test (kernel `89f2b42`, [CI 39951466519](https://github.com/AdyaGMD/ios-spes/actions/runs/39951466519)) also passes on hardware: a HackiOS-style indirect command buffer writes `0x1b610001`, signals completion fence `1`, and retires at `1116/1116` with no reported GPU faults.

The user also reports a successful `gpu-repeat` test (kernel `7546dd5`): its pass criteria require 512 serialized submissions, at least two ring wraps, and matching data and completion fences. Raw counters were not captured.

Those diagnostics led to the persistent backend and accelerated UI described
above. See the [A610 audit](docs/SPES-GPU-A610-AUDIT-20261023.md) for
architectural evidence and register details.

## Changes

- `tools/mkadt.py --device spes --memory-dtb LIVE.dtb`: spes identity, four Gold
  cores, nominal 2.4 GHz, and a kernel platform marker. RAM comes from a live
  bootloader-populated FDT, never from topaz's hard-coded upper bank.
- `tools/spes_memory.py`: selects an aligned contiguous RAM range above 4 GiB;
  excludes explicit reservations and rejects unresolved high-memory pools,
  missing memory maps, and stock zero-filled memory placeholders.
- Patch **0088**: FocalTech AVDD on **GPIO98 / SOUTH tile**, reset 86, IRQ 80;
  integer 1080×2400 coordinates instead of topaz's fractional 1350×3000 input.
  Touch defaults off on spes; opt in with `sweettouch=1` after initial diagnostics.
  Patch **0096** enables PMIC keys with `sweetkeys=1`; volume buttons are
  user-confirmed working. The inherited USB driver remains disabled on spes.
- The shim accepts `BOOT_HEADER_VERSION=3`, matching the supplied stock firmware.
  Version 4 remains the upstream default. Embedded payload packaging is retained;
  temporary bootloader acceptance and RAM-only userspace execution are verified.

## Evidence

Inspected the user's `spes_global_images_OS1.0.8.0.TGCMIXM_13.0` firmware:

| Item | Observed |
| --- | --- |
| boot / vendor_boot headers | Both version 3 |
| Khaje base DTB | vendor_boot DTB index 8 |
| SPES board overlays | DTBO indices 6 and 15; active board revision still unknown |
| Continuous splash | `0x5c000000`, reservation `0xf00000` |
| Memory | `/memory/reg` is all zero; ABL fills it at boot |
| Touch | FocalTech I²C `0x38`, AVDD GPIO98, display coordinates 1080×2400 |

Source reference: [Jabiyeff/kernel_xiaomi_sm6225 at
6c2b3e7](https://github.com/Jabiyeff/kernel_xiaomi_sm6225/tree/6c2b3e7528a0778cd80c95eabb490746b5422f8c),
`arch/arm64/boot/dts/vendor/qcom/{khaje,khaje-idp,spes}.dtsi`,
`drivers/pinctrl/qcom/pinctrl-khaje.c`, and
`drivers/input/touchscreen/ft3418_i2c/focaltech_core.c`.
The GPIO98 SOUTH tile and integer touch decoding come from that source;
hardware testing identified FocalTech `54:52` and confirmed touch events after
patch **0093** enabled the AVDD GPIO output correctly.

## Verified temporary recovery / live memory capture

On 2026-10-18 the official OrangeFox R11.1_2 MIUI recovery booted temporarily
via `fastboot boot` on this handset, with root ADB. No recovery installer or
flash command was run. The live FDT is saved locally in ignored
`dtb/spes-live.dtb`; it is not published because it can contain device identifiers.
The selected XNU RAM range is **0x100000000 + 0xc0000000 (3 GiB)**. The live
DT also confirms AVDD GPIO98, IRQ80 and 1080×2400 touch coordinates.
`shim/out/spes.adt` was generated successfully. This was the initial recovery and memory-map milestone; subsequent tests
reached XNU userspace and then the iOS interface.

## Capturing the live memory map again

Connect the phone with USB debugging enabled and authorize the computer.
Reading `/sys/firmware/fdt` generally needs root or a compatible recovery:

```sh
mkdir -p dtb
adb exec-out su -c 'cat /sys/firmware/fdt' > dtb/spes-live.dtb
```

In an already-running recovery with root ADB, omit `su -c`.
Do not substitute the stock vendor_boot DTB: it has no usable memory map.
The tool intentionally refuses it. No recovery image is supplied in this repository.

## Build preparation

Build XNU with `.github/workflows/xnu.yml` in your own fork (manual dispatch).
It retains the SWEET machine name and applies the numbered patches in `xnu/patches`. Download the
`xnu-kernel` artifact into `xnu/out`. The [first corrected kernel build passed](https://github.com/AdyaGMD/ios-spes/actions/runs/39273597179) at source commit `7f915db`.

The shim needs an AArch64 GNU toolchain and an executable AOSP `mkbootimg`.
For full iOS, obtain the iPhone X D22AP tree/root separately; Apple artifacts
are not included. See [upstream background](docs/TOPAZ-UPSTREAM.md) for the
root construction process; its topaz memory and flashing instructions are not
spes validation results.

```sh
mkdir -p shim/out
python3 tools/mkadt.py shim/out/spes.adt --device spes --memory-dtb dtb/spes-live.dtb
python3 tools/mkpayload.py xnu/out/kernel.development.sweet shim/out/spes.adt shim/out/payload.bin \
  --cmdline 'debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam rd=ufsroot0 ufsrw=0 rootrw=0 sweetlog=0 sweettouch=0 sweetkeys=0 sweethw=0 sweetfb_stayon=1'
BOOT_HEADER_VERSION=3 MKBOOTIMG=/absolute/path/to/mkbootimg shim/build.sh out/payload.bin
```

The command line is for **read-only kernel diagnostics**. An Android userdata
partition cannot serve as an iOS HFS+ root, so this will not reach SpringBoard.
An independently prepared RAM root can instead be supplied via `mkpayload.py
--ramdisk IMAGE` and `rd=md0`; its size must fit the selected memory range.
Do not enable UFS writes or persistent logs against Android userdata.

Only after reviewing the generated image and memory map should a temporary
`fastboot boot shim/out/shim-boot.img` be attempted. The test handset now has an iOS root in
userdata. On another handset, installing that root erases Android data and
requires a separate, explicitly confirmed step.

## RAM-only first-boot diagnostic

Once the kernel artifact is available, build a small diagnostic that runs the
project's static test program as PID 1 from RAM. It needs no iOS filesystem
and requests no storage writes:

```sh
CROSS_COMPILE=aarch64-elf- MKBOOTIMG="$PWD/research/mkbootimg/mkbootimg.py" \
  tools/build-spes-diagnostic.sh xnu/out/kernel.development.sweet dtb/spes-live.dtb
```

Output: `shim/out/spes-diagnostic.img` and its SHA-256 file. This tests XNU boot,
userspace execution and the console, not SpringBoard. No phone action is
performed by the script. Hardware execution was confirmed by photos showing
PID 1 and repeated heartbeat messages on 2026-10-19.

## Read-only storage diagnostic

With a kernel including patch 0090, append `storage` to the diagnostic builder:

```sh
CROSS_COMPILE=aarch64-elf- MKBOOTIMG="$PWD/research/mkbootimg/mkbootimg.py" \
  tools/build-spes-diagnostic.sh xnu/out/kernel.development.sweet dtb/spes-live.dtb storage
```

This produces `shim/out/spes-storage-probe.img`. It keeps `rd=md0`, enables
`spesufsprobe=1`, reads the UFS partition table and prints the result before
starting the RAM test program. The probe blocks SCSI commands other than
TEST UNIT READY and READ(10), forces a read-only disk device, and skips
persistent logging and input drivers. It does not mount Android userdata.
On 2026-10-20 the user reported `result=0` and continued PID 1 heartbeats.
This confirms UFS takeover and userdata partition lookup, not filesystem
mounting or disk writes.

## Touch diagnostic

With patch 0091, the builder's `touch` profile produces
`shim/out/spes-touch-probe.img`. It runs touch independently of storage from
RAM, with `spestouchprobe=1 sweettouch=1 sweettouchdelay=5 sweettouchdiag=3`.
It prints input counters and coordinates roughly every five seconds; tap and
drag to test them. Failures print the stage and stop the touch thread.
The first hardware test reached the I²C probe but got NACKs and no chip ID;
the touch thread stopped while PID 1 remained alive. The separate touch I/O
power supply is under investigation. No partition flash or iOS GUI is involved.

## Checks

```sh
python3 -m unittest discover -s tests -v
bash -n shim/build.sh
```

42 host tests cover memory selection, reserved regions, malformed input,
stock-map rejection, spes ADT contents, the GPU backend against mocked hardware,
framebuffer handoff and audio/Wi-Fi profile checks.
All shim C/assembly translation units cross-compile with Clang for Cortex-A53.
All 155 port patches apply to the pinned XNU tree and the full kernel builds in CI.

On 2026-10-20, patch 0093 enabled the advertised extended-GPIO feature on
GPIO98. A photo confirms chip ID 54:52 and changing HID touch events and
coordinates. Six report errors were recorded, stable across the visible
samples; further reliability testing remains. No RPM voltage request was
needed for that boot.

## Prepare an iOS root on macOS

`tools/mkiosroot-macos.sh` builds a local 16 GiB raw case-sensitive journaled
HFS+ image from the three iPhone X 16.7.16/20H392 filesystem components. It
mounts source images read-only, preserves numeric owners and hard links,
merges cryptex content, applies the existing bring-up tweaks and runs fsck.
It refuses to overwrite an existing output. Administrator access is required
for file ownership. It never connects to or flashes the phone.

```sh
sudo tools/mkiosroot-macos.sh \
  research/ipsw-x/087-86698-044.dmg \
  research/ipsw-x/087-86593-047.dmg \
  research/ipsw-x/087-86715-047.dmg \
  research/spes-ios-root.img
```

The raw image is published only after successful assembly and filesystem
validation. The temporary workspace is retained for diagnosis; source mounts
are detached on exit. This host preparation does not authorize installation
or validate that SpringBoard will boot on spes.
