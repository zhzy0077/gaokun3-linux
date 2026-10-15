#!/usr/bin/env python3
"""Check V4L2 decoder DRM PRIME exports through libavcodec's public API."""
import ctypes as c
import json


class HWConfig(c.Structure):
    _fields_ = [('pix_fmt', c.c_int), ('methods', c.c_int), ('device_type', c.c_int)]


avcodec = c.CDLL('libavcodec.so.62')
avutil = c.CDLL('libavutil.so.60')
avcodec.avcodec_find_decoder_by_name.argtypes = [c.c_char_p]
avcodec.avcodec_find_decoder_by_name.restype = c.c_void_p
avcodec.avcodec_get_hw_config.argtypes = [c.c_void_p, c.c_int]
avcodec.avcodec_get_hw_config.restype = c.POINTER(HWConfig)
avutil.av_get_pix_fmt.argtypes = [c.c_char_p]
avutil.av_get_pix_fmt.restype = c.c_int
drm = avutil.av_get_pix_fmt(b'drm_prime')
assert drm >= 0
results = {}
for name in ('h264_v4l2m2m', 'hevc_v4l2m2m', 'vp9_v4l2m2m'):
    decoder = avcodec.avcodec_find_decoder_by_name(name.encode())
    assert decoder, f'{name} missing'
    configs = []
    for i in range(32):
        ptr = avcodec.avcodec_get_hw_config(decoder, i)
        if not ptr:
            break
        configs.append(ptr.contents.pix_fmt)
    results[name] = {'drm_prime': drm in configs}
print(json.dumps(results, indent=2))
if not all(r['drm_prime'] for r in results.values()):
    raise SystemExit('V4L2 DRM PRIME support missing')
