# SC8280XP video decoding

The `iris-sc8280xp` test branch replaces the old legacy Venus additions with
SC8280XP platform data for Iris and enables the codec in the Gaokun board DT.
The test kernel boots and registers Iris, but EL2 firmware startup remains
blocked. See the runtime findings below.

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
   Check `ffmpeg -decoders` for these wrappers: Fedora's `ffmpeg-free` omits
   some of them. RPM Fusion's full `ffmpeg-libs` or a separate full FFmpeg
   build can supply them.
4. Repeat playback after suspend/resume, checking kernel logs for new faults.
5. With Firefox hardware decoding enabled, run `gfxtest v4l2 -d DEVICE`, then
   play a local sample in an isolated Firefox profile. Capture decoder-selection
   logs and verify actual hardware decoding, rendered video, and dropped frames.

VA-API may still report no `msm_drv_video.so`; this integration uses V4L2 M2M.
Firefox's sequential scanning of the CAMSS capture nodes is a separate startup
issue and remains to be fixed in Firefox.

Firefox's V4L2 path additionally requires DRM PRIME frame export. The stock
FFmpeg 8.1.3 libraries inspected on this device expose V4L2 decoder wrappers
but no DRM PRIME hardware configuration for them. This is the problem tracked
in [Mozilla bug 1852765](https://bugzilla.mozilla.org/show_bug.cgi?id=1852765).
The `gaokun-video-userspace.yml` workflow builds isolated shared libraries from
`jc-kynesim/rpi-ffmpeg`, pinned to commit
`f60aae17021abae85b1ba9759e8b2da33f723902` (the `test/8.1.2/main` branch).
It checks the public libavcodec capability API before uploading the bundle.
Use its `lib` directory through `LD_LIBRARY_PATH` for the isolated test process;
system libraries remain managed by the distribution packages.

## Playback checker

Use a FFmpeg executable that lists `h264_v4l2m2m`, `hevc_v4l2m2m`, and
`vp9_v4l2m2m` in `-decoders`. Prepare the 720p samples before the test boot:

```sh
python3 tools/video/validate-decoder.py --ffmpeg /path/to/ffmpeg \
  --work-dir /path/to/playback-results --prepare-only
```

After the test boot, omit `--prepare-only` to perform five hardware/software
frame-checksum comparisons per codec and 60 seconds of paced decoding per
codec. The checker saves V4L2 capabilities, the compliance report, FFmpeg logs,
and a JSON result. `--codecs h264` restricts the first bring-up attempt.
Compliance failures are recorded separately from playback results; inspect
that report even when the decode checks pass. Repeat into a separate results
directory after suspend/resume. Firefox playback remains an additional check.
With the isolated DRM PRIME libraries, add `--drm-prime` to check hardware-frame
output as well as the pixel comparisons.

For Firefox, use a fresh results directory:

```sh
python3 tools/video/validate-firefox.py --samples /path/to/playback-results \
  --results /path/to/firefox-results --library-dir /path/to/ffmpeg-stage/lib
```

This opens temporary Firefox profiles for H.264 and VP9, plays the local
samples, records browser frame counters, and requires actual V4L2 output-frame
logs. It leaves the regular Firefox profile untouched. `--codecs hevc` can
test HEVC separately when the browser exposes that codec.

The pre-boot baseline on `7.2.9-gaokun3-el2+` played all 90 H.264 frames but
logged zero V4L2 output frames, correctly failing the hardware-playback check.

## EL2 runtime findings (2026-10-15)

On `7.2.9-iris1-gaokun3-el2+`, Iris registers decoder and encoder nodes.
Opening either initially fails at `PAS_INIT_IMAGE`: SCM returns -2, mapped
to Linux -EINVAL. The packaged driver reports this to userspace as ENOMEM.

Temporary diagnostic modules built against the exact CI development RPM
established the following:

| Experiment | Result | CI run |
| --- | --- | --- |
| Use a PAS context with TZMEM and prepared authentication | Metadata initialization, memory setup and authentication succeed; video protection-range setup fails with -EIO | [38681846600](https://github.com/zhzy0077/linux-gaokun-buildbot/actions/runs/38681846600) |
| Temporarily skip protection-range setup | Firmware-ready polling times out | [38682067019](https://github.com/zhzy0077/linux-gaokun-buildbot/actions/runs/38682067019) |
| Query the firmware resource table before authentication | TrustZone returns -EIO and supplies no usable table | [38682333207](https://github.com/zhzy0077/linux-gaokun-buildbot/actions/runs/38682333207) |

The first error is caused by missing PAS metadata sharing. Authentication
success alone does not demonstrate that the processor started executing.
The remaining timeout requires investigation of firmware IOMMU mappings and
the EL2 reset/start sequence. The resource-query failure alone does not establish
that the API is unsupported.

[Upstream EL2 support](https://lkml.iu.edu/2508.2/04531.html) requires a separate
firmware IOMMU domain and mappings for firmware and its device resources.
[The PAS migration patch](https://www.mail-archive.com/linux-kernel@vger.kernel.org/msg2659652.html)
also explains the missing context and shared-memory preparation.
SC8280XP mapping and reset details must be established before adapting that
support. An EL1 comparison requires the Qualcomm hypervisor boot path.

The diagnostic patch in `tools/video/diagnostic` is excluded from the normal
kernel patch series. Its options default off. All three tests restored the
packaged Iris module afterward; no runtime hardware-decoding test has passed.
