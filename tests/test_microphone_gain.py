"""Board-scoped UCM capture calibration and packaging coverage."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
UCM = ROOT / 'tools/audio/ucm2/Qualcomm/gaokun3-mic'


class MicrophoneGainTests(unittest.TestCase):
    def test_only_internal_mic_enable_paths_change(self):
        baseline = (ROOT / 'tools/audio/dp-audio/ucm2/Qualcomm/gaokun-dp-audio/HiFi.conf').read_text()
        expected = baseline
        for channel in range(2):
            expected = expected.replace(
                f'/codecs/qcom-lpass/va-macro/DMIC{channel}EnableSeq.conf',
                f'/Qualcomm/gaokun3-mic/DMIC{channel}EnableSeq.conf')
        self.assertEqual((UCM / 'HiFi.conf').read_text(), expected)
        for channel in range(2):
            sequence = (UCM / f'DMIC{channel}EnableSeq.conf').read_text()
            self.assertIn(f'cset "name=\'VA_DEC{channel} Volume\' 106"', sequence)
            self.assertNotIn("Volume' 100", sequence)

    def test_board_selector_preserves_lenovo(self):
        selector = (ROOT / 'tools/audio/sc8280xp.conf').read_text()
        self.assertIn('True.Include.x13s.File "/Qualcomm/sc8280xp/LENOVO-X13s.conf"', selector)
        self.assertIn('True.Include.huawei.File "/Qualcomm/gaokun3-mic/Gaokun3.conf"', selector)
        self.assertIn('File "/Qualcomm/gaokun3-mic/HiFi.conf"', (UCM / 'Gaokun3.conf').read_text())

    def test_package_and_image_install_all_files(self):
        rpm = (ROOT / 'packaging/rpm/gaokun3-platform.spec.in').read_text()
        image = (ROOT / 'scripts/ci/lib/common_image.sh').read_text()
        self.assertIn('install -m644 tools/audio/ucm2/Qualcomm/gaokun3-mic/*.conf', rpm)
        for name in ('Gaokun3.conf', 'HiFi.conf', 'DMIC0EnableSeq.conf', 'DMIC1EnableSeq.conf'):
            self.assertIn(f'tools/audio/ucm2/Qualcomm/gaokun3-mic/{name}:/usr/share/alsa/ucm2/Qualcomm/gaokun3-mic/{name}', image)


if __name__ == '__main__':
    unittest.main()
