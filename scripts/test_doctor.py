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
            result = self.run_doctor("--root", tmp, "--mode", "checkout", "--format", "json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertFalse(report["summary"]["passed"])
            failures = [check for check in report["checks"] if check["status"] == "fail"]
            self.assertTrue(any(check["name"] == "required_paths" for check in failures))

    def _write_consumer_project(self, root: Path) -> None:
        """A project as an `install --project` would leave it: managed AGENTS.md
        block + a filtered skills/ + INDEX.jsonl, and NO toolkit-checkout files
        (no scripts/audit.sh, no pyproject.toml)."""
        (root / "AGENTS.md").write_text(
            "# My project\n\n<!-- skill-governance-toolkit: BEGIN -->\nrules\n<!-- skill-governance-toolkit: END -->\n",
            encoding="utf-8",
        )
        skill_dir = root / "skills" / "example"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: example\ndescription: Example.\nmetainfo:\n  category: [governance]\n  tier: stable\n---\nBody.\n",
            encoding="utf-8",
        )
        (root / "skills" / "INDEX.jsonl").write_text(
            '{"name":"example","path":"skills/example/SKILL.md","metainfo":{"category":["governance"],"tier":"stable"}}\n',
            encoding="utf-8",
        )

    def test_consumer_project_passes_without_checkout_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_consumer_project(root)
            result = self.run_doctor("--root", tmp, "--format", "json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["mode"], "consumer")
            self.assertTrue(report["summary"]["passed"])
            names = {c["name"] for c in report["checks"]}
            # Consumer mode checks delivered artifacts, never checkout-only files.
            self.assertNotIn("required_paths", names)
            self.assertIn("installed_skills", names)
            self.assertIn("agents_md", names)

    def test_explicit_checkout_mode_still_flags_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_consumer_project(root)
            result = self.run_doctor("--root", tmp, "--mode", "checkout", "--format", "json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertEqual(report["mode"], "checkout")
            failures = {c["name"] for c in report["checks"] if c["status"] == "fail"}
            self.assertIn("required_paths", failures)

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

            result = self.run_doctor("--root", tmp, "--mode", "checkout", "--format", "json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            freshness = next(check for check in report["checks"] if check["name"] == "index_freshness")
            self.assertEqual(freshness["status"], "fail")
            self.assertIn("build_index.py", freshness["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
