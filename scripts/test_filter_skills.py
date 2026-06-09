#!/usr/bin/env python3
"""Behavior tests for filter_skills.py — focused on the --info-summary aggregator
that closes the info-lane loop (sum info_flags.* across out/scores/index.jsonl)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
SCRIPT = ROOT / "scripts" / "filter_skills.py"


class InfoSummaryTests(unittest.TestCase):
    def _run(self, index: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(SCRIPT), "--index", str(index), "--info-summary"],
            text=True,
            capture_output=True,
            check=False,
        )

    def _write_scores(self, lines: list[str]) -> Path:
        tmp = Path(tempfile.mkdtemp()) / "scores.jsonl"
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return tmp

    def test_aggregates_info_flags_with_total_and_affected(self) -> None:
        index = self._write_scores(
            [
                '{"skill_name":"a","info_flags":{"negative_rule_placement":2}}',
                '{"skill_name":"b","info_flags":{"negative_rule_placement":0}}',
                '{"skill_name":"c","info_flags":{"negative_rule_placement":1}}',
                '{"skill_name":"d"}',
            ]
        )
        result = self._run(index)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Row format: info\t<flag>\t<total>\t<skills_affected>
        self.assertIn("info\tnegative_rule_placement\t3\t2", result.stdout)

    def test_multiple_flags_each_summed(self) -> None:
        index = self._write_scores(
            [
                '{"skill_name":"a","info_flags":{"negative_rule_placement":1,"other_signal":4}}',
                '{"skill_name":"b","info_flags":{"other_signal":1}}',
            ]
        )
        result = self._run(index)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("info\tnegative_rule_placement\t1\t1", result.stdout)
        self.assertIn("info\tother_signal\t5\t2", result.stdout)

    def test_no_info_flags_reports_nothing_but_succeeds(self) -> None:
        index = self._write_scores(['{"skill_name":"a"}', '{"skill_name":"b"}'])
        result = self._run(index)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("info\t", result.stdout)


if __name__ == "__main__":
    unittest.main()
