#!/usr/bin/env python3
"""
doctor.py - quick health check for a Skill Governance Toolkit checkout.

The command is intentionally stdlib-only. It checks the things users need
before install, development, or release work: required files, Git state,
INDEX.jsonl freshness, skill metadata shape, local runtime pollution, and
the no-runtime-dependencies contract.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from build_index import build_index


REQUIRED_PATHS = [
    "AGENTS.md",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "skills/INDEX.jsonl",
    "scripts/audit.sh",
    "scripts/install.sh",
    "scripts/agent_audit.py",
]
LOCAL_RUNTIME_DIRS = [".claude", ".codex", ".gemini", ".cursor"]


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    message: str
    details: dict[str, Any]


def ok(name: str, message: str, **details: Any) -> Check:
    return Check(name=name, status="ok", message=message, details=details)


def warn(name: str, message: str, **details: Any) -> Check:
    return Check(name=name, status="warn", message=message, details=details)


def fail(name: str, message: str, **details: Any) -> Check:
    return Check(name=name, status="fail", message=message, details=details)


def run_command(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=root, text=True, capture_output=True, check=False)


def check_required_paths(root: Path) -> Check:
    missing = [path for path in REQUIRED_PATHS if not (root / path).exists()]
    if missing:
        return fail("required_paths", "Required project files are missing.", missing=missing)
    return ok("required_paths", "Required project files are present.", count=len(REQUIRED_PATHS))


def check_git(root: Path) -> Check:
    probe = run_command(root, ["git", "rev-parse", "--is-inside-work-tree"])
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return warn("git", "Directory is not a Git work tree.")

    branch = run_command(root, ["git", "branch", "--show-current"]).stdout.strip()
    status = run_command(root, ["git", "status", "--short", "--ignored"])
    lines = [line for line in status.stdout.splitlines() if line.strip()]
    tracked_dirty = [line for line in lines if not line.startswith("!!")]
    ignored = [line for line in lines if line.startswith("!!")]

    details = {
        "branch": branch or None,
        "tracked_dirty": tracked_dirty,
        "ignored": ignored,
    }
    if tracked_dirty:
        return warn("git", "Git work tree has uncommitted tracked or untracked files.", **details)
    return ok("git", "Git work tree is clean.", **details)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"bad JSON on line {line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"line {line_number} is not a JSON object")
        entries.append(value)
    return entries


def canonical_jsonl(entries: list[dict[str, Any]]) -> list[str]:
    return [json.dumps(entry, ensure_ascii=False, separators=(",", ":")) for entry in entries]


def check_index(root: Path) -> list[Check]:
    index_path = root / "skills" / "INDEX.jsonl"
    skills_dir = root / "skills"
    if not index_path.exists():
        return [fail("skill_index", "skills/INDEX.jsonl is missing.")]
    if not skills_dir.exists():
        return [fail("skill_index", "skills/ directory is missing.")]

    try:
        entries = load_jsonl(index_path)
    except ValueError as exc:
        return [fail("skill_index", "skills/INDEX.jsonl is invalid.", error=str(exc))]

    counts_by_category: Counter[str] = Counter()
    counts_by_tier: Counter[str] = Counter()
    missing_metainfo: list[str] = []
    missing_disk_paths: list[str] = []
    for entry in entries:
        name = str(entry.get("name") or "<unnamed>")
        path = entry.get("path")
        if not path or not (root / str(path)).exists():
            missing_disk_paths.append(name)
        metainfo = entry.get("metainfo") or {}
        if not metainfo or metainfo.get("tier") == "unknown":
            missing_metainfo.append(name)
            continue
        counts_by_tier[str(metainfo.get("tier", "unknown"))] += 1
        for category in metainfo.get("category") or []:
            counts_by_category[str(category)] += 1

    checks: list[Check] = []
    if entries and not missing_metainfo and not missing_disk_paths:
        checks.append(
            ok(
                "skill_index",
                "Skill index is valid.",
                skills=len(entries),
                categories=dict(sorted(counts_by_category.items())),
                tiers=dict(sorted(counts_by_tier.items())),
            )
        )
    else:
        checks.append(
            fail(
                "skill_index",
                "Skill index has structural problems.",
                skills=len(entries),
                missing_metainfo=missing_metainfo,
                missing_disk_paths=missing_disk_paths,
            )
        )

    try:
        generated = build_index(skills_dir)
    except SystemExit as exc:
        checks.append(fail("index_freshness", "Could not rebuild skill index.", error=str(exc)))
        return checks

    current_lines = [line for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    generated_lines = canonical_jsonl(generated)
    if current_lines == generated_lines:
        checks.append(ok("index_freshness", "skills/INDEX.jsonl matches generated output."))
    else:
        checks.append(fail("index_freshness", "skills/INDEX.jsonl is stale. Run: python3 scripts/build_index.py"))
    return checks


def check_local_runtime_dirs(root: Path) -> Check:
    present = [path for path in LOCAL_RUNTIME_DIRS if (root / path).exists()]
    if present:
        return warn(
            "local_runtime_dirs",
            "Local runtime install directories are present in the checkout.",
            present=present,
        )
    return ok("local_runtime_dirs", "No local runtime install directories detected.")


def check_pyproject(root: Path) -> Check:
    path = root / "pyproject.toml"
    if not path.exists():
        return warn("python_metadata", "pyproject.toml is missing.")
    text = path.read_text(encoding="utf-8")
    if "dependencies = []" not in text:
        return warn(
            "python_metadata",
            "pyproject.toml does not explicitly declare an empty dependency list.",
        )
    return ok("python_metadata", "Python project metadata is present and declares no runtime dependencies.")


def run_doctor(root: Path) -> dict[str, Any]:
    resolved = root.expanduser().resolve()
    checks: list[Check] = [
        check_required_paths(resolved),
        check_git(resolved),
        *check_index(resolved),
        check_local_runtime_dirs(resolved),
        check_pyproject(resolved),
    ]
    counts = Counter(check.status for check in checks)
    return {
        "root": str(resolved),
        "summary": {
            "ok": counts.get("ok", 0),
            "warn": counts.get("warn", 0),
            "fail": counts.get("fail", 0),
            "passed": counts.get("fail", 0) == 0,
        },
        "checks": [asdict(check) for check in checks],
    }


def print_text(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"Doctor report: {report['root']}")
    print(f"Summary: {summary['ok']} ok, {summary['warn']} warn, {summary['fail']} fail")
    print("")
    labels = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}
    for check in report["checks"]:
        print(f"[{labels[check['status']]}] {check['name']}: {check['message']}")
        for key, value in sorted(check["details"].items()):
            if value not in (None, "", [], {}):
                print(f"  {key}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a quick Skill Governance Toolkit health check.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Project root to inspect.")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    args = parser.parse_args()

    report = run_doctor(args.root)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report)
    return 0 if report["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
