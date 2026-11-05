#!/usr/bin/env bash
# Rebuild Fedora Workstation Live media with Gaokun3 packages and boot files.
set -euo pipefail

if [[ $# != 3 ]]; then
    echo "Usage: $0 FEDORA-LIVE.iso RPM_DIRECTORY NEW_OUTPUT.raw" >&2
    exit 2
fi
[[ $EUID == 0 && $(uname -m) == aarch64 ]] || {
    echo 'Run as root on a native aarch64 Linux builder.' >&2
    exit 1
}
if [[ ${GAOKUN_LIVE_PRIVATE_MOUNTS:-0} != 1 ]]; then
    exec unshare --mount --propagation private env GAOKUN_LIVE_PRIVATE_MOUNTS=1 "$0" "$@"
fi

source_iso=$(realpath "$1")
rpm_dir=$(realpath "$2")
output_image=$(realpath -m "$3")
[[ -f $source_iso && -d $rpm_dir && ! -e $output_image ]] || {
    echo 'Supply an existing ISO, an RPM directory and a new output path.' >&2
    exit 1
}

one_rpm() {
    local -n result=$1
    local pattern=$2
    result=("$rpm_dir"/$pattern)
    [[ ${#result[@]} == 1 ]] || {
        echo "Expected one RPM matching $pattern in $rpm_dir" >&2
        exit 1
    }
}

shopt -s nullglob
one_rpm kernel_rpm 'kernel-gaokun3-el2-*.rpm'
one_rpm modules_rpm 'kernel-modules-gaokun3-el2-*.rpm'
one_rpm firmware_rpm 'linux-firmware-gaokun3-*.rpm'
one_rpm platform_rpm 'gaokun3-platform-*.rpm'
one_rpm fingerprint_rpm 'gaokun3-fingerprint-*.rpm'
rpms=("${kernel_rpm[0]}" "${modules_rpm[0]}" "${firmware_rpm[0]}" \
      "${platform_rpm[0]}" "${fingerprint_rpm[0]}")
all_rpms=("$rpm_dir"/*.rpm)
[[ ${#all_rpms[@]} == 5 ]] || {
    echo 'Supply exactly the five matching Gaokun EL2, platform, firmware and fingerprint RPMs.' >&2
    exit 1
}

for command in blkid chroot file fsck.fat losetup mkfs.erofs mkfs.vfat mount \
               parted rsync setfiles sha256sum udevadm umount unshare; do
    command -v "$command" >/dev/null
done

mkdir -p "$(dirname "$output_image")"
work=$(mktemp -d "$(dirname "$output_image")/.gaokun-live.XXXXXX")
target_loop=''
cleanup() {
    local result=$?
    trap - EXIT
    umount -R "$work/media" 2>/dev/null || true
    umount -R "$work/root/dev" 2>/dev/null || true
    umount "$work/root/proc" "$work/root/sys" "$work/root/run" 2>/dev/null || true
    umount "$work/source" "$work/iso" 2>/dev/null || true
    [[ -z $target_loop ]] || losetup -d "$target_loop" 2>/dev/null || true
    rm -rf "$work"
    exit "$result"
}
trap cleanup EXIT
mkdir -p "$work"/{iso,source,root,media}

mount -o loop,ro "$source_iso" "$work/iso"
squashfs="$work/iso/LiveOS/squashfs.img"
[[ -f $squashfs ]] || { echo 'Fedora LiveOS payload is missing.' >&2; exit 1; }
file "$squashfs" | grep -q 'EROFS filesystem'
mount -o loop,ro "$squashfs" "$work/source"
[[ -f $work/source/etc/os-release && -x $work/source/usr/bin/dnf ]]
grep -q '^VERSION_ID=45$' "$work/source/etc/os-release"
rsync -aHAX --numeric-ids "$work/source/" "$work/root/"
umount "$work/source"

mkdir -p "$work/root/var/tmp/gaokun-rpms"
cp "${rpms[@]}" "$work/root/var/tmp/gaokun-rpms/"
mount --rbind /dev "$work/root/dev"
mount --make-rslave "$work/root/dev"
mount -t proc proc "$work/root/proc"
mount -t sysfs -o ro sysfs "$work/root/sys"
mount -t tmpfs tmpfs "$work/root/run"
if [[ -e $work/root/etc/resolv.conf || -L $work/root/etc/resolv.conf ]]; then
    cp -a "$work/root/etc/resolv.conf" "$work/resolv.conf.saved"
fi
rm -f "$work/root/etc/resolv.conf"
cp -L /etc/resolv.conf "$work/root/etc/resolv.conf"

chroot "$work/root" /bin/bash -euxo pipefail <<'CHROOT'
mapfile -t old_firmware < <(rpm -qa --qf '%{NAME}\n' |
    grep -E '^(atheros-firmware|qcom-firmware)$' || true)
if (( ${#old_firmware[@]} )); then
    dnf -y remove --noautoremove "${old_firmware[@]}"
fi
dnf -y install --allowerasing /var/tmp/gaokun-rpms/*.rpm \
    systemd-boot-unsigned sdubby dracut-live
rpm -q kernel-gaokun3-el2 kernel-modules-gaokun3-el2 linux-firmware-gaokun3 \
    gaokun3-platform gaokun3-fingerprint
mapfile -t pi_packages < <(rpm -qa --qf '%{NAME}\n' |
    grep -E '^bcm(283x-firmware|2835-firmware|2711-firmware|2712-firmware|283x-overlays)$' || true)
if (( ${#pi_packages[@]} )); then
    dnf -y remove --noautoremove "${pi_packages[@]}"
fi

mapfile -t kernels < <(find /usr/lib/modules -mindepth 1 -maxdepth 1 -type d \
    -name '*-gaokun3-el2*' -printf '%f\n')
[[ ${#kernels[@]} == 1 ]]
krel=${kernels[0]}
mkdir -p /usr/share/gaokun3 /usr/share/anaconda/post-scripts
printf '%s\n' "$krel" > /usr/share/gaokun3/live-kernel-release

dracut --force --no-hostonly --no-hostonly-cmdline \
    --add dmsquash-live --add-drivers 'erofs overlay' \
    --kver "$krel" /tmp/gaokun-live-initrd.img

cat > /usr/share/anaconda/post-scripts/90-gaokun3-boot.ks <<'POST'
%post --interpreter=/bin/bash --erroronfail --log=/root/gaokun3-boot.log
set -euo pipefail
krel=$(cat /usr/share/gaokun3/live-kernel-release)
test -x /usr/libexec/gaokun3/kernel-setup
mountpoint -q /boot/efi
rm -f /etc/kernel/cmdline
/usr/libexec/gaokun3/kernel-setup "$krel" qcom/sc8280xp-huawei-gaokun3-el2.dtb
if ! bootctl --esp-path=/boot/efi install; then
    bootctl --esp-path=/boot/efi --no-variables install
fi
token=$(cat /etc/kernel/entry-token)
entry="/boot/efi/loader/entries/$token-$krel.conf"
test -s "$entry"
if grep -Eq 'root=live:|rd\.live' "$entry"; then
    echo 'Live-media arguments reached the installed boot entry.' >&2
    exit 1
fi
grep -q 'root=UUID=' "$entry"
echo "default $token-$krel.conf" > /boot/efi/loader/loader.conf
echo 'timeout 5' >> /boot/efi/loader/loader.conf
sync -f /boot/efi
%end
POST

python3 -c 'from pykickstart.parser import KickstartParser; from pykickstart.version import makeVersion; p=KickstartParser(makeVersion("F45")); p.readKickstart("/usr/share/anaconda/post-scripts/90-gaokun3-boot.ks"); assert len(p.handler.scripts) == 1'
lsinitrd -m /tmp/gaokun-live-initrd.img | grep -xq dmsquash-live
lsinitrd /tmp/gaokun-live-initrd.img | grep -q '/erofs\.ko$'
lsinitrd /tmp/gaokun-live-initrd.img | grep -q '/overlay\.ko$'

dnf clean all
rm -rf /var/tmp/gaokun-rpms
CHROOT

krel=$(cat "$work/root/usr/share/gaokun3/live-kernel-release")
dtb=sc8280xp-huawei-gaokun3-el2.dtb
[[ -f $work/root/boot/vmlinuz-$krel ]]
[[ -f $work/root/usr/lib/modules/$krel/dtb/qcom/$dtb ]]
[[ -s $work/root/tmp/gaokun-live-initrd.img ]]
[[ -x $work/root/usr/libexec/gaokun3/kernel-setup ]]
grep -q '^%post ' "$work/root/usr/share/anaconda/post-scripts/90-gaokun3-boot.ks"

cp "$work/root/tmp/gaokun-live-initrd.img" "$work/gaokun-live-initrd.img"
rm -f "$work/root/tmp/gaokun-live-initrd.img"
rm -f "$work/root/etc/resolv.conf"
if [[ -e $work/resolv.conf.saved || -L $work/resolv.conf.saved ]]; then
    cp -a "$work/resolv.conf.saved" "$work/root/etc/resolv.conf"
fi
umount -R "$work/root/dev"
umount "$work/root/proc" "$work/root/sys" "$work/root/run"

if ! chroot "$work/root" setfiles -F -e /dev -e /proc -e /sys -e /run \
    /etc/selinux/targeted/contexts/files/file_contexts /; then
    touch "$work/root/.autorelabel"
fi

new_erofs="$work/gaokun-live.erofs"
mkfs.erofs -zzstd,9 "$new_erofs" "$work/root"
old_size=$(stat -c %s "$squashfs")
new_size=$(stat -c %s "$new_erofs")
[[ $new_size -lt 4294967296 ]]

iso_size=$(stat -c %s "$source_iso")
mib=$((1024 * 1024))
image_size=$((iso_size - old_size + new_size + 128 * mib))
image_size=$(((image_size + mib - 1) / mib * mib))
truncate -s "$image_size" "$output_image"
parted -s "$output_image" mklabel gpt
parted -s "$output_image" mkpart ESP fat32 1MiB 100%
parted -s "$output_image" set 1 esp on
target_loop=$(losetup --find --show --partscan "$output_image")
udevadm settle
mkfs.vfat -F 32 -n GAOKUNLIVE "${target_loop}p1"
mount "${target_loop}p1" "$work/media"
rsync -rt --exclude=/EFI --exclude=/boot --exclude=/LiveOS/squashfs.img \
    "$work/iso/" "$work/media/"
mkdir -p "$work/media"/{EFI/BOOT,EFI/systemd/drivers,LiveOS,gaokun,loader/entries,firmware/qcom/sc8280xp/HUAWEI/gaokun3}
cp "$new_erofs" "$work/media/LiveOS/squashfs.img"

cp "$work/root/usr/lib/systemd/boot/efi/systemd-bootaa64.efi" \
    "$work/media/EFI/BOOT/BOOTAA64.EFI"
cp "$work/root/usr/share/gaokun3/el2/qebspilaa64.efi" \
    "$work/root/usr/share/gaokun3/el2/slbounceaa64.efi" \
    "$work/media/EFI/systemd/drivers/"
cp "$work/root/usr/share/gaokun3/el2/tcblaunch.exe" "$work/media/"
for firmware in qcadsp8280.mbn qccdsp8280.mbn qcslpi8280.mbn; do
    cp "$work/root/usr/lib/firmware/qcom/sc8280xp/HUAWEI/gaokun3/$firmware" \
        "$work/media/firmware/qcom/sc8280xp/HUAWEI/gaokun3/"
done
cp "$work/root/boot/vmlinuz-$krel" "$work/media/gaokun/linux"
cp "$work/gaokun-live-initrd.img" "$work/media/gaokun/initrd"
cp "$work/root/usr/lib/modules/$krel/dtb/qcom/$dtb" "$work/media/gaokun/$dtb"

platform_args=$(cat "$work/root/usr/share/gaokun3/platform-cmdline")
cat > "$work/media/loader/entries/gaokun-live.conf" <<ENTRY
title Fedora 45 Live - Gaokun3
linux /gaokun/linux
initrd /gaokun/initrd
devicetree /gaokun/$dtb
options root=live:LABEL=GAOKUNLIVE rd.live.image rd.live.overlay.overlayfs=1 $platform_args
ENTRY
printf 'default gaokun-live.conf\ntimeout 5\n' > "$work/media/loader/loader.conf"
source_sha=$(sha256sum "$squashfs" | awk '{print $1}')
cat > "$work/media/gaokun/image-build.txt" <<BUILD
Fedora Live ISO: $(basename "$source_iso")
Gaokun kernel: $krel
Source LiveOS SHA256: $source_sha
BUILD

cmp "$new_erofs" "$work/media/LiveOS/squashfs.img"
[[ $(blkid -s LABEL -o value "${target_loop}p1") == GAOKUNLIVE ]]
grep -q 'root=live:LABEL=GAOKUNLIVE' "$work/media/loader/entries/gaokun-live.conf"
grep -q '^%post ' "$work/root/usr/share/anaconda/post-scripts/90-gaokun3-boot.ks"
sync
umount "$work/media"
fsck.fat -n "${target_loop}p1"
losetup -d "$target_loop"
target_loop=''
umount "$work/iso"
echo "Prepared $output_image ($image_size bytes, $krel)"

