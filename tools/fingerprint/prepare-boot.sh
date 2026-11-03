#!/usr/bin/env bash
set -euo pipefail

# Usage: sudo prepare-boot.sh EXTRACTED_ARTIFACTS IMAGE INITRAMFS CURRENT_ENTRY
[[ $EUID -eq 0 ]] || { echo "Run as root" >&2; exit 1; }
stage=$(realpath "${1:?extracted artifact directory}")
vendor_image=$(realpath "${2:?fingerpr.mbn}")
initramfs=$(realpath "${3:?prepared experimental initramfs}")
current_entry=$(realpath "${4:?current boot entry}")
tools_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(realpath "$tools_dir/../..")
krel=$(cat "$stage/metadata/kernel-release")
[[ $krel =~ ^[0-9][a-zA-Z0-9.+_-]*-gaokun3-el2\+?$ ]]
python3 "$repo_root/tools/boot/check-kernel-config.py" \
    --repo "$repo_root" --distro fedora --package "$stage/metadata"
cmp "$stage/metadata/.config" "$stage/boot/config-$krel"
expected=b081543c7b6ae4360969007836747601e8c48ec48a8335a5479e45ec0e34355a
[[ $(sha256sum "$vendor_image" | cut -d ' ' -f 1) == "$expected" ]]
[[ -f "$stage/boot/config-$krel" ]]
[[ $(awk '$1 == "version" {print $2}' "$current_entry") == "$(uname -r)" ]]
options=$(sed -n 's/^options[[:space:]]\+//p' "$current_entry")
[[ $options == *root=* ]]
[[ " $options " == *" panic="* ]] || options+=" panic=30"
mountpoint -q /boot/efi

destination=/boot/efi/gaokun3-fingerprint
entry=/boot/efi/loader/entries/gaokun3-fingerprint.conf
kernel="$stage/boot/linux-$krel.efi"
dtb="$stage/boot/sc8280xp-huawei-gaokun3-fp-el2.dtb"
needed=$(( $(stat -c %s "$kernel") + $(stat -c %s "$dtb") + $(stat -c %s "$initramfs") + 1048576 ))
if [[ -d $destination ]]; then
    needed=$((needed - $(du -sb "$destination" | cut -f 1)))
fi
available=$(df -B1 --output=avail /boot/efi | tail -1)
(( available >= needed )) || { echo "ESP needs $needed bytes; available $available" >&2; exit 1; }

if [[ -d /usr/lib/modules/$krel ]]; then
    cmp "$stage/lib/modules/$krel/kernel/drivers/tee/qcomtee/qcomtee.ko" \
        "/usr/lib/modules/$krel/kernel/drivers/tee/qcomtee/qcomtee.ko"
else
    cp -a "$stage/lib/modules/$krel" /usr/lib/modules/
fi
chown -R root:root "/usr/lib/modules/$krel"
restorecon -R "/usr/lib/modules/$krel"
depmod "$krel"
install -m 0644 "$stage/boot/config-$krel" "$stage/boot/System.map-$krel" /boot/
install -D -m 0644 "$vendor_image" \
    /usr/lib/firmware/qcom/sc8280xp/HUAWEI/gaokun3/fingerpr.mbn
restorecon /usr/lib/firmware/qcom/sc8280xp/HUAWEI/gaokun3/fingerpr.mbn
install -D -m 0644 "$stage/metadata/kernel-release" /var/lib/gaokun3-fingerprint/kernel-release
install -d "$destination"
install -m 0644 "$kernel" "$destination/linux.efi"
install -m 0644 "$dtb" "$destination/board.dtb"
install -m 0644 "$initramfs" "$destination/initrd.img"
cat > "$entry" <<EOF
title      Gaokun3 fingerprint experiment
version    $krel
sort-key   gaokun3-fingerprint
linux      /gaokun3-fingerprint/linux.efi
devicetree /gaokun3-fingerprint/board.dtb
initrd     /gaokun3-fingerprint/initrd.img
options    $options
EOF
sync -f /boot/efi
sha256sum "$destination/linux.efi" "$destination/board.dtb" "$destination/initrd.img"
printf 'Prepared boot entry: %s\n' "$entry"
