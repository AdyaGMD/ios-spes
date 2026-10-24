# GPU comparison and ports — 2026-10-24

References fetched for this review:

- [Topaz e477291](https://github.com/MakrSas/ios-topaz/tree/e477291): newest commits
  add display modes (0948), screen-buffer reserve (0949), and touch releases (0950).
- [HackiOS d82c64a](https://github.com/oosexgang/hackios-xnu-kernel/tree/d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c):
  MiniIOSurface.cpp, MiniIOMobileFramebuffer.cpp, RedwoodGPU.cpp and ADSP references.
- Installed EAGL source basis remains HackiOS userland
  906425b75e02b4f99eb5d7bb1ef7c9583472d772 with our attach-GPU patch.

User reports DeepSeek's frame-holding build behaves as described: fewer black
frames, still slow. The reported image prefix is ba0b4e51; this review did not
independently identify that image from the phone. The reviewed local baseline
was e5f5c6e/e13f3f4, followed by the independent audio checkpoint d56ecfd.

## Findings, evidence, and implementation

### GPU still runs at its initial diagnostic rate

Our 0098 writes GPUCC GFX CFG 0: source CXO, divider 1, 19.2 MHz. The saved
`research/spes-eagl-fence-boot.txt` confirms cfg=0 after update. This is an
observed configuration, not an inference from frame rate. Topaz defaults to
GPLL0 / 2 (nominal 300 MHz); its optional higher frequencies use a GPU PLL.

0107 ports only the 300 MHz parent selection: GCC 0x79004 bit 15, GFX CFG
0x503 (source 5, HID divider 3), update and readback/root-running checks. The
local stock gpucc-khaje.c independently confirms source 5 is GPLL0 and the
GFX command register is 0x101c. No PLL retuning or high-rate voltage settings
are imported. `spesgpu_mhz=300` explicitly opts in; 19 keeps the original
19.2 MHz path. Unsupported values stop startup. The UI builder selects 300;
`SPES_GPU_MHZ=19` remains the comparison/recovery option. The clock selection
is not a measured frequency and hardware stability at this setting is pending.
This is a 15.625-fold nominal clock difference, not a promised FPS multiplier.

### CoreAnimation has no published display mode

Our vsync timer can run at 60 Hz while selector 79/current mode and
TimingElements/ColorElements are missing. Topaz 0948 documents a 50 ms frame
cadence with these absent. 0106 ports the mode properties and current-mode
block 0x40, with bounds checks for inline and descriptor outputs. The UI builder
now defaults to the user's tested six cores and 60 Hz instead of silently
reverting to one core and 10 Hz. Overrides remain available.

### Surface creation ignores caller-owned pixel memory

HackiOS MiniIOSurface::create recognizes IOSurfaceAddress and wires that exact
client range. Our create path ignored the property and allocated zeroed memory.
Selector 6 wrapping existed, but is a separate API and cannot fix this omission.
This can explain missing picture/layer contents; whether the missing home-screen
icons use this path must be established by the next boot's new log lines.

0104 implements dictionary-address wrapping, preserves exact supplied lengths,
tries writable then read-only wiring, and rejects unsupported address-range lists
rather than silently making blank pictures. It also records/retains the owning
task: another process now gets its own mapping instead of receiving the owner's
virtual address. Existing selector 6 wrappers retain their page-prefix handling.
Wrapped surfaces still use EAGL's CPU upload fallback; this does not expose
unaligned client pictures directly to GPU writes.

### GPU waits block the display timer and surface IDs are looked up too late

The current frame-holding fix waits up to 500 ms per layer inside the vsync
callback. It also allows a producer to replace a pending record after one second;
the previous callback can then clear fDirty for that newer record. Only IDs are
stored, so objects may disappear before presentation. HackiOS retains the actual
surfaces at submission and uses a separate presenter with a bounded queue.

0105 uses a dedicated presenter and retained surface pointers. The producer
sleeps on a wait event; timeout drops the incoming frame without replacing a
frame already being presented. Vsync only schedules the worker, not GPU waits.
Power-off and the retry limit release retained frames; incomplete pixels remain
unshown. Panel copying and fade-out are serialized, but GPU waiting holds no
framebuffer lock. Existing safe frame holding is preserved.

## Differences intentionally not copied

- Topaz 0949 reserves physically contiguous buffers because its GPU path uses
  identity mappings. spes has tested page-table mapping of noncontiguous buffers.
  A 120 MiB contiguous reserve is not a general cure for its upload cost.
- Topaz's higher-rate PLL options explicitly lack GX voltage voting. They are
  not included in this change.
- HackiOS's EAGL already supplies more shader/blur support than Topaz's current
  older fork. Wholesale replacement would remove those handlers. Our BGRA
  subimage refill and GPU attach blit already address the shared allocation cost.
- Wrapped client surfaces are rejected for direct GPU import in HackiOS too.
  Removing that guard without handling layout, offset and ownership is not an
  icons fix.
- Both upstreams still copy/scale frames to a boot framebuffer. No evidence here
  establishes hardware scanout, a fully native Apple GPU stack, or a measured
  frame-rate equivalence between these different phones.

## Validation and pending hardware work

All three reconstructed surface/framebuffer patches apply in order. Host tests
execute the actual handoff functions with pending GPU work, missing surface IDs,
producer timeout, power-off and retry exhaustion under ASan/UBSan. Local arm64
syntax checks cover SweetSurface, SweetFramebuffer, RedwoodGPU and sweet_touch.
Logs are under research/gpu-comparison/. CI and the hardware result belong in
NOTES.md when available. No updated userspace library or userdata write is
required for these kernel ports. Check for the selected-clock and modes logs,
client-memory creation logs, icons/wallpaper correctness, and frame times.
