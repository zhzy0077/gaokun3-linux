#!/usr/bin/env bash
set -euo pipefail
[[ $EUID == 0 && $# == 2 ]] || {
    echo 'Usage: sudo install-libfprint.sh LIBFPRINT_STAGE NATIVE_CLIENT_DIRECTORY' >&2
    exit 1
}
stage=$(realpath "$1")
native=$(realpath "$2")
tools_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
prefix=/opt/gaokun3-fingerprint
[[ $(cat /sys/module/qcomtee/parameters/user_bridge_mode) == [12] ]]
[[ -f "$stage/opt/gaokun3-fingerprint/libfprint/lib64/libfprint-2.so.2.0.0" ]]
[[ -x "$native/qtee-client" && -x "$native/reset-mcu" ]]
firmware=/usr/lib/firmware/qcom/sc8280xp/HUAWEI/gaokun3/fingerpr.mbn
[[ $(sha256sum "$firmware" | cut -d ' ' -f 1) == b081543c7b6ae4360969007836747601e8c48ec48a8335a5479e45ec0e34355a ]]
systemctl stop fprintd.service
install -d -m 0755 "$prefix/native"
cp -a "$stage/opt/gaokun3-fingerprint/libfprint" "$prefix/"
chown -R root:root "$prefix/libfprint"
install -m 0755 "$native/qtee-client" "$native/reset-mcu" \
    "$tools_dir/run-qtee-client.py" "$prefix/native/"
install -m 0755 "$tools_dir/fingerprint-helper" "$prefix/"
install -d -m 0700 /var/lib/gaokun3-fingerprint/secure-files
policy=$(mktemp -d)
trap 'rm -rf "$policy"' EXIT
checkmodule -M -m -o "$policy/gaokun3_fingerprint.mod" "$tools_dir/gaokun3-fingerprint.te"
semodule_package -o "$policy/gaokun3_fingerprint.pp" -m "$policy/gaokun3_fingerprint.mod"
semodule -i "$policy/gaokun3_fingerprint.pp"
semanage fcontext -a -t gaokun3_fp_tee_device_t /dev/tee0 || \
    semanage fcontext -m -t gaokun3_fp_tee_device_t /dev/tee0
semanage fcontext -a -t fprintd_var_lib_t '/var/lib/gaokun3-fingerprint/secure-files(/.*)?' || \
    semanage fcontext -m -t fprintd_var_lib_t '/var/lib/gaokun3-fingerprint/secure-files(/.*)?'
restorecon -RF "$prefix" /var/lib/gaokun3-fingerprint/secure-files
restorecon /dev/tee0
install -D -m 0644 "$tools_dir/fprintd-override.conf" \
    /etc/systemd/system/fprintd.service.d/gaokun3-fingerprint.conf
systemctl daemon-reload
systemctl start fprintd.service
busctl call net.reactivated.Fprint /net/reactivated/Fprint/Manager \
    net.reactivated.Fprint.Manager GetDevices
