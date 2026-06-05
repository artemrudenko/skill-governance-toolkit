#!/usr/bin/env python3
"""Behavior tests for externalized audit configuration (thresholds, vocabularies,
profiles, pattern packs) loaded from the rule catalog's optional `config` block."""

from __future__ import annotations

import json
import os
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
