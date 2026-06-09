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
        self.assertIn("python3 scripts/sgt.py doctor", commands)
        self.assertIn("python3 scripts/sgt.py quickstart", commands)
        self.assertIn("./install.sh --dry-run", commands)
        self.assertIn("python3 scripts/sgt.py audit", commands)

    def test_consumer_project_recommends_skill_use_not_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "# Proj\n\n<!-- skill-governance-toolkit: BEGIN -->\nx\n<!-- skill-governance-toolkit: END -->\n",
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
            result = self.run_quickstart("--root", tmp, "--format", "json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["mode"], "consumer")
            commands = {c["command"] for c in report["common_commands"]}
            # Consumer installs do not ship install.sh or the self-audit runner.
            self.assertNotIn("./install.sh", commands)
            self.assertNotIn("python3 scripts/sgt.py audit", commands)
            self.assertNotIn("install.sh", report["next_step"]["command"])

    def test_uninstalled_directory_routes_to_installer_not_fix_loop(self) -> None:
        # An empty dir is not a broken install — guide to the installer with an
        # absolute command that resolves from any CWD (not a relative path that
        # only exists inside a toolkit checkout).
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_quickstart("--root", tmp, "--format", "json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertGreater(report["doctor_summary"]["fail"], 0)
            self.assertIn("not installed", report["next_step"]["label"])
            command = report["next_step"]["command"]
            self.assertTrue(command.endswith("sgt.py init"), command)
            self.assertTrue(Path(command.split()[1]).is_absolute(), command)


if __name__ == "__main__":
    unittest.main(verbosity=2)
