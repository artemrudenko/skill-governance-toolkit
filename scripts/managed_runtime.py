#!/usr/bin/env python3
"""Install runtime scripts without overwriting unverified local files."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

MARKER = '.sgt-runtime-hashes.json'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_hashes(dest: Path) -> dict[str, str]:
    marker = dest / MARKER
    if dest.is_symlink() or marker.is_symlink():
        return {}
    try:
        values = json.loads(marker.read_text(encoding='utf-8'))
        if not isinstance(values, dict):
            return {}
        return {name: value for name, value in values.items()
                if isinstance(name, str) and Path(name).name == name and name not in ('.', '..')
                and isinstance(value, str) and len(value) == 64}
    except (OSError, ValueError):
        return {}


def unchanged(dest: Path, name: str, hashes: dict[str, str]) -> bool:
    path = dest / name
    return (not dest.is_symlink() and name in hashes and Path(name).name == name
            and not path.is_symlink() and path.is_file() and digest(path) == hashes[name])


def install(source: Path, dest: Path) -> None:
    marker = dest / MARKER
    if dest.is_symlink() or marker.is_symlink():
        raise ValueError(f'symlinked runtime directory or ownership marker: {dest}')
    if marker.exists():
        try:
            data = json.loads(marker.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or len(load_hashes(dest)) != len(data):
                raise ValueError('invalid ownership entries')
        except (OSError, ValueError) as exc:
            raise ValueError(f'invalid runtime ownership marker: {marker}') from exc
    manifest = source / 'runtime-manifest.txt'
    names = [line.split('#', 1)[0].strip() for line in manifest.read_text(encoding='utf-8').splitlines()]
    names.append('runtime-manifest.txt')
    if any(Path(name).name != name or name in ('.', '..') for name in names if name):
        raise ValueError('invalid runtime script name')
    dest.mkdir(parents=True, exist_ok=True)
    previous = load_hashes(dest)
    owned = {name: value for name, value in previous.items() if unchanged(dest, name, previous)}
    for name in filter(None, names):
        src = source / name
        if src.is_symlink() or not src.is_file():
            raise ValueError(f'missing or linked runtime script: {name}')
        target = dest / name
        if not target.exists() and not target.is_symlink() or unchanged(dest, name, previous):
            shutil.copy2(src, target)
            owned[name] = digest(target)
            continue
        if not target.is_symlink() and target.is_file() and digest(src) == digest(target):
            continue
        number = 0
        while True:
            suffix = f'.{number}' if number else ''
            alternate = f'{src.stem}.skill-governance-toolkit{suffix}{src.suffix}'
            candidate = dest / alternate
            if not candidate.exists() and not candidate.is_symlink() or unchanged(dest, alternate, previous):
                shutil.copy2(src, candidate)
                owned[alternate] = digest(candidate)
                break
            if not candidate.is_symlink() and candidate.is_file() and digest(src) == digest(candidate):
                break
            number += 1
        print(f'  ! preserved scripts/{name}; incoming version: scripts/{alternate} (not active)', file=sys.stderr)
    marker.write_text(json.dumps(owned, indent=2, sort_keys=True) + '\n', encoding='utf-8')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('usage: managed_runtime.py SOURCE_SCRIPTS TARGET_SCRIPTS')
        install(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError) as exc:
        print(f'managed runtime: {exc}', file=sys.stderr)
        raise SystemExit(2)
