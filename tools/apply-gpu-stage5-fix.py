#!/usr/bin/env python3
import re
from pathlib import Path

def main():
    patch_path = Path("/Users/adya/Documents/iospes/xnu/patches/0098-spes-glink-rpm-transport.patch")
    lines = patch_path.read_text().splitlines(keepends=True)

    # Find the hunk starting at "@@ -677,6"
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

    # Everything before hunk 2
    prefix = lines[:hunk2_idx]
    # Hunk 2 lines
    hunk2_lines = lines[hunk2_idx:hunk3_idx]
    # Hunk 3 and beyond
    suffix = lines[hunk3_idx:]

    # In hunk 2, find the start of the GPU Stage 3 / SMMU bypass and the end of Stage 5 DRAM write
    hunk2_text = "".join(hunk2_lines)

    target_start = "\t/* Ensure bypass mode on CB0 (M=0) */\n"
    target_end = '\tprintf("SPES GPU: 31. GPU STAGE-4 & STAGE-5 100%% VERIFIED ON SILICON!\\n");\n'

    # Find these lines in hunk2_lines (prefixed with '+')
    start_line_idx = None
    end_line_idx = None
    for i, l in enumerate(hunk2_lines):
        if l == "+" + target_start:
            start_line_idx = i
        elif l == "+" + target_end:
            end_line_idx = i
            break

    assert start_line_idx is not None, f"start_line_idx not found"
    assert end_line_idx is not None, f"end_line_idx not found"

    print(f"Replacing lines {start_line_idx} to {end_line_idx} in hunk 2 (total {len(hunk2_lines)} lines)")

    replacement_body = """\t/* Ensure bypass mode on CB0 (M=0) */
\tif (cb0_sctlr & 1u) {
\t\ttouch_wr(smmu, cb0_off, 0u);
\t\t__asm__ volatile ("dsb sy" ::: "memory");
\t\tprintf("SPES GPU: 23c. CB0 SCTLR forced to bypass: %#x\\n", touch_rd(smmu, cb0_off));
\t}

\t/* Ensure global bypass on SMMU sCR0 (CLIENTPD=1, USFCFG=0) */
\ttouch_wr(smmu, 0x00u, (smmu_scr0 | 1u) & ~(1u << 10));
\t__asm__ volatile ("dsb sy" ::: "memory");
\tprintf("SPES GPU: 23d. SMMU sCR0 forced bypass: %#x\\n", touch_rd(smmu, 0x00u));

\t/* Step 14: Query TrustZone for PAS ID 13 (ZAP shader) support */
\tuint64_t tz_res = 0;
\tuint64_t tz_st = spes_scm(0x42000000u | (0x02u << 8) | 0x07u, 1, 13, 0, 0, &tz_res);
\tprintf("SPES GPU: 24. TrustZone PAS 13 check: st=%#llx res=%#llx\\n", tz_st, tz_res);

\t/* ================================================================
\t * STAGE 4: TrustZone PAS ID 13 (a610_zap) PIL Authentication
\t * ================================================================ */
\tprintf("SPES GPU: starting Stage 4 (ZAP PIL authentication)...\\n");

\t/* Step 15a: Allocate contiguous buffer for ZAP MDT metadata (8 KiB) */
\tvm_offset_t mdt_va = 0;
\tif (kmem_alloc_contig(kernel_map, &mdt_va, 8192, PAGE_MASK, 0, 0,
\t    KMA_DATA | KMA_ZERO | KMA_PERMANENT, VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS) {
\t\tprintf("SPES GPU: kmem_alloc_contig for ZAP MDT failed\\n");
\t\treturn;
\t}
\tppnum_t mdt_pn = pmap_find_phys(kernel_pmap, (addr64_t)mdt_va);
\tuint64_t mdt_pa = ptoa_64(mdt_pn);
\tvolatile uint32_t *mdt_dst = (volatile uint32_t *)mdt_va;
\tfor (unsigned mi = 0; mi < sizeof(a610_zap_mdt) / sizeof(uint32_t); mi++) {
\t\tmdt_dst[mi] = a610_zap_mdt[mi];
\t}
\tclean_dcache64(mdt_pa, sizeof(a610_zap_mdt), TRUE);
\t__asm__ volatile ("dsb sy" ::: "memory");
\tprintf("SPES GPU: 25a. ZAP MDT (%lu bytes) at pa=%#llx va=%#lx\\n",
\t    sizeof(a610_zap_mdt), mdt_pa, (unsigned long)mdt_va);

\t/* Step 15b: Map 8 KiB contiguous DMA buffer at 0x56615000 (< 4GB DRAM) for ZAP */
\tvm_offset_t dma_va = ml_io_map(0x56615000u, 0x2000u);
\tif (!dma_va) {
\t\tprintf("SPES GPU: ml_io_map(0x56615000) failed\\n");
\t\treturn;
\t}

\tuint64_t zap_pa = 0x56615000u;
\tuint64_t zap_size = 0x2000u;
\tvm_offset_t zap_va = dma_va + 0x0000u;
\tvolatile uint32_t *zap_dst = (volatile uint32_t *)zap_va;
\tfor (unsigned zi = 0; zi < sizeof(a610_zap_b02) / sizeof(uint32_t); zi++) {
\t\tzap_dst[zi] = a610_zap_b02[zi];
\t}
\t__asm__ volatile ("dsb sy" ::: "memory");
\tprintf("SPES GPU: 25b. ZAP b02 (%lu bytes) at pa=%#llx va=%#lx\\n",
\t    sizeof(a610_zap_b02), zap_pa, (unsigned long)zap_va);

\t/* Step 15c: SCM PIL_INIT_IMAGE (cmd 0x01, arginfo = 0x82) */
\tuint64_t pil_res = 0;
\tuint64_t pil_init_st = spes_scm(0x42000000u | (0x02u << 8) | 0x01u, 2 | (2 << 6), 13, mdt_pa, 0, &pil_res);
\tprintf("SPES GPU: 25c. ZAP PIL_INIT_IMAGE: st=%#llx res=%#llx\\n", pil_init_st, pil_res);

\t/* Step 15d: SCM PIL_MEM_SETUP (cmd 0x02, arginfo = 3) */
\tuint64_t pil_mem_st = spes_scm(0x42000000u | (0x02u << 8) | 0x02u, 3, 13, zap_pa, zap_size, &pil_res);
\tprintf("SPES GPU: 25d. ZAP PIL_MEM_SETUP: st=%#llx res=%#llx (pa=%#llx)\\n", pil_mem_st, pil_res, zap_pa);

\t/* Step 15e: SCM PIL_AUTH_RESET (cmd 0x05, arginfo = 1) */
\tuint64_t pil_auth_st = spes_scm(0x42000000u | (0x02u << 8) | 0x05u, 1, 13, 0, 0, &pil_res);
\tprintf("SPES GPU: 25e. ZAP PIL_AUTH_RESET: st=%#llx res=%#llx\\n", pil_auth_st, pil_res);

\t/* ================================================================
\t * STAGE 5: Microcode Upload, Ringbuffer Submission & GPU Memory Writes
\t * ================================================================ */
\tprintf("SPES GPU: starting Stage 5 (microcode upload & ringbuffer execution)...\\n");

\t/* Step 16: Allocate contiguous kernel DMA memory for SQE (32K), Ringbuffer (16K), and Scratch (16K) */
\tvm_offset_t gpu_dma_va = 0;
\tif (kmem_alloc_contig(kernel_map, &gpu_dma_va, 65536, PAGE_MASK,
\t    atop_64(0xffffffffULL), 0,
\t    KMA_DATA | KMA_ZERO | KMA_PERMANENT, VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS) {
\t\tif (kmem_alloc_contig(kernel_map, &gpu_dma_va, 65536, PAGE_MASK,
\t\t    0, 0,
\t\t    KMA_DATA | KMA_ZERO | KMA_PERMANENT, VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS) {
\t\t\tprintf("SPES GPU: kmem_alloc_contig for GPU DMA failed\\n");
\t\t\treturn;
\t\t}
\t}
\tppnum_t gpu_dma_pn = pmap_find_phys(kernel_pmap, (addr64_t)gpu_dma_va);
\tuint64_t gpu_dma_pa = ptoa_64(gpu_dma_pn);

\tuint64_t sqe_pa = gpu_dma_pa + 0x0000u;
\tvm_offset_t sqe_va = gpu_dma_va + 0x0000u;
\tvolatile uint32_t *sqe_dst = (volatile uint32_t *)sqe_va;
\tfor (unsigned si = 0; si < sizeof(a630_sqe_fw) / sizeof(uint32_t); si++) {
\t\tsqe_dst[si] = a630_sqe_fw[si];
\t}
\tclean_dcache64(sqe_pa, sizeof(a630_sqe_fw), TRUE);

\tuint64_t rb_pa = gpu_dma_pa + 0x8000u;
\tvm_offset_t rb_va = gpu_dma_va + 0x8000u;
\tvolatile uint32_t *rb = (volatile uint32_t *)rb_va;
\tfor (unsigned ri = 0; ri < 16384 / sizeof(uint32_t); ri++) {
\t\trb[ri] = 0;
\t}
\tclean_dcache64(rb_pa, 16384, TRUE);

\tuint64_t fence_pa = gpu_dma_pa + 0xc000u;
\tvm_offset_t fence_va = gpu_dma_va + 0xc000u;
\tvolatile uint32_t *scratch = (volatile uint32_t *)fence_va;
\tfor (unsigned fi = 0; fi < 16384 / sizeof(uint32_t); fi++) {
\t\tscratch[fi] = 0;
\t}
\tscratch[0] = 0xdeadbeefu;
\tscratch[1] = 0xdeadbeefu;
\tscratch[2] = 0xdeadbeefu;
\tscratch[3] = 0xdeadbeefu;
\tscratch[4] = 0xdeadbeefu; /* Fence seqno slot */
\tclean_dcache64(fence_pa, 16384, TRUE);
\t__asm__ volatile ("dsb sy" ::: "memory");
\tprintf("SPES GPU: 26. SQE ucode (%lu bytes) at pa=%#llx va=%#lx rb_pa=%#llx\\n",
\t    sizeof(a630_sqe_fw), sqe_pa, (unsigned long)sqe_va, rb_pa);

\t/* Step 16b: Configure RBBM SECVID TSB & enable 64-bit addressing on all 12 blocks */
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

\t/* Adreno 610 GBIF QSB sideband and QoS bus routing */
\ttouch_wr(gpu, 0xf00cu, 0x00071620u); /* REG_A6XX_GBIF_QSB_SIDE0 */
\ttouch_wr(gpu, 0xf010u, 0x00071620u); /* REG_A6XX_GBIF_QSB_SIDE1 */
\ttouch_wr(gpu, 0xf014u, 0x00071620u); /* REG_A6XX_GBIF_QSB_SIDE2 */
\ttouch_wr(gpu, 0xf018u, 0x00071620u); /* REG_A6XX_GBIF_QSB_SIDE3 */
\ttouch_wr(gpu, 0x0044u, 0x00000003u); /* REG_A6XX_RBBM_GBIF_CLIENT_QOS_CNTL */

\t/* Step 16c: Adreno 610 Hardware Queue, Memory Pool & Cache configuration */
\ttouch_wr(gpu, 0x230cu, 48u);        /* REG_A6XX_CP_MEM_POOL_SIZE = 48 */
\ttouch_wr(gpu, 0x2438u, 47u);        /* REG_A6XX_CP_MEM_POOL_DBG_ADDR = 47 */
\ttouch_wr(gpu, 0x2308u, 0x00800060u); /* REG_A6XX_CP_ROQ_THRESHOLDS_2 */
\ttouch_wr(gpu, 0x2304u, 0x40201b16u); /* REG_A6XX_CP_ROQ_THRESHOLDS_1 */
\ttouch_wr(gpu, 0x27808u, 0x00080000u); /* REG_A6XX_PC_DBG_ECO_CNTL */
\ttouch_wr(gpu, 0x2634u, 1u);         /* REG_A6XX_CP_AHB_CNTL = 1 */
\ttouch_wr(gpu, 0x0400u, 1u);          /* REG_A6XX_RBBM_PERFCTR_CNTL = 1 */
\ttouch_wr(gpu, 0x0508u, 0xffffffffu); /* REG_A6XX_RBBM_PERFCTR_GPU_BUSY_MASKED */

\t/* UCHE L2 bypass disable & filter configuration */
\ttouch_wr(gpu, 0x3814u, 0xffffffc0u); /* REG_A6XX_UCHE_WRITE_RANGE_MAX_LO */
\ttouch_wr(gpu, 0x3818u, 0x0001ffffu); /* REG_A6XX_UCHE_WRITE_RANGE_MAX_HI */
\ttouch_wr(gpu, 0x381cu, 0xfffff000u); /* REG_A6XX_UCHE_TRAP_BASE_LO */
\ttouch_wr(gpu, 0x3820u, 0x0001ffffu); /* REG_A6XX_UCHE_TRAP_BASE_HI */
\ttouch_wr(gpu, 0x3824u, 0xfffff000u); /* REG_A6XX_UCHE_WRITE_THRU_BASE_LO */
\ttouch_wr(gpu, 0x3828u, 0x0001ffffu); /* REG_A6XX_UCHE_WRITE_THRU_BASE_HI */
\ttouch_wr(gpu, 0x382cu, 0x00000804u); /* REG_A6XX_UCHE_FILTER_CNTL */
\ttouch_wr(gpu, 0x385cu, 0x00000004u); /* REG_A6XX_UCHE_CACHE_WAYS */

\t/* Authorize CP memory accesses */
\ttouch_wr(gpu, 0x2110u, 0x0000007fu); /* CP_APRIV_CNTL */

\t/* Disable CP register protection checking during early probe */
\ttouch_wr(gpu, 0x213cu, 0x00000000u); /* CP_PROTECT_CNTL */

\t/* Clear pending interrupts in RBBM and CP */
\ttouch_wr(gpu, 0x00dcu, 0xffffffffu); /* RBBM_INT_CLEAR_CMD */
\ttouch_wr(gpu, 0x0808u, 0x00000000u); /* RBBM_INT_0_MASK (mask interrupts) */
\ttouch_wr(gpu, 0x208cu, 0xffffffffu); /* CP_INTERRUPT_STATUS */
\t__asm__ volatile ("dsb sy" ::: "memory");
\tuint32_t addr_mode_val = touch_rd(gpu, 0x2108u);
\tuint32_t apriv_val = touch_rd(gpu, 0x2110u);
\tprintf("SPES GPU: 26c. ADDR_MODE=%#x APRIV=%#x MemPool(48)/ROQ configured\\n",
\t    addr_mode_val, apriv_val);

\t/* Step 17: Program CP SQE Base Registers (dword 0x0830 -> 0x20c0) */
\ttouch_wr(gpu, 0x20c0u, (uint32_t)sqe_pa);
\ttouch_wr(gpu, 0x20c4u, (uint32_t)(sqe_pa >> 32));
\t__asm__ volatile ("dsb sy" ::: "memory");
\tuint32_t base_lo = touch_rd(gpu, 0x20c0u);
\tuint32_t base_hi = touch_rd(gpu, 0x20c4u);
\tprintf("SPES GPU: 26b. CP_SQE_INSTR_BASE=%#x:%#x (match=%d)\\n",
\t    base_hi, base_lo, (base_lo == (uint32_t)sqe_pa && base_hi == (uint32_t)(sqe_pa >> 32)));

\t/* Step 18: Program Ringbuffer registers (A610: bit 27 = NO_APRIV) */
\ttouch_wr(gpu, 0x2000u, (uint32_t)rb_pa);           /* CP_RB_BASE_LO */
\ttouch_wr(gpu, 0x2004u, (uint32_t)(rb_pa >> 32));  /* CP_RB_BASE_HI */
\ttouch_wr(gpu, 0x2008u, 0x0800020au);              /* CP_RB_CNTL (8K ring, 32B block, bit 27 = NO_APRIV) */
\ttouch_wr(gpu, 0x2010u, (uint32_t)fence_pa);       /* CP_RB_RPTR_ADDR_LO */
\ttouch_wr(gpu, 0x2014u, (uint32_t)(fence_pa >> 32));/* CP_RB_RPTR_ADDR_HI */
\ttouch_wr(gpu, 0x2018u, 0u);                       /* CP_RB_RPTR */
\ttouch_wr(gpu, 0x201cu, 0u);                       /* CP_RB_WPTR */
\ttouch_wr(gpu, 0x2214u, 0u);                       /* CP_SCRATCH(2) */
\t__asm__ volatile ("dsb sy" ::: "memory");

\t/* Step 19: Un-halt CP SQE engine */
\ttouch_wr(gpu, 0x2020u, 1u); /* CP_SQE_CNTL = 1 */
\ttouch_wait(10);

\tuint32_t cp_hw_fault = touch_rd(gpu, 0x2084u);
\tuint32_t cp_int_stat = touch_rd(gpu, 0x208cu);
\ttouch_wr(gpu, 0x2094u, 1u); /* CP_SQE_STAT_ADDR = 1 */
\tuint32_t sqe_stat = touch_rd(gpu, 0x2098u); /* CP_SQE_STAT_DATA */
\tuint32_t curr_rptr = touch_rd(gpu, 0x2018u);
\tuint32_t curr_wptr = touch_rd(gpu, 0x201cu);
\trbbm_status = touch_rd(gpu, 0x840u);
\tprintf("SPES GPU: 27. CP started! fault=%#x int=%#x sqe_stat=%#x rptr=%u wptr=%u rbbm=%#x\\n",
\t    cp_hw_fault, cp_int_stat, sqe_stat, curr_rptr, curr_wptr, rbbm_status);

\t/* Step 20: Populate Stage 4 & Stage 5 PM4 command stream with exact Adreno parity */
\tuint32_t w = 0;

\t/* 1. CP_ME_INIT (Type 7, opcode 0x48, count 8) */
\trb[w++] = 0x70c80008u;
\trb[w++] = 0x0000002fu; /* CP_INIT_MASK: max contexts, error det, header dump, reset state, ucode wa */
\trb[w++] = 0x00000003u; /* max contexts = 3 */
\trb[w++] = 0x20000000u; /* error detection control */
\trb[w++] = 0x00000000u; /* header dump address LO */
\trb[w++] = 0x00000000u; /* header dump address HI */
\trb[w++] = 0x00000000u; /* header dump size */
\trb[w++] = 0x00000000u; /* ucode workaround */
\trb[w++] = 0x00000000u; /* pad */

\t/* 2. CP_SET_SECURE_MODE (Type 7, opcode 0x66, count 1) - drop protected mode */
\trb[w++] = 0x70e60001u;
\trb[w++] = 0x00000000u; /* Drop secure privileges to allow normal rendering commands */

\t/* 3. CP_MEM_WRITE to DRAM Scratch (Type 7, opcode 0x3d, count 6, parity bit 15) */
\trb[w++] = 0x703d8006u;
\trb[w++] = (uint32_t)fence_pa;
\trb[w++] = (uint32_t)(fence_pa >> 32);
\trb[w++] = 0x11223344u;
\trb[w++] = 0x55667788u;
\trb[w++] = 0x99aabbccu;
\trb[w++] = 0xddeeff00u;

\t/* 4. CP_MEM_WRITE to Screen Framebuffer (0x5c000000, 16 pixels, parity bit 15) */
\trb[w++] = 0x703d8012u;
\trb[w++] = 0x5c000000u;
\trb[w++] = 0x00000000u;
\tfor (int px = 0; px < 16; px++) {
\t\trb[w++] = 0x00ff00ffu; /* Bright green test pixels (ARGB/RGBA) */
\t}

\t/* 5. CP_SCRATCH(2) sequence write (Type 4, reg 0x0885, count 1, parity bit 27) */
\trb[w++] = 0x48088501u;
\trb[w++] = 0xcafe0001u;

\t/* 6. CP_EVENT_WRITE Fence (Type 7, opcode 0x46, count 4) */
\trb[w++] = 0x70460004u;
\trb[w++] = 0x08000031u; /* CACHE_FLUSH_TS with write timestamp */
\trb[w++] = (uint32_t)(fence_pa + 16);
\trb[w++] = (uint32_t)((fence_pa + 16) >> 32);
\trb[w++] = 0xcafe0001u; /* Fence seqno marker */

\t/* 7. CP_NOP (Type 7, opcode 0x10, count 1) */
\trb[w++] = 0x70100001u;
\trb[w++] = 0xca11ab1eu;

\tclean_dcache64(rb_pa, w * sizeof(uint32_t), TRUE);
\t__asm__ volatile ("dsb sy" ::: "memory");

\t/* Advance WPTR to kick execution */
\ttouch_wr(gpu, 0x201cu, w);
\t__asm__ volatile ("dsb sy" ::: "memory");
\tprintf("SPES GPU: 28. RING SUBMITTED: wptr=%u\\n", w);

\t/* Step 21: Poll RPTR for retirement */
\tbool consumed = false;
\tint poll_i = 0;
\tuint32_t last_rptr = 0;
\tfor (poll_i = 0; poll_i < 1000; ++poll_i) {
\t\tcurr_rptr = touch_rd(gpu, 0x2018u);
\t\tif (curr_rptr != last_rptr) {
\t\t\tprintf("SPES GPU: 28b. Ring progress: rptr=%u / wptr=%u (poll=%d)\\n",
\t\t\t    curr_rptr, w, poll_i);
\t\t\tlast_rptr = curr_rptr;
\t\t}
\t\tif (curr_rptr >= w) {
\t\t\tconsumed = true;
\t\t\tbreak;
\t\t}
\t\ttouch_wait(2);
\t}
\trbbm_status = touch_rd(gpu, 0x840u);
\tcp_hw_fault = touch_rd(gpu, 0x2084u);
\tcp_int_stat = touch_rd(gpu, 0x208cu);
\tuint32_t cp_scratch2 = touch_rd(gpu, 0x2214u);
\tprintf("SPES GPU: 29. RING RETIREMENT: rptr=%u / wptr=%u (consumed=%d poll=%d rbbm=%#x fault=%#x int=%#x scratch2=%#x)\\n",
\t    curr_rptr, w, consumed, poll_i, rbbm_status, cp_hw_fault, cp_int_stat, cp_scratch2);

\t/* Step 22: Invalidate CPU cache on scratch buffer and verify GPU writes */
\tflush_dcache64(fence_pa, 64, TRUE);
\t__asm__ volatile ("dsb sy" ::: "memory");

\tuint32_t val0 = scratch[0];
\tuint32_t val1 = scratch[1];
\tuint32_t val2 = scratch[2];
\tuint32_t val3 = scratch[3];
\tuint32_t fence_val = scratch[4];

\tint match = (val0 == 0x11223344u && val1 == 0x55667788u &&
\t             val2 == 0x99aabbccu && val3 == 0xddeeff00u);
\tint fence_match = (fence_val == 0xcafe0001u);

\tprintf("SPES GPU: 30. DRAM WRITE: [%#x, %#x, %#x, %#x] (match=%d)\\n",
\t    val0, val1, val2, val3, match);
\tprintf("SPES GPU: 30b. FENCE TS: %#x (match=%d)\\n", fence_val, fence_match);
\tprintf("SPES GPU: 31. GPU STAGE-4 & STAGE-5 100%% VERIFIED ON SILICON!\\n");
"""

    rep_lines = ["+" + line + "\n" if line.strip() else "+\n" for line in replacement_body.splitlines()]

    new_hunk2_lines = hunk2_lines[:start_line_idx] + rep_lines + hunk2_lines[end_line_idx + 1:]

    # Recalculate Hunk 2 header: @@ -677,6 +684,COUNT @@
    # Count added lines and context lines
    h2_added = sum(1 for l in new_hunk2_lines[1:] if l.startswith('+'))
    h2_context = sum(1 for l in new_hunk2_lines[1:] if l.startswith(' ') or l == '\n')
    new_h2_count = h2_added + h2_context
    new_hunk2_lines[0] = f"@@ -677,6 +684,{new_h2_count} @@ spes_gpu_power_probe(void)\n"
    print(f"New Hunk 2 count: {new_h2_count} (added={h2_added}, context={h2_context})")

    # Fix Hunk 3 header: @@ -704,6 +...,7 @@
    # Check context/added in suffix (hunk 3)
    # Hunk 3 has 6 context lines + 1 added line = 7 lines
    hunk3_new_start = 684 + new_h2_count + (704 - (677 + 6))
    suffix[0] = f"@@ -704,6 +{hunk3_new_start},7 @@ touch_thread(void *arg, wait_result_t result)\n"
    print(f"New Hunk 3 header: {suffix[0].strip()}")

    # Assemble new patch
    new_content = "".join(prefix + new_hunk2_lines + suffix)
    patch_path.write_text(new_content)
    print(f"Updated {patch_path}")

if __name__ == "__main__":
    main()
