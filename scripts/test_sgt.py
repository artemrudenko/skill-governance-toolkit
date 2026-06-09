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


class UninstallTests(unittest.TestCase):
    def run_sgt(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "sgt.py"), *args],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def _install(self, target: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(ROOT / "scripts" / "install.sh"), "--claude", "--project",
             f"--target-project={target}"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def _seed_user_content(self, target: Path) -> None:
        (target / "AGENTS.md").write_text("# My project rules\nKEEP THIS LINE\n", encoding="utf-8")
        (target / "references").mkdir(parents=True, exist_ok=True)
        (target / "references" / "my-note.md").write_text("USER NOTE", encoding="utf-8")
        (target / "skills" / "my-own-skill").mkdir(parents=True, exist_ok=True)
        (target / "skills" / "my-own-skill" / "SKILL.md").write_text("USER SKILL", encoding="utf-8")

    def test_uninstall_removes_toolkit_keeps_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._seed_user_content(target)
            self.assertEqual(self._install(target).returncode, 0)
            # Sanity: toolkit content landed.
            self.assertTrue((target / "skills" / "skill-find").exists())
            self.assertTrue((target / "references" / "copilot-tools.md").exists())
            self.assertIn("skill-governance-toolkit: BEGIN",
                          (target / "AGENTS.md").read_text(encoding="utf-8"))

            result = self.run_sgt("uninstall", "--scope", "project",
                                  "--target-project", str(target), "--yes")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            # Toolkit content gone.
            self.assertFalse((target / "skills" / "skill-find").exists(), "toolkit skill not removed")
            self.assertFalse((target / "references" / "copilot-tools.md").exists(),
                             "toolkit reference not removed")
            # User content preserved.
            self.assertTrue((target / "skills" / "my-own-skill" / "SKILL.md").exists(),
                            "user skill deleted by uninstall")
            self.assertTrue((target / "references" / "my-note.md").exists(),
                            "user reference deleted by uninstall")
            agents_md = (target / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("KEEP THIS LINE", agents_md, "user content lost from AGENTS.md")
            self.assertNotIn("skill-governance-toolkit: BEGIN", agents_md, "marker block not removed")

    def test_dry_run_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._seed_user_content(target)
            self.assertEqual(self._install(target).returncode, 0)
            before = sorted(p.name for p in (target / "skills").iterdir())

            result = self.run_sgt("uninstall", "--scope", "project",
                                  "--target-project", str(target), "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertRegex(result.stdout, r"(?i)dry.run|would remove")
            after = sorted(p.name for p in (target / "skills").iterdir())
            self.assertEqual(before, after, "dry-run modified the filesystem")
            self.assertTrue((target / "skills" / "skill-find").exists())


class InitTests(unittest.TestCase):
    def run_sgt(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "sgt.py"), *args],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def test_dry_run_prints_plan_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sgt("init", "--yes", "--dry-run", "--target-project", tmp)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Dry-run install plan", result.stdout)
            self.assertFalse((Path(tmp) / "skills").exists(), "dry-run wrote files")

    def test_init_installs_then_runs_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sgt("init", "--host", "claude", "--scope", "project",
                                  "--target-project", tmp, "--yes")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # One command produced a working install...
            self.assertTrue((Path(tmp) / "skills" / "skill-find").exists(),
                            "init did not install skills")
            # ...and ended with the doctor verification step.
            self.assertRegex(result.stdout, r"(?i)verifying install|doctor")


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

    def test_gitlab_pipeline_has_always_green_noop_job(self) -> None:
        # With "Pipelines must succeed" enabled, an MR touching no governed asset
        # produces no pipeline at all and blocks the merge forever. An
        # unconditional placeholder job (gated only on merge_request_event, with no
        # `changes:` filter) guarantees every MR has a passing pipeline.
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sgt("--root", tmp, "ci-init", "--gitlab")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            body = (Path(tmp) / ".gitlab-ci.yml").read_text(encoding="utf-8")
            self.assertIn("noop:", body)
            # Isolate just the noop job block: from "noop:" to the next top-level
            # (column-0) key. The noop job must NOT carry a changes: filter —
            # otherwise it would be skipped on the exact MRs it exists to cover.
            after = body.split("\nnoop:", 1)[1].splitlines()
            noop_lines: list[str] = []
            for line in after:
                if line and not line[0].isspace() and not line.startswith("#"):
                    break
                noop_lines.append(line)
            noop_block = "\n".join(noop_lines)
            self.assertIn("merge_request_event", noop_block)
            self.assertNotIn("changes:", noop_block)

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

    def test_scaffolds_control_plane_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sgt("--root", tmp, "ci-init", "--gitlab")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            ignore = Path(tmp) / "references" / "audit-ignore.json"
            codeowners = Path(tmp) / "CODEOWNERS"
            self.assertTrue(ignore.exists(), "audit-ignore.json not scaffolded")
            self.assertTrue(codeowners.exists(), "CODEOWNERS not scaffolded")
            self.assertIn("audit-ignore.json", codeowners.read_text(encoding="utf-8"))
            # Starter ignore file is an empty, valid suppression list.
            data = json.loads(ignore.read_text(encoding="utf-8"))
            self.assertEqual(data.get("ignores"), [])

    def test_does_not_clobber_existing_control_plane_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "references").mkdir(parents=True, exist_ok=True)
            ignore = Path(tmp) / "references" / "audit-ignore.json"
            ignore.write_text('{"version":"1.0","ignores":["KEEP"]}', encoding="utf-8")
            codeowners = Path(tmp) / "CODEOWNERS"
            codeowners.write_text("# my own owners\n", encoding="utf-8")
            result = self.run_sgt("--root", tmp, "ci-init", "--github", "--ref", "c" * 40)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # Neither pre-existing file is overwritten.
            self.assertIn("KEEP", ignore.read_text(encoding="utf-8"))
            self.assertEqual(codeowners.read_text(encoding="utf-8"), "# my own owners\n")


class GateTests(unittest.TestCase):
    def run_sgt(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "sgt.py"), *args],
            cwd=str(cwd or ROOT), text=True, capture_output=True, check=False,
        )

    def test_help_lists_base_and_check_setup(self) -> None:
        result = self.run_sgt("gate", "--help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--base", result.stdout)
        self.assertIn("--check-setup", result.stdout)

    def test_check_setup_fails_without_codeowners(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sgt("--root", tmp, "gate", "--check-setup")
            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertIn("CODEOWNERS", combined)
            self.assertIn("audit-ignore.json", combined)

    def test_check_setup_passes_when_wired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / "references").mkdir(parents=True, exist_ok=True)
            (target / "references" / "audit-ignore.json").write_text(
                '{"version":"1.0","ignores":[]}', encoding="utf-8")
            (target / "CODEOWNERS").write_text(
                "/references/audit-ignore.json   @sec\n", encoding="utf-8")
            result = self.run_sgt("--root", tmp, "gate", "--check-setup")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_setup_passes_on_toolkit_repo(self) -> None:
        # The toolkit itself is properly wired (has CODEOWNERS + audit-ignore.json).
        result = self.run_sgt("--root", str(ROOT), "gate", "--check-setup")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def _init_git_repo(self, root: Path) -> None:
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        run = lambda *a: subprocess.run(["git", "-C", str(root), *a],
                                        capture_output=True, text=True,
                                        env={**__import__("os").environ, **env})
        run("init", "-q")
        (root / "AGENTS.md").write_text("# clean\n", encoding="utf-8")
        run("add", "-A")
        run("commit", "-qm", "base")

    def test_gate_fails_fast_on_dirty_working_tree(self) -> None:
        # A local `sgt gate` audits committed HEAD only (base...HEAD). An
        # uncommitted change is invisible, so a dirty tree must fail-fast rather
        # than print a false green that the user reads as "safe to push".
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_git_repo(root)
            # Introduce an uncommitted edit.
            (root / "AGENTS.md").write_text("# dirty edit\n", encoding="utf-8")
            result = self.run_sgt("--root", str(root), "gate", "--base", "HEAD", cwd=root)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            combined = (result.stdout + result.stderr).lower()
            self.assertIn("uncommitted", combined)

    def test_gate_allow_dirty_bypasses_the_guard(self) -> None:
        # --allow-dirty is the documented escape hatch: it audits HEAD anyway.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_git_repo(root)
            (root / "AGENTS.md").write_text("# dirty edit\n", encoding="utf-8")
            result = self.run_sgt("--root", str(root), "gate", "--base", "HEAD",
                                  "--allow-dirty", cwd=root)
            # HEAD is clean of findings → gate passes (exit 0), guard skipped.
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
