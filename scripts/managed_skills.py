#!/usr/bin/env python3
"""Install managed skills without replacing or removing user-owned content."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = ".sgt-skill-owned.json"
INDEX_MARKER = ".sgt-index-owned.json"


def hashes(folder: Path) -> dict[str, str]:
    result = {}
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError("skill contains a symlink")
        if path.is_dir():
            result[path.relative_to(folder).as_posix() + "/"] = "directory"
        elif path.is_file() and path.name != MARKER:
            result[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def owned_and_unchanged(folder: Path) -> bool:
    try:
        marker = folder / MARKER
        return (folder.is_dir() and not folder.is_symlink() and marker.is_file()
                and json.loads(marker.read_text(encoding="utf-8")) == hashes(folder))
    except (OSError, ValueError, TypeError):
        return False


def owned_index_unchanged(folder: Path) -> bool:
    try:
        index = folder / "INDEX.jsonl"
        marker = folder / INDEX_MARKER
        return (index.is_file() and not index.is_symlink() and marker.is_file()
                and marker.read_text(encoding="utf-8").strip() == hashlib.sha256(index.read_bytes()).hexdigest())
    except OSError:
        return False


def install(dest: Path, names: list[str], write_index: bool = False) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name in names:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError(f"invalid skill name: {name}")
        source = ROOT / "skills" / name
        target = dest / name
        if not source.is_dir() or source.is_symlink():
            raise ValueError(f"missing source skill: {name}")
        source_hashes = hashes(source)  # Reject links before copytree can follow them.
        if target.exists() or target.is_symlink():
            if not owned_and_unchanged(target):
                print(f"  ! preserved existing or modified skill: {target}", file=sys.stderr)
                continue
            if hashes(target) == source_hashes:
                print(f"  · already current: {target}")
                continue
        with tempfile.TemporaryDirectory(prefix=".sgt-copy-", dir=dest) as tmp:
            staged = Path(tmp) / name
            shutil.copytree(source, staged, symlinks=False)
            (staged / MARKER).write_text(json.dumps(hashes(staged), sort_keys=True) + "\n", encoding="utf-8")
            backup = Path(tmp) / "previous"
            if target.exists():
                os.replace(target, backup)
            try:
                os.replace(staged, target)
            except OSError:
                if backup.exists():
                    os.replace(backup, target)
                raise
        print(f"  ✓ managed skill: {target}")
    if write_index:
        index = dest / "INDEX.jsonl"
        marker = dest / INDEX_MARKER
        if (index.exists() or index.is_symlink()) and not owned_index_unchanged(dest):
            print(f"  ! preserved existing or modified index: {index}", file=sys.stderr)
            return
        source_index = ROOT / "skills" / "INDEX.jsonl"
        entries = [json.loads(line) for line in source_index.read_text(encoding="utf-8").splitlines() if line.strip()]
        managed = {name for name in names if owned_and_unchanged(dest / name)}
        content = "".join(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
                          for entry in entries if entry.get("name") in managed)
        index.write_text(content, encoding="utf-8")
        marker.write_text(hashlib.sha256(content.encode("utf-8")).hexdigest() + "\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) < 4 or sys.argv[1] != "install":
        print("usage: managed_skills.py install DEST [--index] SKILL [SKILL ...]", file=sys.stderr)
        return 2
    try:
        args = sys.argv[3:]
        write_index = "--index" in args
        install(Path(sys.argv[2]), [name for name in args if name != "--index"], write_index)
    except (OSError, ValueError) as exc:
        print(f"managed_skills: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
