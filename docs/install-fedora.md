# Install Fedora from a Gaokun-adapted USB stick

The workflow is: **download Fedora's aarch64 ISO → write a writable USB copy → add Gaokun support → boot the USB on the MateBook → run Fedora's installer → finalize the installed boot files.** No existing installation on the MateBook is required.

A raw ISO write with `dd`, Etcher or Fedora Media Writer produces an ISO9660 filesystem whose files cannot be replaced in place. For this procedure, write the ISO's files onto a FAT32 USB partition instead. If the stick was already raw-written, recreate it using step 2.

This guide targets Fedora Workstation 44 aarch64, Huawei MateBook E Go 2023 / Gaokun3, and EL2 boot. Preparation requires a Fedora **aarch64 Linux environment**, Internet access, a 16 GiB or larger USB stick, and about 30 GiB of working space on an ext4/Btrfs filesystem. An x86 preparation host additionally needs working aarch64 binfmt/QEMU user emulation for the chroot commands.

The ISO layout and relevant installer/dracut code have been inspected. The complete adapted-USB installation procedure remains to be tested on hardware.

## 1. Download the ISO and device packages

Download these files from the [official Fedora directory](https://dl.fedoraproject.org/pub/fedora/linux/releases/44/Workstation/aarch64/iso/):

- `Fedora-Workstation-Live-44-1.7.aarch64.iso`
- `Fedora-Workstation-44-1.7-aarch64-CHECKSUM`

Verify the CHECKSUM signature using [Fedora's verification instructions](https://fedoraproject.org/security/), then check the ISO:

```bash
sha256sum --ignore-missing -c Fedora-Workstation-44-1.7-aarch64-CHECKSUM
```

Run this repository's **Build Package - RPMs Gaokun3** workflow on `main`, with the pinned kernel tag (`v7.3`), `build_el2=true`, and an empty test suffix. Download these four matching RPMs into a directory named `rpms`:

- `kernel-gaokun3-el2`
- `kernel-modules-gaokun3-el2`
- `linux-firmware-gaokun3`
- `gaokun3-platform`

Use current-main builds: firmware release 5 or newer, platform release 9 or newer, and kernel release 17 or newer include the latest packaging changes. The kernel and modules must come from the same build.

Install preparation tools on the preparation host:

```bash
sudo dnf install parted dosfstools rsync erofs-utils util-linux policycoreutils
```

## 2. Write a writable USB copy

**This step erases the selected USB stick.** Identify it by model and serial, then set its whole-drive path and first-partition path. Do not select the computer's system disk.

```bash
lsblk -o NAME,SIZE,MODEL,SERIAL,MOUNTPOINTS

# Replace these paths with the selected USB stick.
gaokun_usb=/dev/disk/by-id/REPLACE_WITH_USB_DRIVE
gaokun_usb_part=/dev/disk/by-id/REPLACE_WITH_USB_DRIVE-part1

# Unmount any mounted partitions of that USB stick before proceeding.
sudo parted -s "$gaokun_usb" mklabel gpt
sudo parted -s "$gaokun_usb" mkpart ESP fat32 1MiB 100%
sudo parted -s "$gaokun_usb" set 1 esp on
sudo partprobe "$gaokun_usb"
sudo udevadm settle
sudo mkfs.vfat -F 32 -n GAOKUNLIVE "$gaokun_usb_part"
```

In the directory containing the downloaded ISO and `rpms/`, keep the following variables in the same shell throughout preparation:

```bash
gaokun_work="$PWD/gaokun-usb-work"
mkdir -p "$gaokun_work"/{iso,usb,source,root}
sudo mount -o loop,ro "$PWD/Fedora-Workstation-Live-44-1.7.aarch64.iso" "$gaokun_work/iso"
sudo mount "$gaokun_usb_part" "$gaokun_work/usb"

# Copy the distribution payload; step 4 supplies the Gaokun boot files.
sudo rsync -rt --exclude=/EFI --exclude=/boot \
  "$gaokun_work/iso/" "$gaokun_work/usb/"
```

## 3. Add Gaokun packages to the live system

The inspected ISO contains `LiveOS/squashfs.img`. Despite its name, this Fedora 44 image is **EROFS** and contains the root directory directly. Mount it, copy the root tree to writable working storage, and preserve its ownership, attributes and SELinux labels:

```bash
sudo mount -o loop,ro "$gaokun_work/iso/LiveOS/squashfs.img" "$gaokun_work/source"
test -d "$gaokun_work/source/usr" || { echo 'Unexpected ISO root layout'; exit 1; }
sudo rsync -aHAX --numeric-ids "$gaokun_work/source/" "$gaokun_work/root/"
sudo umount "$gaokun_work/source"
sudo mkdir -p "$gaokun_work/root/opt/gaokun-rpms"
sudo cp rpms/*.rpm "$gaokun_work/root/opt/gaokun-rpms/"

sudo mount --rbind /dev "$gaokun_work/root/dev"
sudo mount --make-rslave "$gaokun_work/root/dev"
sudo mount -t proc proc "$gaokun_work/root/proc"
sudo mount -t sysfs -o ro sysfs "$gaokun_work/root/sys"
sudo mount -t tmpfs tmpfs "$gaokun_work/root/run"
sudo cp -a "$gaokun_work/root/etc/resolv.conf" "$gaokun_work/resolv.conf.saved"
sudo cp --remove-destination /etc/resolv.conf "$gaokun_work/root/etc/resolv.conf"

sudo chroot "$gaokun_work/root" /bin/bash
```

Run the following **inside the chroot**:

```bash
set -e
# The live root must not have the host's EFI partition mounted here.
mountpoint -q /boot/efi && { echo 'Unexpected mounted EFI partition'; exit 1; }
dnf install --allowerasing /opt/gaokun-rpms/*.rpm \
  systemd-boot-unsigned sdubby dracut-live
# Remove Raspberry Pi boot files from the live image before installation.
dnf remove --noautoremove bcm283x-firmware bcm2835-firmware \
  bcm2711-firmware bcm2712-firmware bcm283x-overlays
```

Review DNF's transaction. The Gaokun firmware replaces Fedora's overlapping Qualcomm/Atheros firmware packages. The standard Fedora live desktop and installer must remain installed. Package boot setup skips provisioning while `/boot/efi` is unmounted; that is expected at this stage.

Still inside the chroot:

```bash
mapfile -t gaokun_kernels < <(find /usr/lib/modules -mindepth 1 -maxdepth 1 \
  -type d -name '*-gaokun3-el2*' -printf '%f\n')
[ "${#gaokun_kernels[@]}" -eq 1 ]
gaokun_krel=${gaokun_kernels[0]}
printf '%s\n' "$gaokun_krel" > /usr/share/gaokun3/live-kernel-release

# This initramfs boots the USB's compressed live filesystem.
dracut --force --no-hostonly --no-hostonly-cmdline \
  --add dmsquash-live --add-drivers 'erofs squashfs overlay' \
  --kver "$gaokun_krel" /tmp/gaokun-live-initrd.img

# Use Fedora's existing installer with systemd-boot for the installed system.
mkdir -p /etc/anaconda/conf.d
cat > /etc/anaconda/conf.d/90-gaokun.conf <<'CONF'
[Bootloader]
type = SDBOOT
efi_dir = systemd
menu_auto_hide = False
CONF

dnf clean all
exit
```

The RPMs are installed **inside the image**, so the live installer can copy the Gaokun kernel, modules and runtime configuration into the destination. Placing RPM files alongside an unchanged live image would not accomplish that.

## 4. Replace the USB boot files and compressed root

Back in the preparation host's shell:

```bash
gaokun_krel=$(cat "$gaokun_work/root/usr/share/gaokun3/live-kernel-release")
gaokun_dtb=sc8280xp-huawei-gaokun3-el2.dtb
sudo mkdir -p "$gaokun_work/usb"/{EFI/BOOT,EFI/systemd/drivers,loader/entries,gaokun,firmware/qcom/sc8280xp/HUAWEI/gaokun3}

sudo cp "$gaokun_work/root/usr/lib/systemd/boot/efi/systemd-bootaa64.efi" \
  "$gaokun_work/usb/EFI/BOOT/BOOTAA64.EFI"
sudo cp "$gaokun_work/root/usr/share/gaokun3/el2/"{qebspilaa64.efi,slbounceaa64.efi} \
  "$gaokun_work/usb/EFI/systemd/drivers/"
sudo cp "$gaokun_work/root/usr/share/gaokun3/el2/tcblaunch.exe" "$gaokun_work/usb/"
sudo cp "$gaokun_work/root/usr/lib/firmware/qcom/sc8280xp/HUAWEI/gaokun3/"{qcadsp8280.mbn,qccdsp8280.mbn,qcslpi8280.mbn} \
  "$gaokun_work/usb/firmware/qcom/sc8280xp/HUAWEI/gaokun3/"
sudo cp "$gaokun_work/root/boot/vmlinuz-$gaokun_krel" "$gaokun_work/usb/gaokun/linux"
sudo cp "$gaokun_work/root/tmp/gaokun-live-initrd.img" "$gaokun_work/usb/gaokun/initrd"
sudo cp "$gaokun_work/root/usr/lib/modules/$gaokun_krel/dtb/qcom/$gaokun_dtb" "$gaokun_work/usb/gaokun/"

gaokun_args=$(cat "$gaokun_work/root/usr/share/gaokun3/platform-cmdline")
sudo tee "$gaokun_work/usb/loader/entries/gaokun-live.conf" >/dev/null <<ENTRY
title Fedora 44 Live - Gaokun3
linux /gaokun/linux
initrd /gaokun/initrd
devicetree /gaokun/$gaokun_dtb
options root=live:LABEL=GAOKUNLIVE rd.live.image rd.live.overlay.overlayfs=1 $gaokun_args
ENTRY
printf 'default gaokun-live.conf\ntimeout 5\n' | sudo tee "$gaokun_work/usb/loader/loader.conf"

sudo umount -R "$gaokun_work/root/dev"
sudo umount "$gaokun_work/root/proc" "$gaokun_work/root/sys" "$gaokun_work/root/run"
sudo rm "$gaokun_work/root/etc/resolv.conf"
sudo cp -a "$gaokun_work/resolv.conf.saved" "$gaokun_work/root/etc/resolv.conf"
sudo rm -f "$gaokun_work/root/tmp/gaokun-live-initrd.img"
sudo rm -rf "$gaokun_work/root/opt/gaokun-rpms"

# Restore SELinux labels for added files, then rebuild the EROFS payload.
sudo setfiles -F -r "$gaokun_work/root" \
  "$gaokun_work/root/etc/selinux/targeted/contexts/files/file_contexts" "$gaokun_work/root"
sudo mkfs.erofs -zzstd,9 "$gaokun_work/gaokun-live.erofs" "$gaokun_work/root"
# A single FAT32 file must be smaller than 4 GiB.
[ "$(stat -c %s "$gaokun_work/gaokun-live.erofs")" -lt 4294967296 ]
sudo cp "$gaokun_work/gaokun-live.erofs" "$gaokun_work/usb/LiveOS/squashfs.img"
sudo cmp "$gaokun_work/gaokun-live.erofs" "$gaokun_work/usb/LiveOS/squashfs.img"
sync
sudo umount "$gaokun_work/usb" "$gaokun_work/iso"
```

Do not use the original ISO's media-check entry: the payload has intentionally changed. The new systemd-boot menu starts the adapted live system directly.

## 5. Boot and install on the MateBook

1. Disable Secure Boot in the MateBook's F2 firmware settings.
2. Boot the USB's UEFI entry and select **Fedora 44 Live - Gaokun3**.
3. Confirm `uname -r` contains `gaokun3-el2`, and check display, keyboard and network.
4. Launch Fedora's standard **Install Fedora** application.
5. Choose the internal installation target, excluding the USB stick. To preserve Windows, use unallocated space and leave its partitions intact.
6. For a straightforward layout, allocate a 1 GiB FAT32 EFI System Partition at `/boot/efi` and an ext4 root at `/`. This guide's finalization commands assume an unencrypted ext4 root. An existing Windows EFI partition must not be formatted; a separate sufficiently sized EFI partition can be used for Fedora.
7. Complete installation, but **remain in the live session before rebooting**.

## 6. Finalize the installed Gaokun boot entry

The live system and installed system need different boot arguments. This step generates the installed root UUID, host-only disk initramfs, DTB entry and DSP firmware copies using the packaged helper. The kernel package supplies the compressed EFI executable.

Close the installer and inspect `lsblk -f`. Set the root and EFI partitions selected in the installer below. These are the **installed system's partitions**, not the USB stick's.

```bash
gaokun_root_partition=/dev/REPLACE_WITH_INSTALLED_ROOT_PARTITION
gaokun_efi_partition=/dev/REPLACE_WITH_INSTALLED_EFI_PARTITION
gaokun_target=/mnt/gaokun-target
sudo mkdir -p "$gaokun_target"
sudo mount "$gaokun_root_partition" "$gaokun_target"
sudo mount "$gaokun_efi_partition" "$gaokun_target/boot/efi"
sudo mount --rbind /dev "$gaokun_target/dev"
sudo mount --make-rslave "$gaokun_target/dev"
sudo mount -t proc proc "$gaokun_target/proc"
sudo mount -t sysfs -o ro sysfs "$gaokun_target/sys"
sudo mount -t tmpfs tmpfs "$gaokun_target/run"
sudo chroot "$gaokun_target" /bin/bash
```

Inside the installed system's chroot:

```bash
set -e
rpm -q kernel-gaokun3-el2 kernel-modules-gaokun3-el2 linux-firmware-gaokun3 gaokun3-platform
cat /etc/fstab
# Require the installed disk's UUIDs in fstab, not live-media/overlay mounts.
gaokun_krel=$(cat /usr/share/gaokun3/live-kernel-release)
rm -f /etc/kernel/cmdline
/usr/libexec/gaokun3/kernel-setup "$gaokun_krel" qcom/sc8280xp-huawei-gaokun3-el2.dtb
bootctl --esp-path=/boot/efi --no-variables install
gaokun_token=$(cat /etc/kernel/entry-token)
printf 'default %s-%s.conf\ntimeout 5\n' "$gaokun_token" "$gaokun_krel" > /boot/efi/loader/loader.conf
cat "/boot/efi/loader/entries/$gaokun_token-$gaokun_krel.conf"
exit
```

Require successful commands. The final entry must contain `root=UUID=...` for the installed root, and existing kernel, initramfs and DTB files. It must contain no `root=live:` or `rd.live.*` arguments. `bootctl --no-variables` installs the fallback ARM64 loader; select this disk's UEFI boot entry in firmware if needed.

Then return to the live session:

```bash
sync
sudo umount -R "$gaokun_target"
```

Shut down, unplug the USB stick, and boot Fedora from the internal drive.

## 7. Verify the new installation

```bash
uname -r
systemctl --failed
nmcli device status
wpctl status
sudo cat /sys/kernel/debug/qcom_socinfo/adsp/{name,oem}
```

The audited ADSP image reports suffix `.529312.3.545165.2` and OEM `SZXY1LWX1197241`. Select 120 Hz in GNOME Displays and check speakers, microphones and Bluetooth. See [firmware provenance](firmware-provenance.md) for the tested versions and remaining APM timeout.
