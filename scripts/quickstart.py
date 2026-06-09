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


# Commands every install can run (the CLI facade ships into a consumer project).
COMMON_COMMANDS = [
    {"label": "Check local readiness", "command": "python3 scripts/sgt.py doctor"},
    {"label": "Show this guide", "command": "python3 scripts/sgt.py quickstart"},
]
# Checkout-only commands: install.sh and the self-audit runner (audit.sh) are NOT
# delivered into a consumer install, so surfacing them there points at nothing.
CHECKOUT_COMMANDS = [
    {"label": "Install interactively", "command": "./install.sh"},
    {"label": "Preview install plan", "command": "./install.sh --dry-run"},
    {"label": "Install Claude project defaults non-interactively", "command": "./install.sh --yes-default"},
    {"label": "Run full self-audit", "command": "python3 scripts/sgt.py audit"},
]
# Consumer-only commands: the gate and the installed-skill list are the useful
# next actions once the toolkit is in your project.
CONSUMER_COMMANDS = [
    {"label": "List installed skills", "command": "python3 scripts/sgt.py skills"},
    {"label": "Run the pre-merge gate", "command": "python3 scripts/sgt.py gate --base main"},
]


def build_quickstart(root: Path) -> dict[str, Any]:
    doctor = run_doctor(root)
    mode = doctor.get("mode", "checkout")
    # Absolute path to this facade so suggested commands work from any CWD, not
    # only from a toolkit checkout (relative `scripts/sgt.py` would not resolve).
    sgt_cli = Path(__file__).resolve().parent / "sgt.py"
    uninstalled = doctor.get("installed") is False
    if doctor["summary"]["fail"] and mode == "consumer" and uninstalled:
        next_step = {
            "label": "Toolkit is not installed in this directory — run the installer, "
                     "or cd into the project where you installed it",
            "command": f"python3 {sgt_cli} init",
        }
    elif doctor["summary"]["fail"]:
        next_step = {
            "label": "Fix health check failures first",
            "command": f"python3 {sgt_cli} doctor",
        }
    elif mode == "consumer":
        next_step = {
            "label": "Invoke a skill by its trigger phrase",
            "command": 'ask your agent: «is there a skill for evaluating prompts?»',
        }
    else:
        next_step = {
            "label": "Install into a target runtime or run a skill directly",
            "command": "./install.sh",
        }

    common = COMMON_COMMANDS + (CHECKOUT_COMMANDS if mode == "checkout" else CONSUMER_COMMANDS)
    return {
        "root": doctor["root"],
        "mode": mode,
        "doctor_summary": doctor["summary"],
        "next_step": next_step,
        "common_commands": common,
        "decision_tree": DECISIONS,
    }


def print_text(report: dict[str, Any]) -> None:
    summary = report["doctor_summary"]
    print("Skill Governance Toolkit quickstart")
    print(f"Root: {report['root']}")
    print(f"Mode: {report.get('mode', 'checkout')}")
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
