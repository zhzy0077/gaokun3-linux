# Gaokun USB failure capture

Run `capture-failure.py` as root before a controlled USB recovery test. It
collects the previous/current boot journals, kernel version, boot ID, USB
inventory, Type-C/DRM state and runtime-PM attributes. It does not reset devices
or read MMIO/debug register dumps.

```sh
sudo systemd-run --unit=gaokun-usb-capture --property=UMask=0077 \
  /usr/bin/python3 "$PWD/tools/usb/capture-failure.py" \
  --output "/var/log/gaokun-usb/$(date +%Y%m%d-%H%M%S)" \
  --follow --seconds 3600
```

Use a new output directory for each experiment. The transient service survives
terminal closure and stops after the requested interval; it does not restart
at boot. Stop it early with `sudo systemctl stop gaokun-usb-capture`.

Live kernel, selected xHCI/PM events and filtered QMP/UCSI/xHCI function
calls are fsynced after each read. Function tracing is restricted to the
listed functions and uses the same private instance.
A private trace instance leaves global tracing settings unchanged and is removed
on normal exit. `latest-state.json` and `heartbeat.json` are refreshed every
15 seconds. Trace records may still be lost between generation and userspace
capture on a hard lockup; a remote serial console is needed to capture that
last interval. Keep raw journals private: they contain local device/account data.

## 2026-10-19 incident

Previous boot: `80dd5d0425ee44168734453ae7eb350f`.
Current boot at capture setup: `6548ce35d70f49099f32dcb6c9b99edd`.
Evidence directory on the affected host:
`/var/log/gaokun-usb/20261019-boot-6548ce35/`.

- Forcing root hubs usb3–usb6 awake for eight seconds did not enumerate the
  missing Genesys hub. All original power/control values were restored.
- At 22:16:34, the empty external xHCI child of `a600000.usb` was unbound.
  The integrated keyboard controller and Type-C/DRM drivers were not unbound.
- At 22:16:35, binding xHCI failed with `Host halt failed, -110` and
  `can't setup: -110`. The controller remained unbound after the failed test.
- The old journal ends at 22:16:53 without normal shutdown. The following
  boot reports an unclean journal. Neither pstore location retained a panic
  record. Temporal proximity implicates the experiment, but the exact reset
  mechanism is unproven. Subsequent commands only read status and clock state.
- In the new boot, xHCI independently reports `HC died` at 22:18:36; subsequent
  suspend attempts fail with -22. This failure predates the new capture service.

Future recovery experiments must record target identity, active USB children,
DRM connector state and operation timestamps before any unbind. A successful
unbind followed by failed bind is not a completed rollback. Do not repeat that
operation blindly; inspect the DWC3/PHY state and preserve evidence first.

## Follow-up analysis at 22:35

The first live trace contained 5,702 `xhci_portsc_writel` records, including
repeated warm-reset-change acknowledgements with the SuperSpeed link in
Polling. It started after the controller failure and does not show its cause.
A second capture at `/var/log/gaokun-usb/20261019-phy-detail/` adds filtered
QMP mode/orientation, common-PHY init/exit, UCSI and xHCI timeout function calls.
Its service is `gaokun-usb-capture-detail`, with a one-hour limit from 22:33.

The current boot timeline is: USB2 hub at 8.99 s, UCSI init timeout at 22.14 s,
USB3 hub at 34.10 s after retry, stop-endpoint command timeout at 76.78 s.
The xHCI timeout handler explicitly calls halt and marks the host dead when a
STOP_RING command expires. The logged death time is the detection time, not
necessarily the time the controller first stopped making progress.

Controller auto IDs and USB bus numbers change between boots. Before the
reboot `a600000.usb` had xHCI `.1.auto`; afterwards it has `.2.auto`.
Earlier boots also show hub failures on `a800000.usb`, so this is not evidence
of a single permanently broken physical socket. Use resolved sysfs paths.

The real EC ACK encoder was compiled with fatal UBSAN: the original source
fails on `gaokun_ec_ucsi_pan_ack(-1)` with a negative shift. Patch 0014 and the
local source mirror now check the sentinel and byte-width bounds before
shifting. Tests cover zero ACK, all eight mask bits, invalid ports without
I/O, transport errors and equality with the fully patched kernel source.
The 129-test suite passed with four environment-dependent skips, including
standard/EL2 patch application. This source fix has not been installed and
is not yet established as the cause or cure of the xHCI failure.

### Same-port replug at approximately 22:35

The user unplugged and replugged the hub. Evidence is frozen in
`replug-2235-trace.log` and `replug-2235-result.json` under the detailed capture
directory. UCSI callbacks appeared at monotonic 1088.55 s and 1092.75 s,
followed by another sideband update at 1093.74 s. Four sequences of
`qmp_combo_usb_power_off -> qmp_combo_com_exit -> qmp_combo_com_init ->
qmp_combo_usb_power_on` were captured. Two ran on the worker executing
`ucsi_handle_connector_change`, two on the Gaokun sideband worker.
No new USB enumeration or traced xHCI halt/reset/command timeout followed.
The controller had already been declared dead at 76.78 s.

This proves the connection notifications reached software and PHY callbacks
ran; replug alone did not recover USB. The function tracer lacks device
pointers, mode arguments and return values, so it does not establish that all
four sequences targeted the same PHY or caused the original controller death.
The continuing `port 4-1` Polling/WRC events map to `a800000.usb`, whereas the
dead hub controller maps to `a600000.usb`; do not conflate those streams.

Code review identifies two areas for the next instrumented test: UCSI core
SAFE/USB mode updates and sideband mux updates share the PHY, while the
Gaokun applied-state cache only tracks its own writes; QMP mode-switch code
also ignores common-init and USB-power-on return values. Neither should be
promoted to a confirmed cause without device/mode/error traces.

## Opt-in capture on test boots

Install `capture-failure.py` as `/usr/local/libexec/gaokun-usb-capture` and
`gaokun-usb-test-capture.service` under `/etc/systemd/system/`, then enable the
unit. It runs only with `gaokun.usb_capture=1` in the kernel command line.
Each boot writes to `/var/log/gaokun-usb/test-boot-<boot-id>/` for one hour;
restarting it in the same boot rejects the existing directory to preserve
its original evidence. Normal boot entries without the marker are unaffected.

On 2026-10-20, the `-usbdiag1` EL2 kernel was deployed as independent test
files because the installed platform package lacks `gaokun3-boot-integration
>= 2`. No RPM dependencies were bypassed or platform packages upgraded.
The deployment consists of `/usr/lib/modules/7.2.9-usbdiag1-gaokun3-el2+/`,
`/boot/config-7.2.9-usbdiag1-gaokun3-el2+`, `/boot/efi/gaokun-usbdiag1/`, and
`gaokun-usbdiag1-{control,experiment}.conf` under the ESP's `loader/entries/`.
These test files are not managed by RPM and require explicit removal when
retiring the experiment. Both entries share the same image, DTB and initramfs;
only `phy_qcom_qmp_combo.gaokun_keep_common_power=0` versus `=1` differs in
their kernel options. Both enable QMP dynamic debug and boot capture.

The current Release 13 entry remains the persistent default. The control
entry is selected for the next boot only. A bounded capture smoke test passed,
and its private trace instance was removed at exit. Hardware acceptance of
the new kernel remains pending; see `docs/usb-hub-diagnostics.md`.
