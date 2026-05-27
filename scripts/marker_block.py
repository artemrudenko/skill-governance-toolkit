#!/usr/bin/env python3
"""marker_block.py — idempotent insert/replace/remove of a managed content block.

Used by install.sh / install.ps1 for the four USER-OWNED project files:
  AGENTS.md, CLAUDE.md, GEMINI.md, .github/copilot-instructions.md

The toolkit NEVER overwrites these files. It manages a single named block
delimited by markers. User edits OUTSIDE the markers are preserved across
fresh installs, upgrades, and uninstalls.

Markers (default marker_id = `skill-governance-toolkit`):
  <!-- {marker_id}: BEGIN -->
  ...managed content...
  <!-- {marker_id}: END -->

Usage:
  marker_block.py upsert --file PATH --src SOURCE_FILE [--marker-id ID]
  marker_block.py remove --file PATH                    [--marker-id ID]

Semantics of `upsert`:
  - File missing       → create with just the managed block
  - File present, no markers → append block at end (after user's existing content)
  - File present, with markers → replace content between markers in place
  All three outcomes are idempotent — re-running upsert is a no-op when content matches.

Exit codes:
  0 — success (whether action was taken or already idempotent)
  1 — IO error or invalid arguments

Pure stdlib. Python 3.8+.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_MARKER_ID = "skill-governance-toolkit"


def _build_block(marker_id: str, src_content: str) -> str:
    """Wrap source content in BEGIN/END markers with a fixed managed-block notice."""
    begin = f"<!-- {marker_id}: BEGIN -->"
    end = f"<!-- {marker_id}: END -->"
    notice = (
        f"<!-- This block is managed by the Skill Governance Toolkit installer.\n"
        f"     Edits INSIDE this block are OVERWRITTEN on upgrade.\n"
        f"     Customize OUTSIDE the markers. -->"
    )
    return f"{begin}\n{notice}\n\n{src_content.rstrip()}\n\n{end}"


def upsert(file_path: str, src_path: str, marker_id: str) -> int:
    dest = Path(file_path)
    try:
        src_content = Path(src_path).read_text(encoding="utf-8")
    except OSError as e:
        print(f"  ! cannot read source {src_path}: {e}", file=sys.stderr)
        return 1

    block = _build_block(marker_id, src_content)
    begin = f"<!-- {marker_id}: BEGIN -->"
    end = f"<!-- {marker_id}: END -->"

    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(block + "\n", encoding="utf-8")
        print(f"  · created {file_path} with managed block")
        return 0

    existing = dest.read_text(encoding="utf-8")

    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    match = pattern.search(existing)
    if match:
        if match.group(0) == block:
            print(f"  · block in {file_path} already current (no change)")
            return 0
        new = pattern.sub(block, existing, count=1)
        dest.write_text(new, encoding="utf-8")
        print(f"  · updated managed block in {file_path} (user content outside markers preserved)")
        return 0

    # No markers in existing file — append at end
    sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    dest.write_text(existing + sep + block + "\n", encoding="utf-8")
    print(f"  · appended managed block to {file_path} (existing content preserved at top)")
    return 0


def remove(file_path: str, marker_id: str) -> int:
    dest = Path(file_path)
    if not dest.exists():
        return 0
    begin = f"<!-- {marker_id}: BEGIN -->"
    end = f"<!-- {marker_id}: END -->"
    existing = dest.read_text(encoding="utf-8")
    pattern = re.compile(r"\n*" + re.escape(begin) + r".*?" + re.escape(end) + r"\n*", re.DOTALL)
    new = pattern.sub("\n", existing)
    if new == existing:
        return 0
    # Cleanup: if the file is now empty (only had our block), delete it; otherwise write
    if new.strip() == "":
        dest.unlink()
        print(f"  · removed {file_path} (file was only the managed block)")
    else:
        dest.write_text(new.rstrip() + "\n", encoding="utf-8")
        print(f"  · removed managed block from {file_path} (user content preserved)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Idempotent marker-block management for user-owned project files."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("upsert", help="Insert or replace the managed block")
    p.add_argument("--file", required=True, help="Destination file (e.g. AGENTS.md)")
    p.add_argument("--src", required=True, help="Source file with content to put inside markers")
    p.add_argument("--marker-id", default=DEFAULT_MARKER_ID)
    p.set_defaults(func=lambda a: upsert(a.file, a.src, a.marker_id))

    p = sub.add_parser("remove", help="Remove the managed block (uninstall)")
    p.add_argument("--file", required=True)
    p.add_argument("--marker-id", default=DEFAULT_MARKER_ID)
    p.set_defaults(func=lambda a: remove(a.file, a.marker_id))

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
