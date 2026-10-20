#!/usr/bin/env bash
# Verify a pristine checkout before applying the reviewed series.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source "$repo_root/kernel-source.env"
python3 "$repo_root/tools/kernel/check-patch-inventory.py"
src=${1:?usage: verify_kernel_source.sh KERNEL_SOURCE}
actual=$(git -C "$src" rev-parse HEAD)
if [[ $actual != "$GAOKUN_KERNEL_COMMIT" ]]; then
    echo "Kernel source mismatch: expected $GAOKUN_KERNEL_TAG ($GAOKUN_KERNEL_COMMIT), got $actual" >&2
    exit 1
fi
if [[ ${KERNEL_TAG:-$GAOKUN_KERNEL_TAG} != "$GAOKUN_KERNEL_TAG" ]]; then
    echo "This patch series targets $GAOKUN_KERNEL_TAG; update kernel-source.env and review patches before changing the tag" >&2
    exit 1
fi
git -C "$src" diff --quiet
git -C "$src" diff --cached --quiet
