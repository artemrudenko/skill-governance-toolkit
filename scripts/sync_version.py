#!/usr/bin/env python3
"""
sync_version.py - keep release version metadata in sync with VERSION.

JSON and TOML manifests cannot reference a shared variable directly, so this
script treats the root VERSION file as the source of truth and rewrites the
derived copies. CI uses --check to fail on drift.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
README_PIN_RE = re.compile(r"(skill-governance-toolkit@|extensions install \.\.\.@)\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?")
PYPROJECT_VERSION_RE = re.compile(r'(?m)^version = "[^"]+"$')


def load_version(root: Path) -> str:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not VERSION_RE.match(version):
        raise ValueError(f"VERSION has invalid semantic version: {version!r}")
    return version


def update_json_file(path: Path, version: str, fields: list[tuple[str, ...]]) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for field_path in fields:
        cursor: Any = payload
        for key in field_path[:-1]:
            cursor = cursor[key]
        leaf = field_path[-1]
        if cursor.get(leaf) != version:
            cursor[leaf] = version
            changed = True
    if changed:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def replace_text(path: Path, pattern: re.Pattern[str], replacement: str) -> bool:
    text = path.read_text(encoding="utf-8")
    new = pattern.sub(replacement, text)
    if new == text:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def sync(root: Path) -> list[str]:
    version = load_version(root)
    changed: list[str] = []

    json_targets = {
        ".claude-plugin/plugin.json": [("version",)],
        ".claude-plugin/marketplace.json": [("metadata", "version"), ("plugins", "0", "version")],
        ".codex-plugin/plugin.json": [("version",)],
        "gemini-extension.json": [("version",)],
    }
    for rel_path, fields in json_targets.items():
        path = root / rel_path
        normalized_fields = [tuple(int(part) if part.isdigit() else part for part in field) for field in fields]
        if update_json_file(path, version, normalized_fields):  # type: ignore[arg-type]
            changed.append(rel_path)

    pyproject = root / "pyproject.toml"
    if replace_text(pyproject, PYPROJECT_VERSION_RE, f'version = "{version}"'):
        changed.append("pyproject.toml")

    readme = root / "README.md"
    readme_replacement = lambda match: f"{match.group(1)}{version}"
    text = readme.read_text(encoding="utf-8")
    new_text = README_PIN_RE.sub(readme_replacement, text)
    if new_text != text:
        readme.write_text(new_text, encoding="utf-8")
        changed.append("README.md")

    return changed


def check(root: Path) -> tuple[bool, list[str]]:
    before = {path: (root / path).read_text(encoding="utf-8") for path in DERIVED_FILES}
    changed = sync(root)
    after = {path: (root / path).read_text(encoding="utf-8") for path in DERIVED_FILES}
    drift = [path for path in DERIVED_FILES if before[path] != after[path]]
    for path, text in before.items():
        if after[path] != text:
            (root / path).write_text(text, encoding="utf-8")
    return not drift, drift or changed


def check_changelog(root: Path) -> bool:
    version = load_version(root)
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    return f"## [{version}]" in text


DERIVED_FILES = [
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".codex-plugin/plugin.json",
    "gemini-extension.json",
    "pyproject.toml",
    "README.md",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync derived version metadata from VERSION.")
    # Default to the repo root derived from this file's location (scripts/..),
    # not CWD — audit.sh may be invoked from any directory.
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: the repo containing this script).",
    )
    parser.add_argument("--check", action="store_true", help="Fail if derived files are not in sync.")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    try:
        if args.check:
            ok, drift = check(root)
            changelog_ok = check_changelog(root)
            if ok and changelog_ok:
                print(f"version metadata ok: {load_version(root)}")
                return 0
            if drift:
                print("version metadata drift:", ", ".join(drift), file=sys.stderr)
            if not changelog_ok:
                print(f"CHANGELOG.md missing release heading for VERSION {load_version(root)}", file=sys.stderr)
            return 1

        changed = sync(root)
        if changed:
            print("updated:", ", ".join(changed))
        else:
            print(f"version metadata already in sync: {load_version(root)}")
        if not check_changelog(root):
            print(f"warning: CHANGELOG.md has no heading for VERSION {load_version(root)}", file=sys.stderr)
        return 0
    except Exception as exc:
        print(f"sync_version: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
