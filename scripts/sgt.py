#!/usr/bin/env python3
"""
sgt.py - small CLI facade for common Skill Governance Toolkit tasks.

This is not a packaging layer. It is a stable stdlib-only entry point over the
existing scripts so users can discover and run the common workflows without
remembering every filename.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from doctor import print_text as print_doctor_text
from doctor import run_doctor
from quickstart import print_text as print_quickstart_text
from quickstart import build_quickstart

# Install root (where the toolkit's own scripts/references/templates live). Distinct
# from `--root`, which is the user's project being operated on.
SGT_ROOT = Path(__file__).resolve().parents[1]

# Source of truth: docs/skill-authoring-standard.md and AGENTS.md. Kept here so the
# scaffolder fails fast on an invalid name/category without parsing the docs.
ACTION_VERBS = (
    "find", "audit", "evaluate", "compare", "build", "extend",
    "frame", "ingest", "mark", "plan", "query", "init",
)
CATEGORIES = ("code-review", "docs", "testing", "governance", "discovery", "research", "delivery")
TIERS = ("stable", "preview", "experimental", "internal")


def load_index(root: Path) -> list[dict[str, Any]]:
    index_path = root / "skills" / "INDEX.jsonl"
    entries: list[dict[str, Any]] = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def command_doctor(args: argparse.Namespace) -> int:
    report = run_doctor(args.root)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_doctor_text(report)
    return 0 if report["summary"]["passed"] else 1


def command_quickstart(args: argparse.Namespace) -> int:
    report = build_quickstart(args.root)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_quickstart_text(report)
    return 0 if report["doctor_summary"]["fail"] == 0 else 1


def command_skills(args: argparse.Namespace) -> int:
    root = args.root.expanduser().resolve()
    try:
        entries = load_index(root)
    except FileNotFoundError:
        print(f"skills/INDEX.jsonl not found under {root}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps({"root": str(root), "skills": entries}, ensure_ascii=False, indent=2))
        return 0

    print("Skills:")
    for entry in entries:
        metainfo = entry.get("metainfo") or {}
        categories = ",".join(metainfo.get("category") or [])
        tier = metainfo.get("tier", "unknown")
        print(f"  - {entry['name']} [{tier}; {categories}]")
    return 0


def command_audit(args: argparse.Namespace) -> int:
    root = args.root.expanduser().resolve()
    script = root / "scripts" / "audit.sh"
    if not script.exists():
        print(f"scripts/audit.sh not found under {root}", file=sys.stderr)
        return 1
    result = subprocess.run(["bash", str(script)], cwd=root, check=False)
    return result.returncode


def validate_skill_name(name: str) -> str | None:
    """Return an error string if `name` violates the naming convention, else None.

    Convention (AGENTS.md §6): `{entity}-{action}[-{qualifier}]`, kebab-case,
    closed-vocab action verb, ≤ 3 words after the entity (≤ 4 segments total).
    """
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+){1,3}", name):
        return (f"'{name}' is not valid: use kebab-case `entity-action[-qualifier]` "
                f"(lower-case, 2–4 segments, e.g. 'prompt-evaluate').")
    segments = name.split("-")
    action = segments[1]
    if action not in ACTION_VERBS:
        return (f"'{action}' is not an allowed action verb. The second segment must be "
                f"one of: {', '.join(ACTION_VERBS)}.")
    return None


def _scaffold_body(name: str, categories: list[str]) -> str:
    """A governance-clean, detect-only SKILL.md template that passes the engine.

    Detect-only by default: no mutation surface, no user-prompt language, so
    SKILL021 (skill-type), SKILL022 (clarification), and SKILL023 (mutating
    contract) are all satisfied out of the box.
    """
    entity = name.split("-")[0]
    return f"""---
name: {name}
description: |
  TODO one-line purpose of {name}.
  Use when the user TODO describes the trigger situation in their own words.
  Triggers: «TODO phrase one», «TODO phrase two», «TODO phrase three».
compatibility: "Claude Code · GitHub Copilot · Cursor v2.2+ · OpenAI Codex CLI · Google Gemini CLI"
license: MIT
metainfo:
  category: [{', '.join(categories)}]
  tier: preview
  owner: "TODO-your-handle"
---

# {name}

> **Skill type:** Detect-only — reads inputs and reports; never edits any source file.

## When to use

Use when TODO. Skip / Don't use for: TODO the negative triggers.

## Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `TARGET` | string | — | TODO what this skill operates on. |

## Procedure

1. **Phase 0 — scope check.** Fail fast if `TARGET` is missing or out of scope.
2. **Phase 1 — analyze.** TODO the core read-only work.
3. **Phase 2 — report.** Emit the result; write only to the documented output path.

## Hard rules

- Detect-only: never modify `{entity}` sources. This skill is fully non-interactive.
- Bounded scope: every run must operate on an explicit `TARGET`, never «everything».

## Output

TODO describe the exact output shape (table / JSONL / report path).
"""


def command_new_skill(args: argparse.Namespace) -> int:
    name = args.name
    err = validate_skill_name(name)
    if err:
        print(f"sgt new-skill: {err}", file=sys.stderr)
        return 2
    categories = [c.strip() for c in args.category.split(",") if c.strip()]
    bad = [c for c in categories if c not in CATEGORIES]
    if not categories or bad:
        print(f"sgt new-skill: unknown category {bad or categories}. "
              f"Closed vocab: {', '.join(CATEGORIES)}.", file=sys.stderr)
        return 2

    skill_dir = (args.root.expanduser() / "skills" / name).resolve()
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists() and not args.force:
        print(f"sgt new-skill: {skill_md} already exists. Pass --force to overwrite.", file=sys.stderr)
        return 1

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md.write_text(_scaffold_body(name, categories), encoding="utf-8")
    print(f"✓ scaffolded skills/{name}/SKILL.md ({', '.join(categories)} · tier preview)")
    print("  Next:")
    print(f"    1. Fill the TODOs (description triggers, procedure, output).")
    print(f"    2. Evaluate it:  invoke skill-evaluate on skills/{name}/SKILL.md")
    print(f"    3. Re-index:     python3 {SGT_ROOT}/scripts/build_index.py")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Skill Governance Toolkit command facade.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Project root to operate on.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    doctor = subcommands.add_parser("doctor", help="Run the quick local health check.")
    doctor.add_argument("--format", choices=["text", "json"], default="text")
    doctor.set_defaults(func=command_doctor)

    quickstart = subcommands.add_parser("quickstart", help="Print next steps and the intent-to-skill map.")
    quickstart.add_argument("--format", choices=["text", "json"], default="text")
    quickstart.set_defaults(func=command_quickstart)

    skills = subcommands.add_parser("skills", help="List indexed skills.")
    skills.add_argument("--format", choices=["text", "json"], default="text")
    skills.set_defaults(func=command_skills)

    audit = subcommands.add_parser("audit", help="Run the full self-audit.")
    audit.set_defaults(func=command_audit)

    new_skill = subcommands.add_parser(
        "new-skill", help="Scaffold a governance-clean SKILL.md skeleton.")
    new_skill.add_argument("name", help="Skill name: entity-action[-qualifier] (e.g. prompt-evaluate).")
    new_skill.add_argument(
        "--category", required=True,
        help=f"Comma-separated metainfo categories. Closed vocab: {', '.join(CATEGORIES)}.")
    new_skill.add_argument("--force", action="store_true", help="Overwrite an existing SKILL.md.")
    new_skill.set_defaults(func=command_new_skill)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
