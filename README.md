# Fedora on Huawei MateBook E Go 2023

Kernel and runtime packages for Gaokun3 (Snapdragon 8cx Gen 3 / SC8280XP).
The reviewed kernel source is pinned in [kernel-source.env](kernel-source.env).

## Contents

- `patches/`, `dts/`, `defconfig/`: kernel changes, device trees and Fedora configuration.

`dts/*.dts`, `dts/*.dtsi` and `defconfig/gaokun3_defconfig` are the authoritative board sources. Local and CI builds import them into the kernel checkout with `tools/kernel/import-board-files.py` after standard patches and before EL2 patches. Local rebuilds refresh these files, including when switching variants; commit or stash edits inside the kernel checkout first. Existing checkouts with an older patch inventory require a fresh `KERN_SRC` directory.
- `firmware/`: device firmware and redistribution notices; [source manifest](docs/firmware-provenance.json) and [update findings](docs/firmware-provenance.md).
- `packaging/rpm/`: kernel, modules, development headers, firmware and platform RPMs.
- `scripts/`: local kernel builds and CI packaging.
- `tools/`: boot/EL2 integration, audio and microphone configuration, Bluetooth address preparation, display defaults and build consistency checks.

## Build and install

To adapt the official aarch64 ISO onto a bootable USB stick and install with Fedora's installer, follow the [fresh-install guide](docs/install-fedora.md).

Run the **Build Package - RPMs Gaokun3** workflow in GitHub Actions to build Fedora packages. Select `build_el2` for the virtualization-enabled kernel used on this device. For a local kernel build, run `bash scripts/local/build_kernel.sh` on Fedora.

Install the matching platform, firmware, kernel and modules RPMs with `sudo dnf install ./<package>.rpm`. Development headers are needed for external module builds. Keep Secure Boot disabled for these unsigned kernels and EFI loaders.

Kernel packages install a Zstd-compressed, self-decompressing EFI kernel and generate a host-only initramfs with the Gaokun boot drivers. The standalone release `.efi` contains the same kernel as the RPM. USB live-image preparation explicitly uses a generic initramfs.

Validated on Gaokun3 with `7.3.0-gaokun3-el2+` on 2026-10-22: the EFI kernel shrank from 52.2 to 14.4 MiB and the initramfs from 82.0 to 58.8 MiB. After removing the Raspberry Pi boot packages, the factory ESP had 93 MiB free. Reboot checks confirmed KVM, GPU initialization, Wi-Fi, Bluetooth, DSP attachment and audio device registration.

The platform package supplies speaker/microphone routing, Bluetooth address setup, display orientation, module loading and kernel boot integration. Fedora supplies the desktop and standard device services.

Platform boot defaults enable QSEE TPM with `tpm_qcom_qsee.allow_probe=1`, including kernel upgrades with an existing command line. An explicit `allow_probe=0` override is preserved. On 2026-10-22, reboot verification confirmed both TPM device nodes and random generation; the 45-second TPM device wait disappeared and total boot time fell from 76.6 to 35.5 seconds. The driver supports capability queries, self-tests, PCR reads and random generation; its command allowlist remains in place.

EL2 boot uses `slbounceaa64.efi`, `tcblaunch.exe` and [qebspil](https://github.com/stephan-gh/qebspil). qebspil loads DSP images from the EFI partition before Linux attaches to them. The firmware RPM synchronizes these images to a mounted, writable qebspil EFI partition; kernel setup provisions the initial boot files. Reboot after firmware updates.

Gaokun3 EL2 builds disable shared CPU-cluster collapse to prevent suspend-triggered hard resets, while retaining individual CPU power collapse. The board-specific EL2 device-tree base carries this workaround into local builds and kernel RPMs. RTC wake and systemd suspend/power-button wake passed with it on 2026-10-24; standby power has not been measured.
