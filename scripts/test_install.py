#!/usr/bin/env python3
"""Behavior tests for installer safety affordances."""

from __future__ import annotations

import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallBehaviorTests(unittest.TestCase):
    def test_project_dry_run_prints_plan_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts" / "install.sh"),
                    "--claude",
                    "--project",
                    f"--target-project={target}",
                    "--dry-run",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Dry-run install plan", result.stdout)
            self.assertIn("No files will be written", result.stdout.replace("no files", "No files"))
            self.assertFalse((target / "AGENTS.md").exists())
            self.assertFalse((target / ".claude").exists())
            self.assertFalse((target / "skills").exists())

    def test_root_installer_forwards_dry_run_in_yes_default_mode(self) -> None:
        result = subprocess.run(
            ["bash", str(ROOT / "install.sh"), "--yes-default", "--dry-run"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Dry-run install plan", result.stdout)

    def test_powershell_installer_accepts_dry_run_when_available(self) -> None:
        if not shutil.which("pwsh"):
            self.skipTest("pwsh not installed")
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(ROOT / "install.ps1"), "-YesDefault", "-DryRun"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Dry-run install plan", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
