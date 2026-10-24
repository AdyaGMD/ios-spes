# HackiOS graphics reuse for spes

Kernel source inspected at `oosexgang/hackios-xnu-kernel` commit
`8e61187098f2c26c5daee8f9f72b6416aa64b9ab` (remote main checked 2026-10-23).
Local userland reference is `906425b75e02b4f99eb5d7bb1ef7c9583472d772`;
remote main was `a79ff0772a3454fd1ef127e181e5b3bce6c9ce18`. Fetched and compared
on 2026-10-23: only thermal, var-store and build changes; no graphics changes.

## Reusable path

CoreAnimation → userland EAGL/OpenGL ES bridge → patched Mesa 25.0.7 Freedreno
→ redwood-drm IOKit calls → RedwoodGPU user client → hardware backend.

Sources:
- [Kernel service](https://github.com/oosexgang/hackios-xnu-kernel/blob/8e61187098f2c26c5daee8f9f72b6416aa64b9ab/xnu/files/iokit/Kernel/RedwoodGPU.cpp)
- [Hardware submission](https://github.com/oosexgang/hackios-xnu-kernel/blob/8e61187098f2c26c5daee8f9f72b6416aa64b9ab/xnu/files/bsd/dev/redwood_adreno.c)
- Userland: `tools/mesa/redwood-drm/redwood_drm.c`,
  `tools/mesa/freedreno-darwin.patch`, `tools/mk-mesa.sh`,
  `userland/src/eagl.c`, `userland/src/gl_osmesa.c`.

## Required adaptations (not yet implemented)

- Keep spes power, clock, firmware and SMMU setup. Redwood targets A642L and a
  GMU; its chip ID, 512 KiB GMEM, recovery/reset sequence and HWCG are not A610.
  A610 has 132 KiB GMEM and a reset quirk; do not report Redwood capabilities.
- Replace the fixed probe mappings with bounded dynamic 4 KiB GPU page tables,
  buffer VA allocation/free, cache maintenance and TLB synchronization. XNU
  uses 16 KiB CPU pages; each physical segment must be split appropriately.
- Maintain ring state across submissions with a lock, wrap/space accounting,
  fault handling and real completion fences. Do not expose a halted diagnostic
  engine as ready. No unverified reset/recovery fallback.
- Adapt IOSurface import: HackiOS `MiniIOSurface` puts pixels one PAGE_SIZE after
  shared state; `SweetSurface` stores state separately. Copying the PAGE_SIZE
  offset would import the wrong pixels. Use its retained `sweet_surface_copy`,
  memory descriptor and actual offset/size; support framebuffer physical memory.
- Preserve surface lifetime and completion synchronization before display swaps.
  HackiOS uses `surface->drawn` and `MiniIOSurfaceDrawn`; SweetSurface currently
  lacks that contract. Mapping bytes alone does not implement synchronization.
- Port the service/DRM selectors and build matching userland libraries. Test a
  standalone triangle and IOSurface render/readback before changing backboardd.
  Keep software rendering available until A610 hardware draws are verified.

## First reused submission primitive

The opt-in `gpu-bridge` diagnostic follows HackiOS `redwood_gpu_submit`'s core
sequence: INDIRECT_BUFFER, WAIT_FOR_IDLE, CACHE_FLUSH_TS with a GPU-written
fence. It deliberately omits A642L timing registers, shader state and arbitrary
user addresses. It uses the existing owned 64 KiB DMA region:

| Purpose | GPU VA | Physical address |
| --- | --- | --- |
| Four-word indirect command buffer | 0x10001000 | 0x5ca0d000 |
| Data marker | 0x011f0020 | 0x5ca0c020 |
| Completion fence | 0x011f0024 | 0x5ca0c024 |

Expected data is 0x1b610001 and fence is 1. The ring reaches 1116 dwords, inside
its 2048-dword capacity. Every stage has bounded waits and fault checks; after
the test the engine halts. No userspace GPU service or UI acceleration is enabled.
Seven host tests validate encoding, mappings, ring bounds and failure handling.
Hardware photo on 2026-10-23 confirms INDIRECT_BUFFER and FENCE_STATUS PASS,
RPTR/WPTR=1116/1116, data=0x1b610001, fence=1, CP/HW/INT0/GFSR=0, FSR=0x400.
Kernel 89f2b42, CI 39951466519. This is a prerequisite, not completion of the UI port.

## Mapping and submission contracts for the next implementation

The repeat diagnostic intentionally supports one producer and one outstanding
submission. It requires RPTR=tail before overwriting any ring words or IB memory,
pads boundary gaps with CP_NOP, and retains the hardware read pointer across
wrap. User reported success on 2026-10-23 for kernel 7546dd5 / CI 39953944022;
raw counters were not supplied. Its PASS gate requires 512 completions and at
least two ring wraps. This does not validate concurrent submissions or fence wrap.

The service adaptation must serialize allocation, mapping and submission under
one lock initially. Buffer references and VA reservations must survive until the
last completion fence. Do not expose physical addresses or accept arbitrary
physical mappings from userspace. Split retained memory-descriptor segments into
4 KiB GPU pages despite the kernel's 16 KiB pages; check every size/address sum
for overflow and roll back partially installed mappings on failure.

Unlike reference redwood_gpu_unmap (which has no success return), the spes
invalidation API must report bounded TLB-sync failure. On failure keep the buffer
and VA reserved, mark the backend unavailable, and do not recycle physical pages.
Map replacement must invalidate the old translation before installing the new
one. Test this first using reserved scratch pages and verified command/fence
submission, before mapping a real IOSurface or changing the iOS root filesystem.

## Reserved-page remap diagnostic

`gpu-remap` uses an initially invalid leaf at GPU VA `0x10010000` and two
reserved physical pages, `0x5ca0e000` and `0x5ca0f000`. It runs after the proven
IB/fence check, without the separate 512-submission stress loop. Three writes
map A → B → A, with markers `0x6d610001..3` and fences `1024..1026`.
Each step checks both physical words so a stale translation cannot pass merely
because the fence completed. The final mapping is removed; there is no deliberate
GPU access after unmapping. Failure retains memory and stops submissions.

This tests live leaf replacement and invalidation, not a dynamic VA allocator,
page-table growth, noncontiguous user buffers or IOSurface lifetime handling.
The future service must also validate `getPhysicalSegment` length and alignment
for every 4 KiB page; the reference `newBuffer` retrieves length but does not
check that it covers the requested page. Partial mapping rollback must propagate
invalidation failure instead of unconditionally freeing the VA and descriptor.

## Owned-buffer prototype

User reported the remap test passing on 2026-10-23; raw counters were not supplied.
The next `gpu-buffers` diagnostic adds a bounded first-fit allocator over the
496 unused leaves of the existing target table. It supports 32 live handles,
rejects token wrap and invalid physical pages, and retains ownership if TLB sync
fails. It requires a serialized caller and verified completion fences.

The diagnostic maps two separately allocated kernel pages into one 8 KiB GPU
buffer (one 4 KiB slice each), submits writes to both, and checks unmapping and
address reuse with a new handle. Permanent backing allocations remain retained
for the whole diagnostic boot, including failure. Hardware validation pending.
This small pool is a prototype; full-screen surfaces need a larger VA window and
page-table growth before exposing the HackiOS service.

## Combined integration (2026-10-24, not hardware verified)

Patch0100 adapts the pinned RedwoodGPU service to SweetSurface and a serialized,
synchronous backend with 256 MiB GPU VA. No MiniIOSurface shared-state prefix is
applied to pixel mappings. Failed submissions or TLB synchronization stop the GPU
and retain backing allocations; reset/recovery and cross-client isolation are
not implemented. This is an experimental trusted-userland bring-up interface.

`spesgpu=1` runs the previous initialization, framebuffer-write, indirect-buffer,
repeat, remap and allocated-buffer gates in sequence, then publishes the service
only after success. The opt-in `tools/build-spes-ios-graphics.sh` builds that full
iOS image, preserving the existing software boot image. It does not install files
or boot a device. GPU buffer reuse uses the HackiOS default (`gpu_keep=1`);
the image no longer passes `gpu_keep=0`, which disabled it for initial integration.

The host build scripts use pinned HackiOS userland and Mesa25.0.7. The A610
bank-layout setting matches the live spes device tree (chip06010001, bank14).
The EAGL bridge first waits for the service and demands an A610 renderer, shader
compilation, triangle drawing and matching center/background pixel readback.
Only a passing check permits method replacement. A passing build is not a
passing render. This guard cannot recover from a GPU/driver kernel failure.

`tools/build-spes-eagl-macos.sh` applies `tools/eagl-attach-gpu.patch` to the
pinned bridge. Mirrored render targets are initialized by a GPU blit from the
IOSurface-backed mirror instead of a CPU hash and upload; the existing CPU path
remains as the fallback. BGRA fallback refills reuse texture storage with
`glTexSubImage2D`, following MakrSas/ios-topaz commit `fe7625f` rather than
reallocating a full-screen texture on every attach. `tests/test_eagl_attach.py`
exercises the real helper with mocked GL state when the pinned source is present.

Local checks: 26 host tests, two kernel translation-unit syntax checks, Mesa/EAGL
cross-build and ad-hoc signature verification pass. No new kernel boot, shader
render, IOSurface rendering or accelerated UI result has been observed yet.
Root installation/injection still needs preparation against the fresh snapshot.
Do not copy upstream inject.c's version-specific private function addresses.
