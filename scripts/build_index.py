#!/usr/bin/env python3
"""
build_index.py — INDEX.jsonl generator for a SKILL.md library.

Scans a skills/ directory, extracts YAML frontmatter from every SKILL.md,
and writes one JSON object per line to INDEX.jsonl. Used by `skill-find` as
the fast-path discovery mechanism — without this, skill-find falls back to
scanning every SKILL.md individually.

Usage:
    python3 scripts/build_index.py [--skills-dir PATH] [--output PATH] [--dry-run]

Defaults:
    --skills-dir ./skills/
    --output    ./skills/INDEX.jsonl  (or wherever the dir lives)

Requirements: Python 3.8+ stdlib only (no pip dependencies).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# ── Minimal YAML frontmatter parser ────────────────────────────────────────────
# We parse only the subset of YAML used in SKILL.md frontmatter:
# - simple key: value pairs
# - nested keys (one level deep)
# - block scalars with | or > (kept as-is)
# - lists with - prefix
# This avoids a pyyaml dependency — frontmatter shapes are stable.

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Extract YAML frontmatter from a markdown file. Returns None if absent."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    body = match.group(1)
    return _parse_yaml_lines(body.splitlines())


def _parse_yaml_lines(lines: list[str]) -> dict[str, Any]:
    """Tiny YAML subset parser. Handles: key:value, key:|block, list-items, nested 2-space indent."""
    result: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        if ":" not in line:
            i += 1
            continue

        # No indent → top-level key
        if not line.startswith(" ") and not line.startswith("\t"):
            key, _, rest = line.partition(":")
            key = key.strip()
            value = rest.strip()

            if value in ("|", ">", "|-", ">-", "|+", ">+"):
                # Block scalar — collect indented lines below
                block_lines: list[str] = []
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if nxt.startswith("  ") or nxt.startswith("\t") or nxt.strip() == "":
                        block_lines.append(nxt[2:] if nxt.startswith("  ") else nxt.lstrip("\t"))
                        i += 1
                    else:
                        break
                joined = "\n".join(block_lines).strip()
                result[key] = joined
                continue

            if value == "":
                # Could be a list or nested object — peek next lines
                items: list[Any] = []
                nested: dict[str, Any] = {}
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if nxt.startswith("  -") or nxt.startswith("\t-"):
                        item = nxt.split("-", 1)[1].strip()
                        items.append(_coerce(item))
                        i += 1
                    elif nxt.startswith("  ") and not nxt.startswith("   "):
                        nk, _, nv = nxt[2:].partition(":")
                        nested[nk.strip()] = _coerce(nv.strip())
                        i += 1
                    elif nxt.strip() == "":
                        i += 1
                    else:
                        break
                if items:
                    result[key] = items
                elif nested:
                    result[key] = nested
                else:
                    result[key] = ""
                continue

            # Inline scalar value
            result[key] = _coerce(value)
            i += 1
        else:
            i += 1  # skip mis-indented lines safely

    return result


def _coerce(raw: str) -> Any:
    """Coerce a YAML scalar string to Python primitive (str / int / float / bool / None / list).

    Supports YAML flow-style inline lists like `[a, b, "c d"]` (needed for the
    `metainfo.category` field) — splits on commas, strips, and recursively coerces
    each element. Does NOT handle nested flow-style maps `{k: v}` — block-style
    only for nested objects, which is what our SKILL.md frontmatter uses.
    """
    s = raw.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        # naive split on commas at top level (no nested brackets in our use)
        return [_coerce(part) for part in inner.split(",")]
    if s.lower() in ("true", "yes"):
        return True
    if s.lower() in ("false", "no"):
        return False
    if s.lower() in ("null", "~", ""):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


# ── Index builder ──────────────────────────────────────────────────────────────


def build_index(skills_dir: Path) -> list[dict[str, Any]]:
    """Scan skills_dir for SKILL.md files, extract frontmatter, return list of entries."""
    if not skills_dir.exists():
        raise SystemExit(f"Skills directory not found: {skills_dir}")

    entries: list[dict[str, Any]] = []
    skill_files = sorted(skills_dir.rglob("SKILL.md"))

    for skill_path in skill_files:
        try:
            text = skill_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"  ! skipped {skill_path}: {e}", file=sys.stderr)
            continue

        fm = parse_frontmatter(text)
        if fm is None:
            print(f"  ! skipped {skill_path}: no frontmatter", file=sys.stderr)
            continue

        if "name" not in fm or "description" not in fm:
            print(f"  ! skipped {skill_path}: missing name or description", file=sys.stderr)
            continue

        rel_path = skill_path.relative_to(skills_dir.parent)

        entry: dict[str, Any] = {
            "name": fm["name"],
            "description": fm["description"],
            "path": str(rel_path),
        }

        # Optional fields — included only if present
        for field in ("compatibility", "license", "tags", "portability"):
            if field in fm:
                entry[field] = fm[field]

        # metainfo block (since 1.8.0) — installer filters / library-audit Phase 8 read this.
        # We surface the whole sub-map so future fields don't need a code change here.
        # Orphan skills (no metainfo) are still indexed so the installer can see them,
        # but get a sentinel `tier="unknown"` so the default --tier filter drops them
        # rather than silently installing skills with unclear stability.
        if "metainfo" in fm and isinstance(fm["metainfo"], dict):
            entry["metainfo"] = fm["metainfo"]
        else:
            entry["metainfo"] = {"category": [], "tier": "unknown"}
            print(f"  ! {skill_path.parent.name}: no metainfo block (will be excluded by default install)", file=sys.stderr)

        # Lines count (handy for clients sorting by complexity)
        body = FRONTMATTER_RE.sub("", text, count=1)
        entry["lines"] = body.count("\n")

        entries.append(entry)

    return entries


def write_index(entries: list[dict[str, Any]], output_path: Path, dry_run: bool = False) -> None:
    """Write entries as JSONL — one JSON object per line, no trailing newline at EOF."""
    lines = [json.dumps(e, ensure_ascii=False, separators=(",", ":")) for e in entries]
    content = "\n".join(lines) + "\n"

    if dry_run:
        print(content)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"✓ wrote {len(entries)} entries to {output_path}")


# ── CLI ────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build INDEX.jsonl from SKILL.md frontmatter — fast-path for skill-find."
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=Path("./skills"),
        help="Directory containing SKILL.md files (default: ./skills)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for INDEX.jsonl (default: {skills-dir}/INDEX.jsonl)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print to stdout instead of writing to disk",
    )

    args = parser.parse_args()

    skills_dir = args.skills_dir.resolve()
    output = args.output if args.output else skills_dir / "INDEX.jsonl"

    print(f"Scanning: {skills_dir}")
    entries = build_index(skills_dir)

    if not entries:
        print("! No skills found.", file=sys.stderr)
        return 1

    write_index(entries, output.resolve(), dry_run=args.dry_run)

    print(f"  {len(entries)} skill(s) indexed:")
    for e in entries:
        desc_preview = (e["description"][:60] + "…") if len(e["description"]) > 60 else e["description"]
        print(f"    · {e['name']:20s} ({e['lines']:>3} lines) — {desc_preview}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
