#!/usr/bin/env python3
"""Reject unreviewed, missing or changed patches before kernel builds."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def check():
    data = json.loads((ROOT / 'patches/inventory.json').read_text())
    entries = data['active']
    reviewed = [entry['path'] for entry in entries]
    present = {str(path.relative_to(ROOT)) for path in (ROOT / 'patches').rglob('*.patch')}
    if len(reviewed) != len(set(reviewed)) or set(reviewed) != present:
        raise ValueError(f'Patch inventory mismatch: missing={set(reviewed) - present}, '
                         f'unreviewed={present - set(reviewed)}')
    for entry in entries:
        for key in ('id', 'category', 'code_fact', 'source', 'evidence'):
            if not entry[key].strip():
                raise ValueError(f"{entry['path']}: missing {key}")
        digest = hashlib.sha256((ROOT / entry['path']).read_bytes()).hexdigest()
        if digest != entry['sha256']:
            raise ValueError(f"{entry['path']}: content changed; update the code review and digest")
    for entry in data['removed']:
        if (ROOT / entry['former_path']).exists():
            raise ValueError(f"Removed patch reintroduced: {entry['former_path']}")
    lock = dict(line.split('=', 1) for line in (ROOT / 'kernel-source.env').read_text().splitlines()
                if line and not line.startswith('#'))
    for key in ('repository', 'tag', 'commit'):
        if data['upstream_' + key] != lock['GAOKUN_KERNEL_' + key.upper()]:
            raise ValueError('Source lock differs from the reviewed patch inventory')
    print(f"{len(entries)} reviewed patches; {len(data['removed'])} removed; "
          f"{data['upstream_tag']} {data['upstream_commit']}")


if __name__ == '__main__':
    check()
