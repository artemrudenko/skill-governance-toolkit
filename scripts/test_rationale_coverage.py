#!/usr/bin/env python3
"""Rationale-coverage guard for the deterministic gate rules.

Forcing function + anti-drift: a gate rule that blocks or flags an MR MUST carry
a reason. Every rule in the catalog must have a non-empty `title` + `description`
(the short `why` shown by `explain-finding` and embedded in findings), AND a row
in docs/checks-reference.md (the long-form rationale). A check you cannot justify
is a candidate for removal — this test makes that explicit. Gate rules only;
skill-evaluate D1–D9 are explained by the LLM in its own output.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "references" / "agent-audit-rules.json"
CHECKS_REF = ROOT / "docs" / "checks-reference.md"

# A documented rule is one that LEADS a markdown table row (its rationale row),
# not merely a prose mention — a passing reference is not a rationale.
ROW_RULE_ID_RE = re.compile(
    r"^\|\s*\*{0,2}((?:DISC|SKILL|SEC|MCP|REF|SCR|HOOK|IGNORE)\d{3})\b", re.M
)


class RationaleCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = json.loads(CATALOG.read_text(encoding="utf-8"))["rules"]
        self.checks_ref = CHECKS_REF.read_text(encoding="utf-8")
        self.documented = set(ROW_RULE_ID_RE.findall(self.checks_ref))

    def test_every_rule_has_nonempty_why(self) -> None:
        """Every gate rule must carry a title + description (the short `why`)."""
        missing = [
            r["rule_id"]
            for r in self.rules
            if not r.get("title", "").strip() or not r.get("description", "").strip()
        ]
        self.assertEqual(
            missing, [], f"Gate rules without a title/description (why): {missing}"
        )

    def test_every_rule_documented_in_checks_reference(self) -> None:
        """Every gate rule must have long-form rationale in checks-reference.md."""
        undocumented = sorted(
            r["rule_id"] for r in self.rules if r["rule_id"] not in self.documented
        )
        self.assertEqual(
            undocumented,
            [],
            f"Gate rules with no checks-reference.md entry: {undocumented}",
        )


if __name__ == "__main__":
    unittest.main()
