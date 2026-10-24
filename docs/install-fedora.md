# Install Fedora on a USB drive, then optionally on the internal disk

Use a **full Fedora Workstation aarch64 installation** on USB. Its root filesystem is writable storage on the USB drive: packages, downloads and settings survive reboot and use the drive's capacity. The boot layout has a 1 GiB FAT32 EFI System Partition and an ext4 root filesystem.

Preparation works from **Windows, macOS or Linux, on x86-64 or ARM64**. The preparation computer downloads and flashes an image; it does not execute ARM programs or need QEMU, a Linux VM, or chroot.

The image builder starts with Fedora's official preinstalled [Workstation ARM disk image](https://dl.fedoraproject.org/pub/fedora/linux/releases/44/Workstation/aarch64/images/). It installs the Gaokun RPMs and creates the matching initramfs on a native ARM GitHub runner. It copies normal filesystems into the USB layout; there is no live ISO filesystem to unpack and repack. XZ is only the download compression around the finished disk image.

This new image workflow requires its first CI run and hardware boot validation. The kernel, firmware and boot helper come from the existing RPM workflow.

## 1. Build or download the USB image

In this repository's GitHub **Actions** tab:

1. Run **Build Package - RPMs Gaokun3** on `main` with `kernel_tag=v7.3`, `build_el2=true`, and an empty test suffix, or choose an already completed matching release.
2. Copy that run's release tag, such as `gaokun3-rpms-v7.3-std-el2-YYYYMMDDHHMMSS`. Use a release containing the cluster-collapse and lid-wake fixes.
3. Run **Build Fedora USB Image - Gaokun3** on the branch containing that workflow, passing the tag as `package_release`.
4. When it succeeds, open the **USB image release** link in the run summary. Download every `fedora-gaokun3-usb.raw.xz.001`, `.002`, … part, both checksum files, and the join script for your OS into one directory. The release also contains build provenance.

The ARM runner installs exactly these four RPMs from the selected release:

- `kernel-gaokun3-el2`
- `kernel-modules-gaokun3-el2`
- `linux-firmware-gaokun3`
- `gaokun3-platform`

Installing through DNF preserves dependency resolution, package metadata and package scripts. The runner generates a host-only initramfs with explicit Gaokun USB/storage drivers, since the runner's own hardware differs from the MateBook. The RPM provides a compressed EFI kernel and stripped modules.

The base image is pinned to `Fedora-Workstation-Disk-44-1.7.aarch64.raw.xz` and SHA256 `0361c13141e6f57e24d6ee5227066c33a45f7f92a95f41d0bbd343e4fd05da18`, matching Fedora's published CHECKSUM. The artifact records the RPM release and image-tooling commit. Image files are published as GitHub Release assets. Each part is at most 1900 MiB, below the 2 GiB per-file limit; the large image is not stored as an Actions artifact.

## 2. Verify and flash from your operating system

Use a **32 GiB or larger USB drive**, preferably a USB SSD for good write performance. The disk image expands to 16 GiB; allow that much local space if you decompress it manually.

Reassemble the parts from that directory. The supplied scripts verify every part and the completed image, and refuse to overwrite an existing output:

| Host | Command |
| --- | --- |
| Windows PowerShell | `powershell -NoProfile -ExecutionPolicy Bypass -File .\join-image.ps1` |
| macOS or Linux terminal | `bash join-image.sh` |

This produces `fedora-gaokun3-usb.raw.xz`. Allow local space for both the downloaded parts and the joined compressed image. Keep the numbered parts until verification succeeds, then they can be deleted.

Use **balenaEtcher** to select the `.raw.xz` image, identify the USB by model and capacity, and flash it with verification enabled. Etcher handles XZ decompression. Flashing erases the selected USB's existing partitions. If Windows or macOS offers to format the Linux partition afterward, cancel it.

## 3. Boot the installed USB system

1. Disable Secure Boot in the MateBook's F2 firmware settings.
2. Boot the USB's UEFI entry and select Fedora.
3. Complete Fedora's first-run account setup.
4. Confirm `uname -r` contains `gaokun3-el2`, and `findmnt /` reports ext4 on the USB.
5. Check display, keyboard, Wi-Fi, audio, and lid-close suspend/lid-open wake.

This USB is a normal installed system. Use `dnf` normally; package changes persist. It has no live-root RAM overlay. The first boot also gives the installation a new machine identity.

After the first successful boot, refresh the host-only initramfs using the actual MateBook hardware:

```bash
sudo /usr/libexec/gaokun3/kernel-setup "$(uname -r)" qcom/sc8280xp-huawei-gaokun3-el2.dtb
```

To use the remaining USB capacity, identify its **whole drive** and root partition with `lsblk -o NAME,SIZE,MODEL,TRAN,FSTYPE,MOUNTPOINTS`. For example, only if the USB is `/dev/sda` and its root is partition 2:

```bash
sudo growpart /dev/sda 2
sudo resize2fs /dev/sda2
```

If the kernel cannot reread the enlarged partition, reboot before `resize2fs`. The root filesystem otherwise retains the original image size.

## 4. Updates and recovery

Install matching newer kernel, modules and platform RPMs with DNF on the USB system. The packaged helper regenerates the initramfs and updates the ESP. There is no need to rebuild a compressed live filesystem for each change.

For image-builder maintenance, `.github/workflows/gaokun3-usb-image.yml` invokes `tools/usb/build-image.sh` on native ARM Linux. Its inputs are the decompressed Fedora disk image, a directory containing the four matching RPMs, and a new output `.raw` filename. The script edits loop-backed image files and has no physical-drive flashing operation. Local execution of this maintenance tool requires native aarch64 Linux; the download-and-flash workflow above supports all listed hosts.

## 5. Optionally install onto the internal drive

Boot the completed USB on the MateBook. Installation now copies this normal root filesystem to an internal ext4 partition and regenerates its boot files. The user account and installed applications come with it.

Use GNOME Disks to prepare **unallocated space on the internal disk**: an ext4 root partition large enough for the USB's used data, plus a 1 GiB FAT32 ESP. To preserve Windows, keep its partitions and EFI files intact. An existing sufficiently sized ESP can be mounted without formatting it. The commands below assume an unencrypted ext4 target and a mounted ESP.

Set the two destination paths from `lsblk -f`; they must be on the internal disk, separate from the running USB:

```bash
set -euo pipefail
gaokun_target=/mnt/gaokun-target
gaokun_root_partition=/dev/REPLACE_WITH_INTERNAL_ROOT_PARTITION
gaokun_efi_partition=/dev/REPLACE_WITH_INTERNAL_EFI_PARTITION
sudo mkdir -p "$gaokun_target"
sudo mount "$gaokun_root_partition" "$gaokun_target"
# Close applications before copying; --one-file-system excludes runtime mounts and the target.
sudo rsync -aHAXx --numeric-ids \
  --exclude=/lost+found --exclude='/tmp/*' --exclude='/var/tmp/*' \
  / "$gaokun_target/"
sudo mkdir -p "$gaokun_target"/{boot/efi,dev,proc,sys,run}
sudo mount "$gaokun_efi_partition" "$gaokun_target/boot/efi"
gaokun_root_uuid=$(sudo blkid -s UUID -o value "$gaokun_root_partition")
gaokun_efi_uuid=$(sudo blkid -s UUID -o value "$gaokun_efi_partition")
sudo tee "$gaokun_target/etc/fstab" >/dev/null <<FSTAB
UUID=$gaokun_root_uuid / ext4 defaults 0 1
UUID=$gaokun_efi_uuid /boot/efi vfat umask=0077 0 2
FSTAB
sudo mount --rbind /dev "$gaokun_target/dev"
sudo mount --make-rslave "$gaokun_target/dev"
sudo mount -t proc proc "$gaokun_target/proc"
sudo mount -t sysfs -o ro sysfs "$gaokun_target/sys"
sudo mount -t tmpfs tmpfs "$gaokun_target/run"
sudo chroot "$gaokun_target" /bin/bash
```

Inside the internal installation's chroot:

```bash
set -euo pipefail
# Give the internal installation its own identity and EFI entry directory.
rm -f /etc/machine-id /var/lib/dbus/machine-id /etc/kernel/entry-token /etc/kernel/cmdline
systemd-machine-id-setup
ln -sf /etc/machine-id /var/lib/dbus/machine-id
/usr/libexec/gaokun3/kernel-setup "$(uname -r)" qcom/sc8280xp-huawei-gaokun3-el2.dtb
bootctl --esp-path=/boot/efi --no-variables install
gaokun_token=$(cat /etc/kernel/entry-token)
printf 'default %s-%s.conf\ntimeout 5\n' "$gaokun_token" "$(uname -r)" > /boot/efi/loader/loader.conf
cat "/boot/efi/loader/entries/$gaokun_token-$(uname -r).conf"
exit
```

Require `root=UUID=...` to match the internal root. Then run `sync`, unmount with `sudo umount -R "$gaokun_target"`, shut down, unplug the USB, and select the internal disk's UEFI entry. The USB remains usable as a recovery system.
