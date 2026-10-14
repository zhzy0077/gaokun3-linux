# Gaokun3 EL2 ADSP boot error handling and diagnostics

Patches:
- `patches/el2/0023-remoteproc-qcom-report-attach-errors-and-SMP2P-state.patch`: error reporting and diagnostics.
- `patches/el2/0024-remoteproc-qcom-wait-for-SMP2P-boot-state.patch`: bounded handling of the observed mapping race.

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
dependency state must reflect failed initialization. These return rules remain
in force after the bounded mapping wait below.

## Observed race and driver fix

The diagnostic kernel captured an initial remote entry count of zero, followed
by four `unmapped ret=-19` results. PAS rejected attach at 4.998527 seconds;
Linux processed an attachable `0x6` notification at 5.003116 seconds, 4.589 ms
later. In two other boots, the notification preceded the probe and attachment
succeeded. This establishes a local mapping-availability race, without claiming
the exact firmware publication timestamp.

Patch 0024 adds `qcom_pas_read_boot_state()` in sleepable PAS probe context:

- Perform the existing state read first. Valid reads and reset-capable devices
  incur no added sleep or deadline-clock reads.
- Only `-ENODEV` on a no-reset device starts a 100 ms monotonic wait budget.
- Sleep 5–10 ms between attempts, then re-read all four levels. The IRQ-chip
  getter has already returned and released its locks before sleeping.
- Stop on the first valid read or different error. A mapped but inactive,
  fatal or stopped state is rejected by the existing state check.
- If mapping remains unavailable at the deadline, return the actual `-ENODEV`.
  Scheduler delays may extend elapsed wall time, but do not restart the budget.

This handles the captured unmapped-entry race, rather than forcing DSP state
after a fixed delay. It does not depend on receiving a ready IRQ edge/completion.
No reset, indefinite deferred probing, userspace rebind or global boot delay is
added. A valid low state is not retried by this mapping-specific fix; diagnostics
remain available to identify that separate case if it occurs.

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
- `SMP2P mapping unavailable`: entry into the bounded probe-context wait.
- `SMP2P map wait`: retry count, elapsed microseconds, final read errno and
  whether the mapping wait exhausted its budget.
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
It also covers 20 delayed mappings (5–100 ms) without a ready IRQ, 16 post-mapping
level combinations, a different error during waiting, deadline expiry and a
scheduler oversleep. Successful fast paths assert zero sleeps/clock reads.
`tests/test_kernel_patches.py` applies the complete series to pristine 7.2.9 and
checks that those tested functions exactly match the applied source, alongside
existing attach/stop regressions. Full kernel builds run only in GitHub Actions.

For a diagnostic workflow use `kernel_tag=v7.2.9`, `build_el2=true`, and an
isolated `test_suffix`: `-adspdiag` was used for 0023 and `-adspfix` for 0024.
The EL2 artifact includes the repository's existing kernel patch series;
it is not release 10 with only these patches added. Installation and reboot require confirmation. Original boot
files, microphone tuning and the current failure state remain untouched while
preparing and building the patch.
