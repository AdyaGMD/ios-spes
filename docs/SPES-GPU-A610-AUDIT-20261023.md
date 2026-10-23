# A610 startup comparison — 2026-10-23

Scope: read-only driver audit requested via the pasted GPT suggestion. Baseline
is HEAD e80d78a plus the existing uncommitted immediate-polling changes in
0098 and its generator. No kernel change or handset operation in this audit.
The active bring-up function is `spes_glink_rpm_probe`, not the older
`spes_gpu_power_probe` inventory function.

## Sources and units

- [Pinned upstream a6xx_gpu.c](https://github.com/torvalds/linux/blob/94426e4201fbb1c5ea4a697eb62a8b7cd7dfccbf/drivers/gpu/drm/msm/adreno/a6xx_gpu.c):
  `hw_init`, `a6xx_cp_init`, `a6xx_gpu_sw_reset`.
- [A610 introduction](https://lkml.indiana.edu/hypermail/linux/kernel/2304.0/00149.html).
- [Phone downstream register definitions](https://github.com/Jabiyeff/kernel_xiaomi_sm6225/blob/6c2b3e7528a0778cd80c95eabb490746b5422f8c/drivers/gpu/msm/a6xx_reg.h),
  locally `research/spes-gpu-linux/a6xx_reg.h`; companion `adreno_a6xx.c`
  and `adreno-gpulist.h` give startup and A610 capability selection.

Linux register constants are DWORD indexes. `touch_wr` takes BYTE offsets.
All offsets below are bytes relative to GPU base 0x05900000. Do not apply
these offsets to GPUCC or GMU apertures.

## Definite address mismatches in current 0098

| Intended register | Current byte offset | Correct byte offset | Consequence |
| --- | ---: | ---: | --- |
| GBIF_HALT | 0x0004 | 0xf114 | Current code does not clear GBIF halt |
| PC_DBG_ECO_CNTL | 0x27808 | 0x27800 | A610 primitive FIFO setup misses its target |
| RBBM_PERFCTR_CNTL | 0x0400 | 0x1400 | Counter enable misses target |
| RBBM_PERFCTR_GPU_BUSY_MASKED | 0x0508 | 0x142c | Busy mask misses target |
| UCHE_TRAP_BASE_LO/HI | 0x381c/20 | 0x3824/28 | Labels swapped with WRITE_THRU; same values currently make this harmless |
| UCHE_WRITE_THRU_BASE_LO/HI | 0x3824/28 | 0x381c/20 | Same swapped labels |
| UCHE_FILTER_CNTL | 0x382c | 0x3860 | Writes GMEM_RANGE_MIN_LO instead of filter |
| RBBM_INT_0_MASK | 0x0808 | 0x00e0 | Interrupt masking misses target |

These are source-level defects, NOT proof of the cause of early int=0x80.
Only the GBIF write above executes before the reported early-halt failure.
RBBM_GBIF_HALT at 0x58 is a separate register and is correct; the existing
21b log reads that register, not GBIF_HALT, so it cannot validate both.

Correct checked offsets include CP_SQE_CNTL 0x2020, CP_INTERRUPT_STATUS
0x208c, CP_HW_FAULT 0x2084, SQE base 0x20c0/4, ROQ 0x2304/8,
MEM_POOL_SIZE 0x230c, MEM_POOL_DBG_ADDR 0x2438, AHB 0x2634,
GBIF_QSB_SIDE0..3 0xf00c..18, QoS 0x44, UCHE_CACHE_WAYS 0x385c,
RBBM_INT_CLEAR_CMD 0xdc, and trusted-base/size 0x3e000..8.

## Startup ordering and missing initialization

Upstream `hw_init` does the following, after platform power and memory setup:

1. Clear GBIF_HALT then RBBM_GBIF_HALT, with readbacks.
2. Clear SECVID_TSB_CNTL (0x3e00c), trusted base/size; set 64-bit modes.
3. Apply hardware clock-gating configuration, GBIF QoS, UCHE ranges/filter/cache.
4. Apply A610 ROQ limits, memory pool, PC FIFO threshold; AHB error response,
   performance counters, UBWC configuration, hang detection and UCHE prefetch.
5. Set CP register protections; use expanded APRIV only on supported hardware.
6. Set interrupt mask; perform common Adreno initialization.
7. Program SQE base and ring base/control/shadow; initialize ring state.
8. Write SQE_CNTL=1, submit ME_INIT, and require retirement/idle.
9. Load ZAP, issue SET_SECURE_MODE(0), and require retirement again.

Current probe includes many steps but omits explicit SECVID_TSB_CNTL clearing,
HWCG table programming, proper GMEM range setup, UBWC, hang counter, UCHE
prefetch and CP protection setup. Treat these as gaps relative to the complete
Linux driver, not as independently demonstrated requirements for ME_INIT.
Do not blindly copy GMU-register operations: upstream wraps platform-specific
power machinery; our RPM/GPUCC path needs its own review.

ROQ values 0x40201b16/0x00800060, pool 48/debug index 47, and intended PC FIFO
value 0x00080000 already agree. A610 selects the A612 HWCG table and uses
132 KiB GMEM in the downstream device description.

The unconditional APRIV=0x6e is unsupported by the phone driver's A610 feature
selection. Downstream guards this write with ADRENO_APRIV, absent for A610;
upstream also gates it on hardware capability. Ring bit 27 means NO_UPDATE
(disable automatic RPTR shadow updates), not a general NO_APRIV mode.

The probe's early SQE_CNTL=3 has no counterpart in upstream normal `hw_init`.
Upstream does write 3 in recovery. That difference warrants a controlled test;
it does not establish that writing 3 with an unset firmware base is illegal.
The A610 software-reset exception is explicit in `a6xx_gpu_sw_reset`; do not
add RBBM_SW_RESET_CMD cycles as a speculative cure. This is separate from
external power-domain control and does not authorize deleting all GPUCC setup.

## What the reported trace establishes

The pasted conversation reports clean status before/just after halt, then
0x80 on a later sample. Bit 7 is CP_ILLEGAL_INSTR_ERROR in the phone header.
It is already set before this probe programs the SMMU, firmware base or ring.
Thus changing ME_INIT contents cannot explain that particular onset.

Timing alone does not distinguish a halt-induced fault from delayed visibility
of a previous fault. Console printing changes the sampling interval. The pending
polling change improves capture timing but has no equally delayed no-write
control. Its `flip_at=0` also means either no transition or an already-bad first
sample; interpret sample 0, not the summary alone. A tight loop's time is not
calibrated merely because a comment estimates milliseconds.

Absence of SMMU fault bits is not proof that fetch/translation works. Verify
actual stream routing, context, translation tables and retirement separately.
Older NOTES entries claiming the root cause is solved are historical hypotheses.

## Smallest useful command test

Current ME_INIT exactly matches upstream `a6xx_cp_init`: opcode 0x48, eight
payload words `[0x2f, 3, 0x20000000, 0, 0, 0, 0, 0]`. Keep it. Require RPTR
advance to submitted WPTR and no new faults before moving on. Then ZAP and
secure-mode transition, followed by one mapped MEM_WRITE and sentinel readback.
Do not include a draw or framebuffer overwrite until that works. CPU heartbeat,
RBBM idle, successful ZAP authentication, or firmware CPU readback alone does
not demonstrate command execution.

## Pending build defect and next experiment

Four printf strings in the uncommitted immediate-polling patch contain literal
newlines inside C string literals (around lines 1672–1689). They will not compile.
The generator is also dirty. Preserve both edits and fix escaping at the source
before producing a new image; update patch hunk lengths after any change.
The existing host tests extract only table/packet fragments and cannot validate
these strings or MMIO addresses.

Recommended staged implementation, not performed in this audit:

1. Correct the verified address mismatches and unsupported APRIV write; retain
   provenance and add independent register-address checks. Fix generator/string
   syntax. Do not combine this with reset, SMMU routing or firmware changes.
2. Before full startup, use equal-duration buffered sampling before and after
   halt, with an alternate no-write control, recording the initial SQE control
   and firmware base. Both diagnostic paths must stop before memory setup or
   command submission. Do not silently continue initialization after a fault.
3. Compare fresh temporary boots with identical delays and known build hashes.
   If the no-write control faults too, stop blaming the halt and inspect power/
   clock/handoff state. If only the write case faults, remove early halt from
   the normal-startup candidate and validate the Linux ordering separately.
4. Restore strict routing, fault and retirement gates before further submission;
   the current post-unhalt check tests HW_FAULT only, ignoring CP interrupt 0x80.
5. Fill the remaining A610 initialization gaps in reviewable groups, then test
   ME_INIT → secure transition → MEM_WRITE before rendering.

No CI run, boot, or hardware success is claimed by this document.
