#!/usr/bin/env python3
"""Behavior tests for init.sh — the bash fallback for integration-init. It can
mutate AGENTS.md (removing deselected-tool marker blocks), so the safety
guarantees (dry-run / advise-only are no-ops) and the removal path need coverage.
Previously only `bash -n` (P1) + an argv-grep (P5) ran against it."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "scripts" / "init.sh"

AGENTS_WITH_CRG_BLOCK = """# AGENTS.md

<!-- skill-init: integrations BEGIN -->

<!-- skill-init: integration:crg BEGIN -->
CRG documentation block.
<!-- skill-init: integration:crg END -->

<!-- skill-init: integrations END -->

## Body
User content stays.
"""


class InitShTests(unittest.TestCase):
    def _skeleton(self, agents: str = AGENTS_WITH_CRG_BLOCK) -> Path:
        """A minimal REPO_ROOT skeleton: scripts/init.sh + AGENTS.md + agents/."""
        repo = Path(tempfile.mkdtemp())
        (repo / "scripts").mkdir()
        shutil.copy(INIT, repo / "scripts" / "init.sh")
        (repo / "AGENTS.md").write_text(agents, encoding="utf-8")
        (repo / "agents").mkdir()
        (repo / "agents" / "code-reviewer.md").write_text("# reviewer\n", encoding="utf-8")
        return repo

    def _run(self, repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(repo / "scripts" / "init.sh"), *args],
            cwd=str(repo), text=True, capture_output=True, check=False, env=env,
        )

    def test_dry_run_mutates_nothing(self) -> None:
        repo = self._skeleton()
        before = (repo / "AGENTS.md").read_text(encoding="utf-8")
        result = self._run(repo, "--dry-run", "--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DRY-RUN", result.stdout)
        self.assertEqual((repo / "AGENTS.md").read_text(encoding="utf-8"), before,
                         "dry-run must not modify AGENTS.md")

    def test_advise_only_mutates_nothing(self) -> None:
        repo = self._skeleton()
        before = (repo / "AGENTS.md").read_text(encoding="utf-8")
        result = self._run(repo, "--advise-only", "--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((repo / "AGENTS.md").read_text(encoding="utf-8"), before,
                         "advise-only must not modify AGENTS.md")

    def test_invalid_tool_fails_fast(self) -> None:
        repo = self._skeleton()
        result = self._run(repo, "--with", "bogus-tool")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_removes_deselected_tool_block(self) -> None:
        # In a real run, marker blocks for tools NOT installed are removed. With
        # no installer (pipx/npm/uvx) on PATH every tool fails its preflight and is
        # treated as deselected, so the crg block is cleaned out — user content and
        # the outer markers are preserved. Skips where installers exist (the real
        # install would attempt network work).
        if any(shutil.which(t) for t in ("pipx", "npm", "uvx")):
            self.skipTest("an integration installer is on PATH; removal path would attempt a real install")
        repo = self._skeleton()
        result = self._run(repo, "--with", "crg")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("integration:crg BEGIN", agents, "deselected crg block not removed")
        self.assertIn("integrations BEGIN", agents, "outer marker must be preserved")
        self.assertIn("User content stays.", agents, "user content must be preserved")


if __name__ == "__main__":
    unittest.main(verbosity=2)
