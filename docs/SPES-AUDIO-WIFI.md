# spes audio and Wi-Fi bring-up — 2026-10-24

## Status and evidence

Neither sound playback nor Wi-Fi association is verified under XNU. Earlier notes
calling Wi-Fi “verified” describe a build, not an observed connection. GPU work
belongs to the other agent. This investigation did not modify its code or boot
an audio/Wi-Fi test kernel.

Read-only collection used OrangeFox, live `/sys/firmware/fdt`, and vendor_a mounted
with `ro,noload`. Vendor was unmounted afterwards. Recovery reports no ALSA sound
cards. Its kernel and stock audio-module vermagic differ, so no modules were
force-loaded. No amplifier registers, radio settings, or device partitions were
written. The phone remains in recovery.

Local evidence is ignored under `research/spes-audio-wifi/`: live.dtb,
recovery-dmesg.txt, recovery-inventory.txt, module-inventory.txt, mixer_paths.xml,
audio_platform_info.xml, aw87xxx_acf.bin, device-tree.json, acf-metadata.json.
These artifacts and firmware must not be committed.

## Audio hardware facts

| Component | Observed configuration |
| --- | --- |
| DSP | ADSP PAS 1, SMEM remote processor 2; reserved 0x53800000 + 0x02e00000 |
| DSP crash record | SMEM item 423 |
| SMP2P | SMEM items 443/429; mailbox channel 10; GIC SPI 279 |
| GLINK | SMEM transport; mailbox channel 8; GIC SPI 277 |
| Mailbox | qcom,bengal-apcs-hmss-global at 0x0f111000, size 0x1000 |
| APR channel | apr_audio_svc, 20 intents of 512 bytes |
| QRTR channel | IPCRTR |
| Codec | Bolero RX/TX/VA macros, WCD937x SoundWire RX/TX slaves |
| Amplifiers | awinic,aw87xxx_pa on I2C at 0x04a84000 |
| Amplifier 0 | address 0x5b, dev_index 0, reset GPIO 35 |
| Amplifier 1 | address 0x58, dev_index 1, reset GPIO 106 |

Stock `speaker` mixer path enables EAR and AUX DAC outputs, both Awinic Music
profiles, RX_MACRO AIF1_PB, and RX_CDC_DMA_RX_0 with two channels. The board has
`qcom,tdm-audio-intf=0`. This is not HackiOS redwood's PRI_TDM_RX_0 speaker route.

The stock 2460-byte ACF has 12 entries; all CRC8 checks passed. Device strings say
`aw87559`, with default-device profiles selected by dev_index. This is configuration
evidence, not a live chip-ID measurement. No profile has been applied. The offline
`tools/spes_acf.py` validates header/version, table and payload bounds, coverage,
and CRCs; it reports metadata only and does not output register-write sequences.
It accepts ACF versions 0.0.0.1 and 1.0.0.0, rejecting unknown versions.

## Wi-Fi hardware facts

Live DT identifies qcom,icnss at 0x0c800000 + 0x00800000, MSA reserved region
0x51900000 + 0x00100000, SMMU SID 0x1a0/mask 1. These latter two settings match
patch 0099. DT fastmap IOVA pool is 0xa0000000 + 0x10000000; the existing code
instead installs an identity context, which needs a separate DMA ownership audit.
Recovery ICNSS probe succeeds, but that does not demonstrate XNU firmware boot,
scan, association, or packet transfer. Do not infer an exact radio chip ID from
the compatible string. HackiOS's WCN6750/WPSS/ath11k path cannot be copied wholesale.

Supply references: RPM L17 (1.3rfa), L16 (1.8xo), L23 (3.3ch0), L8 (cxmx).
Stock qca_cld3_wlan module and WCNSS_qcom_cfg.ini exist. Existing 0099 already has
modem firmware loading, GLINK/QRTR, WLFW, WMI and HTT; audit it before adding a
second transport or enabling its broad modem/Wi-Fi boot sequence.

## Reference pins and next implementation

- [HackiOS kernel](https://github.com/oosexgang/hackios-xnu-kernel/tree/d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c):
  redwood_audio.c and its HAL ABI are useful for PCM delivery; redwood_adsp.c,
  redwood_sound.c and redwood_speaker.c describe APR/ADM/ASM and playback lifecycle.
  Its AW88261 profiles, IPCC/RPMh setup and TDM route are different hardware.
- [Official Xiaomi spes audio source](https://github.com/MiCode/vendor_qcom_opensource_audio-kernel/tree/054e4f359514ddd1509095b15ad9f8e1607086a4):
  local research/spes-audio-kernel; asoc/bengal.c, codecs/aw87xxx,
  codecs/wcd937x and Bolero macro/SoundWire drivers are the device-specific source.
- Xiaomi main kernel spes-r-oss pin 88afd32564211f4cfb60171ed8cbeaa734860601;
  audio lives in the separate repository above, not its techpack directory.

Next: adapt the ADSP transport using the existing SMEM/SCM infrastructure and
APCS mailbox, verify firmware startup and APR service response with amplifiers
held off, then implement the CDC DMA/SoundWire codec route. Only after matching
chip IDs and validated profiles should a bounded, low-volume PCM test run.
For Wi-Fi, first capture the existing modem/WLFW startup result after auditing
DMA mappings and firmware provenance; no reason yet to replace it with ath11k.

Reproduce offline checks:

```sh
python3 tools/spes-peripheral-inventory.py research/spes-audio-wifi/live.dtb
python3 tools/spes_acf.py research/spes-audio-wifi/aw87xxx_acf.bin
python3 -m unittest discover -s tests -p test_spes_acf.py
```
