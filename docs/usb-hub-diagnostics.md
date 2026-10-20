# Gaokun USB Hub investigation (2026-10-19)

## Evidence and confirmed scope

The Genesys 05e3:0610/0616 hub has successfully enumerated with Logitech and
Keychron receivers in earlier boots. It is intermittently unusable, with two
observed failure classes: xHCI STOP_RING timeout followed by `HC died`, and
failure to enable/debounce the port before any hub enumeration.

Evidence lives on the affected host under `/var/log/gaokun-usb/`, not in Git:

- `20261019-boot-6548ce35`: previous unbind/rebind failure and subsequent boot.
- `20261019-phy-detail`: same-port replug after the controller was already dead.
- `20261019-boot-098866e4`: boot with hub disconnected, then first hotplug with
  charger attached, followed by removing only the hub charger.

The third experiment includes suspend/resume before hotplug; it is not a pure
cold-boot/no-suspend comparison. Use monotonic times, since the RTC jumps during
startup. Resolve the platform parent address instead of relying on xHCI auto
IDs or USB bus numbering, which change between boots.

At 255.519 s the first hotplug invokes orientation reconfiguration on the
primary combo PHY. NVMe correctable PCIe errors and the integrated keyboard's
USB disconnect follow at about 255.544 s. At 266.723 s the same PHY changes
mode 2 (USB3-only) to 0 (USB3+DP). The hub does not enumerate and usb4-port1
reports `Cannot enable` approximately every four seconds. No `HC died` is
recorded in that experiment.

Removing only the hub charger changes port0 from power sink to source while
the data role stays host. At 434.215 s / 435.321 s the PHY changes 0 -> 2 -> 0,
again adjacent to integrated keyboard / NVMe errors. The hub remains absent.
This rules out charger removal as recovery of the existing state, not PD as a
possible initial trigger. The generic cable warning is not a cable diagnosis.

`vreg_l4d` is shared with PCIe and the integrated USB PHYs, but regulator
summary shows five active consumers. Disabling the combo PHY's vote alone
should not turn that rail off. Shared-rail collapse is not established.
The correlation instead motivates isolating the external common-reset/clock
cycle from internal PHY reconfiguration.

## Confirmed source fixes

- **0014**: the EC ACK encoder computes `1 << -1` before handling the empty ACK
  sentinel. Fatal UBSAN reproduces this in the real function; validate the
  one-byte port mask before shifting.
- **0015**: after upstream moved PIPE clock ownership into common init/exit,
  USB power-on still disabled it on timeout. Common cleanup then disables it
  again (or a DP user loses its clock). A forced common reinit failure also
  decrements an `init_count` reference it never acquired. Native tests execute
  the real patched functions and reproduce both bugs when reverting the fixes.

Neither error-path bug has been demonstrated as the cause of the observed
hotplug failure: current hotplug logs do not show a PHY initialization timeout.

## Gaokun3 common-power preservation: 0016

Release 16 enables this path by default on `huawei,gaokun3` for forced Type-C
reconfiguration. It keeps the existing common resource votes and clocks,
uses the DP COM internal software reset, and reprograms mode/orientation
through the existing register sequence. Initial power-up and final shutdown
retain their resource lifecycle. Other boards retain the original behavior.
The read-only module parameter permits boot-time rollback:

```text
phy_qcom_qmp_combo.gaokun_keep_common_power=0
```

The initial `usb-phy-diagnostics` / `-usbdiag1` build defaulted off and was
used with explicit `=0` and `=1` boot entries for comparison.

Native tests cover parameter off/on, exact board matching, USB3+DP / DP-only /
USB3-only register paths, reference-count balance and injected regulator,
clock and USB PHY initialization failures. Hardware testing is still required
for signal integrity, DP routing, orientation changes and xHCI survival.

## Hardware results (2026-10-20)

- Control boot `20cf5229`: charger connected directly to the computer, hub on
  the other USB-C port. The user inserted a flash drive into the hub and then
  replaced it with a mouse. The drive enumerated after a descriptor timeout;
  the external USB2 hub and mouse receiver did not enumerate.
- Enabled boot `cef8062b`: USB2 and USB3 Genesys hubs, Logitech receiver/G304,
  and Keychron receiver enumerated. The user reported the mouse working.
  A subsequent 60-second observation retained all USB device paths/IDs and
  produced no new kernel messages. No xHCI death or port-enable failure was
  recorded. Initial hub re-enumeration and peripheral/port changes also appear
  in this boot's logs.
- Success snapshots and traces are retained under
  `/var/log/gaokun-usb/test-boot-cef8062bb49b49b49cda2d2c779165fa/`.
- The user accepted this as the fix and requested promotion to `main`.
  Extended hotplug, PD, DP and suspend/resume coverage remains follow-up work.

## Further hardware acceptance plan

1. Keep the current boot entry intact. Install only the isolated test packages
   after checking ESP capacity and the standard/EL2 DTB matching the new kernel.
2. Boot with `gaokun_keep_common_power=0` as the control. Save kernel
   version, loaded module identity and capture logs before first hotplug.
3. Boot the same test kernel with the parameter enabled. Verify
   `/sys/module/phy_qcom_qmp_combo/parameters/gaokun_keep_common_power` reports Y.
4. Start the capture service, then test hub-only and charger+hub on both Type-C
   ports and both plug orientations. Record USB2 and USB3 hub enumeration and
   receiver operation separately. Test the active DP display and suspend/resume.
5. Acceptance requires no xHCI death, repeated enable/debounce failures,
   integrated keyboard resets or correlated PCIe errors across repeated runs.

Retain logs from each trial. The preserved boot entry and the `=0` parameter
provide rollback while extending coverage to the remaining configurations.
