#!/usr/bin/env python3
"""Behavior tests for `agent_audit.py explain-finding <rule_id>`.

Run via subprocess so each invocation gets a fresh process (and fresh lru_cache
of the rule catalog), exactly matching how a CI author would call the command.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = str(Path(__file__).with_name("agent_audit.py"))


def _run(rule_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, SCRIPT, "explain-finding", rule_id],
        capture_output=True,
        text=True,
    )


class ExplainFindingTests(unittest.TestCase):
    def test_floor_rule_points_to_central_ignore_file_not_inline(self) -> None:
        # SEC011 is a severity-floor rule: inline markers CANNOT suppress it (F3
        # invariant). The explanation must steer the author to the CODEOWNER-gated
        # central file and must NOT offer the inline marker as the path.
        proc = _run("SEC011")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("SEC011", proc.stdout)
        self.assertIn("references/audit-ignore.json", proc.stdout)
        self.assertIn("reason", proc.stdout)
        # A floor rule must never advertise the inline marker as a suppression path.
        self.assertNotIn("sgt-ignore:", proc.stdout)

    def test_advisory_rule_offers_inline_marker(self) -> None:
        # SEC003 (homoglyph) is advisory — the inline marker is the right path.
        proc = _run("SEC003")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("SEC003", proc.stdout)
        self.assertIn("<!-- sgt-ignore: SEC003", proc.stdout)

    def test_output_includes_title_and_severity(self) -> None:
        proc = _run("SEC011")
        self.assertIn("high", proc.stdout.lower())
        self.assertIn("Inline secret value", proc.stdout)

    def test_unknown_rule_exits_nonzero(self) -> None:
        proc = _run("NOPE999")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("NOPE999", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
