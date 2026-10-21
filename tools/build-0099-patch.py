#!/usr/bin/env python3
"""Generate xnu/patches/0099-spes-modem-wifi.patch using git diff for 100% verified git-apply compatibility.
"""
import tempfile
import subprocess
from pathlib import Path

def main():
    root = Path("/Users/adya/Documents/iospes")
    xnu_check = root / "research" / "xnu-check"

    fb_curr = (xnu_check / "iokit/Kernel/arm/SweetFramebuffer.cpp").read_text()
    fb_base = fb_curr.replace('extern "C" void spes_modem_init(void);  /* iokit/Kernel/arm/SpesModem.cpp (boot-arg modem=1) */\n', '')
    fb_base = fb_base.replace('\tspes_modem_init();\n', '')

    ufs_curr = (xnu_check / "bsd/dev/sweet_ufs.c").read_text()
    idx = ufs_curr.find("/*\n * spes: read-only access to other GPT partitions")
    end_idx = ufs_curr.find("static int\nufs_take_over_host(void)")
    assert idx != -1 and end_idx != -1
    ufs_base = ufs_curr[:idx] + ufs_curr[end_idx:]

    files_base = """iokit/Families/IONVRAM/IONVRAMController.cpp				optional iokitcpp

# Power Domains
iokit/Kernel/IOPMrootDomain.cpp    					optional iokitcpp

# SMP
iokit/Kernel/arm/AppleARMSMP.cpp    					optional iokitcpp

# SWEET device-tree platform (empty translation unit on other boards)
iokit/Kernel/arm/SweetPlatformExpert.cpp                         optional iokitcpp

iokit/Kernel/arm/SweetCPU.cpp                                    optional iokitcpp
iokit/Kernel/arm/SweetEntitlements.cpp                           optional iokitcpp
iokit/Kernel/arm/SweetKeyStore.cpp                               optional iokitcpp
iokit/Kernel/arm/SweetWatchdog.cpp                               optional iokitcpp
iokit/Kernel/arm/SweetSurface.cpp                                optional iokitcpp
iokit/Kernel/arm/SweetFramebuffer.cpp                            optional iokitcpp
iokit/Kernel/arm/SweetBattery.cpp                                optional iokitcpp
iokit/Kernel/arm/hid/SweetHID.cpp                                optional iokitcpp
iokit/Kernel/arm/hid/IOHIDEvent.cpp                              optional iokitcpp
iokit/Kernel/arm/hid/IOHIDEventServiceQueue.cpp                  optional iokitcpp
iokit/Kernel/arm/hid/IOHIDEventServiceUserClient.cpp             optional iokitcpp
"""

    files_mod = files_base.replace(
        "iokit/Kernel/arm/SweetCPU.cpp                                    optional iokitcpp\n",
        "iokit/Kernel/arm/SweetCPU.cpp                                    optional iokitcpp\niokit/Kernel/arm/SpesModem.cpp                                   optional iokitcpp\n"
    )

    spes_modem = (xnu_check / "iokit/Kernel/arm/SpesModem.cpp").read_text()

    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        subprocess.run(["git", "init"], cwd=tpath, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=tpath, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tpath, check=True)

        (tpath / "iokit/conf").mkdir(parents=True)
        (tpath / "iokit/Kernel/arm").mkdir(parents=True)
        (tpath / "bsd/dev").mkdir(parents=True)

        (tpath / "iokit/conf/files.arm64").write_text(files_base)
        (tpath / "iokit/Kernel/arm/SweetFramebuffer.cpp").write_text(fb_base)
        (tpath / "bsd/dev/sweet_ufs.c").write_text(ufs_base)

        subprocess.run(["git", "add", "."], cwd=tpath, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=tpath, check=True, capture_output=True)

        (tpath / "iokit/conf/files.arm64").write_text(files_mod)
        (tpath / "iokit/Kernel/arm/SweetFramebuffer.cpp").write_text(fb_curr)
        (tpath / "bsd/dev/sweet_ufs.c").write_text(ufs_curr)
        (tpath / "iokit/Kernel/arm/SpesModem.cpp").write_text(spes_modem)

        subprocess.run(["git", "add", "-N", "iokit/Kernel/arm/SpesModem.cpp"], cwd=tpath, check=True)
        diff_res = subprocess.run(["git", "diff"], cwd=tpath, check=True, capture_output=True, text=True)

        # Verify on clean base
        subprocess.run(["git", "checkout", "."], cwd=tpath, check=True, capture_output=True)
        subprocess.run(["rm", "-f", "iokit/Kernel/arm/SpesModem.cpp"], cwd=tpath, check=True)

        apply_res = subprocess.run(["git", "apply", "--check"], input=diff_res.stdout, cwd=tpath, capture_output=True, text=True)
        assert apply_res.returncode == 0, f"git apply --check failed: {apply_res.stderr}"

        out_patch = root / "xnu" / "patches" / "0099-spes-modem-wifi.patch"
        out_patch.write_text(diff_res.stdout)
        print(f"Generated and verified {out_patch} ({len(diff_res.stdout)} bytes, {len(diff_res.stdout.splitlines())} lines)")

if __name__ == "__main__":
    main()
