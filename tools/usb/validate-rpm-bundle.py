#!/usr/bin/env python3
"""Validate that downloaded RPM files match a Gaokun package manifest."""
import argparse
from pathlib import Path
import subprocess

from live_image import EXPECTED_PACKAGE_ARCHES, load_package_manifest


def validate(manifest_path, rpm_directory):
    _, filenames = load_package_manifest(manifest_path)
    directory = Path(rpm_directory)
    actual_files = {path.name for path in directory.glob('*.rpm')}
    if actual_files != set(filenames):
        missing = sorted(set(filenames) - actual_files)
        extra = sorted(actual_files - set(filenames))
        raise ValueError(f'RPM directory mismatch; missing={missing}, extra={extra}')

    expected_names = set(EXPECTED_PACKAGE_ARCHES)
    actual_names = set()
    for filename in filenames:
        path = directory / filename
        metadata = subprocess.run(
            ['rpm', '-qp', '--qf', '%{NAME}\n%{ARCH}\n', str(path)],
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        if len(metadata) != 2:
            raise ValueError(f'could not read RPM metadata from {filename}')
        name, architecture = metadata
        if name not in EXPECTED_PACKAGE_ARCHES:
            raise ValueError(f'unexpected RPM package {name!r} in {filename}')
        if architecture != EXPECTED_PACKAGE_ARCHES[name]:
            raise ValueError(
                f'{name} has architecture {architecture}; '
                f'expected {EXPECTED_PACKAGE_ARCHES[name]}'
            )
        actual_names.add(name)
    if actual_names != expected_names:
        raise ValueError(
            f'RPM package set mismatch; expected={sorted(expected_names)}, '
            f'actual={sorted(actual_names)}'
        )
    return filenames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package_manifest', type=Path)
    parser.add_argument('rpm_directory', type=Path)
    args = parser.parse_args()
    try:
        filenames = validate(args.package_manifest, args.rpm_directory)
    except (KeyError, OSError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'RPM bundle validation failed: {error}\n')
    print(f'Validated {len(filenames)} Fedora 45 Gaokun RPMs')


if __name__ == '__main__':
    main()
