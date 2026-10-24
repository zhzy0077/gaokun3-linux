#!/usr/bin/env python3
"""Import authoritative board files into a standard, patched kernel checkout."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def import_files(kernel):
    sources = sorted((ROOT / 'dts').glob('*.dts')) + sorted((ROOT / 'dts').glob('*.dtsi'))
    if not sources:
        raise ValueError('No board device trees found')
    files = {Path('arch/arm64/boot/dts/qcom') / p.name: p.read_bytes() for p in sources}
    files[Path('arch/arm64/configs/gaokun3_defconfig')] = (ROOT / 'defconfig/gaokun3_defconfig').read_bytes()

    def git(*args):
        return subprocess.check_output(['git', '-C', str(kernel), *args], text=True).strip()

    # The import must remain a separate commit beneath the temporary EL2 commit.
    if git('status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Commit or stash tracked kernel checkout changes before importing board files')
    changed = [p for p, data in files.items()
               if not (kernel / p).exists() or (kernel / p).read_bytes() != data]
    for p in files:
        target = kernel / p
        if target.exists() and not git('ls-files', '--', str(p)):
            raise ValueError(f'Untracked destination already exists: {target}')
    for p in changed:
        target = kernel / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[p])
    if changed:
        git('add', '--', *(str(p) for p in files))
        git('commit', '-m', 'Import authoritative Gaokun3 DTS and defconfig')
    print(f'Board files synchronized: {len(files)} files, {len(changed)} updated')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    args = parser.parse_args()
    import_files(args.kernel.resolve())
