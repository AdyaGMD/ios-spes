# Review of stalled Stage 5 diagnostics

The supplied photo shows CP_INTERRUPT_STATUS=0x80 immediately after SQE
release, with WPTR=0, before any packets. Later RPTR remains zero and the
scratch/fence retain 0xdeadbeef. The unconditional success messages are false.
The photo predates the current page-table implementation: SQE base is physical
0x5ca00000 rather than current IOVA0x01100000. Do not merge observations from
these different images into one supposedly verified sequence.

## Evidence versus hypotheses

The pinned phone driver `a6xx_reg.h` defines CP_ILLEGAL_INSTR_ERROR as bit7.
This is a microengine error, not a unique diagnosis of SMMU translation failure.
A blocked/corrupt fetch is a candidate; it needs fault registers and routing
readback. No root cause is proven solely by int=0x80.

Earlier NOTES claims that bypass necessarily requires stage2 support and that
SMR VALID acts as a universal S2CR write lock are not established by the cited
code. The pinned Linux driver supports BYPASS and updates S2CR before SMR.
Do not base further writes on these claims without platform evidence.

## Confirmed defects fixed

- SMMU/memory path clocks were not explicitly enabled/checked. Enable the
  Khaje GPU SMMU vote and GCC MEMNOC/SNOC clocks and wait for running status.
- RCG polling tested ROOT_EN bit1 instead of UPDATE bit0, reporting false failure.
- SQE status used byte offsets0x2094/0x2098 (CP_STATUS_1 and adjacent space)
  instead of0x2420/0x2424 (dword0x908/0x909).
- The claimed CP_INT_ACK at0x2090 is CP_PROTECT_STATUS. Remove that write and
  the undocumented write to CP_INTERRUPT_STATUS.
- SMR0 mask1 overlapped exact SMR1 SID1. Use exact, nonoverlapping matches.
- Current framebuffer/DMA tables used the wrong L1/L2 indexes. Put addresses
  above1GiB under L1[1], L2[224]/[229]. Restrict DMA identity mapping to64KiB.
- Zero-length CP_NOP0x70100000 lacks count parity; use0x70108000. This is a
  later packet bug, not an explanation for the photographed pre-packet fault.
- CP_ME_INIT requested a register list at NULL. Omit the list bit; preserve
  header-dump/workaround slots and set operation mode2.
- Halt/return on early SQE errors or failed ME_INIT. Require routing, context
  enable and TLB sync readback before SQE release. No ZAP/render after failure.
- Remove unconditional GPU/subsystem success and unrelated GPIO/audio/DSI work.

Embedded SQE bytes were compared with the original handset firmware and match
exactly after the required four-byte skip. A wrong embedded firmware copy is
not supported by this check.

## Validation

The two new tests compile the actual C table/packet construction extracted from
the tracked patch. An independent page walker and PM4 parity/boundary decoder
both fail on the prior HEAD (unmapped framebuffer; bad NOP at word14), and both
pass after the fix. All17 host tests pass. Full patch-stack application to
sweet_touch.c succeeds. Kernel build and hardware outcome must be recorded
separately; none of these host checks establishes working GPU execution.

References: pinned Jabiyeff/kernel_xiaomi_sm6225 commit
6c2b3e7528a0778cd80c95eabb490746b5422f8c, drivers/gpu/msm/a6xx_reg.h,
adreno_pm4types.h, adreno_a6xx.c; drivers/clk/qcom/gpucc-khaje.c,
gcc-khaje.c; drivers/iommu/arm-smmu.c.
