#!/usr/bin/env python3
"""Behavior tests for the GitLab merge-request comment poster."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import post_mr_comment


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def _report(findings: list[dict[str, object]]) -> dict[str, object]:
    by_severity = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for item in findings:
        by_severity[str(item["severity"])] += 1
    return {
        "kind": "project-audit",
        "summary": {"total": len(findings), "by_severity": by_severity, "passed": not findings},
        "findings": findings,
    }


class PostMrCommentTests(unittest.TestCase):
    def test_render_includes_marker_and_findings(self) -> None:
        report = _report([
            {"rule_id": "SKILL001", "severity": "high", "file": "skills/x/SKILL.md", "line": 1,
             "message": "Missing frontmatter", "suggestion": "Add name and description."},
        ])

        body = post_mr_comment.render_comment(report)

        self.assertIn(post_mr_comment.MARKER, body)
        self.assertIn("SKILL001", body)
        self.assertIn("skills/x/SKILL.md", body)
        self.assertIn("Missing frontmatter", body)

    def test_render_clean_report_says_passed(self) -> None:
        body = post_mr_comment.render_comment(_report([]))

        self.assertIn(post_mr_comment.MARKER, body)
        self.assertNotIn("| high |", body.lower())
        self.assertTrue("no governance findings" in body.lower() or "passed" in body.lower())

    def test_render_reports_truncation_without_silent_cap(self) -> None:
        findings = [
            {"rule_id": "SKILL003", "severity": "low", "file": f"skills/s{i}/SKILL.md", "line": 1,
             "message": "Short description", "suggestion": "Expand triggers."}
            for i in range(5)
        ]

        body = post_mr_comment.render_comment(_report(findings), max_findings=2)

        self.assertIn("3 more", body)

    def test_render_escapes_table_breaking_finding_text(self) -> None:
        # Finding text comes from audited file content; a `|` or newline must not
        # break the Markdown table or inject extra rows/markup into the MR note.
        report = _report([
            {"rule_id": "SKILL015", "severity": "high", "file": "skills/z/SKILL.md", "line": 7,
             "message": "secret | injected\n| evil | row |", "suggestion": "Remove the | pipe."},
        ])

        body = post_mr_comment.render_comment(report)

        # The raw pipe from the message must be escaped, and no stray newline may
        # split the single finding row into multiple table rows.
        self.assertIn("secret \\| injected", body)
        self.assertNotIn("\n| evil | row |", body)

    def test_find_marker_note_returns_id(self) -> None:
        notes = [
            {"id": 10, "body": "unrelated review note"},
            {"id": 11, "body": f"{post_mr_comment.MARKER}\nprevious gate result"},
        ]

        self.assertEqual(post_mr_comment.find_marker_note(notes, post_mr_comment.MARKER), 11)
        self.assertIsNone(post_mr_comment.find_marker_note(notes[:1], post_mr_comment.MARKER))

    def test_cli_dry_run_prints_body_without_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "skill-audit.json"
            audit_path.write_text(json.dumps(_report([
                {"rule_id": "SKILL014", "severity": "high", "file": "skills/y/SKILL.md", "line": 3,
                 "message": "Dangerous command", "suggestion": "Remove destructive shell."},
            ])), encoding="utf-8")

            result = subprocess.run(
                [PYTHON, str(ROOT / "scripts" / "post_mr_comment.py"), str(audit_path), "--dry-run"],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(post_mr_comment.MARKER, result.stdout)
            self.assertIn("SKILL014", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
