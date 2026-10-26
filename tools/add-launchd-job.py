#!/usr/bin/env python3
"""Add one run-once job to launchd.plist (SWEET bring-up tests).

  add-launchd-job.py IN.plist OUT.plist LABEL PROGRAM [ARG ...]

IN is /System/Library/xpc/launchd.plist (binary plist, read by launchd when booted with
launchd_unsecure_cache=1). The job runs PROGRAM as root once at load (LaunchOnlyOnce, no
KeepAlive), with stdout/stderr on /dev/console. A job with the same label is replaced.
"""
import plistlib
import sys


def main():
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    src, dst, label, args = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
    with open(src, 'rb') as f:
        plist = plistlib.load(f)
    key = f'/System/Library/LaunchDaemons/{label}.plist'
    plist['LaunchDaemons'][key] = {
        'Label': label, 'ProgramArguments': args, 'RunAtLoad': True, 'LaunchOnlyOnce': True,
        'KeepAlive': False, 'UserName': 'root', 'POSIXSpawnType': 'Interactive',
        'StandardOutPath': '/dev/console', 'StandardErrorPath': '/dev/console',
    }
    with open(dst, 'wb') as f:
        plistlib.dump(plist, f, fmt=plistlib.FMT_BINARY)
    print(f'{key}: {" ".join(args)}')


if __name__ == '__main__':
    main()
