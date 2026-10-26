#!/usr/bin/env python3
"""Add one run-once job to launchd.plist (SWEET bring-up tests).

  add-launchd-job.py [--env KEY=VALUE ...] IN.plist OUT.plist LABEL PROGRAM [ARG ...]

IN is /System/Library/xpc/launchd.plist (binary plist, read by launchd when booted with
launchd_unsecure_cache=1). The job runs PROGRAM as root once at load (LaunchOnlyOnce, no
KeepAlive), with stdout/stderr on /dev/console. A job with the same label is replaced.
"""
import plistlib
import sys


def main():
    argv, env = sys.argv[1:], {}
    while len(argv) >= 2 and argv[0] == '--env':
        key, _, value = argv[1].partition('=')
        env[key] = value
        argv = argv[2:]
    if len(argv) < 4:
        sys.exit(__doc__)
    src, dst, label, args = argv[0], argv[1], argv[2], argv[3:]
    with open(src, 'rb') as f:
        plist = plistlib.load(f)
    key = f'/System/Library/LaunchDaemons/{label}.plist'
    plist['LaunchDaemons'][key] = {
        'Label': label, 'ProgramArguments': args, 'RunAtLoad': True, 'LaunchOnlyOnce': True,
        'KeepAlive': False, 'UserName': 'root', 'POSIXSpawnType': 'Interactive',
        'StandardOutPath': '/dev/console', 'StandardErrorPath': '/dev/console',
    }
    if env:
        plist['LaunchDaemons'][key]['EnvironmentVariables'] = env
    with open(dst, 'wb') as f:
        plistlib.dump(plist, f, fmt=plistlib.FMT_BINARY)
    print(f'{key}: {" ".join(args)}')


if __name__ == '__main__':
    main()
