# Fedora on Huawei MateBook E Go 2023

Kernel and runtime packages for Gaokun3 (Snapdragon 8cx Gen 3 / SC8280XP).
The reviewed kernel source is pinned in [kernel-source.env](kernel-source.env).

## Contents

- `patches/`, `dts/`, `defconfig/`: kernel changes, device trees and Fedora configuration.
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

EL2 boot uses `slbounceaa64.efi`, `tcblaunch.exe` and [qebspil](https://github.com/stephan-gh/qebspil). qebspil loads DSP images from the EFI partition before Linux attaches to them. The firmware RPM synchronizes these images to a mounted, writable qebspil EFI partition; kernel setup provisions the initial boot files. Reboot after firmware updates.
