# Firmware provenance and update audit

Checked 2026-10-21. All 60 tracked entries under `firmware/` were examined:
58 regular files and two compatibility symlinks. The initial audit below describes the pre-update contents. On 2026-10-21,
all 37 changed linux-firmware files and the OEM ADSP candidate were added
to package 20261021-4. The JSON manifest records the updated hashes and
preserves the previous hashes for those 38 files. [Per-file hashes, sources and comparisons](firmware-provenance.json)
cover every entry, including license notices.

## Sources

The historical `scripts/ci/40_populate_rootfs.sh` before commit `821e1b6`
records the extraction recipe: generic Qualcomm firmware from linux-firmware;
Gaokun DSP, video and service files from Qualcomm/Huawei Windows driver CABs;
and the audio topology from linux-firmware's Lenovo SC8280XP directory.
The later README firmware-bundle link currently returns HTTP 404.

- **linux-firmware:** current comparison pinned to
  `9a80a04181713da7f8187ec928c15160137f3262`. Generic matching files were
  compared by Git blob hash; differing files were downloaded and hashed.
  Historical versions were matched against pinned commits, including
  `1b629c2ee14dd810e503fbb01aa65dae2f8e8327` for the older Bluetooth files.
- **Windows drivers:** downloaded and extracted
  [200.0.10.0](https://github.com/matebook-e-go/uup-drivers-sc8280xp/releases/tag/200.0.10.0),
  published 2024-08-25, the latest published release in that repository.
  Its README identifies Windows Update/UUP as the source. The relevant CABs
  are `qcdx8280`, `qcsubsys_ext_adsp8280`, `qcsubsys_ext_cdsp8280` and
  `qcsubsys_ext_scss8280`. The OEM update comparison covers this release mirror. It also includes
  the older 200.0.9.0 bundle for original-byte provenance.
- **Local aliases:** `ath11k/WCN6855/hw2.1 -> hw2.0` and the Gaokun audio
  topology alias are packaging conveniences, with no independent version.

## Initial audit findings

| Files | Before update | Published comparison | Assessment |
| --- | --- | --- | --- |
| `ath11k/WCN6855/hw2.0/board-2.bin` | Exact linux-firmware commit `cbd0f9753754`, 2026-02-11 | Updated at `8fe920c980c3`, 2026-09-18 | Newer board database available; additions do not establish a fix for this board. |
| `ath11k/WCN6855/hw2.0/{amss.bin,m3.bin,regdb.bin}` | Generic WCN6855 payload | Identical to current upstream | No update in the checked source. |
| `ath11k/WCN6855/hw2.0/nfa765/{amss.bin,m3.bin}` | WLAN build `04685` | `04866.5`, commit `b56c03b62139`, 2026-03-25 | Newer NFA765 variant available. The observed boot uses the generic `03125...6510.41` firmware. |
| `qca/hpbtfw21.tlv`, all 32 `hpnv21*` files | Embedded build `00653-VER_PATCHZ-3` | `00680-VER_PATCHZ-1`, commit `11184fe575c7`, 2026-09-29 | Upstream QCA2066-family update available. The commit subject still says 00653; the downloaded binary identifies 00680. |
| `qca/wcnhpbtfw21.tlv`, `wcnhpnv21.bin`, `wcnhpnv21g.bin` | WCN6855 files | Identical to current upstream | No update in the checked source. This boot loads `wcnhpbtfw21.tlv` and falls back to a locally prepared `hpnv21.bin`; the latter depends on per-device address provisioning. |
| `qcom/a660_gmu.bin`, `a660_sqe.fw` | GPU firmware | Identical to current upstream | No update in the checked source. |
| Gaokun `audioreach-tplg.bin` | Exact Lenovo X13s topology from `f9a35b3f0779`, 2023-06-28; 24,296 bytes | Topology from AudioReach v1.0.0, `2121082a8884`, 2025-10-17; 29,496 bytes | Newer topology exists. It must be evaluated with the Gaokun audio driver, DSP and UCM configuration. |
| `qcadsp8280.mbn` | `ADSP.HT.5.6.c2-00010-MAKENA-1.529312.3` | Windows bundle adds suffix `.545165.2` | Newer ADSP build candidate; no runtime validation performed. |
| `qccdsp8280.mbn`, `qcslpi8280.mbn` | CDSP `00722`, SLPI `00051` | Byte-identical to Windows bundle | No update in the checked bundle. |
| `qcvss8280.mbn`, `qcdxkmsuc8280.mbn` | Video/graphics auxiliary firmware | Same ELF loadable segments; differences confined to the non-loadable metadata segment | No payload update demonstrated. Video version remains `video-firmware.1.1-e736ad69...`. |
| `adspr.jsn`, `adspua.jsn`, `battmgr.jsn`, `cdspr.jsn` | Service registration JSON | Byte-identical to linux-firmware Lenovo descriptors; equivalent JSON in Windows bundle | No functional update. |
| Four license/notice files | Existing distribution notices | Same contents upstream; two moved into `LICENSES/` | Keep redistribution notices with the firmware. |

## Initial audit interpretation

There are 37 files with changed linux-firmware contents, one newer OEM ADSP
candidate, 14 byte-identical upstream/OEM files (including four notices), six
semantically equivalent OEM files and two symlinks. The four JSON files in
the semantic OEM comparison also match linux-firmware byte for byte. Source availability alone
does not validate a change on Gaokun. In particular, the newer Bluetooth files
belong to the `hp` family while this machine selects `wcnhp` firmware, and the
newer NFA765 firmware is a separate variant from the one observed in this boot.

The audit preserves exact source URLs where bytes match, and labels semantic
or payload matches separately. Complete original-byte provenance for the
three differing OEM MBN files (`qcadsp8280.mbn`, `qcvss8280.mbn`, and
`qcdxkmsuc8280.mbn`) is unresolved: neither Windows bundle 200.0.9.0 nor
200.0.10.0 matches their bytes. The extraction recipe establishes their
Windows-driver family; the comparisons above identify build and payload matches.

## Package update

`linux-firmware-gaokun3-20261021-4.fc44.noarch` includes all 38 identified
updates. RPM binary post-processing is disabled to preserve vendor firmware
bytes. Package payload hashes and all installed entries were verified against
the manifest; installed Bluetooth NVM differs only in the provisioned device
address. Post-reboot checks on 7.3.0-right1-gaokun3-el2 confirmed working audio
stream submission and camera capture. The boot log reports ADSP, CDSP and
SLPI as attached to already-running processors, with firmware name unknown.
The installed ADSP MBN is therefore not evidence that the running ADSP
changed; the boot-time APM command timeout remains. Bluetooth now loads
wcnhpnv21.bin successfully without the earlier fallback.

Runtime ADSP identification was subsequently read from Qualcomm SMEM via
`/sys/kernel/debug/qcom_socinfo/adsp/name`:
`12:ADSP.HT.5.6.c2-00010-MAKENA-1.529312.3`, OEM `SHAY6HWX1136182`.
The installed MBN identifies
`ADSP.HT.5.6.c2-00010-MAKENA-1.529312.3.545165.2`, OEM `SZXY1LWX1197241`.
Together with the attached remoteproc state, this confirms that the running
ADSP retains the older build after the RPM update.

The boot source was traced to the installed `qebspilaa64.efi` driver in
`/boot/efi/EFI/systemd/drivers/`. It uses the selected DTB firmware-name and
loads the image from the ESP `/firmware/` directory before ExitBootServices.
The ESP `qcom/sc8280xp/HUAWEI/gaokun3/qcadsp8280.mbn` reports the exact
runtime build and OEM identifiers above; its SHA256 is
`ab9c3d4e3b84813ffdc14540fc8d955e84bca6dcb3e6f2c3d175c471d2b2710a`.
The new Linux copy has SHA256
`36cd002e786011bb8b2bc22e7b030bd1af98c1d32f55856aeba70c6ac48714c0`.
The tested release 20261021-4 did not synchronize this ESP copy;
`tools/boot/kernel-setup.py` handles copying it during kernel setup.
A new-image test can use qebspil with a separate DTB firmware-name and boot
entry, or update the ESP copy after preserving it for rollback. No BIOS
flash or Linux DSP reset support is required for this boot-time test.
The read-only investigation left the ESP unchanged.

Following approval, the ESP ADSP image was replaced with the audited
`.545165.2` build and its SHA256 verified against the installed Linux copy.
The previous ESP image was preserved and verified at
`/home/zhzy0077/.cache/gaokun-firmware-build-20261021/adsp-esp-before-update.mbn`.
After the next reboot, the runtime SMEM table reported
`12:ADSP.HT.5.6.c2-00010-MAKENA-1.529312.3.545165.2` and OEM
`SZXY1LWX1197241`, confirming activation of the new ADSP build.
Speaker playback (silent stream) and internal microphone capture to a discard
sink both completed successfully. No DSP crash was logged. The boot-time
APM command timeout for opcode `1001021` persists with this build.
There were no failed system services; this boot also logged corrected Wi-Fi
PCIe errors and keyboard/touchpad USB reconnections.

RPM release 5 adds post-transaction DSP synchronization for a mounted,
writable FAT ESP with qebspil installed. Unchanged images are skipped;
changed images are copied to a temporary file, compared and flushed before
replacement. Insufficient space leaves the existing boot image intact and
reports an error. Image builds continue to populate the ESP during setup.
