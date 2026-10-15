# SC8280XP video decoding

The `iris-sc8280xp` test branch replaces the old legacy Venus additions with
SC8280XP platform data for Iris and enables the codec in the Gaokun board DT.
Hardware playback validation is pending a boot into the test kernel.

## Integration

- Keep Linux 7.2.9 and `CONFIG_VIDEO_QCOM_IRIS=m`.
- Use `qcom,sc8280xp-venus`, one `core` reset, and the `mx` OPP power domain.
  The video clock controller owns the MMCX vote.
- Use four VPP pipes, following Qualcomm's review of the initial two-pipe
  proposal. Reuse the current VPU2 HFI gen1 descriptor and buffer sizing.
- Select `qcom/sc8280xp/HUAWEI/gaokun3/qcvss8280.mbn` explicitly in the board DT.
  This OEM firmware is shipped in this repository; the generic descriptor's
  fallback firmware is not used on Gaokun.
- Keep the 5 MiB firmware reservation at `0x86700000`, the SMMU stream ID
  `0x2e00`, and the upstream series' clock/OPP/interconnect resources.
- The 7.2.9 common Iris power-on path already initializes register `0xb0088`.
  The old series' extra preset callback is unnecessary with this source version.

Sources:

- [v3 cover letter](https://lkml.indiana.edu/2601.3/00690.html)
- [driver platform data](https://lkml.indiana.edu/2601.3/00693.html)
- [SoC device tree](https://lkml.indiana.edu/2601.3/00695.html)
- [Qualcomm firmware and pipe-count review](https://lkml.indiana.edu/2601.3/09487.html)
- [clock-register explanation](https://lkml.indiana.edu/2601.3/09495.html)

## Build and validation

Run the RPM workflow on the test branch with `kernel_tag=v7.2.9`,
`build_el2=true`, and `test_suffix=-iris1`. The suffix isolates the module
directories from the installed kernel. Both builds must pass the module alias,
vermagic, DTB, configuration, and firmware-presence checks in
`tools/video/check-kernel-video.py`. Their JSON reports accompany the packages.

Before installation, check the available ESP space and preserve the current
boot entry. Stage the matching kernel, modules, DTB and initramfs as a separate
test boot. Perform these checks on the device after boot:

1. Confirm `uname -r` identifies the test kernel and the codec binds to
   `qcom-iris`. Check kernel logs for firmware, IOMMU and power-domain failures.
2. Identify `qcom-iris-decoder` by its V4L2 name, enumerate its output/capture
   formats, and run `v4l2-compliance`. Save its full report.
3. Decode H.264, HEVC and VP9 samples with the explicitly selected FFmpeg
   `*_v4l2m2m` decoder for every advertised codec. Compare the decoded frames
   with software decoding, then test repeated opens and sustained playback.
   The installed Fedora `ffmpeg-free` lacks H.264/HEVC V4L2 decoder wrappers;
   use a separate FFmpeg build containing those wrappers for these tests.
4. Repeat playback after suspend/resume, checking kernel logs for new faults.
5. With Firefox hardware decoding enabled, run `gfxtest v4l2 -d DEVICE`, then
   play a local sample in an isolated Firefox profile. Capture decoder-selection
   logs and verify actual hardware decoding, rendered video, and dropped frames.

VA-API may still report no `msm_drv_video.so`; this integration uses V4L2 M2M.
Firefox's sequential scanning of the CAMSS capture nodes is a separate startup
issue and remains to be fixed in Firefox.
