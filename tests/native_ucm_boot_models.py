#!/usr/bin/env python3
"""Parse both boot-model selector branches on Gaokun, without enabling verbs.

Uses the real libasound and current card. Only a disposable UCM tree is changed;
CardName in the candidate selector is replaced with each model under test.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / 'tools/audio/dp-audio/ucm2'
LONG_NAME = 'HUAWEI-GK_W7X-M1010-GK_W7X_PCB.conf'
MODELS = ('SC8280XP-HUAWEI-GAOKUN3', 'SC8280XP-HUAWEI-GAOKUN3-DPAUDIO')
PROBE = r'''
import ctypes as c,json
lib=c.CDLL('libasound.so.2')
lib.snd_use_case_mgr_open.argtypes=[c.POINTER(c.c_void_p),c.c_char_p]
lib.snd_use_case_get_list.argtypes=[c.c_void_p,c.c_char_p,c.POINTER(c.POINTER(c.c_char_p))]
lib.snd_use_case_free_list.argtypes=[c.POINTER(c.c_char_p),c.c_int]
lib.snd_use_case_mgr_close.argtypes=[c.c_void_p]
mgr=c.c_void_p()
rc=lib.snd_use_case_mgr_open(c.byref(mgr),b'hw:0')
if rc<0: raise RuntimeError('UCM open failed: '+str(rc))
def items(key):
    p=c.POINTER(c.c_char_p)()
    n=lib.snd_use_case_get_list(mgr,key.encode(),c.byref(p))
    if n<0: raise RuntimeError('UCM list failed: '+key)
    result=[p[i].decode() for i in range(0,n,2)]
    lib.snd_use_case_free_list(p,n)
    return result
try:
    verbs=items('_verbs')
    print(json.dumps({v:items('_devices/'+v) for v in verbs}))
finally:
    lib.snd_use_case_mgr_close(mgr)
'''


def check():
    results = {}
    for base in (Path('/usr/share/gaokun3/ucm2'), Path('/usr/share/alsa/ucm2')):
        for model in MODELS:
            with tempfile.TemporaryDirectory(prefix='gaokun-ucm-model-') as directory:
                tree = Path(directory)
                for path in base.iterdir():
                    if path.name not in ('conf.d', 'Qualcomm'):
                        (tree / path.name).symlink_to(path)
                qualcomm = tree / 'Qualcomm'
                qualcomm.mkdir()
                for path in (base / 'Qualcomm').iterdir():
                    if path.name != 'gaokun-dp-audio':
                        (qualcomm / path.name).symlink_to(path)
                (qualcomm / 'gaokun-dp-audio').symlink_to(PAYLOAD / 'Qualcomm/gaokun-dp-audio')
                selectors = tree / 'conf.d/sc8280xp'
                selectors.mkdir(parents=True)
                for path in (PAYLOAD / 'conf.d/sc8280xp').iterdir():
                    if path.name == LONG_NAME:
                        (selectors / path.name).write_text(path.read_text().replace('${CardName}', model))
                    else:
                        (selectors / path.name).symlink_to(path.resolve())
                output = subprocess.check_output([sys.executable, '-c', PROBE], text=True,
                    env=dict(os.environ, ALSA_CONFIG_UCM2=str(tree)))
                parsed = json.loads(output)
                expected = {'HiFi'} | ({'HiFiDP0', 'HiFiDP1'} if model.endswith('DPAUDIO') else set())
                if set(parsed) != expected:
                    raise RuntimeError('Unexpected verbs: ' + output)
                for verb, devices in parsed.items():
                    expected_devices = {'Speaker', 'Headphones', 'Headset', 'Mic'}
                    if verb != 'HiFi':
                        expected_devices.add('HDMI' + verb[-1])
                    if set(devices) != expected_devices:
                        raise RuntimeError('Unexpected devices: ' + output)
                results[str(base) + ':' + model] = parsed
    return results


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
