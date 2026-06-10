#!/usr/bin/env python3
"""Behavior tests for extract_release_notes.py — the GitLab Release body is
derived from CHANGELOG.md by the release CI job; a silent extraction regression
would publish empty or wrong-version release notes on the next tag."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
SCRIPT = ROOT / "scripts" / "extract_release_notes.py"

FIXTURE = """# Changelog

Header prose. Breaking changes are marked 🔴 BREAKING.

---

## [2.0.0] — 2026-01-02 — newest

### Changed
- 🔴 BREAKING: REF002 escalated to floor.

---

## [1.9.0] — 2026-01-01 — older

### Added
- harmless feature.

---

## [1.8.0] — 2025-12-31 — oldest

### Fixed
- a bug.
"""


class ExtractReleaseNotesTests(unittest.TestCase):
    def _run(self, *args: str, changelog: str | None = None) -> subprocess.CompletedProcess[str]:
        cmd = [PYTHON, str(SCRIPT), *args]
        if changelog is not None:
            path = Path(tempfile.mkdtemp()) / "CHANGELOG.md"
            path.write_text(changelog, encoding="utf-8")
            cmd += ["--changelog", str(path)]
        return subprocess.run(cmd, text=True, capture_output=True, check=False)

    def test_extracts_only_the_requested_section(self) -> None:
        result = self._run("--version", "1.9.0", changelog=FIXTURE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## [1.9.0]", result.stdout)
        self.assertIn("harmless feature", result.stdout)
        for other in ("## [2.0.0]", "## [1.8.0]", "REF002", "a bug"):
            self.assertNotIn(other, result.stdout)

    def test_section_excludes_trailing_separator(self) -> None:
        out = self._run("--version", "1.9.0", changelog=FIXTURE).stdout
        self.assertFalse(out.rstrip().endswith("---"),
                         "inter-release '---' separator leaked into the notes")

    def test_breaking_marker_yields_blocking_impact_line(self) -> None:
        out = self._run("--version", "2.0.0", changelog=FIXTURE).stdout
        self.assertIn("Gate impact: 🔴 BREAKING", out)
        self.assertIn("SGT_REF", out)

    def test_no_marker_yields_none_declared_impact_line(self) -> None:
        out = self._run("--version", "1.9.0", changelog=FIXTURE).stdout
        self.assertIn("Gate impact: none declared", out)

    def test_header_prose_marker_does_not_taint_other_sections(self) -> None:
        # The CHANGELOG header explains the 🔴 BREAKING convention — that prose
        # must not make a harmless release read as breaking.
        out = self._run("--version", "1.8.0", changelog=FIXTURE).stdout
        self.assertIn("Gate impact: none declared", out)

    def test_missing_version_fails_with_actionable_error(self) -> None:
        result = self._run("--version", "3.3.3", changelog=FIXTURE)
        self.assertEqual(result.returncode, 1)
        self.assertIn("3.3.3", result.stderr)

    def test_last_section_at_eof_is_extracted(self) -> None:
        result = self._run("--version", "1.8.0", changelog=FIXTURE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("a bug", result.stdout)

    def test_output_flag_writes_file(self) -> None:
        out_path = Path(tempfile.mkdtemp()) / "notes.md"
        result = self._run("--version", "1.9.0", "--output", str(out_path), changelog=FIXTURE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## [1.9.0]", out_path.read_text(encoding="utf-8"))

    def test_current_repo_version_extracts_nonempty_notes(self) -> None:
        """The release job runs with no --version/--changelog flags — the
        REAL repo state must always yield non-empty notes (P37 contract)."""
        result = subprocess.run([PYTHON, str(SCRIPT)], text=True,
                                capture_output=True, check=False, cwd="/")
        self.assertEqual(result.returncode, 0, result.stderr)
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertIn(f"## [{version}]", result.stdout)
        self.assertIn("Gate impact:", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
