#!/usr/bin/env python3
"""Generate the opt-in ADSP survey and WLFW assignment fix after patch 0099."""
from pathlib import Path
import difflib

ROOT = Path(__file__).resolve().parents[1]
BASE_PATCH = ROOT / 'xnu/patches/0099-spes-modem-wifi.patch'
path = 'iokit/Kernel/arm/SpesModem.cpp'
section = BASE_PATCH.read_text().split('+++ b/' + path + '\n', 1)[1].split('diff --git ', 1)[0]
base = ''.join(line[1:] for line in section.splitlines(keepends=True) if line.startswith('+'))
src = base
src = src.replace('static void\nw_on_msa_info', '#include "spes_wlfw_memory.h"\n\nstatic bool\nw_on_msa_info', 1)
src = src.replace('\tLOG("wlfw: %u MSA region(s)", n);', '''\tif (!spes_msa_regions_valid(v, l, WLFW_MSA_BASE, WLFW_MSA_SIZE)) {
\t\tLOG("wlfw: invalid MSA region list; ownership unchanged");
\t\treturn false;
\t}
\tLOG("wlfw: %u MSA region(s)", n);''', 1)
old = '''\t\tif (addr < WLFW_MSA_BASE || addr + size > (uint64_t)WLFW_MSA_BASE + WLFW_MSA_SIZE) {
\t\t\tLOG(" out of the MSA window, skipped");
\t\t\tcontinue;
\t\t}
\t\t(void)scm_assign(addr, size, vm, sec ? 2 : 3);
\t}
}'''
new = '''\t\tif (scm_assign(addr, size, vm, sec ? 2 : 3) != 0) {
\t\t\tLOG("wlfw: MSA assignment failed; not announcing MSA_READY");
\t\t\treturn false; /* Previously assigned regions remain owned; do not retry. */
\t\t}
\t}
\treturn true;
}'''
assert old in src
src = src.replace(old, new, 1)
old = '''\t\t\tw_on_msa_info(d, len);
\t\t\tw_simple(WLFW_MSA_READY, "msa_ready sent");'''
new = '''\t\t\tif (w_on_msa_info(d, len)) {
\t\t\t\tw_simple(WLFW_MSA_READY, "msa_ready sent");
\t\t\t} else {
\t\t\t\tw_step = "MSA validation/assignment failed (stopped)";
\t\t\t}'''
assert old in src
src = src.replace(old, new, 1)
src = src.replace('extern "C" void\nspes_modem_init(void)', '#include "spes_audio_survey.inc"\n\nextern "C" void\nspes_modem_init(void)', 1)
src = src.replace('\tif (started || !PE_parse_boot_argn("modem",', '\tspes_audio_survey_init();\n\tif (started || !PE_parse_boot_argn("modem",', 1)
assert src != base
patch = ''.join(difflib.unified_diff(base.splitlines(True), src.splitlines(True), 'a/' + path, 'b/' + path))
for name in ('spes_wlfw_memory.h', 'spes_smem_read.h', 'spes_audio_survey.inc'):
    text = (ROOT / 'xnu/peripherals' / name).read_text()
    patch += ''.join(difflib.unified_diff([], text.splitlines(True), '/dev/null', 'b/iokit/Kernel/arm/' + name))
(ROOT / 'xnu/patches/0103-spes-audio-survey-wlfw-memory.patch').write_text(patch)
print('Generated 0103-spes-audio-survey-wlfw-memory.patch')
