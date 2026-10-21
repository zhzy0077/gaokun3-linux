# right baseline: issue-to-fix investigation

Target: `7.3.0-right1-gaokun3-el2`, right-0903 recommended + EL2 + local PLL patch.
Investigation performed 2026-10-21 against the build source, live DT/sysfs,
complete boot journal, repository patches, and pinned community sources.

## Ranked fixes and evidence

| Priority / issue | Candidate and required integration | Evidence / confidence |
| --- | --- | --- |
| 1. Missing 120 Hz | [others/0002](../patches/others/0002-drm-panel-himax-hx83121a-enable-DSC-by-default.patch), or the existing boot parameter `panel_himax_hx83121a.enable_dsc=1` | Confirmed default-policy cause. The driver selects the 120/60 Hz mode table only with DSC enabled. Parameter permits the smallest isolated boot test. |
| 2. USB-C initialization/orientation | [others/0004](../patches/others/0004-usb-typec-ucsi-recover-Gaokun-initialization-and-DP.patch) plus [others/0014](../patches/others/0014-platform-arm64-gaokun-fix-UCSI-ACK-negative-shift.patch) | Strong match: fixed port topology, deferred state synchronization, nonblocking notification and initialization retry address the observed early callback path. 0014 validates the ACK sentinel before shifting. Both apply sequentially to a scratch copy of this baseline. Physical hotplug validation remains required. |
| 3. Bluetooth placeholder address | [others/0001](../patches/others/0001-Bluetooth-btqca-only-set-USE_BDADDR_PROPERTY-when-ad.patch), paired with removing the placeholder `local-bd-address` and retaining the installed per-device NVM preparation | Source quirk forces the DT address when the controller address matches NVM. Live address matches `[00 11 22 33 44 55]` from DT. The installed NVM service prepares a different per-device address. This is a coordinated address-policy fix. |
| 4. Cameras absent | [others/0009](../patches/others/0009-media-i2c-ov13b10-support-Gaokun-camera-power.patch), [others/0010](../patches/others/0010-clk-qcom-camcc-sc8280xp-park-camera-clocks.patch), and [camera DTS](../dts/sc8280xp-huawei-gaokun3-camera.dtsi) inclusion / board resources | Live CAMSS is disabled, and the right board DTS does not include its camera fragment. 0009 supplies rear sensor matching/power; 0010 fixes repeat-open clock parking. HI846 recommended fixes already exist. Import the camera-specific resources from the local board DTS; the broad 0099 import patch also contains unrelated changes. Existing camera documentation records prior hardware validation. |
| 5. Hardware decoding absent | Enable the board `&iris` node with OEM firmware and firmware-IOMMU child, then [media/0004](../patches/media/0004-media-iris-Gaokun-EL2-firmware-and-restart.patch) and [media/0005](../patches/media/0005-media-iris-fix-decoder-metadata-EOS-and-restart.patch), plus `qcom_iris.firmware_direct=1` | Live codec is disabled. These patches provide EL2 loading and decoder lifecycle fixes; both apply sequentially in scratch. Board DTS, platform compatibility and resources must be checked together during integration; module config alone is insufficient. See [video validation](video-decoding.md). |
| 6. TPM absent / boot waits | [others/0008](../patches/others/0008-firmware-qcom-add-Gaokun-QSEE-TPM-validation.patch), `CONFIG_TCG_QCOM_TPM_QSEE=m`, dependencies and `tpm_qcom_qsee.allow_probe=1` | Missing module confirmed. Patch adds opt-in QSEE transport with the HLOS fixed-buffer fix. It supports restricted validation commands; normal key management is outside its implemented scope. TPM startup waits are also a userspace dependency issue when this feature is intentionally absent. |
| 7. Battery threshold discrepancy | First reconcile EC `battery_adaptive_charge` and `smart_charge_delay` with desktop policy. Separately port the status-decoding/error-handling portion of community 0072 | EC enable reads **0**, delay **72**; UPower reports thresholds enabled. This establishes configuration/reporting disagreement, not a proven threshold-enforcement bug. 0072 addresses whole-byte status matching, stale state and unchecked reads; it does not enable charging limits. |
| 8. Missing desktop motion sensors | Deploy the SLPI/SSC userspace chain and a desktop bridge | SLPI attaches; no ordinary motion IIO device exists. FastRPC, hexagonrpcd, registry and libssc are needed before iio-sensor-proxy integration. This is a feature integration, with no single local kernel patch. |
| 9. Stale touchscreen autoload | Kernel-aware modules-load configuration for `himax_gaokun_right` | Existing `gaokun3-display.conf` requests `himax_hx83121a_spi`, which belongs to the alternative local driver. Current touchscreen binds and initializes. Configuration should track the selected driver; importing others/0003 would replace the implementation. |
| 10. Suspend wake-source handling | [others/0017](../patches/others/0017-platform-arm64-huawei-gaokun-ec-set-wakeup-source-pr.patch) is an available candidate | Moves wakeup ownership to the EC IRQ and removes adapter wake-event spam. Applies cleanly. No suspend failure was reproduced; baseline already contains upstream/0012 and /0016. |

## Corrections and issues without a demonstrated patch match

- **Bluetooth firmware:** complete logs show successful fallback from missing
  `wcnhpnv21.bin` to `hpnv21.bin`, followed by `QCA setup on UART is completed`.
  The missing first-choice file is recoverable. Do not substitute `wcnhpnv21g.bin`
  based only on the similar filename. The address issue above remains real.
- **DSC timing:** right recommended/0010 already uses `DIV_ROUND_UP`, giving
  267 clocks for the current 800-pixel, 8-bpp, 8-bpc panel. Local others/0005
  derives width from compressed bytes per line; it is an alternative refinement,
  fails direct application against this source, and is unnecessary merely to
  expose 120 Hz. PLL others/0007 is already installed (reverse apply succeeds).
- **APM timeout:** opcode `0x01001021` is `APM_CMD_GET_SPF_STATE`, the initial
  DSP readiness query. ADSP is attached and the later silent playback check
  passed. Local EL2/0023–0024 target the different missing-SMP2P-mapping attach
  failure; others/0012 changes speaker gain. Neither is established as a fix
  for this timeout. Reproduce PCM failure or obtain command/response timing
  before selecting a readiness retry change.
- **SoundWire warnings / ALSA restore:** port-count warnings require comparing
  codec/controller port maps before any DT change. Read-only impedance/control
  restore errors belong to ALSA saved-state handling. No matching proven kernel
  fix identified for either symptom.
- **Remoteproc shutdown-state warnings:** `qcom_sysmon_shutdown_irq_state()`
  queries `shutdown_irq` without checking whether optional `shutdown-ack` exists.
  Sysmon only requests that IRQ when its lookup returns positive; the query
  helper lacks that same guard. Candidate new change: return false for an absent
  optional IRQ while preserving errors from real IRQs. This is distinct from the
  ready/handover SMP2P race patches; attachment succeeds in this boot.
- **Wi-Fi corrected AER:** link is operational and gateway checks passed. The
  community ath11k crash/suspend series addresses different failures. No exact
  AER fix established from this boot; retain counters for a reproducible test.
- **CPU, GPU, RAM and NVMe:** inspected operation passed; no patch indicated.

## Additional source defects found while tracing power management

The reference baseline's EC and battery GPIO error branches call
`dev_err_probe()` without returning. The current repository versions of
[upstream/0016](../patches/upstream/0016-platform-arm64-huawei-gaokun-ec-introduce-EC-enable-.patch)
and [upstream/0015](../patches/upstream/0015-power-supply-gaokun-fix-battery-_STA-handling.patch)
contain the corrected returns. Extract those small deltas; the original features
are already present. This affects GPIO failure/defer paths and does not explain
the currently observed disabled adaptive-charge flag.

## External sources inspected

Pinned community commit: `85522669f355a1b6e9dfcded3f5dee3142aa0d04`.

- [Battery 0072](https://github.com/vahiru/gaokun-android/blob/85522669f355a1b6e9dfcded3f5dee3142aa0d04/patches/0072-power-supply-gaokun-battery-decode-status-bits-and-capacity-level.patch): source inspected. Separate its general status/error fixes from Android capacity-level shutdown policy.
- [UCSI 0092](https://github.com/vahiru/gaokun-android/blob/85522669f355a1b6e9dfcded3f5dee3142aa0d04/patches/0092-usb-typec-ucsi-huawei_gaokun-resend-dropped-GET_CONNECTOR_STATUS.patch): source inspected. Candidate for a reproduced stuck GET_CONNECTOR_STATUS/BUSY failure; requires adapting to local 0004 notification handling. Current early initialization warnings alone do not establish that failure.
- [SLPI deployment](https://github.com/vahiru/gaokun-android/blob/85522669f355a1b6e9dfcded3f5dee3142aa0d04/docs/contrib/slpi-sensors-deploy.md): stack identified in the repository's pinned community comparison; desktop integration remains separate.

## Checks completed

`git apply --check` against the exact build source succeeds for others/0001,
0002, 0004, 0008, 0009, 0010, 0014, 0017 and media/0004–0005. Sequential scratch
application succeeds for the media pair and UCSI pair. These checks establish
source applicability; compiling and booting are the next validation stages.
Report: `/home/zhzy0077/.cache/gaokun-right-build/issue-patch-apply-check.json`.
The installed kernel, build source, firmware, services and boot entry were unchanged.
