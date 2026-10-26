#!/usr/bin/env python3
"""Audio plug-ins as HackiOS has them, on a mounted offline iOS root (never the phone).

  root-audio-hackios-layout.py ROOT [--undo]

- /Library/Audio/Plug-Ins/HAL.disabled/VirtualAudio.plugin goes back to /Library/Audio/Plug-Ins/HAL/:
  iOS's virtual audio device, which takes the real output device and drives it. sweet-root-tweaks.py
  audio() moved it aside in root v12 (2026-10-20), when there was no audio device; without it
  RedwoodAudio.driver is loaded but never asked to play (all31-all33).
- Every bundle in /System/Library/Audio/Plug-Ins/HAL but RedwoodAudio.driver moves to
  /System/Library/Audio/Plug-Ins/HAL.disabled/ (HackiOS init.c: "our audio device, not Apple's
  plug-ins"; AppleAOPAudioPlugin is the iPhone's audio processor, which this phone lacks).
--undo moves everything back.
"""
import os
import shutil
import sys


def move(src, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))
    if os.path.exists(dst):
        sys.exit(f'{dst} exists: not moving {src}')
    shutil.move(src, dst)
    print(f'{src} -> {dst_dir}/')


def main():
    if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != '--undo'):
        sys.exit(__doc__)
    root, undo = sys.argv[1], len(sys.argv) == 3
    lib = os.path.join(root, 'Library/Audio/Plug-Ins')
    sys_hal = os.path.join(root, 'System/Library/Audio/Plug-Ins/HAL')
    sys_off = sys_hal + '.disabled'
    if undo:
        move(os.path.join(lib, 'HAL/VirtualAudio.plugin'), os.path.join(lib, 'HAL.disabled'))
        for name in sorted(os.listdir(sys_off)):
            move(os.path.join(sys_off, name), sys_hal)
        return
    move(os.path.join(lib, 'HAL.disabled/VirtualAudio.plugin'), os.path.join(lib, 'HAL'))
    for name in sorted(os.listdir(sys_hal)):
        if name != 'RedwoodAudio.driver':
            move(os.path.join(sys_hal, name), sys_off)
    left = sorted(os.listdir(sys_hal))
    if left != ['RedwoodAudio.driver']:
        sys.exit(f'HAL left with {left}')


if __name__ == '__main__':
    main()
