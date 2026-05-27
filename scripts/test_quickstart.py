#!/usr/bin/env python3
"""Behavior tests for the quickstart command."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


class QuickstartBehaviorTests(unittest.TestCase):
    def run_quickstart(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "quickstart.py"), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_current_project_outputs_decision_tree(self) -> None:
        result = self.run_quickstart("--format", "json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        uses = {item["use"] for item in report["decision_tree"]}
        self.assertIn("skill-find", uses)
        self.assertIn("library-audit", uses)
        self.assertIn("integration-init", uses)
        commands = {item["command"] for item in report["common_commands"]}
        self.assertIn("python3 scripts/doctor.py", commands)
        self.assertIn("bash scripts/audit.sh", commands)

    def test_health_failures_make_doctor_the_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_quickstart("--root", tmp, "--format", "json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertGreater(report["doctor_summary"]["fail"], 0)
            self.assertEqual(report["next_step"]["command"], "python3 scripts/doctor.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)
