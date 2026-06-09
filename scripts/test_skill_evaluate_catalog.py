#!/usr/bin/env python3
"""Consistency guards for the skill-evaluate Phase 3 sub-check catalog.

These are deterministic structural guards — they do NOT execute the LLM rubric.
They prevent the most likely regressions when sub-checks are added or retired:
catalog ↔ section drift, and the `info` severity contract (info findings must
never cap a dimension / affect score).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "skill-evaluate" / "SKILL.md"
STRUCT = ROOT / "skills" / "skill-evaluate" / "references" / "structural-analysis.md"

# Matches a "## 3.7 — ..." style sub-check section heading.
SECTION_RE = re.compile(r"^##\s+(3\.\d+\w*)\s+—", re.MULTILINE)
# Matches a catalog table row "| 3.7 — Activation coherence | ... |".
CATALOG_ROW_RE = re.compile(r"^\|\s*(3\.\d+\w*)\s+—", re.MULTILINE)


class CatalogConsistencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_text = SKILL.read_text(encoding="utf-8")
        self.struct_text = STRUCT.read_text(encoding="utf-8")

    def test_every_catalog_row_has_a_section(self) -> None:
        """Each sub-check listed in SKILL.md must have a section in structural-analysis.md."""
        catalog_ids = set(CATALOG_ROW_RE.findall(self.skill_text))
        section_ids = set(SECTION_RE.findall(self.struct_text))
        missing = catalog_ids - section_ids
        self.assertFalse(
            missing,
            f"Catalog rows without a structural-analysis section: {sorted(missing)}",
        )

    def test_negative_rule_placement_check_documented(self) -> None:
        """3.8 negative-rule placement must exist as a section."""
        section_ids = set(SECTION_RE.findall(self.struct_text))
        self.assertIn("3.8", section_ids, "3.8 — Negative-rule placement section missing")

    def test_info_flags_in_jsonl_schema(self) -> None:
        """The JSONL output schema must document the info_flags field."""
        self.assertIn(
            "info_flags",
            self.skill_text,
            "info_flags not documented in skill-evaluate JSONL schema",
        )

    def test_info_contract_states_no_cap(self) -> None:
        """The info severity contract must explicitly state it never caps / affects score."""
        # 3.8 section must declare the info contract (does not cap any dimension).
        m = re.search(r"##\s+3\.8\s+—.*?(?=^##\s|\Z)", self.struct_text, re.S | re.M)
        self.assertIsNotNone(m, "3.8 section not found for info-contract assertion")
        section = m.group(0).lower()
        self.assertTrue(
            ("info" in section)
            and ("does not cap" in section or "never cap" in section or "no cap" in section),
            "3.8 must declare the info contract: info-severity finding does NOT cap a dimension",
        )


if __name__ == "__main__":
    unittest.main()
