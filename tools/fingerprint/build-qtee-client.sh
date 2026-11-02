#!/usr/bin/env bash
set -euo pipefail
[[ $# == 2 ]] || { echo "Usage: $0 QUIC_TEEC_SOURCE OUTPUT_DIR" >&2; exit 1; }
source_dir=$(realpath "$1")
output_dir=$(realpath -m "$2")
tools_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
expected=736419e25a2036aac3292a10a93e394a90750ca3
[[ $(git -C "$source_dir" rev-parse HEAD) == "$expected" ]]
[[ -z $(git -C "$source_dir" status --porcelain --untracked-files=no) ]]
cmake -S "$source_dir" -B "$output_dir/library" -DBUILD_UNITTEST=OFF
cmake --build "$output_dir/library" -j4
cc -O2 -Wall -Wextra -Werror -pthread \
    -I "$source_dir/libqcomtee/include" -I "$source_dir/tests" \
    "$tools_dir/qtee-client.c" "$tools_dir/qtee-listener.c" "$tools_dir/gpfs.c" "$source_dir/tests/common.c" \
    "$output_dir/library/libqcomtee/libqcomtee.a" -lcbor \
    -o "$output_dir/qtee-client"
cc -O2 -Wall -Wextra -Werror "$tools_dir/reset-mcu.c" -o "$output_dir/reset-mcu"
printf '%s\n' "$expected" > "$output_dir/quic-teec-commit"
sha256sum "$tools_dir/qtee-client.c" "$tools_dir/reset-mcu.c" \
    "$tools_dir/run-qtee-client.py" "$output_dir/qtee-client" \
    "$output_dir/reset-mcu" \
    "$tools_dir/qtee-listener.c" "$tools_dir/qtee-listener.h" \
    "$tools_dir/gpfs.c" "$tools_dir/gpfs.h" > "$output_dir/sha256sums"
