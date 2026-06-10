#!/usr/bin/env python3
"""
extract_release_notes.py — emit GitLab Release notes from CHANGELOG.md.

Single-source discipline: CHANGELOG.md is the only authored release record;
the release job in the toolkit's own .gitlab-ci.yml derives the per-tag
GitLab Release body from it. A hand-maintained notes file would drift
(the P35 phase-range check exists because exactly that kind of prose drift
recurred across releases).

The notes are the verbatim `## [X.Y.Z]` CHANGELOG section prefixed with a
gate-impact line answering the one question a consumer asks before bumping
`SGT_REF`: «will MRs that passed yesterday block today?» CHANGELOG's header
defines that any rule severity escalation or floor addition MUST carry the
«🔴 BREAKING» marker — so the marker is the single derivation signal.

Usage:
  python3 scripts/extract_release_notes.py                    # version from VERSION
  python3 scripts/extract_release_notes.py --version 1.20.0
  python3 scripts/extract_release_notes.py --output notes.md

Dev/release tooling — never ships into installs (not in runtime-manifest.txt).
Stdlib only. Python 3.8+.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Repo root derived from this file's location (scripts/..), not CWD — the
# release CI job and audit.sh may invoke this from any directory.
REPO_ROOT = Path(__file__).resolve().parents[1]

BREAKING_MARKER = "🔴 BREAKING"

IMPACT_BREAKING = (
    "**Gate impact: 🔴 BREAKING** — previously-passing MRs may start blocking "
    "after bumping `SGT_REF` to this release. Read the Upgrade notes below "
    "before bumping."
)
IMPACT_NONE = (
    "**Gate impact: none declared** — no 🔴 BREAKING marker in this section; "
    "MRs that passed on the previous pin keep passing."
)


def extract_section(changelog: str, version: str) -> str | None:
    """Return the `## [version]` section (heading included), else None.

    The section runs until the next `## [` heading or EOF; the inter-release
    `---` separator is not part of the notes.
    """
    pattern = re.compile(
        rf"^(## \[{re.escape(version)}\][^\n]*\n.*?)(?=^## \[|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    m = pattern.search(changelog)
    if not m:
        return None
    lines = m.group(1).rstrip().splitlines()
    while lines and lines[-1].strip() in ("", "---"):
        lines.pop()
    return "\n".join(lines) + "\n"


def gate_impact_line(section: str) -> str:
    return IMPACT_BREAKING if BREAKING_MARKER in section else IMPACT_NONE


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit GitLab Release notes for one version from CHANGELOG.md."
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Release version (X.Y.Z). Default: contents of the VERSION file.",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        default=REPO_ROOT / "CHANGELOG.md",
        help="Path to CHANGELOG.md (default: the repo containing this script).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write notes to this file instead of stdout.",
    )
    args = parser.parse_args()

    version = args.version or (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    try:
        changelog = args.changelog.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read {args.changelog}: {exc}", file=sys.stderr)
        return 1

    section = extract_section(changelog, version)
    if section is None:
        print(f"CHANGELOG.md has no '## [{version}]' section — release notes "
              "cannot be derived. Add the release heading first.", file=sys.stderr)
        return 1

    notes = gate_impact_line(section) + "\n\n" + section
    if args.output:
        args.output.write_text(notes, encoding="utf-8")
    else:
        sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
