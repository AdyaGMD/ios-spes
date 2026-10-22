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

    t1_start_marker = "\tuint32_t s2cr0 = touch_rd(smmu, 0xc00u);\n"
    t1_end_marker = '\t\tprintf("SPES GPU: SMMU CB0 enable/sync failed; stopping BEFORE SQE\\n");\n'

    t1_start = None
    t1_end = None
    for i, l in enumerate(hunk2_lines):
        if l == "+" + t1_start_marker:
            t1_start = i
        elif l == "+" + t1_end_marker:
            # l is printf, i+1 is return;, i+2 is }
            assert hunk2_lines[i+1] == "+\t\treturn;\n"
            assert hunk2_lines[i+2] == "+\t}\n"
            t1_end = i + 2
            break

    assert t1_start is not None, "t1_start not found"
    assert t1_end is not None, "t1_end not found"

    t2_start_marker = '\tprintf("SPES GPU: 26. SQE ucode (%lu bytes) at pa=%#llx va=%#lx rb_pa=%#llx\\n",\n'
    t2_end_marker = '\t\tprintf("SPES GPU: SQE fetch/start fault BEFORE packets; halted, no ZAP or render\\n");\n'

    t2_start = None
    t2_end = None
    for i, l in enumerate(hunk2_lines):
        if l == "+" + t2_start_marker:
            t2_start = i
        elif l == "+" + t2_end_marker:
            # l is printf, i+1 is return;, i+2 is }
            assert hunk2_lines[i+1] == "+\t\treturn;\n"
            assert hunk2_lines[i+2] == "+\t}\n"
            t2_end = i + 2
            break

    assert t2_start is not None, "t2_start not found"
    assert t2_end is not None, "t2_end not found"

    print(f"t1 range: {t1_start}..{t1_end} (lines {hunk2_idx + t1_start + 1}..{hunk2_idx + t1_end + 1})")
    print(f"t2 range: {t2_start}..{t2_end} (lines {hunk2_idx + t2_start + 1}..{hunk2_idx + t2_end + 1})")

    rep1 = """\tuint32_t smr0_rb  = touch_rd(smmu, 0x800u);
\tuint32_t s2cr0_rb = touch_rd(smmu, 0xc00u);
\tuint32_t smr2_rb  = touch_rd(smmu, 0x808u);
\tuint32_t s2cr2_rb = touch_rd(smmu, 0xc08u);
\tuint32_t s2cr0_type = (s2cr0_rb >> 16) & 3u;
\tuint32_t s2cr0_cb   = s2cr0_rb & 0xffu;
\tuint32_t s2cr0_sh   = (s2cr0_rb >> 8) & 3u;

\tuint32_t hw_sctlr    = touch_rd(smmu, context + 0x00u);
\tuint32_t hw_ttbr0_lo = touch_rd(smmu, context + 0x20u);
\tuint32_t hw_ttbr0_hi = touch_rd(smmu, context + 0x24u);
\tuint64_t hw_ttbr0    = ((uint64_t)hw_ttbr0_hi << 32) | hw_ttbr0_lo;
\tuint32_t hw_tcr      = touch_rd(smmu, context + 0x30u);
\tuint32_t hw_tcr2     = touch_rd(smmu, context + 0x10u);
\tuint32_t hw_mair0    = touch_rd(smmu, context + 0x38u);
\tuint32_t hw_mair1    = touch_rd(smmu, context + 0x3cu);
\tuint32_t hw_cbar0    = touch_rd(smmu, stride + 0x00u);
\tuint32_t hw_cba2r0   = touch_rd(smmu, stride + 0x800u);

\tprintf("SPES GPU: 23f. SMR0=%#x S2CR0=%#x (type=%u cb=%u sh=%u) SMR2=%#x S2CR2=%#x\\n",
\t    smr0_rb, s2cr0_rb, s2cr0_type, s2cr0_cb, s2cr0_sh, smr2_rb, s2cr2_rb);
\tprintf("SPES GPU: 23f2. CB0: SCTLR=%#x TTBR0=%#llx (lo=%#x hi=%#x pt_pa=%#llx)\\n",
\t    hw_sctlr, hw_ttbr0, hw_ttbr0_lo, hw_ttbr0_hi, pt_pa);
\tprintf("SPES GPU: 23f3. TCR=%#x TCR2=%#x MAIR=%#x:%#x CBAR0=%#x CBA2R0=%#x\\n",
\t    hw_tcr, hw_tcr2, hw_mair1, hw_mair0, hw_cbar0, hw_cba2r0);
\tprintf("SPES GPU: 23g. PTE 0x01100000: L1[0]=%#llx L2[8]=%#llx L3[256]=%#llx (pa=%#llx)\\n",
\t    l1[0], l2[8], l3_core[256], (l3_core[256] & ~0xfffull));

\tif (s2cr0_type == 2u || s2cr0_cb == 0xffu) {
\t\tprintf("SPES GPU: S2CR0 stuck in FAULT (raw=%#x type=%u cb=%u); stopping BEFORE SQE\\n",
\t\t    s2cr0_rb, s2cr0_type, s2cr0_cb);
\t\treturn;
\t}

\tif (!(hw_sctlr & 1u) || (touch_rd(smmu, context + 0x7f4u) & 1u)) {
\t\tprintf("SPES GPU: SMMU CB0 enable/sync failed; stopping BEFORE SQE\\n");
\t\treturn;
\t}"""

    rep2 = """\tunsigned sqe_err = 0;
\tfor (unsigned si = 0; si < sizeof(a630_sqe_fw) / sizeof(uint32_t); si++) {
\t\tif (sqe_dst[si] != a630_sqe_fw[si]) {
\t\t\tsqe_err++;
\t\t}
\t}
\tprintf("SPES GPU: 26. SQE mem (%lu B): err=%u d0-3=%#x %#x %#x %#x\\n",
\t    sizeof(a630_sqe_fw), sqe_err, sqe_dst[0], sqe_dst[1], sqe_dst[2], sqe_dst[3]);
\tprintf("SPES GPU: 26b. SQE mem d4-7=%#x %#x %#x %#x (match=%d)\\n",
\t    sqe_dst[4], sqe_dst[5], sqe_dst[6], sqe_dst[7], (sqe_err == 0));

\t/* Point SQE instruction base to 0x01100000 (mapped to sqe_pa in Context 0!) */
\ttouch_wr(gpu, 0x20c0u, 0x01100000u);           /* CP_SQE_INSTR_BASE_LO */
\ttouch_wr(gpu, 0x20c4u, 0x00000000u);           /* CP_SQE_INSTR_BASE_HI */
\t__asm__ volatile ("dsb sy" ::: "memory");
\tuint32_t base_lo = touch_rd(gpu, 0x20c0u);
\tuint32_t base_hi = touch_rd(gpu, 0x20c4u);
\tprintf("SPES GPU: 26c. CP_SQE_INSTR_BASE=%#x:%#x (match=%d)\\n",
\t    base_hi, base_lo, (base_lo == 0x01100000u && base_hi == 0u));

\t/* Program Ringbuffer registers: ring at 0x01000000, RPTR scratch at 0x011f0000 */
\ttouch_wr(gpu, 0x2000u, 0x01000000u);           /* CP_RB_BASE_LO */
\ttouch_wr(gpu, 0x2004u, 0x00000000u);           /* CP_RB_BASE_HI */
\ttouch_wr(gpu, 0x2008u, 0x0800020au);           /* CP_RB_CNTL (8K ring, 32B block, bit 27 = NO_APRIV) */
\ttouch_wr(gpu, 0x2010u, 0x011f0000u);           /* CP_RB_RPTR_ADDR_LO */
\ttouch_wr(gpu, 0x2014u, 0x00000000u);           /* CP_RB_RPTR_ADDR_HI */
\ttouch_wr(gpu, 0x2018u, 0u);                    /* CP_RB_RPTR */
\ttouch_wr(gpu, 0x201cu, 0u);                    /* CP_RB_WPTR */
\ttouch_wr(gpu, 0x2214u, 0u);                    /* CP_SCRATCH(2) */
\t/* 0x2090 is CP_PROTECT_STATUS, NOT CP_INT_ACK. Do not write it. */
\ttouch_wr(gpu, 0x2110u, (1u << 6) | (1u << 5) | (1u << 3) | (1u << 2) | (1u << 1)); /* CP_APRIV_CNTL = 0x6e */
\t__asm__ volatile ("dsb sy" ::: "memory");

\t/* Checkpoint A: BEFORE CP_SQE_CNTL = 1 */
\tuint32_t pre_fault = touch_rd(gpu, 0x2084u); /* CP_HW_FAULT */
\tuint32_t pre_int   = touch_rd(gpu, 0x208cu); /* CP_INTERRUPT_STATUS */
\tprintf("SPES GPU: 26d. Pre-SQE: fault=%#x int=%#x (illegal=%d)\\n",
\t    pre_fault, pre_int, ((pre_int & 0x80u) != 0));

\t/* Step 19: Un-halt CP SQE engine BEFORE submitting init */
\ttouch_wr(gpu, 0x2020u, 1u); /* CP_SQE_CNTL = 1 */
\t__asm__ volatile ("dsb sy" ::: "memory");
\ttouch_wait(10);

\t/* Checkpoint B: Immediately AFTER CP_SQE_CNTL = 1 */
\tuint32_t cp_hw_fault = touch_rd(gpu, 0x2084u);
\tuint32_t cp_int_stat = touch_rd(gpu, 0x208cu);
\ttouch_wr(gpu, 0x2420u, 0u); uint32_t sqe_dbg0 = touch_rd(gpu, 0x2424u);
\ttouch_wr(gpu, 0x2420u, 1u); uint32_t sqe_dbg1 = touch_rd(gpu, 0x2424u);
\ttouch_wr(gpu, 0x2420u, 2u); uint32_t sqe_dbg2 = touch_rd(gpu, 0x2424u);
\ttouch_wr(gpu, 0x2420u, 3u); uint32_t sqe_dbg3 = touch_rd(gpu, 0x2424u);
\tuint32_t curr_rptr = touch_rd(gpu, 0x2018u);
\tuint32_t curr_wptr = touch_rd(gpu, 0x201cu);
\trbbm_status = touch_rd(gpu, 0x840u);
\tprintf("SPES GPU: 27. Post-SQE: fault=%#x int=%#x rptr=%u wptr=%u rbbm=%#x\\n",
\t    cp_hw_fault, cp_int_stat, curr_rptr, curr_wptr, rbbm_status);
\tprintf("SPES GPU: 27b. SQE dbg0-3: %#x %#x %#x %#x\\n",
\t    sqe_dbg0, sqe_dbg1, sqe_dbg2, sqe_dbg3);
\tprintf("SPES GPU: 27c. SMMU: GFSR=%#x FSR=%#x FSYNR=%#x FAR=%#x:%#x\\n",
\t    touch_rd(smmu, 0x48u), touch_rd(smmu, context + 0x58u),
\t    touch_rd(smmu, context + 0x68u), touch_rd(smmu, context + 0x64u),
\t    touch_rd(smmu, context + 0x60u));

\t/* Retain early-abort protection if illegal instruction or fault occurs */
\tif (cp_int_stat || cp_hw_fault) {
\t\ttouch_wr(gpu, 0x2020u, 3u); /* CP_SQE_CNTL = 3 (halt SQE) */
\t\tprintf("SPES GPU: SQE fault detected; halted, early-abort before packets\\n");
\t\treturn;
\t}"""

    rep1_lines = ["+" + line + "\n" if line.strip() else "+\n" for line in rep1.splitlines()]
    rep2_lines = ["+" + line + "\n" if line.strip() else "+\n" for line in rep2.splitlines()]

    # Replace [t2_start : t2_end + 1] and [t1_start : t1_end + 1]
    new_hunk2 = hunk2_lines[:t2_start] + rep2_lines + hunk2_lines[t2_end + 1:]
    new_hunk2 = new_hunk2[:t1_start] + rep1_lines + new_hunk2[t1_end + 1:]

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
