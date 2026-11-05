#!/usr/bin/env python3
"""Write provenance for a compressed Gaokun Fedora Live USB image."""
import argparse
import json
from pathlib import Path

from live_image import load_package_manifest, sha256, validate_sha256


def write_manifest(args):
    package_manifest, rpm_names = load_package_manifest(args.package_manifest)
    rpm_directory = Path(args.rpm_directory)
    image = Path(args.image)
    if not image.is_file():
        raise ValueError(f'image does not exist: {image}')
    if image.stat().st_size == 0:
        raise ValueError(f'image is empty: {image}')
    fedora_sha256 = validate_sha256(args.fedora_sha256, 'Fedora ISO SHA256')
    rpms = []
    for filename in rpm_names:
        path = rpm_directory / filename
        if not path.is_file():
            raise ValueError(f'RPM does not exist: {path}')
        rpms.append({
            'filename': filename,
            'size_bytes': path.stat().st_size,
            'sha256': sha256(path),
        })
    document = {
        'schema_version': 1,
        'tooling_commit': args.tooling_commit,
        'fedora_live_iso': {
            'filename': args.fedora_image,
            'release': 45,
            'variant': 'Workstation',
            'architecture': 'aarch64',
            'sha256': fedora_sha256,
        },
        'package_release': {
            'tag': package_manifest['package_release_tag'],
            'manifest_filename': Path(args.package_manifest).name,
            'manifest_sha256': sha256(args.package_manifest),
            'rpms': rpms,
        },
        'image': {
            'filename': image.name,
            'format': 'xz-compressed GPT raw disk image',
            'size_bytes': image.stat().st_size,
            'sha256': sha256(image),
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + '\n')
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-manifest', required=True, type=Path)
    parser.add_argument('--rpm-directory', required=True, type=Path)
    parser.add_argument('--image', required=True, type=Path)
    parser.add_argument('--fedora-image', required=True)
    parser.add_argument('--fedora-sha256', required=True)
    parser.add_argument('--tooling-commit', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        write_manifest(args)
    except (KeyError, OSError, TypeError, ValueError) as error:
        parser.exit(1, f'Image manifest generation failed: {error}\n')


if __name__ == '__main__':
    main()
