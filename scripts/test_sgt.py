#!/usr/bin/env python3
"""Behavior tests for the sgt command facade."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


class SgtBehaviorTests(unittest.TestCase):
    def run_sgt(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "sgt.py"), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_doctor_subcommand_outputs_json(self) -> None:
        result = self.run_sgt("doctor", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertIn("summary", report)
        self.assertTrue(report["summary"]["passed"])

    def test_quickstart_subcommand_outputs_json(self) -> None:
        result = self.run_sgt("quickstart", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertIn("decision_tree", report)
        self.assertGreaterEqual(len(report["decision_tree"]), 6)

    def test_skills_subcommand_lists_indexed_skills(self) -> None:
        result = self.run_sgt("skills", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        names = {skill["name"] for skill in report["skills"]}
        self.assertIn("skill-find", names)
        self.assertIn("library-audit", names)

    def test_skills_subcommand_fails_without_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sgt("--root", tmp, "skills", "--format", "json")
            self.assertEqual(result.returncode, 1)
            self.assertIn("INDEX.jsonl not found", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
