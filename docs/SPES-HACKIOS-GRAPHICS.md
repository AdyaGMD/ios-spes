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
wrap. Passing this test will not validate concurrent submissions or fence wrap.

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
