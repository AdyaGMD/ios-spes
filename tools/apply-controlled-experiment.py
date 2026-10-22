#!/usr/bin/env python3
import sys
from pathlib import Path

def main():
    patch_path = Path("/Users/adya/Documents/iospes/xnu/patches/0098-spes-glink-rpm-transport.patch")
    lines = patch_path.read_text().splitlines(keepends=True)

    hunk2_idx = None
    hunk3_idx = None
    for idx, l in enumerate(lines):
        if l.startswith("@@ -677,6"):
            hunk2_idx = idx
        elif l.startswith("@@ -704,6"):
            hunk3_idx = idx
            break

    assert hunk2_idx is not None, "Hunk 2 not found"
    assert hunk3_idx is not None, "Hunk 3 not found"

    prefix = lines[:hunk2_idx]
    hunk2_lines = lines[hunk2_idx:hunk3_idx]
    suffix = lines[hunk3_idx:]

    # Insertion 1: Checkpoint 1 right after Step 12 (Line ~1496)
    # Target: printf("SPES GPU: 21b. GBIF_HALT=%#x INT0=%#x VBIF_RESET=%#x\n", gbif_halt, int0_status, vbif_reset);
    cp1_marker = '\tprintf("SPES GPU: 21b. GBIF_HALT=%#x INT0=%#x VBIF_RESET=%#x\\n",\n'
    cp1_idx = None
    for i, l in enumerate(hunk2_lines):
        if l == "+" + cp1_marker:
            cp1_idx = i + 2 # after the printf statement
            break
    assert cp1_idx is not None, "cp1_idx not found"

    # Insertion 2: Checkpoint 2 around `touch_wr(gpu, 0x2020u, 3u);` (Line ~1517)
    cp2_marker = '\ttouch_wr(gpu, 0x2020u, 3u); /* Hold SQE halted while programming memory. */\n'
    cp2_idx = None
    for i, l in enumerate(hunk2_lines):
        if l == "+" + cp2_marker:
            cp2_idx = i
            break
    assert cp2_idx is not None, "cp2_idx not found"

    # Modification 3: Checkpoint 3 & 4 (from `/* Checkpoint A: BEFORE CP_SQE_CNTL = 1 */` down to before ZAP allocation)
    # Target start: `/* Checkpoint A: BEFORE CP_SQE_CNTL = 1 */`
    # Target end: `/* Allocate contiguous buffer for ZAP MDT metadata (8 KiB) */`
    cp3_start_marker = '\t/* Checkpoint A: BEFORE CP_SQE_CNTL = 1 */\n'
    cp3_end_marker = '\t/* Allocate contiguous buffer for ZAP MDT metadata (8 KiB) */\n'

    cp3_start = None
    cp3_end = None
    for i, l in enumerate(hunk2_lines):
        if l == "+" + cp3_start_marker:
            cp3_start = i
        elif l == "+" + cp3_end_marker:
            cp3_end = i
            break

    assert cp3_start is not None, "cp3_start not found"
    assert cp3_end is not None, "cp3_end not found"

    print(f"cp1_idx: {cp1_idx}, cp2_idx: {cp2_idx}, cp3 range: {cp3_start}..{cp3_end}")

    rep_cp1 = """\tuint32_t cp1_hw_fault = touch_rd(gpu, 0x2084u);
\tuint32_t cp1_int_stat = touch_rd(gpu, 0x208cu);
\tuint32_t cp1_rbbm_int = touch_rd(gpu, 0x804u);
\tprintf("SPES GPU: 21c. Checkpoint 1 (GPU MMIO): fault=%#x int=%#x rbbm_int0=%#x\\n",
\t    cp1_hw_fault, cp1_int_stat, cp1_rbbm_int);
"""

    rep_cp2 = """\tuint32_t cp2a_hw_fault = touch_rd(gpu, 0x2084u);
\tuint32_t cp2a_int_stat = touch_rd(gpu, 0x208cu);
\tuint32_t cp2a_rbbm_int = touch_rd(gpu, 0x804u);
\ttouch_wr(gpu, 0x2020u, 3u); /* Hold SQE halted while programming memory. */
\t__asm__ volatile ("dsb sy" ::: "memory");
\tuint32_t cp2b_hw_fault = touch_rd(gpu, 0x2084u);
\tuint32_t cp2b_int_stat = touch_rd(gpu, 0x208cu);
\tuint32_t cp2b_rbbm_int = touch_rd(gpu, 0x804u);
\tprintf("SPES GPU: 22b. Checkpoint 2 (SQE halt 3): pre=[fault=%#x int=%#x int0=%#x] post=[fault=%#x int=%#x int0=%#x]\\n",
\t    cp2a_hw_fault, cp2a_int_stat, cp2a_rbbm_int,
\t    cp2b_hw_fault, cp2b_int_stat, cp2b_rbbm_int);
"""

    rep_cp3_and_4 = """\t/* Checkpoint 3: Before and after CP_SQE_CNTL = 1 */
\tuint32_t cp3a_fault = touch_rd(gpu, 0x2084u);
\tuint32_t cp3a_int   = touch_rd(gpu, 0x208cu);
\tuint32_t cp3a_int0  = touch_rd(gpu, 0x804u);
\tprintf("SPES GPU: 26d. Checkpoint 3 (SQE unhalt 1): pre=[fault=%#x int=%#x int0=%#x]\\n",
\t    cp3a_fault, cp3a_int, cp3a_int0);

\t/* Step 19: Un-halt CP SQE engine BEFORE submitting init */
\ttouch_wr(gpu, 0x2020u, 1u); /* CP_SQE_CNTL = 1 */
\t__asm__ volatile ("dsb sy" ::: "memory");
\ttouch_wait(10);

\tuint32_t cp3b_fault = touch_rd(gpu, 0x2084u);
\tuint32_t cp3b_int   = touch_rd(gpu, 0x208cu);
\tuint32_t cp3b_int0  = touch_rd(gpu, 0x804u);
\ttouch_wr(gpu, 0x2420u, 0u); uint32_t sqe_dbg0 = touch_rd(gpu, 0x2424u);
\ttouch_wr(gpu, 0x2420u, 1u); uint32_t sqe_dbg1 = touch_rd(gpu, 0x2424u);
\ttouch_wr(gpu, 0x2420u, 2u); uint32_t sqe_dbg2 = touch_rd(gpu, 0x2424u);
\ttouch_wr(gpu, 0x2420u, 3u); uint32_t sqe_dbg3 = touch_rd(gpu, 0x2424u);
\tuint32_t pre_rptr   = touch_rd(gpu, 0x2018u);
\tuint32_t pre_wptr   = touch_rd(gpu, 0x201cu);
\trbbm_status         = touch_rd(gpu, 0x840u);
\tprintf("SPES GPU: 26e. Post-unhalt 1: fault=%#x int=%#x int0=%#x rptr=%u wptr=%u rbbm=%#x\\n",
\t    cp3b_fault, cp3b_int, cp3b_int0, pre_rptr, pre_wptr, rbbm_status);
\tprintf("SPES GPU: 26f. SQE dbg0-3: %#x %#x %#x %#x\\n",
\t    sqe_dbg0, sqe_dbg1, sqe_dbg2, sqe_dbg3);

\t/* Halt safely only if a true hardware fault occurs */
\tif (cp3b_fault != 0) {
\t\ttouch_wr(gpu, 0x2020u, 3u); /* CP_SQE_CNTL = 3 */
\t\tprintf("SPES GPU: Hardware fault on unhalt; halted safely before packets\\n");
\t\treturn;
\t}

\t/* Step 20: Submit CP_ME_INIT & CP_MEM_WRITE (Linux upstream A6xx sequence) */
\tuint32_t w = 0;
\trb[w++] = 0x70c80008u; /* CP_ME_INIT (opcode 0x48, count 8) */
\trb[w++] = 0x0000002fu; /* ordinal 1: init mask */
\trb[w++] = 0x00000003u; /* ordinal 2: max contexts = 3 */
\trb[w++] = 0x20000000u; /* ordinal 3: error detection */
\trb[w++] = 0x00000000u; /* ordinal 4: header dump = 0 */
\trb[w++] = 0x00000000u; /* ordinal 5: reset state = 0 */
\trb[w++] = 0x00000000u; /* ordinal 6: ucode wa = 0 */
\trb[w++] = 0x00000000u; /* ordinal 7: pad = 0 */
\trb[w++] = 0x00000000u; /* ordinal 8: pad = 0 */

\trb[w++] = 0x703d8003u; /* CP_MEM_WRITE (opcode 0x3d, count 3) */
\trb[w++] = 0x10000000u; /* target address LO (mapped to scratch in Context 0) */
\trb[w++] = 0x00000000u; /* target address HI */
\trb[w++] = 0xcafe0001u; /* test payload */

\t/* CP_NOP padding to 16 dwords */
\twhile (w < 16) {
\t\trb[w++] = 0x70108000u; /* zero payload requires count parity bit 15 */
\t}
\t__asm__ volatile ("dsb sy" ::: "memory");

\ttouch_wr(gpu, 0x201cu, w); /* Kick WPTR */
\t__asm__ volatile ("dsb sy" ::: "memory");
\tprintf("SPES GPU: 27. Kick WPTR: wptr=%u\\n", w);

\t/* Bounded poll for RPTR advancement */
\tint poll_i;
\tbool rptr_adv = false;
\tuint32_t curr_rptr = 0;
\tfor (poll_i = 0; poll_i < 1000; poll_i++) {
\t\tcurr_rptr = touch_rd(gpu, 0x2018u);
\t\tif (curr_rptr > 0) {
\t\t\trptr_adv = true;
\t\t\tif (curr_rptr >= w) break;
\t\t}
\t\ttouch_wait(1);
\t}

\t/* Checkpoint 4: After submitting CP_ME_INIT and updating ringbuffer WPTR */
\tuint32_t cp4_fault = touch_rd(gpu, 0x2084u);
\tuint32_t cp4_int   = touch_rd(gpu, 0x208cu);
\tuint32_t cp4_int0  = touch_rd(gpu, 0x804u);
\trbbm_status        = touch_rd(gpu, 0x840u);
\tuint32_t scratch0  = scratch[0];

\tprintf("SPES GPU: 27b. Checkpoint 4 (Post-WPTR): rptr=%u / wptr=%u (adv=%d ok=%d poll=%d rbbm=%#x)\\n",
\t    curr_rptr, w, rptr_adv, (curr_rptr >= w), poll_i, rbbm_status);
\tprintf("SPES GPU: 27c. Post-WPTR diag: fault=%#x int=%#x int0=%#x scratch0=%#x\\n",
\t    cp4_fault, cp4_int, cp4_int0, scratch0);
\tprintf("SPES GPU: 27d. SMMU: GFSR=%#x FSR=%#x FSYNR=%#x FAR=%#x:%#x\\n",
\t    touch_rd(smmu, 0x48u), touch_rd(smmu, context + 0x58u),
\t    touch_rd(smmu, context + 0x68u), touch_rd(smmu, context + 0x64u),
\t    touch_rd(smmu, context + 0x60u));

\t/* Halt safely; do not proceed to ZAP or rendering */
\ttouch_wr(gpu, 0x2020u, 3u); /* CP_SQE_CNTL = 3 */
\tif (rptr_adv && curr_rptr >= w && cp4_fault == 0) {
\t\tprintf("SPES GPU: 28. SILICON VERIFIED: Ringbuffer retired %u packets! scratch0=%#x (halted safely)\\n",
\t\t    curr_rptr, scratch0);
\t} else {
\t\tprintf("SPES GPU: 28. STOPPED: rptr=%u wptr=%u fault=%#x scratch0=%#x (halted safely)\\n",
\t\t    curr_rptr, w, cp4_fault, scratch0);
\t}
\treturn;
"""

    rep1_lines = ["+" + line + "\n" if line.strip() else "+\n" for line in rep_cp1.splitlines()]
    rep2_lines = ["+" + line + "\n" if line.strip() else "+\n" for line in rep_cp2.splitlines()]
    rep3_lines = ["+" + line + "\n" if line.strip() else "+\n" for line in rep_cp3_and_4.splitlines()]

    # Apply rep3 first (highest index), then rep2, then rep1
    new_hunk2 = hunk2_lines[:cp3_start] + rep3_lines + hunk2_lines[cp3_end:]
    new_hunk2 = new_hunk2[:cp2_idx] + rep2_lines + new_hunk2[cp2_idx + 1:]
    new_hunk2 = new_hunk2[:cp1_idx] + rep1_lines + new_hunk2[cp1_idx:]

    # Recalculate Hunk 2 line counts
    h2_added = sum(1 for l in new_hunk2[1:] if l.startswith('+'))
    h2_context = sum(1 for l in new_hunk2[1:] if l.startswith(' ') or l == '\n')
    new_h2_count = h2_added + h2_context
    new_hunk2[0] = f"@@ -677,6 +684,{new_h2_count} @@ spes_gpu_power_probe(void)\n"
    print(f"New Hunk 2 count: {new_h2_count} (added={h2_added}, context={h2_context})")

    # Fix Hunk 3 header
    hunk3_new_start = 684 + new_h2_count + (704 - (677 + 6))
    suffix[0] = f"@@ -704,6 +{hunk3_new_start},7 @@ touch_thread(void *arg, wait_result_t result)\n"
    print(f"New Hunk 3 header: {suffix[0].strip()}")

    # Write back
    new_content = "".join(prefix + new_hunk2 + suffix)
    patch_path.write_text(new_content)
    print("Patch updated successfully.")

if __name__ == "__main__":
    main()
