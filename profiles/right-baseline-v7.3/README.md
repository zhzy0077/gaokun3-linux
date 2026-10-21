# Tested right baseline, Linux v7.3

This profile preserves the source and configuration of the locally tested
`7.3.0-right1-gaokun3-el2` build #2 (2026-10-21). The regular packaging
workflows use the reviewed patch inventory; this profile is a separate input.

Apply `right-confirmed-fixes-v7.3.patch` to pristine torvalds/linux commit
`c03c1a14507dfaf8b856c2608f9ac216021fc222` (v7.3), then copy `kernel.config`
to the output directory as `.config`. The patch includes the board DTS,
touchscreen driver, right-0903 baseline and confirmed local fixes. Apply it
once, without also applying the repository's regular patch series.

Build with ARCH=arm64 and the matching configuration using the targets
`vmlinuz.efi modules qcom/sc8280xp-huawei-gaokun3-el2.dtb`.
`source-manifest.json` records the pinned inputs, source hashes, integration
changes and required module parameters. Its local backup paths identify the
original machine's installation records.

The Bluetooth DT address belongs to the tested machine; provision the correct
address when building for another device. Initramfs, module signing, firmware
and boot-entry setup are separate installation steps.

See the [fixes and live verification](../../docs/right_baseline_confirmed_fixes_2026-10-21.md)
for runtime results and the required boot parameters and TPM service masks.
