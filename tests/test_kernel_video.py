"""Exercise the packaging video gate with built-module metadata fixtures."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'check_kernel_video', ROOT / 'tools/video/check-kernel-video.py')
VIDEO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VIDEO)


class KernelVideoTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repo = Path(directory.name)
        self.out = self.repo / 'out'
        (self.out / 'include/config').mkdir(parents=True)
        self.release = '7.3.0-gaokun3-review1+'
        (self.out / 'include/config/kernel.release').write_text(self.release + '\n')
        (self.out / '.config').write_text(
            'CONFIG_VIDEO_QCOM_IRIS=m\nCONFIG_SM_VIDEOCC_8350=m\n')
        self.properties = {
            'compatible': 'qcom,sc8280xp-iris qcom,sm8250-venus',
            'status': 'okay',
            'firmware-name': 'qcom/sc8280xp/HUAWEI/gaokun3/qcvss8280.mbn',
            'clock-names': 'iface core vcodec0_core',
            'reset-names': 'bus core',
            'power-domain-names': 'venus vcodec0 mx mmcx',
            'interconnect-names': 'cpu-cfg video-mem',
            'iommus': '12 2e02 400',
            'phandle': '12',
        }
        self.firmware = self.repo / 'firmware' / self.properties['firmware-name']
        self.firmware.parent.mkdir(parents=True)
        self.firmware.write_bytes(b'firmware fixture')
        self.metadata = {
            'alias': 'of:N*T*Cqcom,sm8250-venus\nof:N*T*Cqcom,sm8250-venusC*',
            'parmtype': 'firmware_direct:bool',
            'vermagic': self.release + ' SMP preempt mod_unload aarch64',
        }
        mock = patch.object(VIDEO, 'output', side_effect=self.output)
        mock.start()
        self.addCleanup(mock.stop)

    def output(self, *args):
        if args[0] == 'fdtget':
            return self.properties[args[-1]]
        if args[0] == 'modinfo':
            return self.metadata[args[2]]
        raise AssertionError(args)

    def check(self, dtb='sc8280xp-huawei-gaokun3.dtb'):
        return VIDEO.check(self.out, dtb, self.repo)

    def test_upstream_fallback_binds_both_variants(self):
        for dtb in ('sc8280xp-huawei-gaokun3.dtb', 'sc8280xp-huawei-gaokun3-el2.dtb'):
            with self.subTest(dtb=dtb):
                report = self.check(dtb)
                self.assertEqual(report['iris_matched_compatibles'], ['qcom,sm8250-venus'])
                self.assertEqual(report['dtb'], dtb)
                self.assertEqual(report['firmware_bytes'], self.firmware.stat().st_size)

    def test_exact_and_trailing_compatible_aliases(self):
        for compatible in ('qcom,sc8280xp-iris', 'qcom,sm8250-venus'):
            for suffix in ('', 'C*'):
                with self.subTest(compatible=compatible, suffix=suffix):
                    self.metadata['alias'] = f'of:N*T*C{compatible}{suffix}'
                    self.assertEqual(self.check()['iris_matched_compatibles'], [compatible])

    def test_unrelated_empty_and_partial_aliases_fail(self):
        for aliases in ('', 'of:N*T*Cqcom,sc7280-venus',
                        'of:N*T*Cqcom,sm8250-venus-extra',
                        'of:N*T*Cqcom,sc8280xp-iris-extra'):
            with self.subTest(aliases=aliases):
                self.metadata['alias'] = aliases
                with self.assertRaisesRegex(ValueError, 'cannot bind'):
                    self.check()

    def test_incorrect_dtb_properties_fail(self):
        for key in ('compatible', 'status', 'firmware-name', 'clock-names',
                    'reset-names', 'power-domain-names', 'interconnect-names', 'iommus'):
            with self.subTest(property=key), patch.dict(self.properties, {key: 'wrong'}):
                with self.assertRaises(ValueError):
                    self.check()

    def test_direct_firmware_parameter_required(self):
        self.metadata['parmtype'] = ''
        with self.assertRaisesRegex(ValueError, 'direct firmware'):
            self.check()

    def test_vermagic_must_match(self):
        self.metadata['vermagic'] = '7.2.9-gaokun3+ SMP'
        with self.assertRaisesRegex(ValueError, 'vermagic'):
            self.check()

    def test_firmware_must_exist(self):
        self.firmware.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing packaged firmware'):
            self.check()

    def test_required_config_cannot_be_disabled(self):
        for option in ('CONFIG_VIDEO_QCOM_IRIS', 'CONFIG_SM_VIDEOCC_8350'):
            with self.subTest(option=option):
                (self.out / '.config').write_text('\n'.join(
                    f'{name}={"n" if name == option else "m"}'
                    for name in ('CONFIG_VIDEO_QCOM_IRIS', 'CONFIG_SM_VIDEOCC_8350')))
                with self.assertRaisesRegex(ValueError, 'Missing required config'):
                    self.check()
