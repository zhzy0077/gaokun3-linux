#!/usr/bin/env python3
"""Validate Live image RPM inputs and release provenance manifests."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


live_image = load_script('live_image', 'live_image.py')
validator = load_script('validate_rpm_bundle', 'validate-rpm-bundle.py')
writer = load_script('write_image_manifest', 'write-image-manifest.py')


class LiveImageTests(unittest.TestCase):
    package_names = {
        'kernel-gaokun3-el2': 'aarch64',
        'kernel-modules-gaokun3-el2': 'aarch64',
        'linux-firmware-gaokun3': 'noarch',
        'gaokun3-platform': 'noarch',
        'gaokun3-fingerprint': 'aarch64',
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rpms = self.root / 'rpms'
        self.rpms.mkdir()
        self.filenames = []
        for index, name in enumerate(self.package_names, 1):
            filename = f'{name}-1.0-1.{self.package_names[name]}.rpm'
            self.filenames.append(filename)
            (self.rpms / filename).write_bytes(f'rpm-{index}'.encode())
        self.manifest = {
            'package_release_tag': 'gaokun3-rpms-v7.3-std-el2-20261105',
            'build_el2': True,
            'kernels': {'el2': {'packages': {
                'kernel': self.filenames[0],
                'kernel_modules': self.filenames[1],
            }}},
            'packages': {
                'firmware': self.filenames[2],
                'platform': self.filenames[3],
                'fingerprint': self.filenames[4],
            },
        }
        self.manifest_path = self.root / 'package-manifest.json'
        self.manifest_path.write_text(json.dumps(self.manifest))

    def rpm_query(self, command, **kwargs):
        filename = Path(command[-1]).name
        package_name = next(
            name for name in self.package_names if filename.startswith(name + '-')
        )
        return SimpleNamespace(stdout=f'{package_name}\n{self.package_names[package_name]}\n')

    def test_rpm_bundle_matches_manifest_and_architecture(self):
        with mock.patch.object(subprocess, 'run', side_effect=self.rpm_query):
            result = validator.validate(self.manifest_path, self.rpms)
        self.assertEqual(result, self.filenames)

    def test_extra_rpm_is_rejected(self):
        (self.rpms / 'unexpected.rpm').write_bytes(b'unexpected')
        with self.assertRaisesRegex(ValueError, 'extra='):
            validator.validate(self.manifest_path, self.rpms)

    def test_wrong_rpm_architecture_is_rejected(self):
        def wrong_arch(command, **kwargs):
            result = self.rpm_query(command, **kwargs)
            return SimpleNamespace(stdout=result.stdout.replace('aarch64', 'x86_64'))

        with mock.patch.object(subprocess, 'run', side_effect=wrong_arch):
            with self.assertRaisesRegex(ValueError, 'architecture'):
                validator.validate(self.manifest_path, self.rpms)

    def test_image_manifest_records_all_provenance(self):
        image = self.root / 'fedora-gaokun3-usb.raw.xz'
        image.write_bytes(b'compressed-image')
        output = self.root / 'image-manifest.json'
        args = argparse.Namespace(
            package_manifest=self.manifest_path,
            rpm_directory=self.rpms,
            image=image,
            fedora_image='Fedora-Workstation-Live-45-1.4.aarch64.iso',
            fedora_sha256='ad73' * 16,
            tooling_commit='eb73a65',
            output=output,
        )
        document = writer.write_manifest(args)
        self.assertEqual(document, json.loads(output.read_text()))
        self.assertEqual(document['image']['sha256'], hashlib.sha256(image.read_bytes()).hexdigest())
        self.assertEqual(len(document['package_release']['rpms']), 5)
        self.assertEqual(document['fedora_live_iso']['release'], 45)


if __name__ == '__main__':
    unittest.main()
