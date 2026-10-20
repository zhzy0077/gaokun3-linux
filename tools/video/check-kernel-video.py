#!/usr/bin/env python3
"""Validate the built Gaokun codec module and DTB before packaging."""
import argparse
import json
from pathlib import Path
import subprocess


def output(*args):
    return subprocess.check_output(list(map(str, args)), text=True).strip()


def check(out, dtb_name, repo):
    dtb = out / 'arch/arm64/boot/dts/qcom' / dtb_name
    module = out / 'drivers/media/platform/qcom/iris/qcom-iris.ko'
    node = '/soc@0/video-codec@aa00000'
    expected = {
        'compatible': 'qcom,sc8280xp-iris qcom,sm8250-venus',
        'status': 'okay',
        'firmware-name': 'qcom/sc8280xp/HUAWEI/gaokun3/qcvss8280.mbn',
        'clock-names': 'iface core vcodec0_core',
        'reset-names': 'bus core',
        'power-domain-names': 'venus vcodec0 mx mmcx',
        'interconnect-names': 'cpu-cfg video-mem',
    }
    actual = {key: output('fdtget', '-t', 's', dtb, node, key) for key in expected}
    for key, value in expected.items():
        if actual[key] != value:
            raise ValueError(f'{dtb_name}: {key}: {actual[key]!r} != {value!r}')
    fw_iommu = output('fdtget', '-t', 'x', dtb, node + '/video-firmware', 'iommus').split()
    apps_smmu = output('fdtget', '-t', 'x', dtb, '/soc@0/iommu@15000000', 'phandle')
    if fw_iommu != [apps_smmu, '2e02', '400']:
        raise ValueError(f'Incorrect firmware IOMMU mapping: {fw_iommu}')
    if 'firmware_direct:bool' not in output('modinfo', '-F', 'parmtype', module).splitlines():
        raise ValueError('Iris module lacks the direct firmware boot option')
    aliases = output('modinfo', '-F', 'alias', module).splitlines()
    if 'of:N*T*Cqcom,sc8280xp-iris' not in aliases:
        raise ValueError('Built Iris module cannot bind the SC8280XP DT node')
    config = (out / '.config').read_text()
    for option in ('CONFIG_VIDEO_QCOM_IRIS=m', 'CONFIG_SM_VIDEOCC_8350=m'):
        if option not in config.splitlines():
            raise ValueError(f'Missing required config: {option}')
    firmware = repo / 'firmware' / actual['firmware-name']
    if not firmware.is_file():
        raise ValueError(f'Missing packaged firmware: {firmware}')
    release = (out / 'include/config/kernel.release').read_text().strip()
    if output('modinfo', '-F', 'vermagic', module).split()[0] != release:
        raise ValueError('Iris module vermagic does not match the built kernel')
    return {'kernel_release': release, 'dtb': dtb_name, 'codec': actual,
            'firmware_iommu': fw_iommu,
            'iris_aliases': aliases, 'firmware_bytes': firmware.stat().st_size}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--dtb', required=True)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(check(args.out, args.dtb, args.repo), indent=2))
