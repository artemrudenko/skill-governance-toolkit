#!/usr/bin/env python3
"""Install project documentation without overwriting unverified local changes."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

MARKER = ".sgt-docs-hashes.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_hashes(dest: Path) -> dict[str, str]:
    try:
        data = json.loads((dest / MARKER).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if isinstance(k, str) and Path(k).name == k
                and isinstance(v, str) and len(v) == 64}
    except (OSError, ValueError):
        return {}


def managed_unchanged(dest: Path, name: str, hashes: dict[str, str]) -> bool:
    path = dest / name
    return (name in hashes and not path.is_symlink() and path.is_file()
            and digest(path) == hashes[name])


def install_docs(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    previous = load_hashes(dest)
    owned = {name: value for name, value in previous.items()
             if managed_unchanged(dest, name, previous)}
    for src in sorted(source.glob("*.md")):
        if not src.is_file():
            continue
        name = src.name
        target = dest / name
        if not target.exists() and not target.is_symlink():
            shutil.copyfile(src, target)
            owned[name] = digest(target)
            print(f"  · placed docs/{name}")
        elif managed_unchanged(dest, name, previous):
            if digest(src) != digest(target):
                shutil.copyfile(src, target)
                print(f"  · updated managed docs/{name}")
            owned[name] = digest(target)
        elif not target.is_symlink() and target.is_file() and digest(src) == digest(target):
            print(f"  · preserved unverified identical docs/{name}")
        else:
            stem = src.stem + ".skill-governance-toolkit"
            number = 0
            while True:
                alternate = f"{stem}{'.' + str(number) if number else ''}.md"
                candidate = dest / alternate
                if not candidate.exists() and not candidate.is_symlink():
                    shutil.copyfile(src, candidate)
                    owned[alternate] = digest(candidate)
                    break
                if managed_unchanged(dest, alternate, previous):
                    shutil.copyfile(src, candidate)
                    owned[alternate] = digest(candidate)
                    break
                if not candidate.is_symlink() and candidate.is_file() and digest(src) == digest(candidate):
                    break
                number += 1
            print(f"  ! preserved docs/{name}; incoming version: docs/{alternate}")
    (dest / MARKER).write_text(json.dumps(owned, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (dest / ".sgt-owned").write_text("".join(name + "\n" for name in sorted(owned)), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: managed_docs.py SOURCE_DOCS TARGET_DOCS")
    install_docs(Path(sys.argv[1]), Path(sys.argv[2]))
