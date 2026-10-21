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

For a new system starting from the official aarch64 ISO, follow the [fresh-install guide](docs/install-fedora.md).

Run the **Build Package - RPMs Gaokun3** workflow in GitHub Actions to build Fedora packages. Select `build_el2` for the virtualization-enabled kernel used on this device. For a local kernel build, run `bash scripts/local/build_kernel.sh` on Fedora.

Install the matching platform, firmware, kernel and modules RPMs with `sudo dnf install ./<package>.rpm`. Development headers are needed for external module builds. Keep Secure Boot disabled for these unsigned kernels and EFI loaders.

The platform package supplies speaker/microphone routing, Bluetooth address setup, display orientation, module loading and kernel boot integration. Fedora supplies the desktop and standard device services.

EL2 boot uses `slbounceaa64.efi`, `tcblaunch.exe` and [qebspil](https://github.com/stephan-gh/qebspil). qebspil loads DSP images from the EFI partition before Linux attaches to them. The firmware RPM synchronizes these images to a mounted, writable qebspil EFI partition; kernel setup provisions the initial boot files. Reboot after firmware updates.
