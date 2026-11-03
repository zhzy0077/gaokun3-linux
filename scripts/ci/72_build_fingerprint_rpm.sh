#!/usr/bin/env bash
set -euo pipefail

: "${GAOKUN_DIR:?missing GAOKUN_DIR}"
: "${WORKDIR:?missing WORKDIR}"
: "${ARTIFACT_DIR:?missing ARTIFACT_DIR}"
: "${FINGERPRINT_LIBFPRINT_STAGE:?missing FINGERPRINT_LIBFPRINT_STAGE}"
: "${FINGERPRINT_NATIVE_DIR:?missing FINGERPRINT_NATIVE_DIR}"

topdir=$(mktemp -d "$WORKDIR/fingerprint-rpmbuild.XXXXXX")
stage="$topdir/stage"
mkdir -p "$topdir"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} \
         "$stage/opt/gaokun3-fingerprint/native" \
         "$stage/etc/modprobe.d" "$stage/etc/systemd/system/fprintd.service.d" \
         "$stage/usr/share/selinux/packages"
cp -a "$FINGERPRINT_LIBFPRINT_STAGE/opt/gaokun3-fingerprint/libfprint" \
    "$stage/opt/gaokun3-fingerprint/"
install -m 0755 "$FINGERPRINT_NATIVE_DIR/qtee-client" "$FINGERPRINT_NATIVE_DIR/reset-mcu" \
    "$GAOKUN_DIR/tools/fingerprint/run-qtee-client.py" \
    "$stage/opt/gaokun3-fingerprint/native/"
install -m 0755 "$GAOKUN_DIR/tools/fingerprint/fingerprint-helper" \
    "$stage/opt/gaokun3-fingerprint/"
install -m 0644 "$GAOKUN_DIR/tools/fingerprint/qcomtee.conf" \
    "$stage/etc/modprobe.d/gaokun3-fingerprint.conf"
install -m 0644 "$GAOKUN_DIR/tools/fingerprint/fprintd-override.conf" \
    "$stage/etc/systemd/system/fprintd.service.d/gaokun3-fingerprint.conf"
checkmodule -M -m -o "$topdir/gaokun3_fingerprint.mod" \
    "$GAOKUN_DIR/tools/fingerprint/gaokun3-fingerprint.te"
semodule_package -o "$stage/usr/share/selinux/packages/gaokun3_fingerprint.pp" \
    -m "$topdir/gaokun3_fingerprint.mod"
tar -C "$stage" -czf "$topdir/SOURCES/gaokun3-fingerprint.tar.gz" .
version=$(date -u +%Y%m%d)
sed -e "s|@FINGERPRINT_VERSION@|$version|g" \
    -e 's|@SOURCE_NAME@|gaokun3-fingerprint.tar.gz|g' \
    "$GAOKUN_DIR/packaging/rpm/gaokun3-fingerprint.spec.in" \
    > "$topdir/SPECS/gaokun3-fingerprint.spec"
rpmbuild --define "_topdir $topdir" -bb "$topdir/SPECS/gaokun3-fingerprint.spec"
rpm=$(find "$topdir/RPMS" -name 'gaokun3-fingerprint-*.rpm' -print -quit)
install -m 0644 "$rpm" "$ARTIFACT_DIR/"
basename "$rpm" > "$WORKDIR/fingerprint-rpm-name.txt"
