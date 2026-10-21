# Upstream hardware review — 2026-10-21

Reviewed MakrSas/ios-topaz `89451b811a4e6cc5cdcf734c45887163d92c599e`.
User reports spes finally reached iOS UI after waiting, but it is slow.

## First adaptation batch

- Upstream 0128 (commit e9c0b8f): remove unmatched IOKit-daemon busy hold.
  Imported as 0094; applies cleanly. Avoids waiting for a daemon that never
  reports readiness in this built-in-driver configuration.
- Upstream 0138 (f999958): publish empty IOAcceleratorES to avoid QuartzCore's
  30-second lookup timeout. Adapted as 0095 without topaz backlight/MDP
  dependencies. This is NOT GPU acceleration. `sweetaccel=0` disables it.
- Existing PMIC key reader can be tested on spes: live FDT has PM6125 USID0,
  power-on@800, GPIO5 volume-up, SPMI core0x1c40000/observer0x3e00000/
  config0x1c0a000. Patch0096 permits `sweetkeys=1` on spes; still off by default
  and USB remains disabled. Hardware behavior needs device testing.

## Remaining review/port work

- GPU: upstream README says HackiOS acceleration source is not published here.
  No usable Adreno acceleration implementation in this fetched branch.
- Wi-Fi: upstream0113–0130 contains PAS modem boot, firmware loading from
  modem_a, GLINK/QRTR services, WLFW and WLAN protocol/data path. Live spes FDT
  matches modem reservation0x4ab00000+0x6900000 and SMEM0x46000000+0x200000.
  Firmware/board data, other carveouts, DMA pool, RF/clock assumptions and EFS
  handling still need comparison. Do not enable wholesale on that evidence.
- Battery: topaz0091 assumes SM5602 gauge@0x71 plus charger@0x6a on SE1.
  Spes live FDT includes sc8551@0x65; identify all active gauge/charger devices
  before using it. Do not enable topaz driver blindly.
- Display: upstream0092–0111 adds direct MDP scanout, cache maintenance,
  buffering and DSI/backlight. Audit RAM allocations and spes panel commands.
- Surface compatibility0131–0139: evaluate separately from hardware changes;
  interfaces/state lifetime fixes have interdependencies.
- CPU: current tested boot uses one Gold core. Four Gold CPUs exist in ADT;
  multi-core boot must be tested before changing the normal profile.
- Other upstream limits remain: Bluetooth, cellular, audio, camera, sensors,
  GPS and RTC are not reported working in the upstream README.

Local patch dry-runs passed; 11 host tests passed. New kernel/device tests
pending. Keep installed root and working 0093 boot image as fallback.
