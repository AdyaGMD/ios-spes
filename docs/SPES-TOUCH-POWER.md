# Redmi Note 11 touch power investigation

## Observations (2026-10-20)

XNU 0091 initializes SE2 I2C firmware (0x303/protocol 3), verifies FIFO
packing, then receives NACKs (ENXIO 6, IRQ 0x40000409) from addresses 0x5d
and 0x38. Chip ID is 00:00; the touch thread stops and RAM PID1 continues.

The same handset in temporary OrangeFox reports FocalTech chip 0x5452 and
a successful probe. Sysfs reports pm6125_l9 enabled at 1800000 microvolts,
with one user. The live device tree connects touchscreen vcc_i2c-supply to
that regulator. The FT3418 Linux driver enables this supply as well as GPIO98
AVDD. XNU currently controls GPIO98 but does not request L9 power.

This makes missing I/O power a hypothesis, not proof that L9 was off in XNU.
Post-power GPIO readbacks are also needed to check power-enable/reset/mux.

## Verified transport details

Reference: Jabiyeff/kernel_xiaomi_sm6225 commit
6c2b3e7528a0778cd80c95eabb490746b5422f8c.

- `drivers/rpmsg/qcom_glink_rpm.c`: GLINK transport over RPM message RAM.
- Live FDT: message RAM physical 0x045f0000, size 0x7000.
- Last 256 bytes contain TOC magic 0x67727430 and at most 20 entries.
- FIFO IDs: ap2r 0x61703272, r2ap 0x72326170. Each entry has offset and
  ring size; tail/head words precede ring data. Cursor writes change ownership.
- Recovery rpmsg device: `soc:rpm-glink.rpm_requests.-1.-1`.
- Recovery `/sys/module/rpm_smd/parameters/rpm_msg_fmt_ver` reads 0.
- `drivers/rpmsg/rpm-smd.c`: v0 request header contains service, request
  length, message ID, active/sleep set, resource type/id and data length.
- `pm6125-rpm-regulator.dtsi`: resource `ldoa`, ID 9.
- `drivers/regulator/rpm-smd-regulator.c`: `uv` voltage and `swen` enable keys.
- `drivers/rpmsg/qcom_glink_native.c`: channel negotiation, intentless data
  transport, signals and replies must be handled before issuing RPM requests.

The existing SM7150 sweet_rpmh helper targets a different controller and
must not be used for spes. Recovery has neither debugfs support nor /dev/mem.

## Next hardware check

Patch 0092 prints the TOC and matching ring metadata without writing RPM RAM,
then prints AVDD/reset/SDA/SCL configuration and I/O readbacks after the existing
touch power sequence. It bounds and aligns every variable MMIO read. It does
not negotiate GLINK, advance cursors, enable L9, or send a PMIC request.

A future client needs bounded waits, validated framing, channel ownership,
matching message-ID acknowledgements, and failure reporting before a touch
probe can depend on a regulator request. Use only the observed 1.8V target;
never infer a PMIC register address or substitute another platform's transport.
