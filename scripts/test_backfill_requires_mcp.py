#!/usr/bin/env python3
"""Behavior tests for backfill_requires_mcp.py — the one-time metainfo.requires.mcp
migration codemod. Uses subprocess against the CLI + the real engine for the
MCP001-gone assertion."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import agent_audit
import build_index

SCRIPT = Path(__file__).resolve().parent / "backfill_requires_mcp.py"


def _skill(body: str, *, requires_mcp: str | None = None) -> str:
    """Build a minimal valid SKILL.md. `requires_mcp` is the flow-style list text
    (e.g. "[github]") inserted as `mcp:` under metainfo.requires, or None to omit."""
    lines = [
        "---",
        "name: x",
        "description: " + ("a" * 90),
        "compatibility: [claude]",
        "license: MIT",
        "metainfo:",
        "  category: [governance]",
        "  tier: preview",
    ]
    if requires_mcp is not None:
        lines += ["  requires:", f"    mcp: {requires_mcp}"]
    lines += ["---", "", "## When to use", body, "> **Skill type:** Detect-only", ""]
    return "\n".join(lines)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(SCRIPT.parent),
        capture_output=True,
        text=True,
    )


class DryRunTests(unittest.TestCase):
    def test_dry_run_reports_missing_and_leaves_file_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "skills" / "demo" / "SKILL.md"
            p.parent.mkdir(parents=True)
            text = _skill("Run mcp__github__search to find issues. verify.")
            p.write_text(text, encoding="utf-8")

            r = _run("--root", d)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("github", r.stdout)
            self.assertIn(str(p), r.stdout)
            # File untouched in dry-run.
            self.assertEqual(p.read_text(encoding="utf-8"), text)

    def test_skill_with_no_mcp_usage_is_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "skills" / "demo" / "SKILL.md"
            p.parent.mkdir(parents=True)
            text = _skill("This skill does ordinary work. verify.")
            p.write_text(text, encoding="utf-8")

            r = _run("--root", d, "--apply")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(p.read_text(encoding="utf-8"), text)

    def test_fenced_code_block_usage_is_not_backfilled(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "skills" / "demo" / "SKILL.md"
            p.parent.mkdir(parents=True)
            body = "Example only:\n\n```\nmcp__github__search\n```\n\nverify."
            text = _skill(body)
            p.write_text(text, encoding="utf-8")

            r = _run("--root", d, "--apply")
            self.assertEqual(r.returncode, 0, r.stderr)
            # No real usage → no backfill → bytes identical.
            self.assertEqual(p.read_text(encoding="utf-8"), text)

    def test_already_declared_server_no_change(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "skills" / "demo" / "SKILL.md"
            p.parent.mkdir(parents=True)
            text = _skill("Run mcp__github__search. verify.", requires_mcp="[github]")
            p.write_text(text, encoding="utf-8")

            dry = _run("--root", d)
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertEqual(p.read_text(encoding="utf-8"), text)

            applied = _run("--root", d, "--apply")
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(p.read_text(encoding="utf-8"), text)


class ApplyTests(unittest.TestCase):
    def test_apply_creates_requires_block_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "skills" / "demo" / "SKILL.md"
            p.parent.mkdir(parents=True)
            text = _skill("Run mcp__github__search. verify.")
            p.write_text(text, encoding="utf-8")

            r = _run("--root", d, "--apply")
            self.assertEqual(r.returncode, 0, r.stderr)

            new_text = p.read_text(encoding="utf-8")
            fm = build_index.parse_frontmatter(new_text)
            self.assertIsNotNone(fm)
            assert fm is not None
            self.assertEqual(fm["metainfo"]["requires"]["mcp"], ["github"])
            # Existing metainfo sub-keys preserved.
            self.assertEqual(fm["metainfo"]["category"], ["governance"])
            self.assertEqual(fm["metainfo"]["tier"], "preview")

    def test_apply_clears_mcp001_in_real_engine(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "skills" / "demo" / "SKILL.md"
            p.parent.mkdir(parents=True)
            p.write_text(_skill("Run mcp__github__search. verify."), encoding="utf-8")

            # Before: MCP001 present.
            before = {f["rule_id"] for f in agent_audit.audit_skill(p)["findings"]}
            self.assertIn("MCP001", before)

            r = _run("--root", d, "--apply")
            self.assertEqual(r.returncode, 0, r.stderr)

            # After: no MCP001 for the backfilled server.
            after = agent_audit.audit_skill(p)["findings"]
            mcp001 = [f for f in after if f["rule_id"] == "MCP001"]
            self.assertEqual(mcp001, [], f"MCP001 should be gone: {mcp001}")

    def test_apply_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "skills" / "demo" / "SKILL.md"
            p.parent.mkdir(parents=True)
            p.write_text(_skill("Run mcp__github__search. verify."), encoding="utf-8")

            _run("--root", d, "--apply")
            first = p.read_text(encoding="utf-8")
            _run("--root", d, "--apply")
            second = p.read_text(encoding="utf-8")
            self.assertEqual(first, second)

    def test_apply_appends_to_existing_requires_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "skills" / "demo" / "SKILL.md"
            p.parent.mkdir(parents=True)
            # Declares serena, uses both serena and github.
            body = "Run mcp__serena__find and mcp__github__search. verify."
            p.write_text(_skill(body, requires_mcp="[serena]"), encoding="utf-8")

            r = _run("--root", d, "--apply")
            self.assertEqual(r.returncode, 0, r.stderr)

            fm = build_index.parse_frontmatter(p.read_text(encoding="utf-8"))
            assert fm is not None
            self.assertEqual(sorted(fm["metainfo"]["requires"]["mcp"]), ["github", "serena"])
            after = agent_audit.audit_skill(p)["findings"]
            self.assertEqual([f for f in after if f["rule_id"] == "MCP001"], [])

    def test_single_skill_flag(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "SKILL.md"
            p.write_text(_skill("Run mcp__github__search. verify."), encoding="utf-8")

            r = _run("--skill", str(p), "--apply")
            self.assertEqual(r.returncode, 0, r.stderr)
            fm = build_index.parse_frontmatter(p.read_text(encoding="utf-8"))
            assert fm is not None
            self.assertEqual(fm["metainfo"]["requires"]["mcp"], ["github"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
