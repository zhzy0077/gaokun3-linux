"""Test persistent snapshot updates without hardware or root access."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('usb_capture', ROOT / 'tools/usb/capture-failure.py')
CAPTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAPTURE)


class UsbCaptureTests(unittest.TestCase):
    def test_snapshot_replacement_and_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'snapshot.json'
            target.write_bytes(b'old')
            with patch.object(CAPTURE.os, 'fsync', wraps=CAPTURE.os.fsync) as sync:
                CAPTURE.durable(target, b'new')
            self.assertEqual(target.read_bytes(), b'new')
            self.assertEqual(sync.call_count, 2)  # file contents and directory entry
            self.assertFalse(target.with_name('snapshot.json.tmp').exists())

    def test_failed_replacement_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'snapshot.json'
            target.write_bytes(b'old')
            with patch.object(CAPTURE.os, 'replace', side_effect=OSError('injected')):
                with self.assertRaises(OSError):
                    CAPTURE.durable(target, b'new')
            self.assertEqual(target.read_bytes(), b'old')
            self.assertFalse(target.with_name('snapshot.json.tmp').exists())

    def test_reused_output_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('sys.argv', ['capture-failure.py', '--output', directory]), \
                 patch.object(CAPTURE.os, 'geteuid', return_value=0), \
                 patch.object(CAPTURE, 'command') as command:
                with self.assertRaises(FileExistsError):
                    CAPTURE.main()
                command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
