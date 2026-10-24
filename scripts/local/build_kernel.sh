#!/usr/bin/env bash
set -euo pipefail

KERNEL_TAG="${KERNEL_TAG:-v7.3}"
GAOKUN_DIR="${GAOKUN_DIR:-$HOME/gaokun/linux-gaokun-buildbot}"
KERN_SRC="${KERN_SRC:-$HOME/gaokun/mainline-linux}"
KERN_OUT="${KERN_OUT:-$HOME/gaokun/kernel-out}"
KERN_OUT_EL2="${KERN_OUT_EL2:-$HOME/gaokun/kernel-out-el2}"

if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    DISTRO="$ID"
else
    echo "Cannot determine OS distribution. Exiting."
    exit 1
fi

if [[ "$DISTRO" != "fedora" ]]; then
    echo "Unsupported distribution: $DISTRO. Only Fedora is supported. Exiting."
    exit 1
fi

read -r -p "Install necessary minimal kernel build toolchain? [y/N] [default: n]: " install_deps
install_deps="${install_deps:-n}"
if [[ "$install_deps" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "Installing build dependencies for $DISTRO..."
    sudo dnf install -y gcc make bison flex bc openssl-devel elfutils-libelf-devel ncurses-devel dwarves git ccache curl
fi

export CCACHE_DIR="${CCACHE_DIR:-$HOME/gaokun/.ccache}"
export CCACHE_BASEDIR="${CCACHE_BASEDIR:-$HOME/gaokun}"
export CCACHE_NOHASHDIR="${CCACHE_NOHASHDIR:-true}"
export CCACHE_COMPILERCHECK="${CCACHE_COMPILERCHECK:-content}"

if [[ -d /usr/lib64/ccache ]]; then
    export PATH="/usr/lib64/ccache:$PATH"
elif [[ -d /usr/lib/ccache ]]; then
    export PATH="/usr/lib/ccache:$PATH"
fi

if [[ "$(uname -m)" == "aarch64" ]]; then
    CROSS_COMPILE="${CROSS_COMPILE:-}"
else
    CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}"
fi

read -r -p "Build EL2 kernel? (Y: only EL2, n: only standard, both: build both) [default: n]: " el2_choice
el2_choice="${el2_choice:-n}"

configure_git_identity() {
    if [[ -z "$(git -C "$KERN_SRC" config user.name || true)" ]]; then
        git -C "$KERN_SRC" config user.name "local builder"
    fi
    if [[ -z "$(git -C "$KERN_SRC" config user.email || true)" ]]; then
        git -C "$KERN_SRC" config user.email "builder@example.com"
    fi
}

ensure_source_tree() {
    if [[ -f "$KERN_SRC/arch/arm64/configs/gaokun3_defconfig" ]]; then
        source "$GAOKUN_DIR/kernel-source.env"
        python3 "$GAOKUN_DIR/tools/kernel/check-patch-inventory.py"
        local reviewed_digest
        reviewed_digest=$(sha256sum "$GAOKUN_DIR/patches/inventory.json" | cut -d " " -f1)
        if [[ ! -f "$KERN_SRC/.gaokun-patch-inventory.sha256" ]] ||
           [[ $(cat "$KERN_SRC/.gaokun-patch-inventory.sha256") != "$reviewed_digest" ]]; then
            echo "Existing source has a different patch inventory; use a new KERN_SRC directory" >&2
            exit 1
        fi
        git -C "$KERN_SRC" merge-base --is-ancestor "$GAOKUN_KERNEL_COMMIT" HEAD || {
            echo "Existing kernel tree is not based on $GAOKUN_KERNEL_TAG; use a new KERN_SRC directory" >&2
            exit 1
        }
        return 0
    fi

    read -r -p "gaokun3_defconfig not found in kernel directory. Pull kernel and apply patches? [y/N] [default: N]: " response
    response="${response:-N}"
    if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "Exiting."
        exit 1
    fi

    if [[ ! -d "$GAOKUN_DIR" ]]; then
        echo "linux-gaokun-buildbot not found. Cloning..."
        mkdir -p "$HOME/gaokun"
        git clone https://github.com/zhzy0077/linux-gaokun-buildbot "$GAOKUN_DIR"
    fi

    read -r -p "Use GitHub mirror (torvalds/linux) for Linux v7.3? [Y/n] [default: Y]: " mirror_choice
    mirror_choice="${mirror_choice:-Y}"
    if [[ "$mirror_choice" =~ ^([nN][oO]|[nN])$ ]]; then
        KERNEL_URL="https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
    else
        KERNEL_URL="https://github.com/torvalds/linux.git"
    fi

    rm -rf "$KERN_SRC"
    git clone --depth=1 "$KERNEL_URL" "$KERN_SRC" -b "$KERNEL_TAG"
    bash "$GAOKUN_DIR/scripts/ci/verify_kernel_source.sh" "$KERN_SRC"
    configure_git_identity

    echo "Applying standard gaokun3 patches..."
    git -C "$KERN_SRC" am "$GAOKUN_DIR"/patches/upstream/*.patch
    git -C "$KERN_SRC" am "$GAOKUN_DIR"/patches/others/*.patch
    git -C "$KERN_SRC" am "$GAOKUN_DIR"/patches/media/*.patch
    python3 "$GAOKUN_DIR/tools/kernel/import-board-files.py" "$KERN_SRC"
    sha256sum "$GAOKUN_DIR/patches/inventory.json" | cut -d " " -f1 > "$KERN_SRC/.gaokun-patch-inventory.sha256"
}

el2_state() {
    if git -C "$KERN_SRC" log -1 --pretty=%B 2>/dev/null | grep -q "^Apply EL2 patches$"; then
        printf 'el2\n'
        return 0
    fi

    if git -C "$KERN_SRC" apply --reverse --check "$GAOKUN_DIR"/patches/el2/*.patch >/dev/null 2>&1; then
        printf 'el2-mixed\n'
        return 0
    fi

    printf 'standard\n'
}

build_kernel() {
    local mode="$1"
    local out_dir
    local dtb_name
    local cmdline
    local conf_root
    local current_state

    cd "$KERN_SRC"
    current_state="$(el2_state)"

    # Refresh board sources beneath the temporary EL2 commit on every build.
    if [[ "$current_state" == "el2" ]]; then
        if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
            echo "Commit or stash tracked kernel changes before switching variants" >&2
            exit 1
        fi
        git reset --hard HEAD~1
        current_state=standard
    elif [[ "$current_state" != "standard" ]]; then
        echo "Restore the kernel checkout to a standard state before importing board files" >&2
        exit 1
    fi
    configure_git_identity
    python3 "$GAOKUN_DIR/tools/kernel/import-board-files.py" "$KERN_SRC"

    if [[ "$mode" == "el2" ]]; then
        out_dir="$KERN_OUT_EL2"
        dtb_name="sc8280xp-huawei-gaokun3-el2.dtb"

        echo -e "\n=== Preparing Source Tree for EL2 Kernel ==="
        echo "Applying EL2 patches to source tree..."
        git apply --index "$GAOKUN_DIR"/patches/el2/*.patch
        git commit -m "Apply EL2 patches"

        mkdir -p "$out_dir"
        make O="$out_dir" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" gaokun3_defconfig
        "$KERN_SRC"/scripts/config --file "$out_dir/.config" --set-str LOCALVERSION "-gaokun3-el2"
    else
        out_dir="$KERN_OUT"
        dtb_name="sc8280xp-huawei-gaokun3.dtb"

        echo -e "\n=== Preparing Source Tree for Standard Kernel ==="
        mkdir -p "$out_dir"
        make O="$out_dir" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" gaokun3_defconfig
    fi

    echo "Starting build..."
    make O="$out_dir" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" olddefconfig
    make O="$out_dir" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" -j"$(nproc)"
    make O="$out_dir" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" modules_prepare

    local krel
    krel="$(<"$out_dir/include/config/kernel.release")"
    echo "KREL ($mode): $krel"

    read -r -p "Compilation of $mode kernel finished. Install this kernel ($krel)? [Y/n] [default: Y]: " do_install
    do_install="${do_install:-Y}"
    if [[ ! "$do_install" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "Skipping installation for $mode kernel."
        return 0
    fi

    local initrd_src
    local dtb_inst_dir
    local dtb_boot_dir

    initrd_src="initramfs-$krel.img"
    dtb_inst_dir="/usr/lib/modules/$krel/dtb/qcom"
    dtb_boot_dir="/boot/dtb-$krel/qcom"

    sudo make O="$out_dir" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" INSTALL_MOD_PATH=/ modules_install
    sudo rm -f /lib/modules/"$krel"/{build,source}

    sudo cp "$out_dir"/arch/arm64/boot/vmlinuz.efi /boot/vmlinuz-"$krel"
    sudo mkdir -p "$dtb_inst_dir"
    sudo cp "$out_dir"/arch/arm64/boot/dts/qcom/"$dtb_name" "$dtb_inst_dir"/"$dtb_name"
    sudo mkdir -p "$dtb_boot_dir"
    sudo cp "$out_dir"/arch/arm64/boot/dts/qcom/"$dtb_name" "$dtb_boot_dir"/"$dtb_name"

    if ! sudo test -f "$dtb_inst_dir/$dtb_name"; then
        echo "ERROR: DTB was not installed where kernel-install expects it:" >&2
        echo "  expected: $dtb_inst_dir/$dtb_name" >&2
        echo "  source:   $out_dir/arch/arm64/boot/dts/qcom/$dtb_name" >&2
        sudo ls -ld "$dtb_inst_dir" 2>/dev/null || true
        sudo find "$(dirname "$dtb_inst_dir")" -maxdepth 3 -type f 2>/dev/null | sort || true
        exit 1
    fi

    if [[ -f /etc/kernel/cmdline ]]; then
        cmdline="$(tr -s '[:space:]' ' ' </etc/kernel/cmdline)"
    else
        cmdline="$(tr ' ' '\n' </proc/cmdline | grep -ve '^BOOT_IMAGE=' -e '^initrd=' | tr '\n' ' ')"
    fi
    cmdline="${cmdline%" "}"

    if [[ "$mode" == "el2" && "$cmdline" != *"modprobe.blacklist=simpledrm"* ]]; then
        cmdline="${cmdline} modprobe.blacklist=simpledrm"
        cmdline="${cmdline#" "}"
    fi

    conf_root="$(mktemp -d)"
    trap 'rm -rf "$conf_root"' RETURN

    printf 'layout=bls\n' >"$conf_root/install.conf"
    printf '%s\n' "$cmdline" >"$conf_root/cmdline"
    printf 'qcom/%s\n' "$dtb_name" >"$conf_root/devicetree"

    sudo dracut --force --hostonly --no-hostonly-cmdline --kver "$krel"

    echo "kernel-install inputs:"
    echo "  kernel release: $krel"
    echo "  kernel image:   /boot/vmlinuz-$krel"
    echo "  initrd:         /boot/$initrd_src"
    echo "  devicetree:     qcom/$dtb_name"
    echo "  dtb source:     $dtb_inst_dir/$dtb_name"

    {
        sudo kernel-install --entry-token=machine-id remove "$krel" >/dev/null 2>&1 || true
        sudo env KERNEL_INSTALL_CONF_ROOT="$conf_root" \
            kernel-install --verbose --make-entry-directory=yes --entry-token=machine-id add \
            "$krel" "/boot/vmlinuz-$krel" "/boot/$initrd_src"
    } || {
        rm -rf "$conf_root"
        trap - RETURN
        return 1
    }

    rm -rf "$conf_root"
    trap - RETURN
}

ensure_source_tree
configure_git_identity

if command -v ccache >/dev/null 2>&1; then
    echo "Resetting ccache statistics..."
    ccache -z
fi

if [[ "$el2_choice" == "both" ]]; then
    build_kernel "std"
    build_kernel "el2"
elif [[ "$el2_choice" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    build_kernel "el2"
else
    build_kernel "std"
fi

if command -v ccache >/dev/null 2>&1; then
    echo -e "\n----------------------------------------"
    echo "Ccache statistics for this build:"
    ccache -s
    echo "----------------------------------------"
fi

echo -e "\nDone! Kernel update script finished."
