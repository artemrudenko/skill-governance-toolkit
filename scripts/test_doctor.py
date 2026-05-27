#!/usr/bin/env python3
"""Behavior tests for the doctor health-check command."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


class DoctorBehaviorTests(unittest.TestCase):
    def run_doctor(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "doctor.py"), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_current_project_passes_in_json_mode(self) -> None:
        result = self.run_doctor("--format", "json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["summary"]["passed"])
        self.assertEqual(report["summary"]["fail"], 0)
        check_names = {check["name"] for check in report["checks"]}
        self.assertIn("index_freshness", check_names)
        self.assertIn("python_metadata", check_names)

    def test_missing_required_files_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_doctor("--root", tmp, "--format", "json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertFalse(report["summary"]["passed"])
            failures = [check for check in report["checks"] if check["status"] == "fail"]
            self.assertTrue(any(check["name"] == "required_paths" for check in failures))

    def test_stale_index_fails_with_actionable_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills" / "example").mkdir(parents=True)
            (root / "skills" / "example" / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: example",
                        "description: Example skill for doctor tests.",
                        "compatibility: all",
                        "license: MIT",
                        "metainfo:",
                        "  category: [governance]",
                        "  tier: stable",
                        "---",
                        "Do the thing.",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "skills" / "INDEX.jsonl").write_text(
                '{"name":"wrong","path":"skills/missing/SKILL.md","metainfo":{"category":["governance"],"tier":"stable"}}\n',
                encoding="utf-8",
            )
            for path in [
                "AGENTS.md",
                "README.md",
                "CHANGELOG.md",
                "LICENSE",
                "scripts/audit.sh",
                "scripts/install.sh",
                "scripts/agent_audit.py",
            ]:
                full = root / path
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text("placeholder\n", encoding="utf-8")

            result = self.run_doctor("--root", tmp, "--format", "json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            freshness = next(check for check in report["checks"] if check["name"] == "index_freshness")
            self.assertEqual(freshness["status"], "fail")
            self.assertIn("build_index.py", freshness["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
