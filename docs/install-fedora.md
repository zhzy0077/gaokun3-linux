# Fresh Fedora installation on Gaokun3

This guide starts with the official Fedora 44 Workstation aarch64 ISO and a separate preparation computer. It does not require an existing Linux installation on the MateBook.

The repository supplies Gaokun kernel, firmware and platform RPMs. The official ISO supplies the Fedora installer and desktop. To run that unmodified installer, use an ARM virtual machine on the preparation computer, install Fedora into a disk image, add the Gaokun packages inside the VM, then write the resulting image to the destination drive. The result is a normal installed Fedora system.

This is a **whole-drive fresh installation**: writing the image replaces the destination drive's partition table and contents, including Windows if that drive contains it. Use a separate USB SSD for an initial installation. The procedure below has been checked against the package scripts; a complete ISO-to-new-drive installation has not yet been tested.

## 1. Download Fedora

Download these two files from the [official Fedora 44 aarch64 directory](https://dl.fedoraproject.org/pub/fedora/linux/releases/44/Workstation/aarch64/iso/):

- `Fedora-Workstation-Live-44-1.7.aarch64.iso`
- `Fedora-Workstation-44-1.7-aarch64-CHECKSUM`

Follow [Fedora's verification instructions](https://fedoraproject.org/security/) to verify the CHECKSUM signature with the Fedora release key, then verify the ISO checksum. On Linux, in the download directory:

```bash
sha256sum --ignore-missing -c Fedora-Workstation-44-1.7-aarch64-CHECKSUM
```

Use the **aarch64** ISO. A stock ISO written directly to USB does not include this repository's Gaokun kernel and boot integration.

## 2. Obtain matching Gaokun packages

In this repository's GitHub Actions, run **Build Package - RPMs Gaokun3** on `main` with:

- `kernel_tag`: the value in `kernel-source.env` (currently `v7.3`).
- `build_el2`: enabled.
- `test_suffix`: empty.

After the workflow succeeds, download these four RPMs from its release or artifacts:

- `kernel-gaokun3-el2`
- `kernel-modules-gaokun3-el2`
- `linux-firmware-gaokun3`
- `gaokun3-platform`

Use the kernel and modules from the same build. For the firmware changes documented here, require firmware release 5 or newer and platform release 8 or newer, built from the current repository. Keep `package-manifest.json` with the download. Development headers and standard non-EL2 kernel packages are unnecessary for this installation.

## 3. Install the ISO into an ARM VM

Use a VM manager that supports **aarch64, the QEMU `virt` machine, and UEFI**. ARM hosts can use hardware acceleration; x86 hosts need aarch64 emulation. A VM with 4 CPUs and 6 GiB RAM is sufficient for the installer.

Create a new **40 GiB qcow2 disk** and attach the downloaded ISO. This disk is the future installation image. Boot the VM from the ISO and launch Fedora's installer.

Use custom storage on the VM disk:

| Partition | Size | Filesystem | Mount point |
| --- | --- | --- | --- |
| EFI System Partition | 1 GiB | FAT32 | `/boot/efi` |
| Fedora root | Remaining space | ext4 | `/` |

This guide uses an unencrypted root filesystem and no separate `/boot`. Complete the installation, detach the ISO, and boot the newly installed Fedora **inside the VM**. Complete account creation and connect the VM to the network.

## 4. Add device support inside the VM

Copy only the four selected Gaokun RPMs into `~/gaokun-rpms` in the guest. Open a terminal **inside the guest**:

```bash
sudo dnf install systemd-boot-unsigned sdubby dracut
sudo mkdir -p /etc/kernel
sudo cp -a /etc/kernel/cmdline /etc/kernel/cmdline.before-gaokun 2>/dev/null || true
sudo rm -f /etc/kernel/cmdline
cd ~/gaokun-rpms
sudo dnf install --allowerasing ./*.rpm
```

The firmware package replaces Fedora's overlapping Qualcomm/Atheros firmware packages. Review DNF's transaction before accepting. The missing `cmdline` file makes the platform helper derive the root UUID from the guest's `/etc/fstab` and add the Gaokun boot parameters.

Require a successful package transaction and kernel setup. If it reports missing modules or insufficient EFI space, fix that error before exporting the disk.

Determine the installed kernel release and explicitly finalize its boot files:

```bash
mapfile -t gaokun_kernels < <(find /usr/lib/modules -mindepth 1 -maxdepth 1 \
  -type d -name '*-gaokun3-el2*' -printf '%f\n')
[ "${#gaokun_kernels[@]}" -eq 1 ] || { echo 'Expected one Gaokun EL2 kernel'; exit 1; }
gaokun_krel=${gaokun_kernels[0]}
sudo /usr/libexec/gaokun3/kernel-setup "$gaokun_krel" \
  qcom/sc8280xp-huawei-gaokun3-el2.dtb
sudo bootctl --esp-path=/boot/efi --no-variables install
gaokun_token=$(cat /etc/kernel/entry-token)
printf 'default %s-%s.conf\ntimeout 5\n' "$gaokun_token" "$gaokun_krel" \
  | sudo tee /boot/efi/loader/loader.conf
```

`bootctl` installs the fallback ARM64 loader at `EFI/BOOT/BOOTAA64.EFI`, allowing the image to boot after being moved to the MateBook. The kernel helper installs the DTB, initramfs, EL2 loaders and DSP firmware copies on the EFI partition.

Inspect the resulting entry and required files:

```bash
sudo cat "/boot/efi/loader/entries/$gaokun_token-$gaokun_krel.conf"
sudo ls -l /boot/efi/EFI/BOOT/BOOTAA64.EFI \
  /boot/efi/EFI/systemd/drivers/{qebspilaa64.efi,slbounceaa64.efi} \
  /boot/efi/tcblaunch.exe \
  /boot/efi/firmware/qcom/sc8280xp/HUAWEI/gaokun3/{qcadsp8280.mbn,qccdsp8280.mbn,qcslpi8280.mbn}
```

The entry must contain the Gaokun kernel, initramfs and `devicetree`, plus `root=UUID=...` matching `/etc/fstab`. Check every file named by the entry exists on the EFI partition.

Shut the guest down. Its default kernel is now intended for Gaokun hardware, so proceed to exporting the image.

## 5. Write the installed system to the destination drive

On the preparation computer, with the VM fully shut down, convert its qcow2 disk:

```bash
qemu-img convert -p -O raw /path/to/fedora-gaokun.qcow2 fedora-gaokun.raw
```

Attach the destination SSD through USB or an NVMe enclosure. It must be at least as large as the virtual disk. Identify it by model, size and serial:

```bash
lsblk -o NAME,SIZE,MODEL,SERIAL,MOUNTPOINTS
```

Unmount all partitions of the destination drive. Replace the placeholder below with its **whole-drive** `/dev/disk/by-id/` path; a `-partN` path is a partition and is unsuitable here.

```bash
gaokun_target=/dev/disk/by-id/REPLACE_WITH_DESTINATION_DRIVE
sudo dd if=fedora-gaokun.raw of="$gaokun_target" bs=16M status=progress conv=fsync
```

Do not write the image to the preparation computer's system drive. If the destination is larger than the image, use a partition editor to repair the backup GPT location, extend the final ext4 partition, and grow its filesystem. This can be done before the first boot.

## 6. First hardware boot

Attach the prepared USB SSD to the MateBook, or fit the prepared internal SSD. Enter firmware settings with F2 and disable Secure Boot. Select the prepared drive's UEFI boot entry, then the Gaokun entry in systemd-boot.

After login:

```bash
uname -r
systemctl --failed
nmcli device status
wpctl status
sudo cat /sys/kernel/debug/qcom_socinfo/adsp/{name,oem}
```

For the firmware audited on 2026-10-21, ADSP should report build suffix `.529312.3.545165.2` and OEM `SZXY1LWX1197241`. This checks the running DSP, rather than just the file installed under `/usr/lib/firmware`.

Select 120 Hz in GNOME Displays. Check speaker output, microphones, Wi-Fi and Bluetooth. Firmware/build provenance and the remaining APM timeout are recorded in [firmware-provenance.md](firmware-provenance.md).
