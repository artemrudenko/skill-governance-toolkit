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


class ConsumerTransformTests(unittest.TestCase):
    """The installed AGENTS.md must describe the CONSUMER's repo, not the
    toolkit's own. Found in pre-ship review of 1.19.0: the canonical file was
    injected verbatim, so every agent turn in a consumer project read «This
    repository is a skill-governance toolkit» and a `bash scripts/audit.sh`
    self-CI command that is deliberately excluded from installs."""

    ALL_SKILLS = (
        "skill-find,skill-evaluate,skill-compare,library-audit,"
        "skill-build-portable,integration-init"
    )

    def _generate(self, skills: str) -> str:
        result = subprocess.run(
            [PYTHON, str(SCRIPT), str(ROOT / "AGENTS.md"), skills],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_no_toolkit_repo_prose_in_consumer_copy(self) -> None:
        out = self._generate(self.ALL_SKILLS)
        for toolkit_speak in (
            "This repository is a **skill-governance toolkit**",
            "scripts/audit.sh",          # self-CI never ships into installs
            "Self-CI for the toolkit",
            "## Stack & Architecture",
            "# AGENTS.md — Skill Governance Toolkit",
        ):
            self.assertNotIn(toolkit_speak, out,
                             f"consumer AGENTS.md still carries toolkit-repo prose: {toolkit_speak!r}")

    def test_consumer_copy_keeps_governance_sections(self) -> None:
        out = self._generate(self.ALL_SKILLS)
        for kept in (
            "## Conventions & Boundaries",
            "### Script & reference path resolution",
            "## Writing Style",
            "## Tool-Name Translation Across Platforms",
            "## Optional integrations",
            "| `skill-find` |",
            "STRICTNESS=permissive",      # first-audit guidance for adopters
        ):
            self.assertIn(kept, out, f"consumer AGENTS.md lost a governance section: {kept!r}")

    def test_full_install_has_no_scoped_notice(self) -> None:
        out = self._generate(self.ALL_SKILLS)
        self.assertNotIn("Scoped install notice", out,
                         "full install must not claim to be a subset")

    def test_subset_install_combines_transform_and_notice(self) -> None:
        out = self._generate("skill-find")
        self.assertIn("Scoped install notice", out)
        self.assertNotIn("| `library-audit` |", out)
        self.assertNotIn("This repository is a **skill-governance toolkit**", out)

    def test_non_toolkit_source_passes_through_verbatim(self) -> None:
        """Anchor guard: a source without the toolkit H1 gets row filtering
        only — no consumer rewrites of user content."""
        src = Path(tempfile.mkdtemp()) / "AGENTS.md"
        src.write_text(SOURCE, encoding="utf-8")
        result = subprocess.run(
            [PYTHON, str(SCRIPT), str(src), "skill-find,library-audit,skill-evaluate"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.rstrip("\n"), SOURCE.rstrip("\n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
