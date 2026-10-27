#!/usr/bin/env python3
"""Unit tests for build_index.py's hand-rolled YAML-subset parser and writer.

build_index owns the INDEX.jsonl pipeline the installer's selective filters read.
Its `_parse_yaml_lines` / `_coerce` are a fragile bespoke parser (block scalars,
nested maps, a deep 6-space `requires.mcp` branch, flow-style lists) previously
covered only INDIRECTLY by the audit.sh P8 round-trip against real SKILL.md
fixtures. These lock the parser contract independent of those fixtures."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import build_index


class CoerceTests(unittest.TestCase):
    def test_scalar_primitives(self) -> None:
        self.assertEqual(build_index._coerce("42"), 42)
        self.assertEqual(build_index._coerce("3.14"), 3.14)
        self.assertIs(build_index._coerce("true"), True)
        self.assertIs(build_index._coerce("yes"), True)
        self.assertIs(build_index._coerce("false"), False)
        self.assertIs(build_index._coerce("no"), False)
        self.assertIsNone(build_index._coerce("null"))
        self.assertIsNone(build_index._coerce("~"))
        self.assertEqual(build_index._coerce("plain text"), "plain text")

    def test_quoted_strings_keep_inner_text(self) -> None:
        self.assertEqual(build_index._coerce('"42"'), "42")   # quoted → stays string
        self.assertEqual(build_index._coerce("'governance'"), "governance")

    def test_flow_style_list(self) -> None:
        self.assertEqual(build_index._coerce("[a, b, c]"), ["a", "b", "c"])
        self.assertEqual(build_index._coerce("[]"), [])
        # Documented limitation: the naive comma split does NOT handle quoted
        # commas. We assert the CURRENT contract so a future fix is a deliberate
        # change, not an accidental one.
        self.assertEqual(build_index._coerce('["a, b"]'), ['"a', 'b"'])


class ParseYamlLinesTests(unittest.TestCase):
    def test_inline_scalar_and_block_scalar(self) -> None:
        fm = build_index._parse_yaml_lines([
            "name: skill-find",
            "description: |",
            "  first line",
            "  second line",
        ])
        self.assertEqual(fm["name"], "skill-find")
        self.assertEqual(fm["description"], "first line\nsecond line")

    def test_category_scalar_vs_inline_list(self) -> None:
        scalar = build_index._parse_yaml_lines(["category: governance"])
        self.assertEqual(scalar["category"], "governance")
        listed = build_index._parse_yaml_lines(["category: [governance, discovery]"])
        self.assertEqual(listed["category"], ["governance", "discovery"])

    def test_nested_two_space_map(self) -> None:
        fm = build_index._parse_yaml_lines([
            "metainfo:",
            "  category: governance",
            "  tier: stable",
        ])
        self.assertEqual(fm["metainfo"], {"category": "governance", "tier": "stable"})

    def test_block_style_list(self) -> None:
        fm = build_index._parse_yaml_lines([
            "tags:",
            "  - alpha",
            "  - beta",
        ])
        self.assertEqual(fm["tags"], ["alpha", "beta"])

    def test_deep_six_space_requires_mcp_block_list(self) -> None:
        # The fragile branch: a 6-space block-style list under metainfo.requires.mcp.
        # Regression target — it previously parsed to None and tripped a false MCP001.
        fm = build_index._parse_yaml_lines([
            "metainfo:",
            "  category: governance",
            "  tier: stable",
            "  requires:",
            "    mcp:",
            "      - serena",
            "      - repomix",
        ])
        self.assertEqual(
            fm["metainfo"],
            {"category": "governance", "tier": "stable",
             "requires": {"mcp": ["serena", "repomix"]}},
        )


class FrontmatterTests(unittest.TestCase):
    def test_absent_frontmatter_returns_none(self) -> None:
        self.assertIsNone(build_index.parse_frontmatter("# just a heading\n"))

    def test_frontmatter_extracted(self) -> None:
        fm = build_index.parse_frontmatter("---\nname: x\n---\nbody\n")
        self.assertEqual(fm, {"name": "x"})

    def test_standard_metadata_keeps_index_shape_and_legacy_fallback(self) -> None:
        fm = build_index.parse_frontmatter(
            '---\nname: sample\nmetadata:\n  sgt-category: "governance, discovery"\n'
            '  sgt-tier: "preview"\n  sgt-requires-mcp: "serena, repomix"\n'
            'metainfo:\n  category: [testing]\n  tier: stable\n  owner: alice\n---\nbody\n'
        )
        self.assertEqual(build_index.governance_metadata(fm), {
            "category": ["governance", "discovery"], "tier": "preview",
            "owner": "alice", "requires": {"mcp": ["serena", "repomix"]},
        })

    def test_plain_standard_metadata_does_not_create_governance_fields(self) -> None:
        self.assertEqual(build_index.governance_metadata({"metadata": {"author": "alice"}}), {})

    def test_bundled_skills_use_standard_top_level_fields_and_string_metadata(self) -> None:
        root = Path(__file__).resolve().parents[1]
        allowed = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
        paths = list((root / "skills").glob("*/SKILL.md"))
        self.assertTrue(paths, "no bundled skills found")
        for path in paths:
            fm = build_index.parse_frontmatter(path.read_text(encoding="utf-8"))
            self.assertFalse(set(fm) - allowed, str(path))
            self.assertTrue(all(isinstance(value, str) for value in fm.get("metadata", {}).values()), str(path))


class ScalarCategoryNormalizationTests(unittest.TestCase):
    def test_scalar_category_emitted_as_list(self) -> None:
        # `category: governance` (scalar) passes the audit engine, but a scalar
        # in INDEX.jsonl makes filter_skills intersect by CHARACTER and doctor
        # count letters. The canonical writer must normalize it to a list.
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skills" / "demo-audit"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: demo-audit\n"
                "description: demo skill for index tests\n"
                "metainfo:\n"
                "  category: governance\n"
                "  tier: preview\n"
                "---\n"
                "body\n",
                encoding="utf-8",
            )
            entries = build_index.build_index(Path(tmp) / "skills")
            self.assertEqual(entries[0]["metainfo"]["category"], ["governance"])


class WriteIndexRoundTripTests(unittest.TestCase):
    def test_jsonl_round_trip(self) -> None:
        entries = [
            {"name": "skill-find", "metainfo": {"category": "discovery", "tier": "stable"}},
            {"name": "library-audit", "metainfo": {"category": ["governance"], "tier": "preview"}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "INDEX.jsonl"
            build_index.write_index(entries, out)
            text = out.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            parsed = [json.loads(line) for line in text.splitlines() if line.strip()]
            self.assertEqual(parsed, entries)


if __name__ == "__main__":
    unittest.main()
