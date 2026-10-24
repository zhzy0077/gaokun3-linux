#!/usr/bin/env python3
"""Split a compressed USB image into release assets below GitHub's 2 GiB limit."""
import argparse
import hashlib
from pathlib import Path

PART_SIZE = 1900 * 1024 * 1024
BUFFER_SIZE = 4 * 1024 * 1024


def split_image(image, part_size=PART_SIZE):
    if image.stat().st_size == 0:
        raise ValueError('Image is empty')
    if list(image.parent.glob(image.name + '.[0-9][0-9][0-9]')):
        raise ValueError('Existing image parts must be removed before packaging')
    count = (image.stat().st_size + part_size - 1) // part_size
    if count > 999:
        raise ValueError('Too many image parts')
    whole = hashlib.sha256()
    checksums = []
    with image.open('rb') as source:
        for number in range(1, count + 1):
            part = image.with_name(f'{image.name}.{number:03}')
            digest = hashlib.sha256()
            remaining = part_size
            with part.open('xb') as output:
                while remaining:
                    block = source.read(min(BUFFER_SIZE, remaining))
                    if not block:
                        break
                    output.write(block)
                    digest.update(block)
                    whole.update(block)
                    remaining -= len(block)
            checksums.append(f'{digest.hexdigest()}  {part.name}\n')
    (image.parent / 'SHA256SUMS.parts').write_text(''.join(checksums))
    (image.parent / 'SHA256SUMS').write_text(f'{whole.hexdigest()}  {image.name}\n')
    return count


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    args = parser.parse_args()
    print(f'Created {split_image(args.image)} parts, each at most 1900 MiB')
