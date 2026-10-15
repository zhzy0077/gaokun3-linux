#!/usr/bin/env python3
"""Play local samples in isolated Firefox profiles and require V4L2 frame logs."""
import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--library-dir', type=Path, required=True)
    parser.add_argument('--codecs', nargs='+', choices=('h264', 'vp9', 'hevc'),
                        default=['h264', 'vp9'])
    parser.add_argument('--firefox', default='/usr/lib64/firefox/firefox')
    args = parser.parse_args()
    work = args.results.resolve()
    work.mkdir(parents=True, exist_ok=False)
    state = {'expected': None, 'result': None}
    done = threading.Event()

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.path != '/result':
                self.send_error(404)
                return
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length < 16384:
                self.send_error(400)
                return
            data = json.loads(self.rfile.read(length))
            if data.get('codec') != state['expected']:
                self.send_error(409)
                return
            state['result'] = data
            self.send_response(200)
            self.end_headers()
            done.set()

    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(work)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    report = {'kernel': os.uname().release, 'started': time.time(),
              'library_dir': str(args.library_dir.resolve()), 'codecs': {}}
    try:
        for codec in args.codecs:
            suffix = 'webm' if codec == 'vp9' else 'mp4'
            video = f'{codec}.{suffix}'
            cmd = ['ffmpeg', '-hide_banner', '-nostdin', '-v', 'error',
                   '-i', str(args.samples / (codec + '.mkv')), '-an', '-c:v', 'copy']
            if suffix == 'mp4':
                cmd += ['-movflags', '+faststart']
            if codec == 'hevc':
                cmd += ['-tag:v', 'hvc1']
            subprocess.run(cmd + [str(work / video)], check=True, timeout=30)
            page = '''<!doctype html><meta charset="utf-8"><title>Iris video test</title>
<h1>Iris hardware video test</h1><video controls muted autoplay width="960"></video>
<pre id="status">Playing CODEC</pre><script>
const codec = CODEC_JSON;
const v = document.querySelector('video');
let sent = false;
async function finish(error) {
  if (sent) return; sent = true;
  const q = v.getVideoPlaybackQuality();
  const result = {codec, error, currentTime:v.currentTime, duration:v.duration,
    totalVideoFrames:q.totalVideoFrames, droppedVideoFrames:q.droppedVideoFrames};
  document.querySelector('#status').textContent = JSON.stringify(result,null,2);
  await fetch('/result',{method:'POST',body:JSON.stringify(result)});
}
v.onended=()=>finish(null);
v.onerror=()=>finish(v.error ? {code:v.error.code,message:v.error.message} : 'video error');
v.src=VIDEO_JSON;
v.play().catch(e=>finish(String(e)));
setTimeout(()=>finish('playback timeout'),30000);
</script>'''.replace('CODEC_JSON', json.dumps(codec)).replace('VIDEO_JSON', json.dumps(video)).replace('Playing CODEC', 'Playing ' + codec)
            (work / 'index.html').write_text(page)
            profile = work / ('profile-' + codec)
            profile.mkdir()
            prefs = {'media.hardware-video-decoding.enabled': True,
                     'media.autoplay.default': 0,
                     'browser.shell.checkDefaultBrowser': False,
                     'browser.startup.homepage_override.mstone': 'ignore',
                     'browser.aboutwelcome.enabled': False}
            (profile / 'user.js').write_text(''.join(
                f'user_pref({json.dumps(k)}, {json.dumps(v)});\n' for k, v in prefs.items()))
            env = dict(os.environ,
                       LD_LIBRARY_PATH=str(args.library_dir.resolve()),
                       MOZ_LOG='PlatformDecoderModule:5,Dmabuf:5',
                       MOZ_LOG_FILE=str(work / (codec + '-media.log')))
            state.update(expected=codec, result=None)
            done.clear()
            with (work / (codec + '-stderr.log')).open('w') as stderr:
                proc = subprocess.Popen([args.firefox, '--no-remote', '--profile', str(profile),
                    f'http://127.0.0.1:{server.server_port}/index.html'], env=env,
                    stdout=stderr, stderr=stderr, start_new_session=True)
                try:
                    deadline = time.monotonic() + 45
                    while not done.wait(.2) and proc.poll() is None and time.monotonic() < deadline:
                        pass
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGTERM)
                        try:
                            proc.wait(5)
                        except subprocess.TimeoutExpired:
                            os.killpg(proc.pid, signal.SIGKILL)
                            proc.wait()
            logs = '\n'.join(p.read_text(errors='replace') for p in work.glob(codec + '-media.log*'))
            result = state['result'] or {'error': 'Firefox exited or did not report playback'}
            result['v4l2_output_frames_logged'] = logs.count('V4L2 Got one frame output')
            report['codecs'][codec] = result
            if result.get('error') or not result.get('totalVideoFrames') or not result['v4l2_output_frames_logged']:
                raise RuntimeError(f'{codec}: hardware playback not verified; inspect {work}')
        report['status'] = 'hardware_playback_verified'
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        server.shutdown()
        server.server_close()
        (work / 'firefox.json').write_text(json.dumps(report, indent=2) + '\n')
        print(work / 'firefox.json', flush=True)


if __name__ == '__main__':
    main()
