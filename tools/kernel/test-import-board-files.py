#!/usr/bin/env python3
"""Exercise imports and rebuilds without compiling a kernel."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('board_import', Path(__file__).with_name('import-board-files.py'))
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.kernel = root / 'kernel'
        self.kernel.mkdir()
        self.repo = root / 'board'
        (self.repo / 'dts').mkdir(parents=True)
        (self.repo / 'defconfig').mkdir()
        (self.repo / 'dts/board.dts').write_text('/dts-v1/;\n')
        (self.repo / 'dts/camera.dtsi').write_text('/* camera */\n')
        (self.repo / 'defconfig/gaokun3_defconfig').write_text('CONFIG_ARM64=y\n')
        original = board.ROOT
        self.addCleanup(setattr, board, 'ROOT', original)
        board.ROOT = self.repo
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.com')
        self.git('commit', '--allow-empty', '-qm', 'Base')
        self.target = self.kernel / 'arch/arm64/boot/dts/qcom/board.dts'

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.kernel), *args], text=True).strip()

    def test_import_and_noop_rebuild(self):
        board.import_files(self.kernel)
        head = self.git('rev-parse', 'HEAD')
        board.import_files(self.kernel)
        self.assertEqual(head, self.git('rev-parse', 'HEAD'))
        self.assertEqual(self.target.read_bytes(), (self.repo / 'dts/board.dts').read_bytes())
        self.assertTrue((self.target.parent / 'camera.dtsi').exists())
        self.assertEqual((self.kernel / 'arch/arm64/configs/gaokun3_defconfig').read_text(), 'CONFIG_ARM64=y\n')

    def test_refresh_beneath_el2_commit(self):
        board.import_files(self.kernel)
        (self.kernel / 'el2-overlay').write_text('EL2')
        self.git('add', 'el2-overlay')
        self.git('commit', '-qm', 'Apply EL2 patches')
        (self.repo / 'dts/board.dts').write_text('/dts-v1/; /* fix */\n')
        # Local builder removes the temporary variant before importing sources.
        self.git('reset', '--hard', 'HEAD~1')
        board.import_files(self.kernel)
        self.assertIn('fix', self.target.read_text())
        self.assertFalse((self.kernel / 'el2-overlay').exists())
        self.git('commit', '--allow-empty', '-qm', 'Apply EL2 patches')
        self.git('reset', '--hard', 'HEAD~1')
        self.assertIn('fix', self.target.read_text())

    def test_preserve_kernel_edits(self):
        board.import_files(self.kernel)
        self.target.write_text('local edit')
        with self.assertRaises(ValueError):
            board.import_files(self.kernel)
        self.assertEqual(self.target.read_text(), 'local edit')

    def test_preserve_untracked_destination(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_text('untracked edit')
        with self.assertRaises(ValueError):
            board.import_files(self.kernel)
        self.assertEqual(self.target.read_text(), 'untracked edit')


if __name__ == '__main__':
    unittest.main()
