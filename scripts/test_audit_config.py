#!/usr/bin/env python3
"""Behavior tests for externalized audit configuration (thresholds, vocabularies,
profiles, pattern packs) loaded from the rule catalog's optional `config` block."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
CATALOG = ROOT / "references" / "agent-audit-rules.json"

VALID_FRONTMATTER = [
    "---",
    "name: sample-skill",
    "description: {desc}",
    "compatibility: all",
    "license: MIT",
    "metainfo:",
    "  category: [{category}]",
    "  tier: stable",
    "---",
    "## When to use",
    "Run the audit to verify the result.",
    "{body}",
]


class BodyThresholdSingleSourceTests(unittest.TestCase):
    """The gate config is the single source of truth for body-length thresholds.
    The prose tables in skill-evaluate 3.1 and library-audit budget-spec must echo
    the config values, never diverge (this is the drift that prompted the rule)."""

    AGENT_AUDIT = ROOT / "scripts" / "agent_audit.py"
    STRUCT = ROOT / "skills" / "skill-evaluate" / "references" / "structural-analysis.md"
    BUDGET = ROOT / "skills" / "library-audit" / "references" / "budget-spec.md"
    STANDARD = ROOT / "docs" / "skill-authoring-standard.md"
    # The library-audit skill body + its report template render the same grid to
    # the agent and into generated reports — they drifted to a 401/201–400 scheme
    # and made reports stricter than the gate, so they must echo the config too.
    LIB_SKILL = ROOT / "skills" / "library-audit" / "SKILL.md"
    LIB_TEMPLATE = ROOT / "skills" / "library-audit" / "assets" / "output-template-detailed.md"
    # AGENTS.md names "skill-evaluate 3.1" as a doc that must echo the config grid,
    # but its SKILL.md 3.1 row was unguarded and drifted (omitted body_critical).
    # Guard it so the rule covers the table it explicitly references.
    EVAL_SKILL = ROOT / "skills" / "skill-evaluate" / "SKILL.md"
    AUDIT_SH = ROOT / "scripts" / "audit.sh"

    def _default(self, key: str) -> str:
        text = self.AGENT_AUDIT.read_text(encoding="utf-8")
        m = re.search(rf'"{key}"\s*:\s*(\d+)', text)
        self.assertIsNotNone(m, f"{key} not found in agent_audit.py defaults")
        return m.group(1)

    def test_docs_echo_config_thresholds(self) -> None:
        budget = self._default("body_budget")   # 500
        critical = self._default("body_critical")  # 600
        for doc in (self.STRUCT, self.BUDGET, self.STANDARD,
                    self.LIB_SKILL, self.LIB_TEMPLATE, self.EVAL_SKILL):
            body = doc.read_text(encoding="utf-8")
            self.assertIn(budget, body, f"{doc.name} must echo body_budget={budget}")
            self.assertIn(critical, body, f"{doc.name} must echo body_critical={critical}")
            # The pre-fix divergent boundary must not resurface (spaced or unspaced).
            self.assertNotIn("401", body, f"{doc.name} still uses the stale 401 boundary")

    def test_audit_sh_reads_thresholds_from_config(self) -> None:
        # The self-CI body-length phase must derive its boundaries from the engine
        # config, not hardcode them — otherwise it can drift stricter than the gate.
        body = self.AUDIT_SH.read_text(encoding="utf-8")
        self.assertIn("body_budget", body, "audit.sh must read body_budget from the config")
        self.assertIn("body_critical", body, "audit.sh must read body_critical from the config")
        # No resurrected hardcoded boundary.
        self.assertNotIn("-le 400", body, "audit.sh still hardcodes the stale 400 boundary")
        self.assertNotIn("401", body, "audit.sh still references the stale 401 boundary")


class AuditConfigTests(unittest.TestCase):
    def _catalog_with_config(self, tmp: Path, config: dict[str, object]) -> Path:
        payload = json.loads(CATALOG.read_text(encoding="utf-8"))
        payload["config"] = config
        path = tmp / "rules.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _skill(self, tmp: Path, *, desc: str = "x" * 90, category: str = "governance", body: str = "") -> Path:
        skill_dir = tmp / "skills" / "sample"
        skill_dir.mkdir(parents=True)
        path = skill_dir / "SKILL.md"
        text = "\n".join(VALID_FRONTMATTER).format(desc=desc, category=category, body=body)
        path.write_text(text, encoding="utf-8")
        return path

    def _audit(self, skill_path: Path, catalog: Path, profile: str = "release-ready") -> list[dict[str, object]]:
        result = subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "agent_audit.py"), "audit-skill", str(skill_path),
             "--profile", profile, "--format", "json"],
            cwd=ROOT, text=True, capture_output=True, check=False,
            env={**os.environ, "AGENT_GOVERNANCE_RULES_PATH": str(catalog)},
        )
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return json.loads(result.stdout)["findings"]

    def _rule_ids(self, findings: list[dict[str, object]]) -> set[str]:
        return {str(f["rule_id"]) for f in findings}

    def test_custom_description_min_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            catalog = self._catalog_with_config(tmp_path, {"thresholds": {"description_min": 200}})
            skill = self._skill(tmp_path, desc="x" * 90)  # OK under default 80, fails under 200

            self.assertIn("SKILL003", self._rule_ids(self._audit(skill, catalog)))

    def test_custom_category_vocabulary_extends_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            catalog = self._catalog_with_config(tmp_path, {"vocabularies": {"categories": ["marketplace"]}})
            skill = self._skill(tmp_path, category="marketplace")

            # marketplace is now valid; the built-in vocab still applies (no SKILL008).
            self.assertNotIn("SKILL008", self._rule_ids(self._audit(skill, catalog)))

    def test_custom_dangerous_pattern_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = {"patterns": {"dangerous": [
                {"label": "kubectl delete", "regex": r"kubectl\s+delete", "suggestion": "Avoid cluster deletion."}
            ]}}
            catalog = self._catalog_with_config(tmp_path, config)
            skill = self._skill(tmp_path, body="Then run kubectl delete ns prod to clean up.")

            self.assertIn("SKILL014", self._rule_ids(self._audit(skill, catalog)))

    def test_custom_security_profile_membership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # A security profile that omits SKILL009 (allowed-tools) entirely.
            catalog = self._catalog_with_config(tmp_path, {"profiles": {"security": ["SKILL001", "SKILL002"]}})
            skill = self._skill(tmp_path)
            skill.write_text(skill.read_text(encoding="utf-8").replace("license: MIT", "license: MIT\nallowed-tools: Read"), encoding="utf-8")

            ids = self._rule_ids(self._audit(skill, catalog, profile="security"))
            self.assertNotIn("SKILL009", ids)

    def test_defaults_apply_when_no_config_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Shipped catalog has no `config` block: built-in vocab still rejects unknown categories.
            skill = self._skill(tmp_path, category="marketplace")

            self.assertIn("SKILL008", self._rule_ids(self._audit(skill, CATALOG)))


    def _run_rules(self, catalog: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "agent_audit.py"), "rules", "--format", "json"],
            cwd=ROOT, text=True, capture_output=True, check=False,
            env={**os.environ, "AGENT_GOVERNANCE_RULES_PATH": str(catalog)},
        )

    def test_severity_floor_rejects_downgraded_security_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = json.loads(CATALOG.read_text(encoding="utf-8"))
            for rule in payload["rules"]:
                if rule["rule_id"] == "SKILL014":
                    rule["severity"] = "low"  # attempt to weaken a blocking safety rule
            catalog = Path(tmp) / "rules.json"
            catalog.write_text(json.dumps(payload), encoding="utf-8")

            result = self._run_rules(catalog)

            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("SKILL014", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_config_rejects_non_integer_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            catalog = self._catalog_with_config(tmp_path, {"thresholds": {"description_min": "lots"}})

            result = self._run_rules(catalog)

            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertNotIn("Traceback", result.stderr)

    def test_config_rejects_invalid_regex_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = {"patterns": {"dangerous": [{"label": "broken", "regex": "(unclosed", "suggestion": "x"}]}}
            catalog = self._catalog_with_config(tmp_path, config)

            result = self._run_rules(catalog)

            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("broken", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_shipped_config_example_is_valid_and_functional(self) -> None:
        example = json.loads((ROOT / "references" / "agent-audit-config.example.json").read_text(encoding="utf-8"))
        self.assertIn("config", example)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            catalog = self._catalog_with_config(tmp_path, example["config"])
            # Valid: `rules` loads it without error.
            self.assertEqual(self._run_rules(catalog).returncode, 0)
            # Functional: the example's `marketplace` category is accepted (no SKILL008).
            skill = self._skill(tmp_path, category="marketplace")
            self.assertNotIn("SKILL008", self._rule_ids(self._audit(skill, catalog)))

    def test_rules_command_validates_config_block(self) -> None:
        # The `rules` command must surface a bad config, not only the audit path.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            catalog = self._catalog_with_config(tmp_path, {"thresholds": {"body_budget": "500"}})

            self.assertEqual(self._run_rules(catalog).returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
