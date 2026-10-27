#!/usr/bin/env python3
"""Behavior tests for the sgt command facade."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sgt


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

    def test_check_distinguishes_absent_validator_and_policy(self) -> None:
        with patch("sgt.shutil.which", return_value=None):
            result = subprocess.run(
                [PYTHON, str(ROOT / "scripts" / "sgt.py"), "check", str(ROOT / "skills" / "skill-find"),
                 "--format", "json", "--require-standard"],
                env={**os.environ, "PATH": ""}, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertEqual(report["standard"]["status"], "not_checked")
        self.assertEqual(report["policy"]["summary"]["total"], 0)
        self.assertEqual(len(report["sha256"]), 64)

    def test_check_reports_validator_errors_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            validator = Path(tmp) / "skills-ref"
            validator.write_text("#!/bin/sh\necho unavailable >&2\nexit 2\n")
            validator.chmod(0o755)
            result = subprocess.run(
                [PYTHON, str(ROOT / "scripts" / "sgt.py"), "check", str(ROOT / "skills" / "skill-find"),
                 "--format", "json"], env={**os.environ, "PATH": tmp},
                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["standard"]["status"], "error")

    def test_check_explicit_scanner_missing_is_not_success(self) -> None:
        result = subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "sgt.py"), "check", str(ROOT / "skills" / "skill-find"),
             "--format", "json", "--cisco"], env={**os.environ, "PATH": ""},
            text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["cisco"]["status"], "error")

    def test_check_preserves_scanner_findings_without_changing_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scanner = Path(tmp) / "skill-scanner"
            scanner.write_text("#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo 'skill-scanner 2.3.2'; "
                               "else echo '{\"findings\":[{\"rule_id\":\"X\"}],\"findings_count\":1,"
                               "\"analyzers_used\":[\"static\"],\"scan_metadata\":{\"rule_contract\":{\"status\":\"passed\"},"
                               "\"cel\":{\"projection_incomplete\":0,\"errors\":[]}}}'; fi\n")
            scanner.chmod(0o755)
            result = subprocess.run(
                [PYTHON, str(ROOT / "scripts" / "sgt.py"), "check", str(ROOT / "skills" / "skill-find"),
                 "--format", "json", "--cisco"], env={**os.environ, "PATH": tmp},
                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["cisco"]["status"], "completed")
        self.assertEqual(report["cisco"]["report"]["findings"][0]["rule_id"], "X")
        self.assertEqual(report["policy"]["summary"]["total"], 0)

    def test_check_sarif_preserves_finding_location_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "SKILL.md"
            skill.write_text("---\nname: test\ndescription: test\n---\nRun rm -rf /\n")
            result = self.run_sgt("check", str(skill), "--format", "sarif")
            report = json.loads(result.stdout)
        self.assertEqual(report["version"], "2.1.0")
        run = report["runs"][0]
        dangerous = next(item for item in run["results"] if item["ruleId"] == "SKILL014")
        self.assertEqual(dangerous["level"], "error")
        self.assertEqual(dangerous["locations"][0]["physicalLocation"]["region"]["startLine"], 5)
        self.assertIn(run["properties"]["standard_status"], ("passed", "failed", "not_checked"))


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
            self.assertIn('sgt-tier: "preview"', body)       # new skills start at preview
            self.assertRegex(body, r"Skill type:\**\s*Detect-only")

    def test_rejects_non_vocab_action_verb(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sgt("--root", tmp, "new-skill", "thing-frobnicate",
                                  "--category", "governance")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("action verb", result.stderr.lower())

    def test_migrate_metadata_preview_apply_and_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "SKILL.md"
            original = ('---\nname: demo-find\ndescription: Example.\nmetainfo:\n'
                        '  category: [discovery, governance]\n  tier: preview\n  owner: team\n'
                        '  requires:\n    mcp: [github, serena]\n---\n\n# Keep body\n')
            skill.write_text(original)
            preview = self.run_sgt("migrate-metadata", str(skill))
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertIn('sgt-category: "discovery, governance"', preview.stdout)
            self.assertEqual(skill.read_text(), original)
            applied = self.run_sgt("migrate-metadata", str(skill), "--apply")
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual((skill.parent / "SKILL.md.sgt-backup").read_text(), original)
            self.assertIn('sgt-requires-mcp: "github, serena"', skill.read_text())
            self.assertTrue(skill.read_text().endswith("# Keep body\n"))

    def test_migration_refuses_unknown_fields_and_existing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "SKILL.md"
            for body in ('metainfo:\n  category: [discovery]\n  custom: value\n',
                         'metadata:\n  author: person\nmetainfo:\n  tier: preview\n'):
                original = '---\nname: demo\ndescription: example\n' + body + '---\nBody\n'
                skill.write_text(original)
                result = self.run_sgt("migrate-metadata", str(skill), "--apply")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(skill.read_text(), original)
                self.assertFalse((skill.parent / "SKILL.md.sgt-backup").exists())

    def test_migration_preserves_crlf_by_refusing_automatic_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "SKILL.md"
            original = b"---\r\nname: demo\r\ndescription: example\r\nmetainfo:\r\n  tier: preview\r\n---\r\n"
            skill.write_bytes(original)
            result = self.run_sgt("migrate-metadata", str(skill), "--apply")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(skill.read_bytes(), original)

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
        (target / "docs").mkdir(parents=True, exist_ok=True)
        (target / "docs" / "my-doc.md").write_text("USER DOC", encoding="utf-8")

    def test_uninstall_removes_toolkit_keeps_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self._seed_user_content(target)
            self.assertEqual(self._install(target).returncode, 0)
            # Sanity: toolkit content landed.
            self.assertTrue((target / "skills" / "skill-find").exists())
            self.assertTrue((target / "references" / "copilot-tools.md").exists())
            self.assertTrue((target / "docs" / "architecture.md").exists(), "toolkit doc not installed")
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
            # Toolkit-owned docs removed; user's own doc preserved.
            self.assertFalse((target / "docs" / "architecture.md").exists(),
                             "toolkit doc not removed by uninstall")
            self.assertTrue((target / "docs" / "my-doc.md").exists(),
                            "user doc deleted by uninstall")
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

    def test_gitlab_repo_substitution_keeps_job_token_clone_auth(self) -> None:
        # The template's SGT_REPO embeds gitlab-ci-token:${CI_JOB_TOKEN}@ so a
        # private toolkit mirror clones without a PAT. When ci-init substitutes
        # a plain https origin/--repo URL, it must re-inject that prefix —
        # otherwise the written pipeline silently loses clone auth.
        sha = "b" * 40
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sgt(
                "--root", tmp, "ci-init", "--gitlab", "--ref", sha,
                "--repo", "https://gitlab.example.com/ai-tools/skill-governance-toolkit.git")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            body = (Path(tmp) / ".gitlab-ci.yml").read_text(encoding="utf-8")
            self.assertIn(
                'SGT_REPO: "https://gitlab-ci-token:${CI_JOB_TOKEN}@gitlab.example.com'
                '/ai-tools/skill-governance-toolkit.git"', body)

    def test_gitlab_repo_substitution_leaves_authed_and_ssh_urls_alone(self) -> None:
        sha = "c" * 40
        cases = [
            "https://gitlab-ci-token:${CI_JOB_TOKEN}@gitlab.example.com/g/t.git",
            "git@gitlab.example.com:g/t.git",
        ]
        for url in cases:
            with tempfile.TemporaryDirectory() as tmp:
                result = self.run_sgt("--root", tmp, "ci-init", "--gitlab",
                                      "--ref", sha, "--repo", url)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                body = (Path(tmp) / ".gitlab-ci.yml").read_text(encoding="utf-8")
                self.assertIn(f'SGT_REPO: "{url}"', body)

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


class CiInitConsumerShaTests(unittest.TestCase):
    """Regression guard: ci-init must never pin the CONSUMER's git HEAD. In a
    consumer install SGT_ROOT is the user's project, so a naive `git rev-parse HEAD`
    there pins a SHA absent from the toolkit mirror → the generated gate fails on
    every PR."""

    @staticmethod
    def _git(repo: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
            check=True, capture_output=True,
        )

    def test_head_not_pinned_outside_toolkit_checkout(self) -> None:
        import sgt
        with tempfile.TemporaryDirectory() as tmp:
            consumer = Path(tmp)
            # A consumer install dir that IS a git repo with a commit (the trap),
            # but lacks the toolkit's dev-only checkout markers.
            self._git(consumer, "init", "-q")
            (consumer / "file.txt").write_text("x", encoding="utf-8")
            self._git(consumer, "add", "-A")
            self._git(consumer, "commit", "-qm", "consumer commit")
            original = sgt.SGT_ROOT
            sgt.SGT_ROOT = consumer
            try:
                self.assertFalse(sgt._sgt_root_is_toolkit_checkout())
                self.assertIsNone(sgt._current_head_sha(), "must not pin the consumer's HEAD")
                self.assertIsNone(sgt._origin_url(), "must not pin the consumer's origin")
            finally:
                sgt.SGT_ROOT = original

    def test_head_resolves_inside_real_toolkit_checkout(self) -> None:
        import sgt
        # The real checkout (SGT_ROOT) has the markers and resolves a 40-char SHA.
        self.assertTrue(sgt._sgt_root_is_toolkit_checkout())
        self.assertRegex(sgt._current_head_sha() or "", r"^[0-9a-f]{40}$")


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

    def test_gate_blocks_on_introduced_high_finding(self) -> None:
        # The RED path through the facade: an MR-style commit introducing a
        # high finding (inline token in .mcp.json) must make `sgt gate` exit
        # non-zero. Previously only the engine-level block (audit.sh P22) was
        # tested; the facade's exit-code propagation was unverified.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_git_repo(root)
            (root / ".mcp.json").write_text(
                '{"mcpServers":{"x":{"token":"ghp_012345678901234567890123456789012345"}}}\n',
                encoding="utf-8")
            env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
            subprocess.run(["git", "-C", str(root), "add", "-A"],
                           capture_output=True, env={**os.environ, **env})
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "introduce token"],
                           capture_output=True, env={**os.environ, **env})
            result = self.run_sgt("--root", str(root), "gate", "--base", "HEAD~1", cwd=root)
            self.assertNotEqual(result.returncode, 0,
                                "gate stayed green on an introduced high finding:\n"
                                + result.stdout + result.stderr)

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


class GlobalUninstallTests(unittest.TestCase):
    """`sgt uninstall --scope global` rmtree's under Path.home() — the most
    destructive sgt path. HOME is redirected to a temp dir (Path.home() honours
    $HOME on POSIX) so the real home is never touched.

    Toolkit-owned boundary (_plan_install_dir): skill dirs named in the toolkit's
    skills/INDEX.jsonl + skills/INDEX.jsonl itself, .sgt-owned sidecar entries in
    agents/references/commands/docs, scripts listed in runtime-manifest.txt, and
    host root files (CLAUDE.md/AGENTS.md) only when byte-identical to source.
    Everything else — the user's own skills and scripts — must be preserved.
    """

    def run_sgt(self, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, HOME=str(home))
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "sgt.py"), *args],
            cwd=ROOT, text=True, capture_output=True, check=False, env=env,
        )

    def _install_global(self, home: Path) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, HOME=str(home))
        return subprocess.run(
            ["bash", str(ROOT / "scripts" / "install.sh"), "--claude", "--global"],
            cwd=ROOT, text=True, capture_output=True, check=False, env=env,
        )

    def _seed_user_content(self, home: Path) -> tuple[Path, Path]:
        user_skill = home / ".claude" / "skills" / "my-own" / "SKILL.md"
        user_script = home / ".claude" / "scripts" / "mine.py"
        for p, body in ((user_skill, "USER SKILL"), (user_script, "print('mine')")):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        return user_skill, user_script

    def test_global_uninstall_removes_toolkit_keeps_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            r = self._install_global(home)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            user_skill, user_script = self._seed_user_content(home)
            claude = home / ".claude"
            # Sanity: toolkit content landed in ~/.claude.
            self.assertTrue((claude / "skills" / "skill-find").is_dir())
            self.assertTrue((claude / "references" / "copilot-tools.md").exists())
            self.assertTrue((claude / "scripts" / "sgt.py").exists())
            self.assertTrue((claude / "CLAUDE.md").exists())

            result = self.run_sgt(home, "uninstall", "--scope", "global", "--yes")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            # Toolkit-owned content removed.
            self.assertFalse((claude / "skills" / "skill-find").exists(),
                             "toolkit skill not removed by global uninstall")
            self.assertFalse((claude / "skills" / "INDEX.jsonl").exists(),
                             "skills/INDEX.jsonl not removed by global uninstall")
            self.assertFalse((claude / "references" / "copilot-tools.md").exists(),
                             "toolkit reference not removed by global uninstall")
            self.assertFalse((claude / "scripts" / "sgt.py").exists(),
                             "runtime script not removed by global uninstall")
            self.assertFalse((claude / "CLAUDE.md").exists(),
                             "host-owned CLAUDE.md (byte-identical to source) not removed")
            # User content preserved — the boundary that matters.
            self.assertTrue(user_skill.exists(), "user's own skill deleted by global uninstall")
            self.assertEqual(user_skill.read_text(encoding="utf-8"), "USER SKILL")
            self.assertTrue(user_script.exists(), "user's own script deleted by global uninstall")
            self.assertEqual(user_script.read_text(encoding="utf-8"), "print('mine')")

    def test_global_uninstall_dry_run_removes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.assertEqual(self._install_global(home).returncode, 0)
            user_skill, user_script = self._seed_user_content(home)
            claude = home / ".claude"
            before = sorted(str(p.relative_to(home)) for p in home.rglob("*"))

            result = self.run_sgt(home, "uninstall", "--scope", "global", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r"(?i)dry.run|would remove")

            after = sorted(str(p.relative_to(home)) for p in home.rglob("*"))
            self.assertEqual(before, after, "uninstall --dry-run modified the filesystem")
            self.assertTrue((claude / "skills" / "skill-find").is_dir())
            self.assertTrue(user_skill.exists())
            self.assertTrue(user_script.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
