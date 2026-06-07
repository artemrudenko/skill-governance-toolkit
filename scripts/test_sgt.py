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


class NewSkillTests(unittest.TestCase):
    def run_sgt(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "sgt.py"), *args],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def _audit_skill(self, skill_md: Path, fail_on: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "agent_audit.py"), "audit-skill",
             str(skill_md), "--fail-on", fail_on],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def test_scaffold_is_governance_clean_by_construction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sgt("--root", tmp, "new-skill", "thing-evaluate",
                                  "--category", "governance")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            skill_md = Path(tmp) / "skills" / "thing-evaluate" / "SKILL.md"
            self.assertTrue(skill_md.exists(), "SKILL.md not created")
            # The scaffold must pass the engine's own gate with no medium+ findings.
            audit = self._audit_skill(skill_md, "medium")
            self.assertEqual(audit.returncode, 0, audit.stdout + audit.stderr)
            body = skill_md.read_text(encoding="utf-8")
            self.assertIn("name: thing-evaluate", body)
            self.assertIn("tier: preview", body)               # new skills start at preview
            self.assertRegex(body, r"Skill type:\**\s*Detect-only")

    def test_rejects_non_vocab_action_verb(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sgt("--root", tmp, "new-skill", "thing-frobnicate",
                                  "--category", "governance")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("action verb", result.stderr.lower())

    def test_rejects_unknown_category(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sgt("--root", tmp, "new-skill", "thing-find",
                                  "--category", "made-up")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("category", result.stderr.lower())

    def test_refuses_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = self.run_sgt("--root", tmp, "new-skill", "thing-find", "--category", "discovery")
            self.assertEqual(first.returncode, 0, first.stderr)
            again = self.run_sgt("--root", tmp, "new-skill", "thing-find", "--category", "discovery")
            self.assertNotEqual(again.returncode, 0)
            forced = self.run_sgt("--root", tmp, "new-skill", "thing-find",
                                  "--category", "discovery", "--force")
            self.assertEqual(forced.returncode, 0, forced.stderr)


class CiInitTests(unittest.TestCase):
    def run_sgt(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "sgt.py"), *args],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def test_github_writes_workflow_with_explicit_ref(self) -> None:
        sha = "a" * 40
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sgt("--root", tmp, "ci-init", "--github", "--ref", sha)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            wf = Path(tmp) / ".github" / "workflows" / "skill-gate.yml"
            self.assertTrue(wf.exists(), "workflow not written")
            body = wf.read_text(encoding="utf-8")
            self.assertIn(sha, body)
            self.assertNotIn("REPLACE-WITH-40-CHAR-COMMIT-SHA", body)
            # Setup guidance must mention the token/branch-protection steps.
            self.assertRegex(result.stdout, r"(?i)branch protection|CODEOWNERS|secret")

    def test_default_ref_is_current_head_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sgt("--root", tmp, "ci-init", "--gitlab")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            wf = Path(tmp) / ".gitlab-ci.yml"
            self.assertTrue(wf.exists())
            body = wf.read_text(encoding="utf-8")
            self.assertNotIn("REPLACE-WITH-40-CHAR-COMMIT-SHA", body)
            self.assertRegex(body, r'SGT_REF:\s*"[0-9a-f]{40}"')

    def test_refuses_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = self.run_sgt("--root", tmp, "ci-init", "--github", "--ref", "b" * 40)
            self.assertEqual(first.returncode, 0, first.stderr)
            again = self.run_sgt("--root", tmp, "ci-init", "--github", "--ref", "b" * 40)
            self.assertNotEqual(again.returncode, 0)
            forced = self.run_sgt("--root", tmp, "ci-init", "--github", "--ref", "b" * 40, "--force")
            self.assertEqual(forced.returncode, 0, forced.stderr)

    def test_requires_exactly_one_platform(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            none = self.run_sgt("--root", tmp, "ci-init")
            self.assertNotEqual(none.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
