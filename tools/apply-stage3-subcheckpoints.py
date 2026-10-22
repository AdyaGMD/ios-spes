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

    target_start_marker = '\tvm_offset_t smmu = 0;\n'
    if not any(l == "+" + target_start_marker for l in hunk2_lines):
        target_start_marker = '\t/* Step 13: Map GPU SMMU MMIO aperture (0x059a0000, 64 KiB) */\n'
    target_end_marker = '\t/* Step 20: Submit CP_ME_INIT (Linux upstream A6xx sequence) */\n'

    start_idx = None
    end_idx = None
    for i, l in enumerate(hunk2_lines):
        if l == "+" + target_start_marker:
            start_idx = i
        elif l == "+" + target_end_marker:
            end_idx = i
            break

    assert start_idx is not None, "target_start_marker not found"
    assert end_idx is not None, "target_end_marker not found"

    print(f"Replacement range in hunk2: {start_idx}..{end_idx}")

    rep_block = """\tvm_offset_t smmu = 0;
\tuint32_t cb0_off = 0;
#define LOG_CP(tag) do { \\
\t\t__asm__ volatile ("dsb sy" ::: "memory"); \\
\t\tuint32_t _gfsr = smmu ? touch_rd(smmu, 0x48u) : 0u; \\
\t\tuint32_t _fsr  = (smmu && cb0_off) ? touch_rd(smmu, cb0_off + 0x58u) : 0u; \\
\t\tprintf("SPES GPU: %s: int=%#x fault=%#x int0=%#x rbbm=%#x sqe=%#x gfsr=%#x fsr=%#x\\n", \\
\t\t    tag, \\
\t\t    touch_rd(gpu, 0x208cu), touch_rd(gpu, 0x2084u), \\
\t\t    touch_rd(gpu, 0x804u), touch_rd(gpu, 0x840u), \\
\t\t    touch_rd(gpu, 0x2020u), _gfsr, _fsr); \\
\t} while (0)

\t/* Checkpoint 1 (23-0): Before SMMU initialization begins */
\tLOG_CP("23-0 (Pre-SMMU)");

\t/* Step 13: Map GPU SMMU MMIO aperture (0x059a0000, 64 KiB) */
\tsmmu = ml_io_map(0x059a0000u, 0x10000u);
\tif (!smmu) {
\t\tprintf("SPES GPU: SMMU MMIO map failed\\n");
\t\treturn;
\t}
\tuint32_t smmu_scr0 = touch_rd(smmu, 0x00u);
\tuint32_t smmu_id0  = touch_rd(smmu, 0x20u);
\tuint32_t smmu_id1  = touch_rd(smmu, 0x24u);
\tuint32_t smmu_id2  = touch_rd(smmu, 0x28u);

\tuint32_t shift = (smmu_id1 >> 31) ? 16 : 12;
\tuint32_t pages = 1u << (((smmu_id1 >> 28) & 7u) + 1u);
\tuint32_t stride = 1u << shift;
\tuint32_t num_cb = smmu_id1 & 0xffu;
\tcb0_off = pages * stride;

\tprintf("SPES GPU: 23. SMMU sCR0=%#x ID0=%#x ID1=%#x (pgsz=%uK pages=%u cb=%u)\\n",
\t    smmu_scr0, smmu_id0, smmu_id1, (1u << (shift - 10)), pages, num_cb);

\tuint32_t cb0_sctlr = touch_rd(smmu, cb0_off);
\tuint32_t cb0_fsr   = touch_rd(smmu, cb0_off + 0x58u);
\tuint32_t cbar0     = touch_rd(smmu, stride + 0x00u);
\tuint32_t cba2r0    = touch_rd(smmu, stride + 0x800u);
\tprintf("SPES GPU: 23b. CB0 SCTLR=%#x FSR=%#x CBAR0=%#x CBA2R0=%#x\\n",
\t    cb0_sctlr, cb0_fsr, cbar0, cba2r0);

\tprintf("SPES GPU: 23c. Boot SMR: 0=%#x 1=%#x 2=%#x 3=%#x\\n",
\t    touch_rd(smmu, 0x800u), touch_rd(smmu, 0x804u), touch_rd(smmu, 0x808u), touch_rd(smmu, 0x80cu));
\tprintf("SPES GPU: 23d. Boot S2CR: 0=%#x 1=%#x 2=%#x 3=%#x\\n",
\t    touch_rd(smmu, 0xc00u), touch_rd(smmu, 0xc04u), touch_rd(smmu, 0xc08u), touch_rd(smmu, 0xc0cu));

\t/* Map 64 KiB contiguous DMA carveout in continuous splash RAM (< 4GB DRAM) at 0x5ca00000 */
\tvm_offset_t gpu_dma_va = ml_io_map(0x5ca00000u, 0x10000u);
\tif (!gpu_dma_va) {
\t\tprintf("SPES GPU: ml_io_map(0x5ca00000) failed\\n");
\t\treturn;
\t}
\tuint64_t gpu_dma_pa = 0x5ca00000u;
\tuint64_t sqe_pa   = gpu_dma_pa + 0x0000u;
\tuint64_t rb_pa    = gpu_dma_pa + 0x8000u;
\tuint64_t fence_pa = gpu_dma_pa + 0xc000u;

\tvolatile uint32_t *sqe_dst = (volatile uint32_t *)(gpu_dma_va + 0x0000u);
\tfor (unsigned si = 0; si < sizeof(a630_sqe_fw) / sizeof(uint32_t); si++) {
\t\tsqe_dst[si] = a630_sqe_fw[si];
\t}

\tvolatile uint32_t *rb = (volatile uint32_t *)(gpu_dma_va + 0x8000u);
\tfor (unsigned ri = 0; ri < 16384 / sizeof(uint32_t); ri++) {
\t\trb[ri] = 0;
\t}

\tvolatile uint32_t *scratch = (volatile uint32_t *)(gpu_dma_va + 0xc000u);
\tfor (unsigned fi = 0; fi < 4096 / sizeof(uint32_t); fi++) {
\t\tscratch[fi] = 0xdeadbeefu;
\t}
\t__asm__ volatile ("dsb sy" ::: "memory");

\t/* Checkpoint 2 (23-1): After mapping DMA memory and copying SQE firmware */
\tLOG_CP("23-1 (Post-DMA-Copy)");

\t/* Allocate 32 KiB (8 contiguous 4K pages) for SMMU Stage 1 Page Tables */
\tvm_offset_t pt_va = 0;
\tif (kmem_alloc_contig(kernel_map, &pt_va, 32768, PAGE_MASK, 0, 0,
\t    KMA_DATA | KMA_ZERO | KMA_PERMANENT, VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS) {
\t\tprintf("SPES GPU: kmem_alloc_contig for SMMU page tables failed\\n");
\t\treturn;
\t}
\tuint64_t pt_pa = ptoa_64(pmap_find_phys(kernel_pmap, (addr64_t)pt_va));
\tmemset((void *)pt_va, 0, 32768);

\t/* ARM SMMUv2 3-level page tables (4K granule, 39-bit VA):
\t * L1 root table: pt_va + 0x0000 (pt_pa + 0x0000)
\t * L2 table:      pt_va + 0x1000 (pt_pa + 0x1000)
\t * L3 Core:       pt_va + 0x2000 (pt_pa + 0x2000) -> 0x01000000..0x011fffff
\t * L3 Target:     pt_va + 0x3000 (pt_pa + 0x3000) -> 0x10000000..0x101fffff
\t * L3 FB:         pt_va + 0x4000 (pt_pa + 0x4000) -> 0x5c000000..0x5c1fffff
\t * L3 DMA:        pt_va + 0x5000 (pt_pa + 0x5000) -> 0x5ca00000..0x5cbfffff
\t */
\tuint64_t *l1 = (uint64_t *)(pt_va + 0x0000u);
\tuint64_t *l2 = (uint64_t *)(pt_va + 0x1000u);
\tuint64_t *l3_core = (uint64_t *)(pt_va + 0x2000u);
\tuint64_t *l3_target = (uint64_t *)(pt_va + 0x3000u);
\tuint64_t *l3_fb = (uint64_t *)(pt_va + 0x4000u);
\tuint64_t *l3_dma = (uint64_t *)(pt_va + 0x5000u);
\tuint64_t *l2_high = (uint64_t *)(pt_va + 0x6000u);

\tuint64_t l2_pa = pt_pa + 0x1000u;
\tuint64_t l3_core_pa = pt_pa + 0x2000u;
\tuint64_t l3_target_pa = pt_pa + 0x3000u;
\tuint64_t l3_fb_pa = pt_pa + 0x4000u;
\tuint64_t l3_dma_pa = pt_pa + 0x5000u;

\t#define SPES_PTE_TABLE   3ull
\t#define SPES_PTE_PAGE    3ull
\t#define SPES_PTE_CORE    ((1ull << 6) | (2ull << 8) | (1ull << 10) | (1ull << 11))
\t#define SPES_PTE_RO      (1ull << 7)

\tl1[0] = l2_pa | SPES_PTE_TABLE;
\tl2[8]   = l3_core_pa | SPES_PTE_TABLE;
\tl2[128] = l3_target_pa | SPES_PTE_TABLE;
\tl1[1] = (pt_pa + 0x6000u) | SPES_PTE_TABLE;
\tl2_high[224] = l3_fb_pa | SPES_PTE_TABLE;
\tl2_high[229] = l3_dma_pa | SPES_PTE_TABLE;

\t/* Core mappings */
\tfor (unsigned i = 0; i < 4; i++) {
\t\tl3_core[i] = (rb_pa + i * 4096u) | SPES_PTE_CORE | SPES_PTE_PAGE;
\t}
\tfor (unsigned i = 0; i < 8; i++) {
\t\tl3_core[256 + i] = (sqe_pa + i * 4096u) | SPES_PTE_CORE | SPES_PTE_RO | SPES_PTE_PAGE;
\t}
\tl3_core[496] = fence_pa | SPES_PTE_CORE | SPES_PTE_PAGE;

\t/* Target mappings */
\tfor (unsigned i = 0; i < 16; i++) {
\t\tl3_target[i] = (fence_pa + (i % 4) * 4096u) | SPES_PTE_CORE | SPES_PTE_PAGE;
\t}

\t/* FB mappings (0x5c000000..0x5c1fffff identity) */
\tfor (unsigned i = 0; i < 512; i++) {
\t\tl3_fb[i] = (0x5c000000u + i * 4096u) | SPES_PTE_CORE | SPES_PTE_PAGE;
\t}

\t/* DMA mappings: only the owned 64 KiB carveout, not 2 MiB. */
\tfor (unsigned i = 0; i < 16; i++) {
\t\tl3_dma[i] = (0x5ca00000u + i * 4096u) | SPES_PTE_CORE | SPES_PTE_PAGE;
\t}
\tto_memory(pt_va, 0u);

\t/* Checkpoint 3 (23-2): After allocating and populating SMMU page tables */
\tLOG_CP("23-2 (Post-PT-Populate)");

\tto_memory(pt_va, 32768);
\t__asm__ volatile ("dsb sy" ::: "memory");

\t/* Checkpoint 4 (23-3): After making page-table writes visible to hardware */
\tLOG_CP("23-3 (Post-PT-Sync)");

\t/* Configure SMMU Context Bank 0 */
\tuint32_t context = cb0_off;
\ttouch_wr(smmu, context + 0x00u, 0u);                      /* CB0_SCTLR = 0 (quiesce) */
\ttouch_wr(smmu, stride + 0x800u, 1u);                     /* CBA2R0 = 1 (64-bit translation format) */
\ttouch_wr(smmu, stride + 0x000u, (1u << 16) | (3u << 8) | (0xfu << 12)); /* CBAR0 = 0x1f300 (Stage 1) */
\ttouch_wr(smmu, context + 0x10u, (1u | 1u << 4 | 7u << 15)); /* CB0_TCR2: 36-bit PA, 16-bit ASID */
\ttouch_wr(smmu, context + 0x30u, (25u | 1u << 8 | 1u << 10 | 3u << 12 | 1u << 23)); /* CB0_TCR: 39-bit VA, 4K granule, inner/outer WB WA */
\ttouch_wr(smmu, context + 0x20u, (uint32_t)pt_pa);         /* CB0_TTBR0_LO */
\ttouch_wr(smmu, context + 0x24u, (uint32_t)(pt_pa >> 32)); /* CB0_TTBR0_HI */
\ttouch_wr(smmu, context + 0x28u, 0u);                      /* CB0_TTBR1_LO = 0 */
\ttouch_wr(smmu, context + 0x2cu, 0u);                      /* CB0_TTBR1_HI = 0 */
\ttouch_wr(smmu, context + 0x38u, 0xf404ff44u);             /* CB0_MAIR0: 0=uncached, 1=cached, 2=device */
\ttouch_wr(smmu, context + 0x3cu, 0u);                      /* CB0_MAIR1 = 0 */
\ttouch_wr(smmu, context + 0x58u, 0xc00001feu);             /* CB0_FSR: clear all faults */
\t__asm__ volatile ("dsb sy" ::: "memory");

\t/* Checkpoint 5 (23-4): After programming Context Bank 0 translation registers */
\tLOG_CP("23-4 (Post-CB0-Prog)");

\ttouch_wr(smmu, context + 0x610u, 0u);                     /* CB0_TLBIASID: invalidate ASID 0 */
\ttouch_wr(smmu, context + 0x7f0u, 1u);                     /* CB0_TLBSYNC = 1 */
\tfor (int ti = 0; ti < 1000 && (touch_rd(smmu, context + 0x7f4u) & 1); ti++) {
\t\ttouch_wait(1);
\t}
\t__asm__ volatile ("dsb sy" ::: "memory");

\t/* Checkpoint 6 (23-5): After TLB invalidation and synchronization */
\tLOG_CP("23-5 (Post-TLB-Sync)");

\ttouch_wr(smmu, context + 0x00u, (1u << 0) | (1u << 1) | (1u << 2) | (1u << 5) | (1u << 8) | (1u << 12)); /* CB0_SCTLR = ON | HUPCF */
\t__asm__ volatile ("dsb sy" ::: "memory");

\t/* Checkpoint 7 (23-6): After enabling Context Bank 0 through SCTLR */
\tLOG_CP("23-6 (Post-CB0-Enable)");

\t/* Exact stream matches: invalidate SMRs first to unlock S2CR writes per ARM SMMUv2 spec. */
\ttouch_wr(smmu, 0x800u, 0u);                               /* Invalidate SMR0 */
\ttouch_wr(smmu, 0x804u, 0u);                               /* Invalidate SMR1 */
\ttouch_wr(smmu, 0x808u, 0u);                               /* Invalidate SMR2 */
\ttouch_wr(smmu, 0x80cu, 0u);                               /* Invalidate SMR3 */
\t__asm__ volatile ("dsb sy" ::: "memory");

\t/* Checkpoint 8 (23-7): After invalidating the existing SMR entries */
\tLOG_CP("23-7 (Post-SMR-Inv)");

\t/* Route streams to Context Bank 0 */
\ttouch_wr(smmu, 0xc00u, 0x300u);                             /* S2CR0: context 0, SHCFG_NSH=3, type=0 */
\ttouch_wr(smmu, 0xc04u, 0x300u);                             /* S2CR1 */
\ttouch_wr(smmu, 0xc08u, 0x300u);                             /* S2CR2 */
\ttouch_wr(smmu, 0xc0cu, 0x300u);                             /* S2CR3 */
\t__asm__ volatile ("dsb sy" ::: "memory");

\t/* Checkpoint 9 (23-8): After programming S2CR0 and S2CR2 */
\tLOG_CP("23-8 (Post-S2CR)");

\t/* Re-enable exact Stream Match Registers (Stream 0 = SQE/CP, Stream 1 = LPAC, Stream 2 = secure) */
\ttouch_wr(smmu, 0x800u, (1u << 31) | 0u);                   /* SMR0: valid, stream 0 */
\ttouch_wr(smmu, 0x804u, (1u << 31) | 1u);                   /* SMR1: valid, stream 1 */
\ttouch_wr(smmu, 0x808u, (1u << 31) | 2u);                   /* SMR2: valid, stream 2 */
\t__asm__ volatile ("dsb sy" ::: "memory");

\t/* Checkpoint 10 (23-9): After programming SMR0 and SMR2 */
\tLOG_CP("23-9 (Post-SMR)");

\tuint32_t smr_rb[4], s2cr_rb[4];
\tfor (unsigned i = 0; i < 4; i++) {
\t\tsmr_rb[i]  = touch_rd(smmu, 0x800u + i * 4u);
\t\ts2cr_rb[i] = touch_rd(smmu, 0xc00u + i * 4u);
\t}
\tuint32_t s2cr0_type = (s2cr_rb[0] >> 16) & 3u;
\tuint32_t s2cr0_cb   = s2cr_rb[0] & 0xffu;
\tprintf("SPES GPU: 23f. SMR[0-1]: [0]=%#x (v=%d id=%u mask=%#x) [1]=%#x (v=%d id=%u mask=%#x)\\n",
\t    smr_rb[0], (smr_rb[0] >> 31) & 1, smr_rb[0] & 0x7fffu, (smr_rb[0] >> 16) & 0x7fffu,
\t    smr_rb[1], (smr_rb[1] >> 31) & 1, smr_rb[1] & 0x7fffu, (smr_rb[1] >> 16) & 0x7fffu);
\tprintf("SPES GPU: 23f2. SMR[2-3]: [2]=%#x (v=%d id=%u mask=%#x) [3]=%#x (v=%d id=%u mask=%#x)\\n",
\t    smr_rb[2], (smr_rb[2] >> 31) & 1, smr_rb[2] & 0x7fffu, (smr_rb[2] >> 16) & 0x7fffu,
\t    smr_rb[3], (smr_rb[3] >> 31) & 1, smr_rb[3] & 0x7fffu, (smr_rb[3] >> 16) & 0x7fffu);
\tprintf("SPES GPU: 23f3. S2CR[0-3]: [0]=%#x (t=%u cb=%u sh=%u) [1]=%#x(t=%u) [2]=%#x(t=%u cb=%u sh=%u) [3]=%#x(t=%u)\\n",
\t    s2cr_rb[0], (s2cr_rb[0] >> 16) & 3u, s2cr_rb[0] & 0xffu, (s2cr_rb[0] >> 8) & 3u,
\t    s2cr_rb[1], (s2cr_rb[1] >> 16) & 3u,
\t    s2cr_rb[2], (s2cr_rb[2] >> 16) & 3u, s2cr_rb[2] & 0xffu, (s2cr_rb[2] >> 8) & 3u,
\t    s2cr_rb[3], (s2cr_rb[3] >> 16) & 3u);

\t/* SMR2 writeability probe: test if SMR2 accepts writes or is locked/hypervisor-trapped */
\ttouch_wr(smmu, 0x808u, 0x12345678u);
\t__asm__ volatile ("dsb sy" ::: "memory");
\tuint32_t smr2_test1 = touch_rd(smmu, 0x808u);

\ttouch_wr(smmu, 0x808u, (1u << 31) | 2u);
\t__asm__ volatile ("dsb sy" ::: "memory");
\tuint32_t smr2_test2 = touch_rd(smmu, 0x808u);
\tprintf("SPES GPU: 23f4. SMR2 write test: wr(0x12345678)->%#x wr(VALID|2)->%#x\\n",
\t    smr2_test1, smr2_test2);

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

\tprintf("SPES GPU: 23f5. TCR=%#x TCR2=%#x MAIR=%#x:%#x CBAR0=%#x CBA2R0=%#x\\n",
\t    hw_tcr, hw_tcr2, hw_mair1, hw_mair0, hw_cbar0, hw_cba2r0);
\tprintf("SPES GPU: 23g. PTE 0x01100000: L1[0]=%#llx L2[8]=%#llx L3[256]=%#llx (pa=%#llx)\\n",
\t    l1[0], l2[8], l3_core[256], (l3_core[256] & ~0xfffull));

\tif (s2cr0_type == 2u || s2cr0_cb == 0xffu) {
\t\tprintf("SPES GPU: S2CR0 stuck in FAULT (raw=%#x type=%u cb=%u); stopping BEFORE SQE\\n",
\t\t    s2cr_rb[0], s2cr0_type, s2cr0_cb);
\t\treturn;
\t}

\tif (!(hw_sctlr & 1u) || (touch_rd(smmu, context + 0x7f4u) & 1u)) {
\t\tprintf("SPES GPU: SMMU CB0 enable/sync failed; stopping BEFORE SQE\\n");
\t\treturn;
\t}

\t/* Configure RBBM SECVID TSB & enable 64-bit addressing on all 12 blocks */
\t/* Checkpoint 2A: after SMMU context-bank and stream configuration */
\tLOG_CP("23h. CP-2A (SMMU)");

\ttouch_wr(gpu, 0x3e000u, 0x0u); /* RBBM_SECVID_TSB_TRUSTED_BASE_LO */
\ttouch_wr(gpu, 0x3e004u, 0x0u); /* RBBM_SECVID_TSB_TRUSTED_BASE_HI */
\ttouch_wr(gpu, 0x3e008u, 0x0u); /* RBBM_SECVID_TSB_TRUSTED_SIZE */

\ttouch_wr(gpu, 0x2108u, 0x1u);  /* CP_ADDR_MODE_CNTL */
\ttouch_wr(gpu, 0x3004u, 0x1u);  /* VSC_ADDR_MODE_CNTL */
\ttouch_wr(gpu, 0x21804u, 0x1u); /* GRAS_ADDR_MODE_CNTL */
\ttouch_wr(gpu, 0x23814u, 0x1u); /* RB_ADDR_MODE_CNTL */
\ttouch_wr(gpu, 0x27804u, 0x1u); /* PC_ADDR_MODE_CNTL */
\ttouch_wr(gpu, 0x2f814u, 0x1u); /* HLSQ_ADDR_MODE_CNTL */
\ttouch_wr(gpu, 0x29804u, 0x1u); /* VFD_ADDR_MODE_CNTL */
\ttouch_wr(gpu, 0x25804u, 0x1u); /* VPC_ADDR_MODE_CNTL */
\ttouch_wr(gpu, 0x3800u, 0x1u);  /* UCHE_ADDR_MODE_CNTL */
\ttouch_wr(gpu, 0x2b804u, 0x1u); /* SP_ADDR_MODE_CNTL */
\ttouch_wr(gpu, 0x2d804u, 0x1u); /* TPL1_ADDR_MODE_CNTL */
\ttouch_wr(gpu, 0x3e040u, 0x1u); /* RBBM_SECVID_TSB_ADDR_MODE_CNTL */
\t__asm__ volatile ("dsb sy" ::: "memory");
\t/* Checkpoint 2B: after GPU address-mode and security-register configuration */
\tLOG_CP("24b. CP-2B (ADDR)");

\t/* Adreno 610 GBIF QSB sideband and QoS bus routing */
\ttouch_wr(gpu, 0xf00cu, 0x00071620u); /* REG_A6XX_GBIF_QSB_SIDE0 */
\ttouch_wr(gpu, 0xf010u, 0x00071620u); /* REG_A6XX_GBIF_QSB_SIDE1 */
\ttouch_wr(gpu, 0xf014u, 0x00071620u); /* REG_A6XX_GBIF_QSB_SIDE2 */
\ttouch_wr(gpu, 0xf018u, 0x00071620u); /* REG_A6XX_GBIF_QSB_SIDE3 */
\ttouch_wr(gpu, 0xf000u, 0x00080707u); /* REG_A6XX_GBIF_QSB_SIDE_HALT */
\ttouch_wr(gpu, 0x2030u, 0x00000000u); /* CP_ROQ_THRESH_CONFIG */
\ttouch_wr(gpu, 0x2034u, 0x00000000u); /* CP_MEM_POOL_DBG_CNTL */
\ttouch_wr(gpu, 0x0e00u, 0x00000001u); /* UCHE_WRITE_THRU_BASE_LO */
\ttouch_wr(gpu, 0x0e04u, 0x00000000u); /* UCHE_WRITE_THRU_BASE_HI */
\ttouch_wr(gpu, 0x0e08u, 0x00000000u); /* UCHE_TRAP_BASE_LO */
\ttouch_wr(gpu, 0x0e0cu, 0x00000000u); /* UCHE_TRAP_BASE_HI */
\ttouch_wr(gpu, 0x0e010u, 0x00000001u); /* UCHE_MODE_CNTL (line size 64B) */
\ttouch_wr(gpu, 0x0824u, 0x00001802u); /* RBBM_INTERFACE_HANG_INT_CNTL */
\ttouch_wr(gpu, 0x0818u, 0x00000000u); /* RBBM_INT_CLEAR_CMD */
\t__asm__ volatile ("dsb sy" ::: "memory");
\t/* Checkpoint 2C: after GBIF/CP/UCHE hardware configuration */
\tLOG_CP("25c. CP-2C (GBIF)");

\t/* Clear any pending interrupts latched during bus configuration */
\ttouch_wr(gpu, 0x00dcu, 0x31c002c2u); /* RBBM_INT_0_CLEAR */
\t__asm__ volatile ("dsb sy" ::: "memory");
\t/* Checkpoint 2D: after RBBM interrupt-clear operations */
\tLOG_CP("25d. CP-2D (INTCLR)");

\tunsigned sqe_err = 0;
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
\t/* Checkpoint 2E: after SQE instruction-base programming */
\tLOG_CP("26c2. CP-2E (SQEBASE)");

\t/* Program Ringbuffer registers: ring at 0x01000000, RPTR scratch at 0x011f0000 */
\ttouch_wr(gpu, 0x2000u, 0x01000000u);           /* CP_RB_BASE_LO */
\ttouch_wr(gpu, 0x2004u, 0x00000000u);           /* CP_RB_BASE_HI */
\ttouch_wr(gpu, 0x2008u, 0x0800020au);           /* CP_RB_CNTL (8K ring, 32B block, bit 27 = NO_APRIV) */
\ttouch_wr(gpu, 0x2010u, 0x011f0000u);           /* CP_RB_RPTR_ADDR_LO */
\ttouch_wr(gpu, 0x2014u, 0x00000000u);           /* CP_RB_RPTR_ADDR_HI */
\ttouch_wr(gpu, 0x2018u, 0u);                    /* CP_RB_RPTR */
\ttouch_wr(gpu, 0x201cu, 0u);                    /* CP_RB_WPTR */
\ttouch_wr(gpu, 0x2214u, 0u);                    /* CP_SCRATCH(2) */
\t__asm__ volatile ("dsb sy" ::: "memory");
\t/* Checkpoint 2F: after Ringbuffer base/control/pointer programming */
\tLOG_CP("26c3. CP-2F (RBCONFIG)");

\t/* 0x2090 is CP_PROTECT_STATUS, NOT CP_INT_ACK. Do not write it. */
\ttouch_wr(gpu, 0x2110u, (1u << 6) | (1u << 5) | (1u << 3) | (1u << 2) | (1u << 1)); /* CP_APRIV_CNTL = 0x6e */
\t__asm__ volatile ("dsb sy" ::: "memory");
\t/* Checkpoint 2G: after CP_APRIV programming */
\tLOG_CP("26c4. CP-2G (APRIV)");

\t/* Checkpoint 3: Before CP_SQE_CNTL = 1 */
\tLOG_CP("26d. Checkpoint 3 (Pre-Unhalt)");

\t/* Step 19: Un-halt CP SQE engine BEFORE submitting init */
\ttouch_wr(gpu, 0x2020u, 1u); /* CP_SQE_CNTL = 1 */
\t__asm__ volatile ("dsb sy" ::: "memory");
\ttouch_wait(10);

\t/* Checkpoint 3B: After CP_SQE_CNTL = 1 */
\tLOG_CP("26e. Post-unhalt 1");
\ttouch_wr(gpu, 0x2420u, 0u); uint32_t sqe_dbg0 = touch_rd(gpu, 0x2424u);
\ttouch_wr(gpu, 0x2420u, 1u); uint32_t sqe_dbg1 = touch_rd(gpu, 0x2424u);
\ttouch_wr(gpu, 0x2420u, 2u); uint32_t sqe_dbg2 = touch_rd(gpu, 0x2424u);
\ttouch_wr(gpu, 0x2420u, 3u); uint32_t sqe_dbg3 = touch_rd(gpu, 0x2424u);
\tuint32_t pre_rptr   = touch_rd(gpu, 0x2018u);
\tuint32_t pre_wptr   = touch_rd(gpu, 0x201cu);
\trbbm_status         = touch_rd(gpu, 0x840u);
\tprintf("SPES GPU: 26f. SQE dbg0-3: %#x %#x %#x %#x (rptr=%u wptr=%u)\\n",
\t    sqe_dbg0, sqe_dbg1, sqe_dbg2, sqe_dbg3, pre_rptr, pre_wptr);

\t/* Halt safely only if a true hardware fault occurs */
\tuint32_t cp3b_fault = touch_rd(gpu, 0x2084u);
\tif (cp3b_fault != 0) {
\t\ttouch_wr(gpu, 0x2020u, 3u); /* CP_SQE_CNTL = 3 */
\t\tprintf("SPES GPU: Hardware fault on unhalt; halted safely before packets\\n");
\t\treturn;
\t}
#undef LOG_CP
"""

    rep_lines = ["+" + line + "\n" if line.strip() else "+\n" for line in rep_block.splitlines()]

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
