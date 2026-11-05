#!/usr/bin/env python3
"""Shared validation helpers for Gaokun Fedora Live image artifacts."""
import hashlib
import json
from pathlib import Path


EXPECTED_PACKAGE_ARCHES = {
    'kernel-gaokun3-el2': 'aarch64',
    'kernel-modules-gaokun3-el2': 'aarch64',
    'linux-firmware-gaokun3': 'noarch',
    'gaokun3-platform': 'noarch',
    'gaokun3-fingerprint': 'aarch64',
}


def load_package_manifest(path):
    manifest = json.loads(Path(path).read_text())
    if manifest.get('build_el2') is not True:
        raise ValueError('package release does not contain the EL2 package set')
    el2 = manifest['kernels']['el2']['packages']
    names = [
        el2['kernel'],
        el2['kernel_modules'],
        manifest['packages']['firmware'],
        manifest['packages']['platform'],
        manifest['packages']['fingerprint'],
    ]
    if len(names) != len(set(names)):
        raise ValueError('package manifest contains duplicate RPM names')
    for name in names:
        path_value = Path(name)
        if path_value.name != name or path_value.suffix != '.rpm':
            raise ValueError(f'unsafe RPM asset name: {name!r}')
    return manifest, names


def sha256(path, chunk_size=4 * 1024 * 1024):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def validate_sha256(value, description):
    if len(value) != 64 or any(character not in '0123456789abcdefABCDEF'
                               for character in value):
        raise ValueError(f'{description} must be a 64-character SHA256')
    return value.lower()
