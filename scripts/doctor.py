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

# A checkout (the toolkit's own source tree) ships dev-only files that an
# install never delivers — `scripts/audit.sh` and `pyproject.toml` are the
# clearest signals. Their absence means we are in a *consumer* project, where
# the checkout health checks (required_paths, git cleanliness, index freshness
# vs the FULL corpus) would false-flag a perfectly healthy install.
CHECKOUT_MARKERS = ["scripts/audit.sh", "pyproject.toml"]
AGENTS_MARKER_BEGIN = "<!-- skill-governance-toolkit: BEGIN -->"


def detect_mode(root: Path) -> str:
    return "checkout" if all((root / m).exists() for m in CHECKOUT_MARKERS) else "consumer"


def looks_uninstalled(checks: list[dict[str, Any]]) -> bool:
    """A consumer-mode dir with neither the managed AGENTS.md block nor any
    installed skill was simply never set up here — not a broken install. Lets
    both `doctor` and `quickstart` give the same 'not installed' message instead
    of alarming 'broken' wording for a pristine directory."""
    failing = {c["name"] for c in checks if c["status"] == "fail"}
    return {"agents_md", "installed_skills"} <= failing


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


def check_index_structure(root: Path) -> Check:
    """The structural half of the index check: present, parseable, every entry
    has metainfo and resolves to a file on disk. No freshness comparison — a
    consumer install legitimately carries a *filtered* subset of the corpus."""
    index_path = root / "skills" / "INDEX.jsonl"
    skills_dir = root / "skills"
    if not index_path.exists():
        return fail("skill_index", "skills/INDEX.jsonl is missing.")
    if not skills_dir.exists():
        return fail("skill_index", "skills/ directory is missing.")

    try:
        entries = load_jsonl(index_path)
    except ValueError as exc:
        return fail("skill_index", "skills/INDEX.jsonl is invalid.", error=str(exc))

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
        categories = metainfo.get("category") or []
        if isinstance(categories, str):
            categories = [categories]  # scalar would be counted letter-by-letter
        for category in categories:
            counts_by_category[str(category)] += 1

    if entries and not missing_metainfo and not missing_disk_paths:
        return ok(
            "skill_index",
            "Skill index is valid.",
            skills=len(entries),
            categories=dict(sorted(counts_by_category.items())),
            tiers=dict(sorted(counts_by_tier.items())),
        )
    return fail(
        "skill_index",
        "Skill index has structural problems.",
        skills=len(entries),
        missing_metainfo=missing_metainfo,
        missing_disk_paths=missing_disk_paths,
    )


def check_index(root: Path) -> list[Check]:
    index_path = root / "skills" / "INDEX.jsonl"
    skills_dir = root / "skills"
    checks: list[Check] = [check_index_structure(root)]
    if checks[0].status == "fail" and not index_path.exists():
        return checks

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


def check_agents_md(root: Path) -> Check:
    """Consumer-mode: AGENTS.md carries the toolkit's managed marker block."""
    path = root / "AGENTS.md"
    if not path.exists():
        return fail("agents_md", "AGENTS.md is missing — re-run the installer to write the managed rules block.")
    text = path.read_text(encoding="utf-8", errors="ignore")
    if AGENTS_MARKER_BEGIN not in text:
        return warn("agents_md", "AGENTS.md present but the managed toolkit block marker is absent.")
    return ok("agents_md", "AGENTS.md carries the managed toolkit block.")


def check_installed_skills(root: Path) -> Check:
    """Consumer-mode: at least one installed skill directory with a SKILL.md."""
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return fail("installed_skills", "skills/ directory is missing — nothing was installed.")
    installed = sorted(p.name for p in skills_dir.iterdir() if p.is_dir() and (p / "SKILL.md").exists())
    if not installed:
        return fail("installed_skills", "No installed skills found under skills/.")
    return ok("installed_skills", "Installed skills present.", count=len(installed), skills=installed)


def check_python_runtime(_root: Path) -> Check:
    """Consumer-mode: the interpreter running the toolkit is recent enough."""
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 8):
        return warn("python_runtime", f"Python {major}.{minor} is older than the recommended 3.8+.")
    return ok("python_runtime", f"Python {major}.{minor} runtime is adequate.")


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


def run_doctor(root: Path, mode: str = "auto") -> dict[str, Any]:
    resolved = root.expanduser().resolve()
    if mode == "auto":
        mode = detect_mode(resolved)

    if mode == "consumer":
        # Only inspect artifacts the installer actually delivers. Checkout-only
        # checks (required_paths, git cleanliness, full-corpus index freshness,
        # pyproject) would false-flag a healthy install, so they are skipped.
        checks: list[Check] = [
            check_agents_md(resolved),
            check_installed_skills(resolved),
            check_index_structure(resolved),
            check_python_runtime(resolved),
        ]
    else:
        checks = [
            check_required_paths(resolved),
            check_git(resolved),
            *check_index(resolved),
            check_local_runtime_dirs(resolved),
            check_pyproject(resolved),
        ]
    counts = Counter(check.status for check in checks)
    check_dicts = [asdict(check) for check in checks]
    return {
        "root": str(resolved),
        "mode": mode,
        "installed": not (mode == "consumer" and looks_uninstalled(check_dicts)),
        "summary": {
            "ok": counts.get("ok", 0),
            "warn": counts.get("warn", 0),
            "fail": counts.get("fail", 0),
            "passed": counts.get("fail", 0) == 0,
        },
        "checks": check_dicts,
    }


def print_text(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"Doctor report: {report['root']}")
    print(f"Mode: {report.get('mode', 'checkout')}")
    if report.get("installed") is False:
        print("Status: toolkit is NOT installed in this directory — run the installer, "
              "or cd into the project where you installed it.")
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
    parser.add_argument(
        "--mode",
        choices=["auto", "checkout", "consumer"],
        default="auto",
        help="Health-check profile. 'auto' detects a toolkit checkout vs an installed consumer project.",
    )
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    args = parser.parse_args()

    report = run_doctor(args.root, mode=args.mode)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report)
    return 0 if report["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
