#!/usr/bin/env bash
# Adapt Fedora's preinstalled ARM disk image on a native ARM Linux builder.
set -euo pipefail

if [[ $# != 3 ]]; then
    echo "Usage: $0 FEDORA.raw RPM_DIRECTORY NEW_OUTPUT.raw" >&2
    exit 2
fi
[[ $EUID == 0 && $(uname -m) == aarch64 ]] || {
    echo 'Run as root on a native aarch64 Linux builder (the GitHub workflow supplies one).' >&2
    exit 1
}
source_image=$(realpath "$1")
rpm_dir=$(realpath "$2")
output_image=$(realpath -m "$3")
[[ -f "$source_image" && -d "$rpm_dir" && ! -e "$output_image" ]]
shopt -s nullglob
rpms=("$rpm_dir"/*.rpm)
[[ ${#rpms[@]} == 4 ]] || { echo 'Supply exactly the four matching EL2/runtime RPMs.' >&2; exit 1; }
for command in losetup mount umount rsync parted mkfs.vfat mkfs.ext4 blkid chroot; do
    command -v "$command" >/dev/null
done
work=$(mktemp -d)
source_loop=''
target_loop=''
cleanup() {
    local result=$?
    trap - EXIT
    umount -R "$work/target" 2>/dev/null || true
    umount -R "$work/source" 2>/dev/null || true
    [[ -z $target_loop ]] || losetup -d "$target_loop"
    [[ -z $source_loop ]] || losetup -d "$source_loop"
    # Leave failed output images for inspection. Never recurse into mounted trees.
    rmdir "$work/target" "$work/source" "$work" 2>/dev/null || true
    exit "$result"
}
trap cleanup EXIT
mkdir "$work/source" "$work/target"
source_loop=$(losetup --find --show --read-only --partscan "$source_image")
udevadm settle
# Fedora Workstation Disk: ESP, /boot, root. Fail if the pinned layout changes.
[[ $(blkid -s TYPE -o value "${source_loop}p1") == vfat ]]
[[ $(blkid -s TYPE -o value "${source_loop}p2") == ext4 ]]
source_root="${source_loop}p3"
case $(blkid -s TYPE -o value "$source_root") in
    ext4) mount -o ro,noload "$source_root" "$work/source" ;;
    btrfs)
        mount -o ro "$source_root" "$work/source"
        if [[ ! -f "$work/source/etc/os-release" ]]; then
            [[ -f "$work/source/root/etc/os-release" ]]
            umount "$work/source"
            mount -o ro,subvol=root "$source_root" "$work/source"
        fi
        ;;
    *) echo 'Unexpected Fedora root filesystem' >&2; exit 1 ;;
esac
[[ -f "$work/source/etc/os-release" ]]
mount -o ro,noload "${source_loop}p2" "$work/source/boot"

# A fresh layout gives Gaokun a 1 GiB ESP without resizing Fedora partitions.
truncate -s 16G "$output_image"
parted -s "$output_image" mklabel gpt
parted -s "$output_image" mkpart ESP fat32 1MiB 1025MiB
parted -s "$output_image" set 1 esp on
parted -s "$output_image" mkpart root ext4 1025MiB 100%
target_loop=$(losetup --find --show --partscan "$output_image")
udevadm settle
mkfs.vfat -F 32 -n GAOKUNEFI "${target_loop}p1"
mkfs.ext4 -F -L GAOKUNROOT "${target_loop}p2"
mount "${target_loop}p2" "$work/target"
rsync -aHAXx --numeric-ids --exclude=/lost+found "$work/source/" "$work/target/"
rsync -aHAXx --numeric-ids --exclude=/efi --exclude=/lost+found "$work/source/boot/" "$work/target/boot/"
root_uuid=$(blkid -s UUID -o value "${target_loop}p2")
esp_uuid=$(blkid -s UUID -o value "${target_loop}p1")
cat > "$work/target/etc/fstab" <<FSTAB
UUID=$root_uuid / ext4 defaults 0 1
UUID=$esp_uuid /boot/efi vfat umask=0077 0 2
FSTAB
mkdir -p "$work/target"/{dev,proc,sys,run,boot/efi,var/tmp/gaokun-rpms}
cp "${rpms[@]}" "$work/target/var/tmp/gaokun-rpms/"
# Do not mount the ESP until after package installation: posttrans must defer.
mount --rbind /dev "$work/target/dev"
mount --make-rslave "$work/target/dev"
mount -t proc proc "$work/target/proc"
mount -t sysfs -o ro sysfs "$work/target/sys"
mount -t tmpfs tmpfs "$work/target/run"
rm -f "$work/target/etc/resolv.conf"
cp -L /etc/resolv.conf "$work/target/etc/resolv.conf"
chroot "$work/target" /bin/bash -euxo pipefail <<'CHROOT'
# Install normally so dependencies, RPM metadata and scriptlets remain consistent.
dnf -y install --allowerasing /var/tmp/gaokun-rpms/*.rpm \
    systemd-boot-unsigned sdubby dracut e2fsprogs cloud-utils-growpart rsync file
rpm -q kernel-gaokun3-el2 kernel-modules-gaokun3-el2 linux-firmware-gaokun3 gaokun3-platform
# Firmware packages for other ARM boards can consume substantial ESP space.
mapfile -t pi_packages < <(rpm -qa --qf '%{NAME}\n' | grep -E '^bcm(283x-firmware|2835-firmware|2711-firmware|2712-firmware|283x-overlays)$' || true)
if (( ${#pi_packages[@]} )); then dnf -y remove --noautoremove "${pi_packages[@]}"; fi
cat > /etc/dracut.conf.d/92-gaokun-usb.conf <<'CONF'
hostonly="yes"
hostonly_cmdline="no"
add_drivers+=" ext4 usb-storage uas xhci-hcd xhci-plat-hcd dwc3 dwc3-qcom dwc3-generic-plat phy-qcom-qmp-combo phy-qcom-qmp-usb phy-qcom-snps-femto-v2 nvme "
CONF
# Host detection sees the runner, so explicitly include the target USB path.
rm -f /etc/kernel/cmdline
systemctl set-default graphical.target
systemctl enable gdm NetworkManager
CHROOT
mount "${target_loop}p1" "$work/target/boot/efi"
chroot "$work/target" /bin/bash -euxo pipefail <<'CHROOT'
mapfile -t kernels < <(find /usr/lib/modules -mindepth 1 -maxdepth 1 -type d -name '*-gaokun3-el2*' -printf '%f\n')
[[ ${#kernels[@]} == 1 ]]
krel=${kernels[0]}
/usr/libexec/gaokun3/kernel-setup "$krel" qcom/sc8280xp-huawei-gaokun3-el2.dtb
bootctl --esp-path=/boot/efi --no-variables install
token=$(cat /etc/kernel/entry-token)
printf 'default %s-%s.conf\ntimeout 5\n' "$token" "$krel" > /boot/efi/loader/loader.conf
file "/boot/efi/$token/$krel/linux" | grep 'zstd compressed'
entry="/boot/efi/loader/entries/$token-$krel.conf"
cat "$entry"
grep -q "root=$(findmnt -n -o SOURCE --fstab --target /)" "$entry"
lsinitrd -m "/boot/initramfs-$krel.img"
printf '%s\n' "$krel" > /usr/share/gaokun3/usb-kernel-release
dnf clean all
rm -rf /var/tmp/gaokun-rpms
# Let each flashed installation receive a new identity on first boot.
rm -f /var/lib/dbus/machine-id /var/lib/systemd/random-seed /etc/ssh/ssh_host_*
truncate -s 0 /etc/machine-id
ln -s /etc/machine-id /var/lib/dbus/machine-id
ln -sfn ../run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
# Relabel offline while the target ARM userspace and policy are available.
setfiles -F -e /dev -e /proc -e /sys -e /run -e /boot/efi \
    /etc/selinux/targeted/contexts/files/file_contexts /
CHROOT
sync
umount -R "$work/target"
# Discard free blocks so compression does not retain deleted package/cache data.
e2fsck -f -p "${target_loop}p2"
mount "${target_loop}p2" "$work/target"
fstrim "$work/target"
umount "$work/target"
echo "Prepared $output_image"
