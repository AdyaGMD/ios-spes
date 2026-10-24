#!/usr/bin/env python3
"""Generate the combined graphics patch from a build tree through patch 0099.
Does not dispatch CI or change the device. Keep imported sources in xnu/graphics.
"""
import difflib
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
base=Path(sys.argv[1])
def diff(name,old,new):
    return f'diff --git a/{name} b/{name}\n'+('new file mode 100644\n' if not old else '')+''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+name if old else '/dev/null',tofile='b/'+name))
name='bsd/dev/sweet_touch.c'; old=(base/name).read_text();s=old
if 'spes_gpu_backend.h' in s: raise SystemExit('Expected unmodified 0099 baseline')
s=s.replace('static void\nspes_glink_rpm_probe(void)', '#include "spes_gpu_backend.h"\n\nstatic void\nspes_glink_rpm_probe(void)')
s=s.replace('\tint enabled = 0;\n\t(void)PE_parse_boot_argn("spesrpmprobe",', '\tint combined = 0;\n\t(void)PE_parse_boot_argn("spesgpu", &combined, sizeof(combined));\n\tint enabled = combined;\n\t(void)PE_parse_boot_argn("spesrpmprobe",')
for arg,var,value in [('spesgpuhalt','halt_test',0),('spesgpurun','run_sqe',1),('spesgpudisplay','display_test',1),('spesgpuib','bridge_test',1),('spesgpurepeat','repeat_test',1),('spesgpuremap','remap_test',1),('spesgpubuffers','buffer_test',1)]:
    line=f'\t(void)PE_parse_boot_argn("{arg}", &{var}, sizeof({var}));'
    assert line in s,arg
    s=s.replace(line,line+f'\n\tif (combined == 1) {var} = {value};')
s=s.replace('\t\t(void)spes_gpu_retire(gpu, smmu, context, w, "REPEAT_STATUS");', '\t\tpassed = passed && completed == 512 && wraps >= 2 &&\n\t\t    spes_gpu_retire(gpu, smmu, context, w, "REPEAT_STATUS");')
s=s.replace('\t\t    stages, (unsigned)unmapped, l3_target[16]);', '\t\t    stages, (unsigned)unmapped, l3_target[16]);\n\t\tpassed = remap_ok && stages == 3 && unmapped && clean;')
s=s.replace('\t\t    (unsigned)released, (unsigned)reused, (unsigned)cleaned, (unsigned)pool.poisoned);', '\t\t    (unsigned)released, (unsigned)reused, (unsigned)cleaned, (unsigned)pool.poisoned);\n\t\tpassed = ok && released && reused && cleaned;')
needle='\ttouch_wr(gpu, 0x2020u, 3u);\n}\n\nstatic void\ntouch_thread'
assert needle in s
s=s.replace(needle,'\tif (combined == 1 && passed &&\n\t    spes_gpu_backend_start(gpu, smmu, context, gpu_dma_va, l2, w)) return;\n'+needle)
# Device-tree-backed A610 layout; byte offsets from downstream a6xx_reg.h.
setup = """\tif (combined == 1) {
\t\t/* spes: UBWC1, 64-byte accesses, highest bank bit14; GMEM132KiB. */
\t\ttouch_wr(gpu, 0x382cu, 0x00100000u);
\t\ttouch_wr(gpu, 0x3830u, 0u);
\t\ttouch_wr(gpu, 0x3834u, 0x00120fffu);
\t\ttouch_wr(gpu, 0x3838u, 0u);
\t\ttouch_wr(gpu, 0x23820u, 0xbu); /* RB_NC_MODE_CNTL */
\t\ttouch_wr(gpu, 0x2d810u, 0xbu); /* TPL1_NC_MODE_CNTL */
\t\ttouch_wr(gpu, 0x2b808u, 0xbu); /* SP_NC_MODE_CNTL */
\t\ttouch_wr(gpu, 0x3804u, 0x00a00000u); /* UCHE_MODE_CNTL */
\t\ttouch_wr(gpu, 0x3864u, 1u); /* UCHE_CLIENT_PF */
\t}
"""
anchor='\t/* Clear pending interrupts in RBBM and CP */'
assert anchor in s
s=s.replace(anchor,setup+anchor)
patch=diff(name,old,s)
for name,local in [('bsd/dev/spes_gpu_backend.h','spes_gpu_backend.h'),('iokit/Kernel/arm/RedwoodGPU.cpp','RedwoodGPU.cpp')]:
    patch+=diff(name,'',(ROOT/'xnu/graphics'/local).read_text())
name='iokit/conf/files.arm64';old=(base/name).read_text();new=old+'\niokit/Kernel/arm/RedwoodGPU.cpp optional iokitcpp\n';patch+=diff(name,old,new)
(ROOT/'xnu/patches/0100-spes-graphics-service.patch').write_text(patch)
