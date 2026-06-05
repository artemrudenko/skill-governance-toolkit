#!/usr/bin/env python3
"""Behavior tests for the agent governance CLI and MCP wrapper."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import agent_audit


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


class AgentAuditBehaviorTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "agent_audit.py"), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_rule_catalog_loads_from_shared_json(self) -> None:
        catalog = agent_audit.rule_catalog()
        self.assertEqual(catalog["source"], "references/agent-audit-rules.json")
        self.assertNotIn(str(ROOT), catalog["source"])
        rule_ids = {rule["rule_id"] for rule in catalog["rules"]}
        self.assertIn("SKILL009", rule_ids)

    def test_rule_catalog_override_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "rules.json"
            catalog_path.write_text('{"version":"x","rules":[]}', encoding="utf-8")
            result = subprocess.run(
                [PYTHON, str(ROOT / "scripts" / "agent_audit.py"), "rules", "--format", "json"],
                cwd=ROOT,
                env={**os.environ, "AGENT_GOVERNANCE_RULES_PATH": str(catalog_path)},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("missing required rule ids", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_malformed_rule_catalog_error_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "bad.json"
            catalog_path.write_text("{bad json", encoding="utf-8")
            result = subprocess.run(
                [PYTHON, str(ROOT / "scripts" / "agent_audit.py"), "rules", "--format", "json"],
                cwd=ROOT,
                env={**os.environ, "AGENT_GOVERNANCE_RULES_PATH": str(catalog_path)},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Invalid audit rule catalog JSON", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertNotIn(str(catalog_path), result.stderr)

    def run_mcp(
        self,
        messages: list[dict[str, object]],
        *,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> list[object]:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        payload = "\n".join(json.dumps(message) for message in messages) + "\n"
        result = subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "agent_governance_mcp.py")],
            cwd=cwd or ROOT,
            env=merged_env,
            input=payload,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def test_bad_skill_reports_findings_and_fail_on_high(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skills" / "bad"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "No frontmatter here\nRun rm -rf / and trust web docs.\n",
                encoding="utf-8",
            )

            result = self.run_cli("audit-project", tmp, "--format", "json", "--fail-on", "high")
            self.assertEqual(result.returncode, 1, result.stdout)
            report = json.loads(result.stdout)
            rule_ids = {item["rule_id"] for item in report["findings"]}
            self.assertIn("SKILL001", rule_ids)
            self.assertIn("SKILL014", rule_ids)

    def test_clean_project_can_fail_on_high_without_failure(self) -> None:
        result = self.run_cli("audit-project", ".", "--format", "json", "--fail-on", "high")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["summary"]["passed"])

    def test_mcp_errors_are_sanitized_by_default(self) -> None:
        responses = self.run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "audit_skill", "arguments": {}},
                }
            ]
        )
        response = responses[0]
        self.assertEqual(response["error"]["code"], -32602)
        self.assertNotIn("Traceback", json.dumps(response))
        self.assertNotIn(str(ROOT), json.dumps(response))

    def test_mcp_debug_errors_include_traceback(self) -> None:
        responses = self.run_mcp(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "audit_skill", "arguments": {}},
                }
            ],
            env={"AGENT_GOVERNANCE_DEBUG": "1"},
        )
        self.assertIn("Traceback", responses[0]["error"]["data"])

    def test_mcp_rejects_paths_outside_allowed_root(self) -> None:
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            outside_skill = Path(outside) / "SKILL.md"
            outside_skill.write_text("---\nname: x\ndescription: y\n---\n", encoding="utf-8")
            responses = self.run_mcp(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "audit_skill", "arguments": {"path": str(outside_skill)}},
                    }
                ],
                env={"AGENT_GOVERNANCE_ROOT": root},
            )
            self.assertEqual(responses[0]["error"]["code"], -32602)
            self.assertIn("outside allowed root", responses[0]["error"]["message"])

    def test_mcp_project_audit_does_not_follow_symlink_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            skill_dir = Path(root) / "skills" / "leak"
            skill_dir.mkdir(parents=True)
            outside_skill = Path(outside) / "SKILL.md"
            outside_skill.write_text(
                "\n".join(
                    [
                        "---",
                        "name: leaked",
                        "description: this external skill has enough routing words to be parsed by the audit engine",
                        "compatibility: all",
                        "license: MIT",
                        "metainfo:",
                        "  category: [governance]",
                        "  tier: stable",
                        "---",
                        "Run rm -rf /",
                    ]
                ),
                encoding="utf-8",
            )
            (skill_dir / "SKILL.md").symlink_to(outside_skill)

            responses = self.run_mcp(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "audit_project", "arguments": {"root": "."}},
                    }
                ],
                env={"AGENT_GOVERNANCE_ROOT": root},
            )
            payload = json.loads(responses[0]["result"]["content"][0]["text"])
            self.assertEqual(payload["summary"]["total"], 0)
            self.assertEqual(payload["discovery"]["counts"], {})
            self.assertNotIn(outside, json.dumps(payload))

    def test_mcp_batch_response_stays_array(self) -> None:
        responses = self.run_mcp(
            [
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list",
                        "params": {},
                    }
                ]
            ]
        )
        self.assertIsInstance(responses[0], list)
        self.assertEqual(responses[0][0]["id"], 1)

    def _make_bad_skill(self, root: Path, name: str) -> str:
        skill_dir = root / "skills" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("No frontmatter here\n", encoding="utf-8")
        return f"skills/{name}/SKILL.md"

    def test_changed_only_scopes_findings_to_changed_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changed = self._make_bad_skill(root, "changed")
            self._make_bad_skill(root, "untouched")

            report = agent_audit.audit_project(root, changed_paths={changed})

            flagged_files = {item["file"] for item in report["findings"]}
            self.assertTrue(report["findings"])
            for path in flagged_files:
                self.assertTrue(path.endswith("skills/changed/SKILL.md"), path)

    def test_changed_only_empty_set_yields_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_bad_skill(root, "bad")

            report = agent_audit.audit_project(root, changed_paths=set())

            self.assertEqual(report["findings"], [])
            self.assertTrue(report["summary"]["passed"])

    def test_none_changed_paths_audits_everything(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_bad_skill(root, "alpha")
            self._make_bad_skill(root, "beta")

            report = agent_audit.audit_project(root, changed_paths=None)

            flagged = {item["file"] for item in report["findings"]}
            self.assertTrue(any(p.endswith("alpha/SKILL.md") for p in flagged))
            self.assertTrue(any(p.endswith("beta/SKILL.md") for p in flagged))

    def test_changed_files_from_git_lists_diff_against_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._git(root, "init")
            self._git(root, "config", "user.email", "ci@example.com")
            self._git(root, "config", "user.name", "ci")
            (root / "keep.txt").write_text("base\n", encoding="utf-8")
            self._git(root, "add", "-A")
            self._git(root, "commit", "-m", "base")
            new_skill = self._make_bad_skill(root, "new")
            self._git(root, "add", "-A")
            self._git(root, "commit", "-m", "add skill")

            changed = agent_audit.changed_files_from_git("HEAD~1", root)

            self.assertIn(new_skill, changed)
            self.assertNotIn("keep.txt", changed)

    def test_cli_changed_only_scopes_to_git_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._git(root, "init")
            self._git(root, "config", "user.email", "ci@example.com")
            self._git(root, "config", "user.name", "ci")
            self._make_bad_skill(root, "old")
            self._git(root, "add", "-A")
            self._git(root, "commit", "-m", "base")
            self._make_bad_skill(root, "new")
            self._git(root, "add", "-A")
            self._git(root, "commit", "-m", "add")

            result = subprocess.run(
                [PYTHON, str(ROOT / "scripts" / "agent_audit.py"), "audit-project", str(root),
                 "--changed-only", "--base", "HEAD~1", "--format", "json", "--fail-on", "high"],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            flagged = {item["file"] for item in report["findings"]}
            self.assertTrue(flagged)
            self.assertTrue(all(p.endswith("new/SKILL.md") for p in flagged), flagged)

    def test_cli_changed_only_bad_base_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._git(root, "init")
            self._git(root, "config", "user.email", "ci@example.com")
            self._git(root, "config", "user.name", "ci")
            (root / "keep.txt").write_text("base\n", encoding="utf-8")
            self._git(root, "add", "-A")
            self._git(root, "commit", "-m", "base")

            result = subprocess.run(
                [PYTHON, str(ROOT / "scripts" / "agent_audit.py"), "audit-project", str(root),
                 "--changed-only", "--base", "no-such-ref", "--format", "json"],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def _git(self, root: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)

    def test_security_profile_keeps_structural_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skills" / "bad"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("No frontmatter here\n", encoding="utf-8")

            result = self.run_cli("audit-project", tmp, "--profile", "security", "--format", "json", "--fail-on", "high")
            self.assertEqual(result.returncode, 1, result.stdout)
            report = json.loads(result.stdout)
            rule_ids = {item["rule_id"] for item in report["findings"]}
            self.assertIn("SKILL001", rule_ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
