#!/usr/bin/env python3
"""
filter_skills.py — apply selection filters over skills/INDEX.jsonl and emit a
newline-separated list of skill names. Used by install.sh to decide which
skill subdirectories to copy.

The installer reads metainfo (category / tier) from INDEX.jsonl instead of
parsing every SKILL.md, so this helper is the single canonical decoder of the
filter semantics.

Filter rules (since 1.8.0):
  --skill A,B,C        Hard list. Other filters ignored when set.
  --category X,Y       Skill must have ≥1 category in this set (OR within --category).
  --tier T1,T2         Skill's tier must be in this set. Default: stable,preview.
  (no filters)         All skills, tier-filtered to default (stable,preview).

`unknown` tier (orphan skill without metainfo) is excluded by default — opt
into it with `--tier unknown` if you really need to install orphan skills.

Diagnostic modes:
  --list-categories    Print 'category\\tcount' rows. Used by --interactive in install.sh.
  --filtered-index     Print a fresh INDEX.jsonl containing only the filtered subset
                       (used so the destination skill-find sees only what's installed).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def load_index(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        print(f"filter_skills: INDEX.jsonl not found at {path}", file=sys.stderr)
        sys.exit(2)
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"filter_skills: bad JSON in {path}: {e}", file=sys.stderr)
            sys.exit(2)
    return entries


def parse_csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def apply_filters(
    entries: list[dict[str, Any]],
    skill_list: list[str] | None,
    category_list: list[str] | None,
    tier_list: list[str],
) -> list[dict[str, Any]]:
    """Apply the v1.8.0 filter rules and return surviving entries."""
    result: list[dict[str, Any]] = []
    for e in entries:
        mi = e.get("metainfo") or {}
        cats = mi.get("category") or []
        tier = mi.get("tier", "unknown")

        if skill_list is not None:
            if e["name"] not in skill_list:
                continue
            # --skill overrides tier+category filters by design (explicit names ⇒ user knows what they want)
            result.append(e)
            continue

        if category_list is not None:
            if not (set(cats) & set(category_list)):
                continue

        if tier not in tier_list:
            continue

        result.append(e)
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    p.add_argument("--index", required=True, type=Path, help="Path to skills/INDEX.jsonl")
    p.add_argument("--category", default="", help="Comma-separated category filter")
    p.add_argument("--tier", default="stable,preview", help="Comma-separated tier filter")
    p.add_argument("--skill", default="", help="Comma-separated skill name list (overrides tier+category)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--list-categories", action="store_true", help="Print 'category\\tcount' summary and exit")
    g.add_argument("--filtered-index", action="store_true", help="Print filtered INDEX.jsonl to stdout")
    args = p.parse_args()

    entries = load_index(args.index)

    if args.list_categories:
        c: Counter[str] = Counter()
        # Also count per-tier so the interactive menu can show stability mix.
        tiers: Counter[str] = Counter()
        for e in entries:
            mi = e.get("metainfo") or {}
            tiers[mi.get("tier", "unknown")] += 1
            for cat in mi.get("category") or []:
                c[cat] += 1
        for cat, cnt in sorted(c.items()):
            print(f"category\t{cat}\t{cnt}")
        for tier, cnt in sorted(tiers.items()):
            print(f"tier\t{tier}\t{cnt}")
        return 0

    skill_list = parse_csv(args.skill) if args.skill else None
    category_list = parse_csv(args.category) if args.category else None
    tier_list = parse_csv(args.tier) if args.tier else ["stable", "preview"]

    filtered = apply_filters(entries, skill_list, category_list, tier_list)

    if args.filtered_index:
        for e in filtered:
            print(json.dumps(e, ensure_ascii=False, separators=(",", ":")))
        return 0

    # Default: print one skill name per line — install.sh consumes this with `read -a`.
    for e in filtered:
        print(e["name"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
