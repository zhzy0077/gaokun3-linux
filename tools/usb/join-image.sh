#!/usr/bin/env bash
# Run from the directory containing all image parts and checksum files.
set -euo pipefail
image=fedora-gaokun3-usb.raw.xz
[[ ! -e "$image" && ! -e "$image.partial" ]] || {
    echo 'Output already exists; move it aside before joining.' >&2
    exit 1
}
if command -v sha256sum >/dev/null; then
    checksum=(sha256sum)
else
    checksum=(shasum -a 256)
fi
"${checksum[@]}" --check SHA256SUMS.parts
# The manifest defines both the required files and their order.
while read -r digest part; do
    [[ $digest =~ ^[[:xdigit:]]{64}$ && $part =~ ^fedora-gaokun3-usb\.raw\.xz\.[0-9]{3}$ ]]
    cat -- "$part"
done < SHA256SUMS.parts > "$image.partial"
mv "$image.partial" "$image"
"${checksum[@]}" --check SHA256SUMS
echo "Verified $image. Select this file in balenaEtcher."
