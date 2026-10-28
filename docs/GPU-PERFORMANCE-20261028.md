# GPU performance investigation, 2026-10-28

## Confirmed baseline

The phone log `research/spes-latest-20261028-boot.txt` (flush 7) identifies
all48-noround: `spessurfround=0`, `spesgpu_mhz=785`, no `spesgpu_cache`.
The user reports some garbled images and slow interaction. This is **not** a
result for all49's cached-PTE experiment.

Six active windows (20+ submissions, under 10 seconds) give approximately
51.88 ms per **timed submission**, weighted by the number of retained timing
samples, and 12.22 submitted batches/second. These are not displayed FPS.
The timing ring retains only 64 entries, so timing sample counts and census
submission counts can differ. Do not divide a census by the timing count.
GPU clock measures 772–775 MHz. CPU cache maintenance is generally below
1 ms per submission in those windows. The GPU workload, rather than that
CPU cache maintenance, remains the dominant measured cost.

Prior 1115 MHz and GMEM/sysmem tests did not resolve the problem. Avoid
another frequency increase or overriding client pitches. Remaining copies,
linear rendering bandwidth, and synchronization are still candidates; this
log alone does not prove which is the ultimate limit.

## Concrete missed optimization

The currently built Turnip source (`tu_device.cc`) advertises
`VK_EXT_image_drm_format_modifier` and `VK_EXT_queue_family_foreign` on
Darwin, but deliberately disables `VK_EXT_external_memory_dma_buf`.
metal2vulkan's `dma_buf_image_names()` required DMA_BUF import support,
and `host_pitched_image()` consulted `makes_dma_buf_images()`. Therefore
its explicit-pitch fallback for **host pointer** imports could never run.

Vulkan explicitly says the modifier extension does not require a specific
external-memory handle type:
https://docs.vulkan.org/refpages/latest/refpages/source/VK_EXT_image_drm_format_modifier.html

Patch `userland/metal-patches/m2v/0002-spes-host-image-modifiers.patch`
separates host modifier capability from DMA_BUF capability. Creation enables
the extension where advertised; adoption uses only the extensions the caller
enabled. Host imports try the existing explicit-layout implementation. The
DMA_BUF route still requires its original import and foreign-queue extensions.
Format/usage, memory type, dedicated allocation, returned pitch, allocation
size and bounds checks remain unchanged. Unsupported layouts still shadow.

Mesa's `fd6_layout.c` accepts explicit linear 4-byte-texel pitches at 64-byte
alignment, versus the default 256-byte alignment. This can eliminate copies
for e.g. 3200- and 4544-byte rows, without changing client memory. It does
**not** make 3152- or 4512-byte pitches supported, nor eliminate all copies.
No on-device speed or correctness claim yet.

The build script now applies new local patches even when the upstream source
cache already exists; it recognizes already-applied patches and fails on drift.

## Validation

- ARM64 iOS release bridge compiled; NegroniMetal linked successfully.
- Runtime device tests: 16 passed, including the new host-modifier-without-
  DMA_BUF regression and existing DMA_BUF eligibility checks.
- Layout tests: 16 passed, 2 failed **also without this patch**. Both failures
  assert the upstream refusal of padded writable aliases, already changed by
  the imported flame patch. This change does not modify `linear_plan.rs`.
- Patch reverse-application check and shell syntax check passed.
- Logs under `research/gpu-performance-20261028/` (ignored).

## Device validation still required

Keep the 785 MHz, uncached-PTE baseline first to isolate the userland change.
Check image correctness, same scrolling workload, GPU timing and census copy
pixels. If it helps, separately test all49's cached PTEs. Never call a successful
compile a measured performance improvement.
