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

    # Target: from `/* Step 20: Submit CP_ME_INIT` down to `/* Allocate contiguous buffer for ZAP MDT metadata (8 KiB) */`
    target_start_marker = "\t/* Step 20: Submit CP_ME_INIT"
    target_end_marker = '\t/* Allocate contiguous buffer for ZAP MDT metadata (8 KiB) */\n'

    start_idx = None
    end_idx = None
    for i, l in enumerate(hunk2_lines):
        if l.startswith("+" + target_start_marker):
            start_idx = i
        elif l == "+" + target_end_marker:
            end_idx = i
            break

    assert start_idx is not None, "target_start_marker not found"
    assert end_idx is not None, "target_end_marker not found"

    print(f"target range: {start_idx}..{end_idx}")

    rep_two_stages = """\t/* Step 20: Submit CP_ME_INIT (Linux upstream A6xx sequence) */
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

\t/* CP_NOP padding to 16 dwords */
\twhile (w < 16) {
\t\trb[w++] = 0x70108000u; /* zero payload requires count parity bit 15 */
\t}
\t__asm__ volatile ("dsb sy" ::: "memory");

\t/* Kick WPTR for Test 1: CP_ME_INIT */
\ttouch_wr(gpu, 0x201cu, w);
\t__asm__ volatile ("dsb sy" ::: "memory");
\tprintf("SPES GPU: 27. Test 1: CP_ME_INIT submitted (wptr=%u)\\n", w);

\t/* Bounded poll for CP_ME_INIT retirement */
\tint poll_init;
\tbool init_adv = false;
\tuint32_t rptr_init = 0;
\tfor (poll_init = 0; poll_init < 1000; poll_init++) {
\t\trptr_init = touch_rd(gpu, 0x2018u);
\t\tif (rptr_init > 0) {
\t\t\tinit_adv = true;
\t\t\tif (rptr_init >= w) break;
\t\t}
\t\ttouch_wait(1);
\t}

\t/* Checkpoint 4A: CP_ME_INIT results */
\tuint32_t cp4a_fault = touch_rd(gpu, 0x2084u);
\tuint32_t cp4a_int   = touch_rd(gpu, 0x208cu);
\tuint32_t cp4a_int0  = touch_rd(gpu, 0x804u);
\trbbm_status         = touch_rd(gpu, 0x840u);
\tuint32_t smmu_gfsr  = touch_rd(smmu, 0x48u);
\tuint32_t smmu_fsr   = touch_rd(smmu, context + 0x58u);

\tprintf("SPES GPU: 27b. Checkpoint 4A (CP_ME_INIT): rptr=%u / wptr=%u (adv=%d ok=%d poll=%d rbbm=%#x)\\n",
\t    rptr_init, w, init_adv, (rptr_init >= w), poll_init, rbbm_status);
\tprintf("SPES GPU: 27c. Checkpoint 4A diag: fault=%#x int=%#x int0=%#x GFSR=%#x FSR=%#x\\n",
\t    cp4a_fault, cp4a_int, cp4a_int0, smmu_gfsr, smmu_fsr);

\t/* Verify Stage A success before attempting Stage B (CP_MEM_WRITE) */
\tif (!init_adv || rptr_init < w || cp4a_fault != 0 || (smmu_gfsr != 0)) {
\t\ttouch_wr(gpu, 0x2020u, 3u); /* CP_SQE_CNTL = 3 (halt SQE) */
\t\tprintf("SPES GPU: 27d. Test 1 (CP_ME_INIT) FAILED; halted safely, skipping MEM_WRITE\\n");
\t\treturn;
\t}
\tprintf("SPES GPU: 27d. Test 1 (CP_ME_INIT) PASSED! SQE alive and taking commands.\\n");

\t/* Test 2: Submit CP_MEM_WRITE to scratch buffer */
\tuint32_t w2 = w;
\trb[w2++] = 0x703d8003u; /* CP_MEM_WRITE (opcode 0x3d, count 3) */
\trb[w2++] = 0x10000000u; /* target address LO (mapped to scratch[0] in Context 0) */
\trb[w2++] = 0x00000000u; /* target address HI */
\trb[w2++] = 0xcafe0001u; /* test payload */

\t/* CP_NOP padding to 32 dwords */
\twhile (w2 < 32) {
\t\trb[w2++] = 0x70108000u;
\t}
\t__asm__ volatile ("dsb sy" ::: "memory");

\t/* Kick WPTR for Test 2: CP_MEM_WRITE */
\ttouch_wr(gpu, 0x201cu, w2);
\t__asm__ volatile ("dsb sy" ::: "memory");
\tprintf("SPES GPU: 28. Test 2: CP_MEM_WRITE submitted (wptr=%u)\\n", w2);

\t/* Bounded poll for CP_MEM_WRITE retirement */
\tint poll_mem;
\tbool mem_adv = false;
\tuint32_t rptr_mem = 0;
\tfor (poll_mem = 0; poll_mem < 1000; poll_mem++) {
\t\trptr_mem = touch_rd(gpu, 0x2018u);
\t\tif (rptr_mem > w) {
\t\t\tmem_adv = true;
\t\t\tif (rptr_mem >= w2) break;
\t\t}
\t\ttouch_wait(1);
\t}

\t/* Checkpoint 4B: CP_MEM_WRITE results */
\tuint32_t cp4b_fault = touch_rd(gpu, 0x2084u);
\tuint32_t cp4b_int   = touch_rd(gpu, 0x208cu);
\tuint32_t cp4b_int0  = touch_rd(gpu, 0x804u);
\trbbm_status         = touch_rd(gpu, 0x840u);
\t__asm__ volatile ("dsb sy" ::: "memory");
\tuint32_t scratch0   = scratch[0];
\tint scratch_match   = (scratch0 == 0xcafe0001u);

\tprintf("SPES GPU: 28b. Checkpoint 4B (MEM_WRITE): rptr=%u / wptr=%u (adv=%d ok=%d poll=%d rbbm=%#x)\\n",
\t    rptr_mem, w2, mem_adv, (rptr_mem >= w2), poll_mem, rbbm_status);
\tprintf("SPES GPU: 28c. Checkpoint 4B diag: fault=%#x int=%#x int0=%#x scratch0=%#x (match=%d)\\n",
\t    cp4b_fault, cp4b_int, cp4b_int0, scratch0, scratch_match);

\t/* Halt safely; do not proceed to ZAP or rendering */
\ttouch_wr(gpu, 0x2020u, 3u); /* CP_SQE_CNTL = 3 */
\tif (mem_adv && rptr_mem >= w2 && cp4b_fault == 0 && scratch_match) {
\t\tprintf("SPES GPU: 29. SILICON VERIFIED: SQE init + memory write 100%% SUCCESS! (halted safely)\\n");
\t} else {
\t\tprintf("SPES GPU: 29. STOPPED: rptr=%u wptr=%u match=%d (halted safely)\\n",
\t\t    rptr_mem, w2, scratch_match);
\t}
\treturn;
"""

    rep_lines = ["+" + line + "\n" if line.strip() else "+\n" for line in rep_two_stages.splitlines()]

    new_hunk2 = hunk2_lines[:start_idx] + rep_lines + hunk2_lines[end_idx:]

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
