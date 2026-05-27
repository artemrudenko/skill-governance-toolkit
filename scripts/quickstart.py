#!/usr/bin/env python3
"""
quickstart.py - concise next-step guide for Skill Governance Toolkit users.

It turns the project health signal from doctor.py into a short decision tree:
what to run first, which skill to invoke for each common job, and which install
command to use for local experiments.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from doctor import run_doctor


DECISIONS = [
    {
        "need": "Find whether a useful skill already exists",
        "use": "skill-find",
        "trigger": "is there a skill for X",
    },
    {
        "need": "Score one SKILL.md for quality and safety",
        "use": "skill-evaluate",
        "trigger": "evaluate this skill",
    },
    {
        "need": "Compare local and upstream/corporate skills",
        "use": "skill-compare",
        "trigger": "compare these skills",
    },
    {
        "need": "Audit a whole skill library",
        "use": "library-audit",
        "trigger": "audit my skills",
    },
    {
        "need": "Make a host-specific skill portable",
        "use": "skill-build-portable",
        "trigger": "make this skill portable",
    },
    {
        "need": "Set up optional integrations",
        "use": "integration-init",
        "trigger": "set up integrations",
    },
]


def build_quickstart(root: Path) -> dict[str, Any]:
    doctor = run_doctor(root)
    if doctor["summary"]["fail"]:
        next_step = {
            "label": "Fix health check failures first",
            "command": "python3 scripts/doctor.py",
        }
    else:
        next_step = {
            "label": "Install into a target runtime or run a skill directly",
            "command": "./install.sh",
        }

    return {
        "root": doctor["root"],
        "doctor_summary": doctor["summary"],
        "next_step": next_step,
        "common_commands": [
            {
                "label": "Check local readiness",
                "command": "python3 scripts/sgt.py doctor",
            },
            {
                "label": "Show this guide",
                "command": "python3 scripts/sgt.py quickstart",
            },
            {
                "label": "Install interactively",
                "command": "./install.sh",
            },
            {
                "label": "Preview install plan",
                "command": "./install.sh --dry-run",
            },
            {
                "label": "Install Claude project defaults non-interactively",
                "command": "./install.sh --yes-default",
            },
            {
                "label": "Run full self-audit",
                "command": "python3 scripts/sgt.py audit",
            },
        ],
        "decision_tree": DECISIONS,
    }


def print_text(report: dict[str, Any]) -> None:
    summary = report["doctor_summary"]
    print("Skill Governance Toolkit quickstart")
    print(f"Root: {report['root']}")
    print(f"Health: {summary['ok']} ok, {summary['warn']} warn, {summary['fail']} fail")
    print("")
    print(f"Next: {report['next_step']['label']}")
    print(f"  {report['next_step']['command']}")
    print("")
    print("Common commands:")
    for command in report["common_commands"]:
        print(f"  - {command['label']}: {command['command']}")
    print("")
    print("Decision tree:")
    for item in report["decision_tree"]:
        print(f"  - {item['need']}: {item['use']} (trigger: \"{item['trigger']}\")")


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a concise Skill Governance Toolkit quickstart guide.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Project root to inspect.")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    args = parser.parse_args()

    report = build_quickstart(args.root)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report)
    return 0 if report["doctor_summary"]["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
