#!/usr/bin/env python3
"""Behavior tests for install-pre-commit-hook.sh — a script that writes/overwrites
a commit-blocking git hook. Untested before: hook creation + executability,
marker presence, backup of a pre-existing foreign hook, --check writing nothing,
uninstall scoping, and the not-a-git-repo guard."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install-pre-commit-hook.sh"
MARKER = "skill-init: CRG freshness check"


class PreCommitHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.hook = self.repo / ".git" / "hooks" / "pre-commit"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=str(self.repo), text=True, capture_output=True, check=False,
        )

    def test_install_creates_executable_hook_with_marker(self) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.hook.exists(), "hook not created")
        self.assertIn(MARKER, self.hook.read_text(encoding="utf-8"))
        self.assertTrue(os.stat(self.hook).st_mode & stat.S_IXUSR, "hook is not executable")

    def test_check_mode_writes_nothing(self) -> None:
        result = self._run("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.hook.exists(), "--check must not create the hook")

    def test_existing_foreign_hook_is_backed_up_not_lost(self) -> None:
        self.hook.parent.mkdir(parents=True, exist_ok=True)
        self.hook.write_text("#!/bin/sh\necho my own hook\n", encoding="utf-8")
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        backups = list(self.hook.parent.glob("pre-commit.bak.*"))
        self.assertTrue(backups, "pre-existing foreign hook was not backed up")
        self.assertIn("my own hook", backups[0].read_text(encoding="utf-8"))
        self.assertIn(MARKER, self.hook.read_text(encoding="utf-8"))

    def test_uninstall_removes_our_hook(self) -> None:
        self._run()
        self.assertTrue(self.hook.exists())
        result = self._run("--uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.hook.exists(), "uninstall did not remove our hook")

    def test_uninstall_leaves_foreign_hook_untouched(self) -> None:
        self.hook.parent.mkdir(parents=True, exist_ok=True)
        self.hook.write_text("#!/bin/sh\necho foreign\n", encoding="utf-8")
        result = self._run("--uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.hook.exists(), "uninstall wrongly removed a foreign hook")
        self.assertIn("foreign", self.hook.read_text(encoding="utf-8"))

    def test_not_a_git_repo_fails(self) -> None:
        with tempfile.TemporaryDirectory() as plain:
            result = subprocess.run(
                ["bash", str(SCRIPT)], cwd=plain, text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Not a git repository", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
