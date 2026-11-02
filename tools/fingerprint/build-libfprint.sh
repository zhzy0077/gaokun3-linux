#!/usr/bin/env bash
set -euo pipefail
[[ $# == 2 ]] || { echo 'Usage: build-libfprint.sh PINNED_SOURCE NEW_OUTPUT' >&2; exit 1; }
source_dir=$(realpath "$1")
output=$(realpath -m "$2")
tools_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[[ $(git -C "$source_dir" rev-parse HEAD) == 80a4b5ec612892c5c056c48dddaa561452cf37ec ]]
[[ ! -e "$output" ]]
mkdir -p "$output/source"
git -C "$source_dir" archive HEAD | tar -xf - -C "$output/source"
git -C "$output/source" apply "$tools_dir/libfprint.patch"
cp "$tools_dir/fte7001.c" "$output/source/libfprint/drivers/"
podman build --network=host -t localhost/gaokun3-libfprint-fedora45 \
    -f "$tools_dir/Containerfile.libfprint" "$tools_dir" > "$output/container.log" 2>&1
podman run --rm --network=host --userns=keep-id -v "$output/source:/src:Z" -w /src \
    localhost/gaokun3-libfprint-fedora45 bash -euc '
meson setup build --prefix=/opt/gaokun3-fingerprint/libfprint --libdir=lib64 \
    -Ddrivers=fte7001 -Dintrospection=false -Ddoc=false -Dinstalled-tests=false \
    -Dudev_rules=disabled -Dudev_hwdb=disabled
meson compile -C build -j4
meson test -C build fpi-device fpi-ssm fpi-assembling --print-errorlogs
DESTDIR=/src/stage meson install -C build
' > "$output/build.log" 2>&1
sha256sum "$tools_dir/fte7001.c" "$tools_dir/libfprint.patch" \
    "$output/source/stage/opt/gaokun3-fingerprint/libfprint/lib64/libfprint-2.so.2.0.0" \
    > "$output/SHA256SUMS"
