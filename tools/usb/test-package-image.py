#!/usr/bin/env python3
"""Check release splitting and checksum-enforced reassembly."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('package_image', TOOLS / 'package-image.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / 'fedora-gaokun3-usb.raw.xz'
        self.data = bytes(range(256)) * 13
        self.image.write_bytes(self.data)

    def join(self):
        return subprocess.run(['bash', str(TOOLS / 'join-image.sh')], cwd=self.root,
                              capture_output=True, text=True)

    def test_round_trip_and_no_overwrite(self):
        self.assertLess(package.PART_SIZE, 2 * 1024**3)
        self.assertEqual(package.split_image(self.image, 1000), 4)
        self.image.unlink()
        self.assertEqual(self.join().returncode, 0)
        self.assertEqual(self.image.read_bytes(), self.data)
        self.assertNotEqual(self.join().returncode, 0)

    def test_corruption_rejected_before_join(self):
        package.split_image(self.image, 1000)
        self.image.unlink()
        (self.root / (self.image.name + '.002')).write_bytes(b'corrupt')
        self.assertNotEqual(self.join().returncode, 0)
        self.assertFalse(self.image.exists())

    def test_missing_part_rejected(self):
        package.split_image(self.image, 1000)
        self.image.unlink()
        (self.root / (self.image.name + '.003')).unlink()
        self.assertNotEqual(self.join().returncode, 0)
        self.assertFalse(self.image.exists())

    def test_exact_boundary(self):
        self.assertEqual(package.split_image(self.image, len(self.data)), 1)
        self.image.unlink()
        self.assertEqual(self.join().returncode, 0)
        self.assertEqual(self.image.read_bytes(), self.data)


if __name__ == '__main__':
    unittest.main()
