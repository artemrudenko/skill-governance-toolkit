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

    def test_checks_reference_documents_every_rule(self) -> None:
        doc = (ROOT / "docs" / "checks-reference.md").read_text(encoding="utf-8")
        for rule in agent_audit.rule_catalog()["rules"]:
            self.assertIn(rule["rule_id"], doc, f"{rule['rule_id']} missing from checks-reference.md")

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

    def test_report_includes_policy_provenance(self) -> None:
        for command, target in (("audit-project", "."), ("audit-skill", "skills/library-audit/SKILL.md")):
            result = self.run_cli(command, target, "--format", "json")
            report = json.loads(result.stdout)
            self.assertIn("rules_version", report, command)
            self.assertIn("engine_version", report, command)
            self.assertTrue(report["engine_version"], command)

    def test_changed_only_empty_base_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skills" / "bad"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("No frontmatter here\n", encoding="utf-8")

            # Empty base (e.g. unset CI_MERGE_REQUEST_DIFF_BASE_SHA) must FAIL CLOSED
            # with exit 2 — not silently switch scope to the whole tree, which could
            # block unrelated MRs on legacy assets or (under --fail-on none) pass green
            # having audited nothing meaningful.
            result = self.run_cli("audit-project", tmp, "--changed-only", "--base", "", "--format", "json", "--fail-on", "high")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("non-empty --base", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

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

    def _valid_skill_text(self, body: str) -> str:
        return "\n".join(
            [
                "---",
                "name: sample-skill",
                "description: this sample skill has enough routing words and trigger phrases for deterministic audit tests",
                "compatibility: all",
                "license: MIT",
                "metainfo:",
                "  category: [governance]",
                "  tier: stable",
                "---",
                body,
            ]
        )

    def _write_valid_skill(self, root: Path, body: str) -> Path:
        skill_dir = root / "skills" / "sample"
        skill_dir.mkdir(parents=True)
        path = skill_dir / "SKILL.md"
        path.write_text(self._valid_skill_text(body), encoding="utf-8")
        return path

    def test_missing_skill_type_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._write_valid_skill(
                Path(tmp),
                "## When to use\nUse this to audit and verify sample skills.\n## Predecessor\nnone\n## Successor\nterminal\n",
            )

            report = agent_audit.audit_skill(skill)

            self.assertIn("SKILL021", {item["rule_id"] for item in report["findings"]})

    def test_ask_contract_contradiction_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._write_valid_skill(
                Path(tmp),
                "\n".join(
                    [
                        "# Sample",
                        "> **Skill type:** Detect-only.",
                        "## When to use",
                        "Use this to audit and verify sample skills.",
                        "Default `RESUME=auto` — never asks.",
                        "If the target is ambiguous, otherwise ask the user which one to inspect.",
                        "## Predecessor",
                        "none",
                        "## Successor",
                        "terminal",
                    ]
                ),
            )

            report = agent_audit.audit_skill(skill)

            self.assertIn("SKILL022", {item["rule_id"] for item in report["findings"]})

    def test_clarification_policy_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._write_valid_skill(
                Path(tmp),
                "\n".join(
                    [
                        "# Sample",
                        "> **Skill type:** Detect-only.",
                        "## When to use",
                        "Use this to audit and verify sample skills.",
                        "If NEED is missing, ask the user for it before proceeding.",
                        "## Predecessor",
                        "none",
                        "## Successor",
                        "terminal",
                        "## Hard rules",
                        "- ✅ **Clarification policy:** permitted only in Phase 0 when NEED is missing.",
                    ]
                ),
            )

            report = agent_audit.audit_skill(skill)

            self.assertNotIn("SKILL022", {item["rule_id"] for item in report["findings"]})

    def test_task_without_sequential_fallback_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._write_valid_skill(
                Path(tmp),
                "\n".join(
                    [
                        "# Sample",
                        "> **Skill type:** Detect-only.",
                        "## When to use",
                        "Use this to audit and verify sample skills.",
                        "Call `Task` to run agents/code-reviewer.md.",
                        "## Predecessor",
                        "none",
                        "## Successor",
                        "terminal",
                    ]
                ),
            )

            report = agent_audit.audit_skill(skill)

            self.assertIn("SKILL018", {item["rule_id"] for item in report["findings"]})

    def test_task_with_sequential_fallback_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._write_valid_skill(
                Path(tmp),
                "\n".join(
                    [
                        "# Sample",
                        "> **Skill type:** Detect-only.",
                        "## When to use",
                        "Use this to audit and verify sample skills.",
                        "Optionally call `Task` to run agents/code-reviewer.md.",
                        "Sequential fallback: inline the agent instructions and emit the same finding schema.",
                        "## Predecessor",
                        "none",
                        "## Successor",
                        "terminal",
                    ]
                ),
            )

            report = agent_audit.audit_skill(skill)

            self.assertNotIn("SKILL018", {item["rule_id"] for item in report["findings"]})

    def test_mutating_skill_contract_requires_safety_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._write_valid_skill(
                Path(tmp),
                "\n".join(
                    [
                        "# Sample",
                        "> **Skill type:** MUTATING.",
                        "## When to use",
                        "Use this to audit sample skills.",
                        "This skill changes project files.",
                        "## Predecessor",
                        "none",
                        "## Successor",
                        "terminal",
                    ]
                ),
            )

            report = agent_audit.audit_skill(skill)

            self.assertIn("SKILL023", {item["rule_id"] for item in report["findings"]})

    # --- Part 2: SKILL020 fires only on real workflow chains ---

    def test_skill020_silent_for_standalone_skill(self) -> None:
        """A standalone skill (no chain signal) does NOT trip SKILL020."""
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._write_valid_skill(
                Path(tmp),
                "\n".join(
                    [
                        "# Sample",
                        "> **Skill type:** Detect-only.",
                        "## When to use",
                        "Use this to audit and verify sample skills.",
                    ]
                ),
            )
            report = agent_audit.audit_skill(skill)
            self.assertNotIn("SKILL020", {item["rule_id"] for item in report["findings"]})

    def test_skill020_fires_when_handoffs_declared(self) -> None:
        """A `handoffs:` frontmatter key signals a chain but no Predecessor/Successor."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skills" / "sample"
            skill_dir.mkdir(parents=True)
            path = skill_dir / "SKILL.md"
            path.write_text(
                "\n".join(
                    [
                        "---",
                        "name: sample-skill",
                        "description: this sample skill has enough routing words and trigger phrases for deterministic audit tests",
                        "compatibility: all",
                        "license: MIT",
                        "handoffs: [other-skill]",
                        "metainfo:",
                        "  category: [governance]",
                        "  tier: stable",
                        "---",
                        "# Sample",
                        "> **Skill type:** Detect-only.",
                        "## When to use",
                        "Use this to audit and verify sample skills.",
                    ]
                ),
                encoding="utf-8",
            )
            report = agent_audit.audit_skill(path)
            findings = {item["rule_id"]: item for item in report["findings"]}
            self.assertIn("SKILL020", findings)
            self.assertEqual(findings["SKILL020"]["severity"], "low")
            self.assertIn("workflow relationship", findings["SKILL020"]["message"])

    def test_skill020_fires_on_handoff_body_language(self) -> None:
        """Workflow-relationship prose in the body is a chain signal."""
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._write_valid_skill(
                Path(tmp),
                "\n".join(
                    [
                        "# Sample",
                        "> **Skill type:** Detect-only.",
                        "## When to use",
                        "Use this to audit sample skills.",
                        "This skill replaces the older sample-audit skill.",
                    ]
                ),
            )
            report = agent_audit.audit_skill(skill)
            self.assertIn("SKILL020", {item["rule_id"] for item in report["findings"]})

    def test_skill020_fires_on_replaced_by_metainfo(self) -> None:
        """metainfo.replaced_by is a chain signal."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skills" / "sample"
            skill_dir.mkdir(parents=True)
            path = skill_dir / "SKILL.md"
            path.write_text(
                "\n".join(
                    [
                        "---",
                        "name: sample-skill",
                        "description: this sample skill has enough routing words and trigger phrases for deterministic audit tests",
                        "compatibility: all",
                        "license: MIT",
                        "metainfo:",
                        "  category: [governance]",
                        "  tier: stable",
                        "  replaced_by: newer-skill",
                        "---",
                        "# Sample",
                        "> **Skill type:** Detect-only.",
                        "## When to use",
                        "Use this to audit and verify sample skills.",
                    ]
                ),
                encoding="utf-8",
            )
            report = agent_audit.audit_skill(path)
            self.assertIn("SKILL020", {item["rule_id"] for item in report["findings"]})

    def test_skill020_silent_when_chain_documented(self) -> None:
        """A skill with a chain signal AND a Predecessor section does not trip."""
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._write_valid_skill(
                Path(tmp),
                "\n".join(
                    [
                        "# Sample",
                        "> **Skill type:** Detect-only.",
                        "## When to use",
                        "Use this to audit sample skills.",
                        "This skill replaces the older sample-audit skill.",
                        "## Predecessor",
                        "sample-audit",
                        "## Successor",
                        "terminal",
                    ]
                ),
            )
            report = agent_audit.audit_skill(skill)
            self.assertNotIn("SKILL020", {item["rule_id"] for item in report["findings"]})

    def test_non_skill_assets_are_content_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".mcp.json").write_text(
                '{"mcpServers":{"x":{"command":"node","env":{"TOKEN":"ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}}}',
                encoding="utf-8")
            report = agent_audit.audit_project(root)
            self.assertIn("SEC011", {f["rule_id"] for f in report["findings"]})

    def test_security_catalog_catches_extended_secret_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._write_valid_skill(
                Path(tmp),
                "\n".join(
                    [
                        "# Sample",
                        "> **Skill type:** Detect-only.",
                        "## When to use",
                        "Use this to audit and verify sample skills.",
                        "Example leaked token: xoxb-1234567890-abcdef",
                        "## Predecessor",
                        "none",
                        "## Successor",
                        "terminal",
                    ]
                ),
            )

            report = agent_audit.audit_skill(skill)

            self.assertIn("SKILL015", {item["rule_id"] for item in report["findings"]})

    # --- Part 1: findings carry rule title + rationale ---

    def test_finding_dicts_carry_title_and_rationale(self) -> None:
        """Each serialized finding gains the catalog `title` + `rationale` (description)."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skills" / "bad"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("No frontmatter here\n", encoding="utf-8")

            report = agent_audit.audit_project(tmp)
            catalog = agent_audit.rules_by_id()
            self.assertTrue(report["findings"])
            for item in report["findings"]:
                rule = catalog.get(item["rule_id"])
                self.assertIsNotNone(rule, item["rule_id"])
                self.assertEqual(item["title"], rule["title"])
                self.assertEqual(item["rationale"], rule["description"])

    def test_audit_skill_findings_carry_title_and_rationale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._write_valid_skill(Path(tmp), "## When to use\nverify nothing.\n")
            report = agent_audit.audit_skill(skill)
            catalog = agent_audit.rules_by_id()
            self.assertTrue(report["findings"])
            for item in report["findings"]:
                rule = catalog[item["rule_id"]]
                self.assertEqual(item["title"], rule["title"])
                self.assertEqual(item["rationale"], rule["description"])

    def test_finding_key_ignores_title_and_rationale(self) -> None:
        """Delta identity must not shift when title/rationale are present."""
        base = {"rule_id": "SKILL001", "file": "skills/x/SKILL.md", "message": "m"}
        enriched = {**base, "title": "T", "rationale": "R", "line": 9, "severity": "high"}
        self.assertEqual(agent_audit.finding_key(base), agent_audit.finding_key(enriched))

    def test_text_report_renders_title_and_why(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skills" / "bad"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("No frontmatter here\n", encoding="utf-8")
            result = self.run_cli("audit-project", tmp, "--format", "text")
            catalog = agent_audit.rules_by_id()
            self.assertIn(catalog["SKILL001"]["title"], result.stdout)
            self.assertIn("Why:", result.stdout)

    def test_github_format_title_contains_rule_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skills" / "bad"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("No frontmatter here\n", encoding="utf-8")
            result = self.run_cli("audit-project", tmp, "--format", "github")
            title = agent_audit.rules_by_id()["SKILL001"]["title"]
            self.assertIn(f"title=SKILL001: {title}::", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
