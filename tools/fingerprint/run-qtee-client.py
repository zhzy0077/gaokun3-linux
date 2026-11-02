#!/usr/bin/env python3
"""Verify the vendor image and pass an immutable copy to the native client."""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("binary", type=Path)
parser.add_argument("image", type=Path)
modes = ("template-count", "enroll-series-wait", "verify-wait", "delete-template")
parser.add_argument("mode", nargs="?", default="listener-template-count",
                    choices=tuple("listener-" + mode for mode in modes))
args = parser.parse_args()
data = args.image.read_bytes()
expected = "b081543c7b6ae4360969007836747601e8c48ec48a8335a5479e45ec0e34355a"
if hashlib.sha256(data).hexdigest() != expected:
    raise SystemExit("Vendor firmware SHA256 mismatch")
fd = os.memfd_create("gaokun-fingerprint-verified", os.MFD_ALLOW_SEALING)
view = memoryview(data)
while view:
    view = view[os.write(fd, view):]
fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW |
            fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
os.set_inheritable(fd, True)
os.lseek(fd, 0, os.SEEK_SET)
binary = str(args.binary.resolve(strict=True))
command = [binary, f"/proc/self/fd/{fd}", args.mode]
os.execv(binary, command)
