#!/usr/bin/env python3
"""Behavior tests for filter_skills.py — the single canonical decoder of the
installer's selection semantics (--category / --tier / --skill / --filtered-index)
plus the --info-summary aggregator that closes the info-lane loop.

A bug in apply_filters silently installs the wrong skill subset while the rest of
the suite stays green, so these assertions are installer-critical."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
SCRIPT = ROOT / "scripts" / "filter_skills.py"


def _entry(name: str, tier: str, categories: list[str]) -> str:
    """One INDEX.jsonl line with the metainfo the filter reads."""
    cats = ",".join(f'"{c}"' for c in categories)
    return (
        f'{{"name":"{name}","path":"skills/{name}/SKILL.md",'
        f'"metainfo":{{"category":[{cats}],"tier":"{tier}"}}}}'
    )


class ApplyFiltersTests(unittest.TestCase):
    """Exercise the selection logic install.sh shells into at runtime."""

    # A fixture corpus spanning every tier and a couple of categories.
    CORPUS = [
        _entry("stable-gov", "stable", ["governance"]),
        _entry("preview-disc", "preview", ["discovery"]),
        _entry("exp-test", "experimental", ["testing"]),
        _entry("internal-tool", "internal", ["governance"]),
        '{"name":"orphan","path":"skills/orphan/SKILL.md"}',  # no metainfo → tier unknown
    ]

    def _index(self) -> Path:
        tmp = Path(tempfile.mkdtemp()) / "INDEX.jsonl"
        tmp.write_text("\n".join(self.CORPUS) + "\n", encoding="utf-8")
        return tmp

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(SCRIPT), "--index", str(self._index()), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def _names(self, result: subprocess.CompletedProcess[str]) -> list[str]:
        return [line for line in result.stdout.splitlines() if line.strip()]

    def test_default_tier_installs_only_stable_and_preview(self) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._names(result), ["stable-gov", "preview-disc"])

    def test_default_excludes_experimental_internal_and_orphan(self) -> None:
        names = self._names(self._run())
        for excluded in ("exp-test", "internal-tool", "orphan"):
            self.assertNotIn(excluded, names)

    def test_category_filter_is_or_matching(self) -> None:
        names = self._names(self._run("--category", "governance,discovery"))
        # Both stable-gov (governance) and preview-disc (discovery) survive; the
        # experimental testing skill is still tier-excluded.
        self.assertEqual(names, ["stable-gov", "preview-disc"])

    def test_category_filter_still_applies_tier(self) -> None:
        # testing only lives on an experimental skill → empty under default tier.
        self.assertEqual(self._names(self._run("--category", "testing")), [])

    def test_explicit_tier_opts_into_experimental(self) -> None:
        names = self._names(self._run("--tier", "experimental"))
        self.assertEqual(names, ["exp-test"])

    def test_skill_list_overrides_tier_and_category(self) -> None:
        # internal-tool would be tier-excluded by default, but an explicit --skill
        # name is a hard override (user named it, they get it).
        names = self._names(self._run("--skill", "internal-tool,exp-test"))
        self.assertEqual(sorted(names), ["exp-test", "internal-tool"])

    def test_tier_unknown_opts_into_orphans(self) -> None:
        self.assertEqual(self._names(self._run("--tier", "unknown")), ["orphan"])

    def test_filtered_index_emits_exactly_matching_jsonl(self) -> None:
        result = self._run("--filtered-index")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self._names(result)
        # One JSON object per surviving skill, and only the surviving skills.
        self.assertEqual(len(lines), 2)
        self.assertIn('"name":"stable-gov"', "".join(lines))
        self.assertIn('"name":"preview-disc"', "".join(lines))
        self.assertNotIn("exp-test", "".join(lines))

    def test_missing_index_exits_nonzero(self) -> None:
        result = subprocess.run(
            [PYTHON, str(SCRIPT), "--index", "/no/such/INDEX.jsonl"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)


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
