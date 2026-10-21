# Confirmed fixes for the right baseline — 2026-10-21

Target release remains `7.3.0-right1-gaokun3-el2`; hashes distinguish this update.
Build directory: `/home/zhzy0077/.cache/gaokun-right-build` (B).

## Changes

- Enable existing 120/60 Hz DSC modes through `panel_himax_hx83121a.enable_dsc=1`.
- Keep the Bluetooth driver's existing address policy; replace the placeholder
  DT address with this machine's already prepared NVM address. Correct the
  Bluetooth rail property to `vddrfa1p7-supply`, which the driver consumes.
- Override the distribution's display modules-load file in `/etc` and let the
  touchscreen load by its device alias. This supports both installed kernels.
- Set EC adaptive charging to 1 and delay to 0, retaining the existing 40/70
  thresholds. Live readback confirmed those values; battery state changed from
  charging above the limit to discharging. Reboot readback confirmed persistence.
- Apply local UCSI recovery/ACK fixes (others/0004, 0014).
- Include the camera DT fragment and OV13B10 power/clock fixes (others/0009, 0010).
- Enable Iris with OEM firmware, firmware IOMMU child, EL2 loader and decoder
  lifecycle fixes (media/0004, 0005); select `qcom_iris.firmware_direct=1`.
- Add QSEE TPM validation support (others/0008), configure its module and include
  it in initramfs; select `tpm_qcom_qsee.allow_probe=1`. Scope provisioning/PCR
  service masks to this boot entry, consistent with the driver's restricted
  command implementation.
- Guard an absent optional sysmon shutdown IRQ before querying its state.
- Return the GPIO acquisition errors already reported by EC and battery probe.

## Validation and records

34 targeted UCSI, camera, TPM and video tests passed. A UBSAN harness using
the actual sysmon helper passed null/absent IRQ, high/low level and IRQ-error
cases. The complete source patch
passes application checking against pristine v7.3. Full kernel/modules/EL2 DTB build passed (9 minutes 30 seconds). Installation,
module signing, DT/source/config checks, initramfs checks and ESP SHA-256
readback passed. Results are under B/logs and in
`B/confirmed-fixes-install-verification.json`. UCSI is built into the EFI kernel;
its verification uses the built-in config and kernel artifact rather than
module vermagic. ESP free space after deployment is 16,371,712 bytes.

- `B/right-confirmed-fixes-v7.3.patch`: reproducible complete source changes.
- `B/source-manifest.json`: per-file source hashes, config hash and patch inputs.
- `B/record-confirmed-fixes.py`: provenance generation and pristine application check.
- `B/install-confirmed-fixes.sh`: signed module installation and initramfs build.
- `B/deploy-confirmed-fixes.py`: source/DT/initramfs/capacity checks and ESP readback.
- `B/before-confirmed-fixes/`: previous modules archive, ESP files, entry, config,
  System.map and battery settings.
- `B/rollback-confirmed-fixes.py`: restores the previous kernel/modules/ESP;
  run with sudo if rollback is needed. It retains battery/autoload configuration.

The persistent default remains the existing 7.2.9 release. The one-shot selection
was consumed by the updated boot described below. Runtime acceptance includes
120 Hz modes, Bluetooth address, camera enumeration/repeated capture, hardware
video decoding, TPM queries, USB-C hotplug and charge-control persistence.

## Reboot verification

Updated boot ID: `9621ec783eb14069adc1ed8b8282a340`, release
`7.3.0-right1-gaokun3-el2`, build #2 dated Oct 21 13:40:37 CST 2026.
The kernel command line contains all three opt-in parameters. The graphical
target was reached at 37.36 seconds, with a GNOME greeter session.

| Area | Evidence from updated boot |
| --- | --- |
| Cameras | HI846 and OV13B10 chip IDs read successfully; libcamera added both cameras. Capture remains untested. OV13B10 crop metadata and camera calibration warnings remain. |
| Bluetooth | Firmware fallback succeeded and QCA UART setup completed. The address needs live readback on this kernel. |
| UCSI / sysmon / autoload | No PPM initialization failure, alt-mode registration failure, optional shutdown-IRQ warning, or stale module-load failure recorded during this boot. USB-C hotplug remains untested. |
| Display | DSC parameter enabled. GNOME rejected its stored portrait 60 Hz mode; the active refresh rate was not recorded. |
| Iris / TPM | Direct VPU2 firmware mapping and QSEE TPM control-area discovery logged. Decoder operation and TPM protocol queries remain untested. |
| USB | `a800000.usb` soft reset timed out and DWC3 probe failed with -110 at 9.43 seconds. USB connect-debounce and EC supplier-link errors remain. |
| Audio / Wi-Fi | APM readiness opcode 0x01001021 timed out. Correctable PCIe AER events remain on the Wi-Fi link. |
| Suspend | Logind requested suspend at 83.14 seconds; journal ends with s2idle entry at 86.62 seconds. No recorded resume or saved pstore crash evidence. Physical wake/restart outcome needs user confirmation. |

The current boot, `5a6aebbd589c428a94e3df84baef1252`, runs
`7.2.9-gaokun3-el2+`. Its compositor reports 2560×1600 at 119.9999 Hz active.
EC readback confirms adaptive charging 1, delay 0, thresholds 40/70 and
discharging at 80%. These live observations belong to the current older kernel.
Installed updated ESP artifacts still match the installation hashes.

Preserved evidence: `B/logs/reboot-updated-7.3-full.log` and
`B/logs/reboot-updated-7.3-kernel.log`. Further live acceptance of 7.3 requires
booting that entry after resolving the suspend/restart history.

## Second reboot: live verification on updated 7.3

Boot ID `04b4b003-bb67-4f29-ba28-af2e77b41fe0` runs the intended #2 build
of `7.3.0-right1-gaokun3-el2`. This supersedes the earlier live-check limitation.

| Area | Live result |
| --- | --- |
| Display | Mutter reports 2560×1600 at 119.9999 Hz active and preferred, with 60 Hz also available. |
| Bluetooth | Powered on with corrected address A6:2D:A4:BE:72:F2. |
| Battery | Adaptive charging 1, delay 0, thresholds 40/70 persisted; discharging at 77% during initial readback. |
| TPM | `/dev/tpmrm0` read-only smoke test passed capability, SHA256 PCR and two GetRandom queries; QCOM DPA fTPM identified. |
| Cameras | Both enumerated. Each captured five frames twice, with close/reopen between runs, all exits 0. Images were not saved. |
| Video | H.264, HEVC and VP9 each passed five hardware/software SHA256 comparisons. Playback commands exited successfully after about 2.6 seconds despite requesting ten seconds; sustained playback remains unverified. V4L2 compliance: 41/48 passed; seven failures cover bus-info naming, source-change events, colorspace and buffer ownership. |
| USB | Both a600000.usb and a800000.usb bound to dwc3. Six root hubs and the HID device enumerated. Prior reset timeout and debounce failure did not recur. Type-C port0 partner is present; physical hotplug/DP remains untested. |
| Audio | PipeWire endpoints present; one second of silent playback completed. Initial APM readiness timeout persists; audible output was not assessed. |
| Wi-Fi / services | Gateway ping 3/3 succeeded; no corrected AER events recorded in this boot. No failed system or user units. |

Remaining log findings include EC-to-SBU supplier-link errors, the deprecated
UCSI workqueue warning, HI846 external-clock warning, and libcamera crop,
calibration and link-frequency metadata warnings. Suspend/resume remains untested.
The earlier USB timeout and Wi-Fi AER events are intermittent observations.

Evidence under B/logs: `reboot-recheck-full.log`, `reboot-recheck-kernel.log`,
`reboot-recheck-tpm.json`, `reboot-recheck-camera.log`, and
`reboot-recheck-video/decode.json` with per-test logs.

## Comparison with the full-patch edition

The saved journal for full-patch `7.2.9-gaokun3-el2+`, boot
`5a6aebbd589c428a94e3df84baef1252`, contains the same APM opcode 1001021
timeout at 11.23 seconds, HI846 24/25 MHz warning at 13.47 seconds, and
OV13B10 crop-query / missing camera calibration and helper warnings. These
findings also occur on that edition; they do not establish regressions in 7.3.
Extracted evidence: `B/logs/full-patch-7.2.9-comparison.log`.

The historical [Iris validation](video-decoding.md#direct-vpu2-boot-results)
already records 41/48 compliance passes with the same four failure categories.
This establishes prior occurrence in the Iris implementation; an identical
compliance run on the installed full-patch release was not performed this turn.
Camera capture and video checksum tests passed on the updated 7.3 kernel, so
the remaining diagnostics should be distinguished from demonstrated functional
failures.
