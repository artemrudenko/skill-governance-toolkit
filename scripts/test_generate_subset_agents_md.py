#!/usr/bin/env python3
"""Behavior tests for generate_subset_agents_md.py — the installer's subset-aware
AGENTS.md rewriter. Runs at install time under --category/--tier/--skill; an
untested regression here would silently ship a misleading skill table."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
SCRIPT = ROOT / "scripts" / "generate_subset_agents_md.py"

SOURCE = """# AGENTS.md

| Skill | What it does |
|---|---|
| `skill-find` | discover skills |
| `library-audit` | audit a library |
| `skill-evaluate` | score a skill |

---

## Body

Use `inline-code` here. A non-skill row | `x` | should survive.
"""


class SubsetGeneratorTests(unittest.TestCase):
    def _run(self, source: str, skills: str) -> subprocess.CompletedProcess[str]:
        src = Path(tempfile.mkdtemp()) / "AGENTS.md"
        src.write_text(source, encoding="utf-8")
        return subprocess.run(
            [PYTHON, str(SCRIPT), str(src), skills],
            text=True, capture_output=True, check=False,
        )

    def test_drops_uninstalled_skill_rows_keeps_installed(self) -> None:
        result = self._run(SOURCE, "skill-find")
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        self.assertIn("| `skill-find` |", out)
        self.assertNotIn("| `library-audit` |", out)
        self.assertNotIn("| `skill-evaluate` |", out)

    def test_inserts_scoped_notice_with_omitted_list(self) -> None:
        out = self._run(SOURCE, "skill-find").stdout
        self.assertIn("Scoped install notice", out)
        self.assertIn("1 skill(s) actually present", out)
        # Omitted rows are named so the reader knows what was trimmed.
        self.assertIn("`library-audit`", out)
        self.assertIn("`skill-evaluate`", out)

    def test_preserves_table_header_and_non_skill_rows(self) -> None:
        out = self._run(SOURCE, "skill-find").stdout
        self.assertIn("| Skill | What it does |", out)  # header preserved
        self.assertIn("Use `inline-code` here", out)     # body verbatim
        self.assertIn("| `x` |", out)                    # single-segment name survives

    def test_notice_lands_after_first_separator(self) -> None:
        out = self._run(SOURCE, "skill-find").stdout
        head, _, tail = out.partition("\n---\n")
        self.assertIn("# AGENTS.md", head)
        self.assertIn("Scoped install notice", tail)

    def test_degenerate_source_without_separator_prepends_notice(self) -> None:
        out = self._run("| `skill-find` | x |\n| `library-audit` | y |\n", "skill-find").stdout
        self.assertTrue(out.lstrip().startswith(">"), "notice should be prepended when no separator")
        self.assertNotIn("| `library-audit` |", out)

    def test_wrong_argument_count_errors(self) -> None:
        result = subprocess.run(
            [PYTHON, str(SCRIPT), "only-one-arg"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Usage", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
