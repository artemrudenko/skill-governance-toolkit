#!/usr/bin/env python3
"""Behavior tests for OPS reporting subcommands/flags:
OPS10 findings history + report-trends, OPS11 list-suppressions, OPS12 --whole-tree."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

# A far-future date so "future" fixtures never expire as the calendar advances.
FUTURE = "2999-01-01"
# A past date that is always expired.
PAST = "2000-01-01"


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(ROOT / "scripts" / "agent_audit.py"), *args],
        cwd=str(cwd or ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def _write_ignore_doc(root: Path, ignores: list[dict]) -> None:
    refs = root / "references"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "audit-ignore.json").write_text(
        json.dumps({"version": "1.0", "ignores": ignores}), encoding="utf-8"
    )


def _make_skill(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


# ── OPS11: list-suppressions ──────────────────────────────────────────────────
class ListSuppressionsTests(unittest.TestCase):
    def test_central_expired_and_future_both_reported_nonzero_on_expired(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_ignore_doc(root, [
                {"rule_id": "SEC003", "path": "a.md", "reason": "old waiver", "expires": PAST},
                {"rule_id": "SEC011", "path": "b.md", "reason": "future waiver", "expires": FUTURE},
            ])
            res = _run_cli("list-suppressions", "--root", str(root), "--format", "json")
            self.assertEqual(res.returncode, 2, res.stderr)
            data = json.loads(res.stdout)
            rule_ids = {e["rule_id"] for e in data["suppressions"]}
            self.assertEqual(rule_ids, {"SEC003", "SEC011"})
            self.assertTrue(any(e["expired"] for e in data["suppressions"]))

    def test_only_future_entry_no_window_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_ignore_doc(root, [
                {"rule_id": "SEC011", "path": "b.md", "reason": "future waiver", "expires": FUTURE},
            ])
            res = _run_cli("list-suppressions", "--root", str(root), "--format", "json")
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            self.assertEqual(len(data["suppressions"]), 1)
            self.assertFalse(data["suppressions"][0]["expired"])

    def test_expiring_within_window_triggers_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_ignore_doc(root, [
                {"rule_id": "SEC011", "path": "b.md", "reason": "future waiver", "expires": FUTURE},
            ])
            # The future entry is many days out; a huge window catches it.
            res = _run_cli("list-suppressions", "--root", str(root),
                           "--expiring-within", "999999", "--format", "json")
            self.assertEqual(res.returncode, 2, res.stderr)

    def test_inline_markers_discovered(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_ignore_doc(root, [])
            _make_skill(root, "skills/demo/SKILL.md",
                        "---\nname: demo\ndescription: x\n---\n"
                        "body line <!-- sgt-ignore: SEC003 advisory -->\n")
            res = _run_cli("list-suppressions", "--root", str(root), "--format", "json")
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            inline = [e for e in data["suppressions"] if e["source"] == "inline"]
            self.assertTrue(any(e["rule_id"] == "SEC003" for e in inline))

    def test_text_format_runs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_ignore_doc(root, [
                {"rule_id": "SEC011", "path": "b.md", "reason": "future", "expires": FUTURE},
            ])
            res = _run_cli("list-suppressions", "--root", str(root), "--format", "text")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("SEC011", res.stdout)


# ── OPS12: --whole-tree impact report ─────────────────────────────────────────
class WholeTreeTests(unittest.TestCase):
    def _project_with_findings(self, root: Path) -> None:
        # Two skills, each tripping at least one rule, so by_rule has >1 key.
        # A bare AGENTS.md so discovery has an instruction root.
        (root / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
        # SKILL.md missing required frontmatter fields -> emits findings.
        _make_skill(root, "skills/one/SKILL.md", "---\nname: one\n---\nbody\n")
        _make_skill(root, "skills/two/SKILL.md", "---\nname: two\n---\nbody\n")

    def test_whole_tree_json_has_by_rule_histogram_and_exit_zero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._project_with_findings(root)
            res = _run_cli("audit-project", str(root), "--whole-tree", "--format", "json")
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            self.assertIn("by_rule", data["summary"])
            by_rule = data["summary"]["by_rule"]
            self.assertTrue(by_rule, "by_rule histogram should be non-empty")
            self.assertEqual(sum(by_rule.values()), data["summary"]["total"])

    def test_whole_tree_ignores_fail_on_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._project_with_findings(root)
            # Even with --fail-on any, whole-tree never blocks.
            res = _run_cli("audit-project", str(root), "--whole-tree",
                           "--fail-on", "any", "--format", "json")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("impact report", res.stderr.lower())

    def test_whole_tree_text_prints_histogram(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._project_with_findings(root)
            res = _run_cli("audit-project", str(root), "--whole-tree", "--format", "text")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("by rule", res.stdout.lower())


# ── OPS10: findings history + report-trends ───────────────────────────────────
class FindingsHistoryTests(unittest.TestCase):
    def test_record_appends_findings_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
            _make_skill(root, "skills/one/SKILL.md", "---\nname: one\n---\nbody\n")
            res = _run_cli("audit-project", str(root), "--record", "--format", "json")
            self.assertEqual(res.returncode, 0, res.stderr)
            hist = root / "out" / "security" / "findings.jsonl"
            self.assertTrue(hist.exists(), "findings.jsonl should be created")
            lines = [json.loads(x) for x in hist.read_text().splitlines() if x.strip()]
            self.assertTrue(lines)
            for rec in lines:
                self.assertIn("ts", rec)
                self.assertIn("rule_id", rec)
                self.assertIn("severity", rec)
                self.assertIn("file", rec)
                self.assertIs(rec["suppressed"], False)

    def test_no_record_flag_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
            _make_skill(root, "skills/one/SKILL.md", "---\nname: one\n---\nbody\n")
            res = _run_cli("audit-project", str(root), "--format", "json")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertFalse((root / "out" / "security" / "findings.jsonl").exists())

    def test_report_trends_aggregates_top_rule(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hist = root / "out" / "security" / "findings.jsonl"
            hist.parent.mkdir(parents=True, exist_ok=True)
            events = [
                {"ts": "2026-01-01T00:00:00Z", "rule_id": "SEC003", "severity": "medium",
                 "file": "a.md", "suppressed": False},
                {"ts": "2026-01-01T00:00:00Z", "rule_id": "SEC003", "severity": "medium",
                 "file": "b.md", "suppressed": False},
                {"ts": "2026-01-02T00:00:00Z", "rule_id": "SEC011", "severity": "high",
                 "file": "c.md", "introduced": True, "suppressed": False},
            ]
            hist.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            res = _run_cli("report-trends", "--root", str(root), "--format", "json")
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            self.assertEqual(data["total"], 3)
            self.assertEqual(data["top_rules"][0]["rule_id"], "SEC003")
            self.assertEqual(data["top_rules"][0]["count"], 2)
            self.assertEqual(data["by_severity"]["medium"], 2)
            self.assertEqual(data["by_severity"]["high"], 1)
            self.assertEqual(data["introduced"], 1)

    def test_report_trends_missing_file_empty_exit_zero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            res = _run_cli("report-trends", "--root", str(root), "--format", "json")
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            self.assertEqual(data["total"], 0)
            self.assertEqual(data["top_rules"], [])

    def test_report_trends_text_runs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            res = _run_cli("report-trends", "--root", str(root), "--format", "text")
            self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == "__main__":
    unittest.main()
