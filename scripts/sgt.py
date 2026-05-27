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
import subprocess
import sys
from pathlib import Path
from typing import Any

from doctor import print_text as print_doctor_text
from doctor import run_doctor
from quickstart import print_text as print_quickstart_text
from quickstart import build_quickstart


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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
