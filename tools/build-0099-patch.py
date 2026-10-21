#!/usr/bin/env python3
"""Generate xnu/patches/0099-spes-modem-wifi.patch with exact 3-line standard context.
"""
import difflib
from pathlib import Path

def main():
    root = Path("/Users/adya/Documents/iospes")
    xnu_check = root / "research" / "xnu-check"

    # Part 1: iokit/conf/files.arm64
    diff_files = """--- a/iokit/conf/files.arm64
+++ b/iokit/conf/files.arm64
@@ -10,6 +10,7 @@ iokit/Kernel/arm/AppleARMSMP.cpp    					optional iokitcpp
 iokit/Kernel/arm/SweetPlatformExpert.cpp                         optional iokitcpp
 
 iokit/Kernel/arm/SweetCPU.cpp                                    optional iokitcpp
+iokit/Kernel/arm/SpesModem.cpp                                   optional iokitcpp
 iokit/Kernel/arm/SweetEntitlements.cpp                           optional iokitcpp
 iokit/Kernel/arm/SweetKeyStore.cpp                               optional iokitcpp
 iokit/Kernel/arm/SweetWatchdog.cpp                               optional iokitcpp
"""

    # Part 2: bsd/dev/sweet_ufs.c
    diff_ufs = """--- a/bsd/dev/sweet_ufs.c
+++ b/bsd/dev/sweet_ufs.c
@@ -357,6 +357,107 @@ ufs_find_partition(const char *want)
 	printf("SWEET UFS: no GPT partition named \\"%s\\"\\n", want);
 	return ENOENT;
 }
+
+/*
+ * spes: read-only access to other GPT partitions on LUNs 0-5 (modem firmware in
+ * modem_a, later the EFS copies). Never writes; the LUN0 GPT fence state is untouched.
+ */
+static struct { char name[37]; uint8_t lun; uint64_t first, nblocks; } part_cache[8];
+static unsigned part_cached;
+
+static int
+ufs_lookup_part(const char *want, unsigned *slot)
+{
+	const uint8_t *b = (const uint8_t *)(su.dma + DMA_BOUNCE);
+
+	for (unsigned i = 0; i < part_cached; i++) {
+		if (strcmp(part_cache[i].name, want) == 0) {
+			*slot = i;
+			return 0;
+		}
+	}
+	if (part_cached == sizeof(part_cache) / sizeof(part_cache[0]) || strlen(want) > 36) {
+		return ENOSPC;
+	}
+	for (uint8_t lun = 0; lun < 6; lun++) {
+		su.lun = lun;
+		if (ufs_read_blocks(1, 1) != 0 || memcmp(b, "EFI PART", 8) != 0) {
+			continue;
+		}
+		uint64_t entry_lba;
+		uint32_t nent, esz;
+		memcpy(&entry_lba, b + 72, 8);
+		memcpy(&nent, b + 80, 4);
+		memcpy(&esz, b + 84, 4);
+		if (esz != 128 || nent == 0 || nent * esz > BOUNCE_SIZE ||
+		    ufs_read_blocks(entry_lba, (nent * esz + UFS_BLOCK - 1) / UFS_BLOCK) != 0) {
+			continue;
+		}
+		for (uint32_t i = 0; i < nent; i++) {
+			const uint8_t *e = b + i * esz;
+			char name[37];
+			unsigned c;
+			for (c = 0; c < 36; c++) {
+				uint16_t ch = (uint16_t)(e[56 + 2 * c] | e[57 + 2 * c] << 8);
+				if (ch == 0 || ch > 0x7f) {
+					break;
+				}
+				name[c] = (char)ch;
+			}
+			name[c] = 0;
+			uint64_t first, last;
+			memcpy(&first, e + 32, 8);
+			memcpy(&last, e + 40, 8);
+			if (strcmp(name, want) != 0 || last < first) {
+				continue;
+			}
+			unsigned k = part_cached++;
+			strlcpy(part_cache[k].name, want, sizeof(part_cache[k].name));
+			part_cache[k].lun = lun;
+			part_cache[k].first = first;
+			part_cache[k].nblocks = last - first + 1;
+			printf("SWEET UFS: partition %s: LUN %u blocks 0x%llx+0x%llx (read-only)\\n",
+			    want, lun, first, last - first + 1);
+			*slot = k;
+			return 0;
+		}
+	}
+	return ENOENT;
+}
+
+int sweet_ufs_read_part(const char *want, uint64_t off, void *dst, uint64_t len);
+int
+sweet_ufs_read_part(const char *want, uint64_t off, void *dst, uint64_t len)
+{
+	unsigned slot = 0;
+	int error;
+
+	if (!su.ready) {
+		return EAGAIN;
+	}
+	lck_mtx_lock(&sweet_ufs_lock);
+	uint8_t saved = su.lun;
+	error = ufs_lookup_part(want, &slot);
+	uint64_t bytes = error ? 0 : part_cache[slot].nblocks * UFS_BLOCK;
+	if (!error && (off > bytes || len > bytes - off)) {
+		error = EINVAL;
+	}
+	for (uint64_t done = 0; !error && done < len;) {
+		uint64_t pos = off + done;
+		uint32_t skip = (uint32_t)(pos % UFS_BLOCK);
+		uint32_t want_b = (uint32_t)MIN(len - done, (uint64_t)(BOUNCE_SIZE - skip));
+		uint32_t blocks = (skip + want_b + UFS_BLOCK - 1) / UFS_BLOCK;
+		su.lun = part_cache[slot].lun;
+		error = ufs_read_blocks(part_cache[slot].first + pos / UFS_BLOCK, blocks);
+		if (!error) {
+			memcpy((uint8_t *)dst + done, (const uint8_t *)(su.dma + DMA_BOUNCE) + skip, want_b);
+			done += want_b;
+		}
+	}
+	su.lun = saved;
+	lck_mtx_unlock(&sweet_ufs_lock);
+	return error;
+}
+
 static int
 ufs_take_over_host(void)
 {
"""

    # Part 3: iokit/Kernel/arm/SweetFramebuffer.cpp
    diff_fb = """--- a/iokit/Kernel/arm/SweetFramebuffer.cpp
+++ b/iokit/Kernel/arm/SweetFramebuffer.cpp
@@ -37,6 +37,7 @@
 #include "SweetSurface.h"
 
 extern "C" int sweet_console_muted;     /* osfmk/console/serial_console.c */
+extern "C" void spes_modem_init(void);  /* iokit/Kernel/arm/SpesModem.cpp (boot-arg modem=1) */
 
 #if defined(SWEET)
 #include <IOKit/IOService.h>
@@ -164,6 +165,7 @@ AppleCLCD::start(IOService *provider)
 	if (!IOService::start(provider)) {
 		return false;
 	}
+	spes_modem_init();
 	PE_current_console(&video);
 	fPhys = video.v_baseAddr;
 	fWidth = (uint32_t)video.v_width;
"""

    # Part 4: iokit/Kernel/arm/SpesModem.cpp (new file)
    spes_modem_path = xnu_check / "iokit" / "Kernel" / "arm" / "SpesModem.cpp"
    modem_content = spes_modem_path.read_text()
    diff_modem = list(difflib.unified_diff(
        [],
        modem_content.splitlines(keepends=True),
        fromfile="/dev/null",
        tofile="b/iokit/Kernel/arm/SpesModem.cpp"
    ))

    # Combine all parts
    full_patch = diff_files + diff_ufs + diff_fb + "".join(diff_modem)
    out_patch = root / "xnu" / "patches" / "0099-spes-modem-wifi.patch"
    out_patch.write_text(full_patch)
    print(f"Generated {out_patch} ({len(full_patch)} bytes, {len(full_patch.splitlines())} lines)")

if __name__ == "__main__":
    main()
