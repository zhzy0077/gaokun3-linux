# Install Fedora from the Gaokun3 Live USB

The downloadable image is Fedora 45 Workstation aarch64 Live media adapted for the Huawei MateBook E Go 2023 / Gaokun3. It boots with the Gaokun EL2 kernel and runs Fedora's normal LiveOS installer. The installer copies that Live root to the selected internal disk, then runs an included Anaconda post-script to generate the target disk's host-only initramfs and systemd-boot entry.

## 1. Download and flash

Open the [latest image release](https://github.com/zhzy0077/gaokun3-linux/releases/latest), then download every `fedora-gaokun3-usb.raw.xz.NNN` part, `SHA256SUMS`, `SHA256SUMS.parts`, and the join script for the current operating system into one directory.

Verify and reassemble the image:

| Host | Command |
| --- | --- |
| Windows PowerShell | `powershell -NoProfile -ExecutionPolicy Bypass -File .\join-image.ps1` |
| Linux or macOS | `bash join-image.sh` |

The join script verifies every numbered part and the completed `fedora-gaokun3-usb.raw.xz`.

Use balenaEtcher to flash that file to a USB drive with at least 8 GiB capacity. Etcher reads XZ compression directly and flashing replaces the USB's existing partition table.

## 2. Boot the Live system

1. Disable Secure Boot in the MateBook's F2 firmware settings.
2. Boot the USB's UEFI entry and select **Fedora 45 Live - Gaokun3**.
3. Confirm the booted Gaokun kernel with `uname -r`.
4. Check display, keyboard, touchpad, Wi-Fi, audio and the fingerprint device before starting the installer.

The USB root filesystem is the official Fedora LiveOS EROFS payload with an in-memory overlay. Use it as installer media and keep the USB connected throughout installation.

## 3. Install to the internal disk

Launch **Install Fedora** from the Live desktop and complete the normal Fedora 45 Workstation installation.

For a dual-boot system, select the internal disk, use its unallocated space, and preserve the existing Windows partitions. Give the Fedora EFI System Partition at least 1 GiB when creating a new ESP. The default Anaconda storage layouts supported by the packaged `kernel-setup` helper include ext4, Btrfs and LUKS UUID roots.

At installation completion, leave the USB inserted until Anaconda has finished its post-installation tasks. The `90-gaokun3-boot.ks` snippet runs automatically in the installed target and performs these operations:

- derives the installed root UUID and kernel command line;
- generates the host-only Gaokun initramfs;
- creates the Gaokun BLS entry with the Gaokun DTB;
- installs systemd-boot and the EL2 EFI assets into the target ESP;
- sets the Gaokun entry as the loader default.

Shut down after Anaconda reports completion, remove the USB, and boot Fedora from the internal disk's UEFI entry.

## 4. Verify the installation

```bash
uname -r
grep -R 'root=UUID=' /boot/efi/loader/entries/*.conf
systemctl --failed
nmcli device status
wpctl status
sudo cat /sys/kernel/debug/qcom_socinfo/adsp/{name,oem}
```

The installed entry contains `root=UUID=...`, and the Gaokun kernel release contains `gaokun3-el2`. The installer log is `/root/gaokun3-boot.log`.

## 5. Build a newer image

Run **Build Fedora Live USB Image - Gaokun3** with a package release containing the five matching RPMs:

- `kernel-gaokun3-el2`
- `kernel-modules-gaokun3-el2`
- `linux-firmware-gaokun3`
- `gaokun3-platform`
- `gaokun3-fingerprint`

The workflow downloads the official `Fedora-Workstation-Live-45-1.4.aarch64.iso`, verifies SHA256 `ad73a977709d417f5b7dda4147fc071396b9d8d2bdcca2df615aa3aab7673710`, and runs `tools/usb/build-live-image.sh` on a native ARM runner.

The builder requires a Fedora aarch64 environment with `erofs-utils`, `rsync`, `parted`, `dosfstools`, `policycoreutils`, and `util-linux`. Its local form is:

```bash
sudo tools/usb/build-live-image.sh \
  Fedora-Workstation-Live-45-1.4.aarch64.iso \
  rpm-directory \
  fedora-gaokun3-usb.raw
```

The resulting image has one GPT FAT32 partition labeled `GAOKUNLIVE`. It contains the modified EROFS payload under `LiveOS/squashfs.img`, the Gaokun kernel, DTB and initramfs under `gaokun/`, systemd-boot at `EFI/BOOT/BOOTAA64.EFI`, and the EL2 EFI drivers at `EFI/systemd/drivers/`.
