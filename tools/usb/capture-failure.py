#!/usr/bin/env python3
"""Persist USB failure evidence; never reset devices or read hardware registers.

Run as root. --follow records for a bounded interval and uses a private trace
instance, leaving the global tracer unchanged. Output may contain device IDs.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time

TRACE = Path('/sys/kernel/tracing/instances/gaokun-usb-capture')
FUNCTIONS = (
    'qmp_combo_typec_switch_set', 'qmp_combo_typec_mux_set',
    'qmp_combo_com_init', 'qmp_combo_com_exit',
    'qmp_combo_usb_power_on', 'qmp_combo_usb_power_off',
    'gaokun_ucsi_sync_worker', 'gaokun_ucsi_connector_status',
    'xhci_handle_command_timeout', 'xhci_halt', 'xhci_reset',
)
EVENTS = (
    'xhci-hcd/xhci_handle_command',
    'xhci-hcd/xhci_handle_port_status',
    'xhci-hcd/xhci_portsc_writel',
    'power/device_pm_callback_start',
    'power/device_pm_callback_end',
    'power/suspend_resume',
)


def durable(path, data):
    temporary = path.with_name(path.name + '.tmp')
    try:
        with temporary.open('wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def command(out, name, args):
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=45)
        durable(out / name, result.stdout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        durable(out / name, str(exc).encode())


def snapshot(out, label):
    command(out, label + '-lsusb.txt', ['lsusb'])
    command(out, label + '-topology.txt', ['lsusb', '-t'])
    state = {}
    for base in ('/sys/bus/usb/devices', '/sys/class/typec',
                 '/sys/bus/platform/devices', '/sys/class/drm',
                 '/sys/class/power_supply'):
        for device in Path(base).glob('*'):
            if base.endswith('platform/devices') and not any(
                    x in device.name for x in ('usb', 'xhci')):
                continue
            values = {'path': str(device.resolve())}
            for attr in ('idVendor', 'idProduct', 'product', 'speed', 'status',
                         'enabled', 'data_role', 'power_role', 'orientation',
                         'power_operation_mode', 'online', 'usb_type',
                         'capacity', 'voltage_now', 'current_now', 'power/control',
                         'power/runtime_status', 'power/runtime_active_time',
                         'power/runtime_suspended_time'):
                try:
                    values[attr] = (device / attr).read_text().strip()
                except OSError:
                    pass
            state[str(device)] = values
    durable(out / (label + '-state.json'), json.dumps(state, indent=2).encode())


def follow(out, seconds):
    processes = []
    files = []
    owned_trace = False
    stop = False

    def request_stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    selector = selectors.DefaultSelector()
    try:
        streams = [('kernel-live.log', ['journalctl', '-k', '-f', '-n', '0',
                                      '-o', 'short-monotonic', '--no-pager'])]
        try:
            TRACE.mkdir()
            owned_trace = True
            (TRACE / 'buffer_size_kb').write_text('256')
            available = {line.split()[0] for line in
                         Path('/sys/kernel/tracing/available_filter_functions').read_text().splitlines()}
            functions = [name for name in FUNCTIONS if name in available]
            if functions:
                (TRACE / 'set_ftrace_filter').write_text('\n'.join(functions))
                (TRACE / 'current_tracer').write_text('function')
            durable(out / 'trace-functions.json', json.dumps(functions).encode())
            enabled = []
            for event in EVENTS:
                enable = TRACE / 'events' / event / 'enable'
                if enable.exists():
                    enable.write_text('1')
                    enabled.append(event)
            durable(out / 'trace-events.json', json.dumps(enabled).encode())
            (TRACE / 'tracing_on').write_text('1')
            streams.append(('usb-trace.log', ['cat', str(TRACE / 'trace_pipe')]))
        except OSError as exc:
            durable(out / 'trace-setup-error.txt', str(exc).encode())
        for name, args in streams:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            processes.append(proc)
            f = (out / name).open('ab', buffering=0)
            files.append(f)
            selector.register(proc.stdout, selectors.EVENT_READ, f)
        deadline = time.monotonic() + seconds
        next_snapshot = time.monotonic()
        while not stop and time.monotonic() < deadline:
            for key, _ in selector.select(timeout=1):
                data = os.read(key.fileobj.fileno(), 65536)
                if data:
                    key.data.write(data)
                    os.fsync(key.data.fileno())
                else:
                    selector.unregister(key.fileobj)
            if time.monotonic() >= next_snapshot:
                snapshot(out, 'latest')
                durable(out / 'heartbeat.json', json.dumps({
                    'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'monotonic': time.monotonic(),
                }).encode())
                next_snapshot = time.monotonic() + 15
    finally:
        for proc in processes:
            proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        selector.close()
        for f in files:
            f.close()
        if owned_trace:
            (TRACE / 'tracing_on').write_text('0')
            TRACE.rmdir()
        snapshot(out, 'after')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--follow', action='store_true')
    parser.add_argument('--seconds', type=int, default=1200)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('run as root to capture kernel and trace records')
    if args.seconds <= 0:
        parser.error('--seconds must be positive')
    out = args.output
    # A reused directory would destroy the pre-failure evidence.
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    command(out, 'boots.txt', ['journalctl', '--list-boots', '--no-pager'])
    command(out, 'uname.txt', ['uname', '-a'])
    durable(out / 'boot-id.txt', Path('/proc/sys/kernel/random/boot_id').read_bytes())
    durable(out / 'cmdline.txt', Path('/proc/cmdline').read_bytes())
    for boot, label in (('-1', 'previous'), ('0', 'current')):
        command(out, label + '-kernel.log', ['journalctl', '-b', boot, '-k',
                '-o', 'short-monotonic', '--no-pager'])
        command(out, label + '-journal.log', ['journalctl', '-b', boot,
                '-o', 'short-monotonic', '--no-pager'])
    snapshot(out, 'before')
    if args.follow:
        follow(out, args.seconds)


if __name__ == '__main__':
    main()
