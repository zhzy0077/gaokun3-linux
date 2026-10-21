# right baseline system audit — 2026-10-21

Inspected live kernel `7.3.0-right1-gaokun3-el2`, boot ID
`f86b4421-fdf2-4c43-9bb1-3549b36a33a4`, around 13:30–13:34 CST.
Scope: runtime inventory, logs, source/config/device-tree inspection and
non-disruptive functional checks. No kernel, boot configuration or firmware changes.

## Findings requiring follow-up

| Area | Evidence and implication |
| --- | --- |
| 120 Hz display | Mutter exposes only 2560×1600 at 59.694 Hz. The installed panel driver declares `enable_dsc` with default false. Its DSC mode table contains 120 and 60 Hz; its uncompressed table contains one approximately 60 Hz mode. No DSC override exists in the command line or effective modprobe configuration; initramfs contains the panel module. DRM state has no DSC allocation. The next isolated display test is booting with `panel_himax_hx83121a.enable_dsc=1`, then checking advertised modes and physical output. No source patch is needed to expose the existing DSC path. |
| Cameras | Live `camss@ac5a000` has `status=disabled`; no `/dev/media*` or `/dev/video*`. CAMSS, HI846 and OV13B10 are enabled as modules in the build config. Board integration is absent from this baseline. Repository `docs/camera_support.md` records the separate integration and prior validation. |
| Hardware video decoding | Live `video-codec@aa00000` has `status=disabled`; no decoder device exists. Iris and Venus are configured as modules. Repository `docs/video-decoding.md` describes the separate SC8280XP integration. |
| Bluetooth | Firmware request `qca/wcnhpnv21.bin` fails with ENOENT; installed matching-prefix file is `wcnhpnv21g.bin`. Controller reports powered on with address `55:44:33:22:11:00`, differing from the NVM preparation service's address. Follow-up: full logs confirm fallback to `hpnv21.bin` and successful UART setup. The first failed filename is recoverable; the placeholder address remains a separate issue. |
| TPM / boot delay | `tpm_qcom_qsee` module and TPM device nodes are absent. Userspace waits for both TPM devices and times out. Graphical target takes 55.8 seconds of userspace; total startup is 80.3 seconds. Repository `docs/tpm_qsee_zh.md` describes the separately developed QSEE support. |
| Battery charge limit | EC/UPower reports charging at 85%, while start/end limits are 40/70 and threshold support/enabling is reported. Follow-up: native EC `battery_adaptive_charge` reads 0 (disabled), and `smart_charge_delay` reads 72. UPower’s enabled flag does not establish that the EC enable switch is on. Full-charge capacity is 76.2% of design, a battery health reading. |
| USB-C / external display | Boot logs contain repeated connector-not-initialized and orientation-out-of-range errors. Both Type-C ports eventually register; port0 is a PD sink, port1 a source. Both DP connectors are disconnected. Hotplug, orientation changes and external display operation need attached equipment. |
| Sensors | IIO exposes only the PMIC ADC; no accelerometer/ambient-light device was enumerated. SLPI attachment alone does not verify sensor functionality. |
| Audio | One boot APM command timeout and SoundWire port-count warnings. ALSA restore also attempts writes to read-only headset controls. Speaker/headphone and microphone endpoints exist. One second of silent playback through ALSA default completed successfully without a new kernel error. Audible output and microphone signal remain untested; PipeWire reports the internal microphone muted. |
| Touchscreen startup configuration | Modules-load requests absent `himax_hx83121a_spi`. The baseline's actual `himax_gaokun_right` module loads, identifies HX83121A, completes firmware reload and registers an input device. |

## Verified current operation

- All installed ESP artifact hashes and installed MSM module hash match the PLL installation report.
- GNOME owns an active internal-display scanout; both DSI controllers bind.
- OpenGL reports direct, accelerated Freedreno FD690 rendering, Mesa 26.2.4, OpenGL 4.6.
- Eight CPUs online; hardware cpufreq with schedutil, cluster limits 2.4384 and 2.9952 GHz.
- Thermal readings approximately 37–44 °C; CPU/GPU cooling devices registered.
- About 15 GiB usable RAM and 8 GiB zram swap; hardware-corrupted memory counter zero.
- NVMe SMART: critical warning zero, media errors zero, spare 100%, endurance used 8%, temperature 36 °C. Root filesystem has 267 GiB free; ESP has 16 MiB free.
- Wi-Fi connected on 5 GHz with HE rates; gateway ping 3/3 successful, interface RX/TX errors zero. Boot had corrected PCIe AER events on the Wi-Fi path.
- EL2/VHE initialization succeeds. KVM API version 12 and creation/destruction of an empty VM pass.
- ADSP, CDSP and SLPI are attached. CDSP/SLPI shutdown-state lookup warnings remain in boot logs.
- USB root hubs and Huawei keyboard/touchpad enumerate; lid and power-button input devices exist.
- AC adapter, battery telemetry and RTC register.
- System reports running; no failed system/user units, no deferred probes, kernel taint zero.

## Checks requiring a later interactive test

120 Hz/DSC boot and physical image quality; brightness changes; touchscreen and
touchpad gestures; audible speaker/headphone output and microphone capture;
Bluetooth pairing; USB-C data/DP hotplug in both orientations; suspend/resume
and battery drain. Current suspend counters are success=0, failure=0. Available
sleep mode is s2idle. Hibernation is compiled, while configured swap is zram.

Full kernel log saved at
`/home/zhzy0077/.cache/gaokun-right-build/logs/system-audit-kernel.log`.
