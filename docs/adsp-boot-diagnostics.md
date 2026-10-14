# Gaokun3 EL2 ADSP boot error handling and diagnostics

Patch: `patches/el2/0023-remoteproc-qcom-report-attach-errors-and-SMP2P-state.patch`

## Return values

`qcom_q6v5_read_smp2p_state()` now returns an `int`:

| Result | Return / effect |
| --- | --- |
| All four reads succeed | `0`; mark DETACHED only for ready + handover, with fatal and stop clear |
| Any read fails | First read error, in handover/ready/fatal/stop order; leave state unchanged |

PAS checks that result before registering subdevices:

| Device | Probe decision |
| --- | --- |
| Reset unavailable, state read failed | Propagate the read error through the existing cleanup path |
| Reset unavailable, valid OFFLINE state | Return `-ENODEV` through cleanup |
| Reset unavailable, valid detached state | Continue registration/attachment |
| Reset-capable device | Preserve normal startup capability; log a read error and allow normal boot |

A failed no-reset probe stays **unbound**. Returning a negative result also lets
managed probe resources, including consumer IRQs, be released. This deliberately
replaces the former `return 0` workaround for `sync_state()`: driver binding and
dependency state must reflect failed initialization. No deferred-probe loop,
bounded wait, DSP reset, forced DETACHED state, or userspace rebind is added.
This is an error-handling and diagnostic change, not yet a fix for late readiness.

## Logs available without enabling dynamic debug

Use the EL2 build containing patch 0023. The running release-10 kernel does not
contain these messages; compiling a new build alone does not change that.

```sh
journalctl -b -k -o short-monotonic --no-pager > kernel-boot.log
```

Keep the complete journal before recovering audio. Useful message prefixes:

- `SMP2P initial`: SMEM lookup failure, or version/entry counts and initial value.
- `SMP2P get-state`: hardware bit, entry name, raw sample, level and errno.
  `unmapped ret=-19` identifies an unavailable entry value pointer.
- `SMP2P boot check`: the four Linux IRQ numbers immediately before sampling.
- `SMP2P boot result (level/errno)`: all four read results. Level `-1` means
  unknown due to a failed read; `0/0` means a successfully read low level.
- `SMP2P ready IRQ`: receipt by the consumer, with current remoteproc state.
- `EL2 attach rejected`: state, state-read errno, actual probe errno and whether
  ready completion has already been signaled.
- `EL2 attach accepted`: initial readiness accepted; subsequent remoteproc
  registration/attach messages must still be checked.
- `SMP2P notify`: inbound raw sample, previous software cache and enabled IRQ
  bitmap. This producer-side log remains available after PAS probe failure
  releases its consumer IRQs. A missing consumer ready message alone therefore
  does not imply no remote readiness notification occurred.

Detailed producer logs are gated to `huawei,gaokun3`. Existing SMP2P tracepoints
remain intact. These are low-frequency control-plane messages, not PCM traffic.
The four getter reads are separate observations, not an atomic snapshot.
`cached` is the driver's software cache (also affected by existing SSR handling),
not proof of the remote's immediately preceding hardware value. `ready_seen`
reports a completion, not a direct measurement of the ready line.

Interpretation examples:

1. `unmapped`, with level `-1/-19`: inspect earlier SMEM lookup/version/entry logs.
2. Valid raw samples missing ready/handover, then a later `notify ... sample=0x6`:
   readiness arrived after the initial observation. Live DT must confirm the
   bit mapping; Gaokun3 uses fatal=0, ready=1, handover=2, stop-ack=3.
3. Different raw samples during the four reads: transition during sampling.
4. Valid samples with fatal/stop set: investigate remote firmware state rather
   than treating the read as a missing mapping.

## Verification and deployment boundary

`tests/test_adsp_boot_diagnostics.py` compiles the actual patch postimage
functions into a native harness: 32 valid-level/reset-capability cases, 32
per-position errno cases, error precedence, ready logging, raw getter logging,
unknown-level handling and producer logging with consumer IRQs disabled.
`tests/test_kernel_patches.py` applies the complete series to pristine 7.2.9 and
checks that those tested functions exactly match the applied source, alongside
existing attach/stop regressions. Full kernel builds run only in GitHub Actions.

For a diagnostic workflow use `kernel_tag=v7.2.9`, `build_el2=true`, and an
isolated `test_suffix` such as `-adspdiag`. The EL2 artifact includes the repository's
existing kernel patch series as well as 0023; it is not release 10 with only
this patch added. Installation and reboot require confirmation. Original boot
files, microphone tuning and the current failure state remain untouched while
preparing and building the patch.
