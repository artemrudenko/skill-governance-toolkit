#!/usr/bin/env python3
"""Behavior tests for init.sh — the bash fallback for integration-init. It can
mutate AGENTS.md (removing deselected-tool marker blocks), so the safety
guarantees (dry-run / advise-only are no-ops) and the removal path need coverage.
Previously only `bash -n` (P1) + an argv-grep (P5) ran against it."""

from __future__ import annotations

import os
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

# code-reviewer.md uses the `handoff:{tool}` inner-marker family (NOT
# `integration:{tool}` like AGENTS.md). Deselection cleanup must remove this too.
CODE_REVIEWER_WITH_HANDOFF = """# reviewer

<!-- skill-init: handoffs BEGIN -->
<!-- skill-init: handoff:crg BEGIN -->
crg handoff stanza.
<!-- skill-init: handoff:crg END -->
<!-- skill-init: handoffs END -->

Reviewer body stays.
"""


class InitShTests(unittest.TestCase):
    def _skeleton(self, agents: str = AGENTS_WITH_CRG_BLOCK) -> Path:
        """A minimal REPO_ROOT skeleton: scripts/init.sh + AGENTS.md + agents/."""
        repo = Path(tempfile.mkdtemp())
        (repo / "scripts").mkdir()
        shutil.copy(INIT, repo / "scripts" / "init.sh")
        (repo / "AGENTS.md").write_text(agents, encoding="utf-8")
        (repo / "agents").mkdir()
        (repo / "agents" / "code-reviewer.md").write_text(CODE_REVIEWER_WITH_HANDOFF, encoding="utf-8")
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

    def test_advise_only_lists_all_integrations_without_prereqs(self) -> None:
        # --advise-only must print the full plan for EVERY selected integration
        # even when its prerequisite (pipx/npm) is absent: the prereq guard must
        # be advise/dry-aware (as install_crg already is), else repomix/serena are
        # silently dropped from the plan. Force pipx/npm absent via a minimal PATH.
        repo = self._skeleton()
        bindir = repo / "_minbin"
        bindir.mkdir()
        for tool in ("bash", "env", "cat", "head", "tr", "dirname", "basename",
                     "python3", "sed", "grep", "mkdir", "rm", "mktemp", "sort", "printf"):
            src = shutil.which(tool)
            if src:
                os.symlink(src, bindir / tool)
        # Guard the guard: pipx/npm must be unreachable under this PATH.
        self.assertIsNone(shutil.which("pipx", path=str(bindir)))
        self.assertIsNone(shutil.which("npm", path=str(bindir)))
        env = dict(os.environ)
        env["PATH"] = str(bindir)
        result = self._run(repo, "--advise-only", "--all", env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = result.stdout
        self.assertIn("[would run] npm install -g repomix@", out)
        self.assertIn("[would run] pipx install serena-agent==", out)

    def test_integration_installs_are_version_pinned(self) -> None:
        # Supply-chain pin: the default (non-fork) path must never install a
        # floating `latest` from PyPI/npm — every install command carries an
        # explicit version (env-overridable via SGT_*_VERSION).
        repo = self._skeleton()
        result = self._run(repo, "--advise-only", "--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = result.stdout
        self.assertNotIn("[would run] pipx install code-review-graph\n", out)
        self.assertNotIn("[would run] npm install -g repomix\n", out)
        self.assertIn("pipx install code-review-graph==", out)
        self.assertIn("npm install -g repomix@", out)
        self.assertIn("pipx install serena-agent==", out)
        # `serena-mcp` does not exist on PyPI — the old command 404'd.
        self.assertNotIn("serena-mcp", out)

    def test_version_pins_are_env_overridable(self) -> None:
        repo = self._skeleton()
        env = dict(os.environ, SGT_CRG_VERSION="9.9.9", SGT_REPOMIX_VERSION="8.8.8",
                   SGT_SERENA_VERSION="7.7.7")
        result = self._run(repo, "--advise-only", "--all", env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = result.stdout
        self.assertIn("code-review-graph==9.9.9", out)
        self.assertIn("repomix@8.8.8", out)
        self.assertIn("serena-agent==7.7.7", out)

    def test_invalid_tool_fails_fast(self) -> None:
        repo = self._skeleton()
        result = self._run(repo, "--with", "bogus-tool")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_removes_deselected_tool_block(self) -> None:
        # Marker blocks for tools NOT installed are removed. We force the
        # deselection path deterministically with a minimal PATH that lacks every
        # installer (pipx/npm/uvx), so crg fails its preflight and is treated as
        # deselected — its blocks are cleaned out of BOTH files while user content
        # and the outer markers are preserved. AGENTS.md uses integration:{tool};
        # code-reviewer.md uses handoff:{tool} — both families must be removed.
        repo = self._skeleton()
        bindir = repo / "_minbin"
        bindir.mkdir()
        for tool in ("bash", "env", "cat", "head", "tr", "dirname", "basename",
                     "python3", "sed", "grep", "mkdir", "rm", "mktemp", "sort", "printf"):
            src = shutil.which(tool)
            if src:
                os.symlink(src, bindir / tool)
        for installer in ("pipx", "npm", "uvx"):
            self.assertIsNone(shutil.which(installer, path=str(bindir)))
        env = dict(os.environ)
        env["PATH"] = str(bindir)
        result = self._run(repo, "--with", "crg", env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("integration:crg BEGIN", agents, "deselected crg block not removed")
        self.assertIn("integrations BEGIN", agents, "outer marker must be preserved")
        self.assertIn("User content stays.", agents, "user content must be preserved")
        # code-reviewer.md uses the handoff:{tool} family — its block must also go.
        reviewer = (repo / "agents" / "code-reviewer.md").read_text(encoding="utf-8")
        self.assertNotIn("handoff:crg BEGIN", reviewer, "deselected crg handoff block not removed from code-reviewer.md")
        self.assertIn("handoffs BEGIN", reviewer, "outer handoffs marker must be preserved")
        self.assertIn("Reviewer body stays.", reviewer, "reviewer user content must be preserved")


if __name__ == "__main__":
    unittest.main(verbosity=2)
