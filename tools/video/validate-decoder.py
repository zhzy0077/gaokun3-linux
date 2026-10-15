#!/usr/bin/env python3
"""Prepare codec samples, then compare explicit V4L2 decoding with software."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

CODECS = {
    'h264': ('libx264', ['-preset', 'ultrafast', '-crf', '20']),
    'hevc': ('libx265', ['-preset', 'ultrafast', '-crf', '24',
                       '-x265-params', 'pools=2:frame-threads=2']),
    'vp9': ('libvpx-vp9', ['-deadline', 'realtime', '-cpu-used', '6', '-crf', '30', '-b:v', '0']),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--codecs', nargs='+', choices=CODECS, default=list(CODECS))
    parser.add_argument('--sustain-seconds', type=int, default=60)
    args = parser.parse_args()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    report = {'kernel': os.uname().release, 'started': time.time(), 'tests': {}}
    report_path = work / ('prepare.json' if args.prepare_only else 'decode.json')

    def run(label, cmd, timeout=180):
        result = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, timeout=timeout)
        (work / (label + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f'{label} failed ({result.returncode}); see {work / (label + ".log")}')
        return result.stdout.strip()

    ff = [args.ffmpeg, '-hide_banner', '-nostdin', '-v', 'info', '-threads', '2']
    try:
        report['ffmpeg'] = run('ffmpeg-version', [args.ffmpeg, '-version'])
        if not args.prepare_only:
            nodes = [p for p in Path('/sys/class/video4linux').glob('video*')
                     if (p / 'name').read_text().strip() == 'qcom-iris-decoder']
            if len(nodes) != 1:
                raise RuntimeError(f'Expected one qcom-iris-decoder, found {len(nodes)}')
            device = '/dev/' + nodes[0].name
            report['device'] = device
            report['formats'] = run('v4l2-formats', ['v4l2-ctl', '-d', device,
                                   '--all', '--list-formats-out', '--list-formats'])
            # Preserve failures for driver investigation; playback is checked separately.
            result = subprocess.run(['v4l2-compliance', '-d', device], capture_output=True,
                                    text=True, timeout=120)
            (work / 'v4l2-compliance.log').write_text(result.stdout + result.stderr)
            report['v4l2_compliance_exit'] = result.returncode
        for codec in args.codecs:
            sample = work / (codec + '.mkv')
            if not sample.exists():
                encoder, options = CODECS[codec]
                run(codec + '-encode', ff + ['-f', 'lavfi', '-i',
                    'testsrc2=size=1280x720:rate=30', '-frames:v', '90',
                    '-an', '-c:v', encoder, *options, '-pix_fmt', 'yuv420p', str(sample)])
            tail = ['-map', '0:v:0', '-an', '-pix_fmt', 'yuv420p', '-f', 'hash', '-hash', 'sha256', '-']
            reference = run(codec + '-software', ff + ['-c:v', codec, '-i', str(sample)] + tail)
            if not reference.startswith('SHA256='):
                raise RuntimeError('Missing software decode checksum')
            result = {'software_sha256': reference}
            report['tests'][codec] = result
            if args.prepare_only:
                continue
            for attempt in range(5):
                actual = run(f'{codec}-hardware-{attempt}', ff +
                             ['-c:v', codec + '_v4l2m2m', '-i', str(sample)] + tail)
                if actual != reference:
                    raise RuntimeError(f'{codec} hardware/software frame checksum mismatch')
            result['matching_hardware_decodes'] = 5
            start = time.monotonic()
            run(codec + '-sustained', ff + ['-stream_loop', '-1', '-re',
                '-c:v', codec + '_v4l2m2m', '-i', str(sample), '-t', str(args.sustain_seconds),
                '-an', '-f', 'null', '-'], timeout=args.sustain_seconds + 90)
            result['sustained_wall_seconds'] = time.monotonic() - start
        report['status'] = 'samples_ready' if args.prepare_only else 'decode_checks_passed'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = str(exc)
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2) + '\n')
        print(report_path, flush=True)


if __name__ == '__main__':
    main()
