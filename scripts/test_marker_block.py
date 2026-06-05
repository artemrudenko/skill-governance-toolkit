#!/usr/bin/env python3
"""Behavior tests for marker_block.py — the managed-block writer used by the
installer for the four USER-OWNED project files. These guard the toolkit's
"we never overwrite your files" guarantee: content OUTSIDE the markers must
survive create / upgrade / re-run / uninstall."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import marker_block


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
MARKER = marker_block.DEFAULT_MARKER_ID
BEGIN = f"<!-- {MARKER}: BEGIN -->"
END = f"<!-- {MARKER}: END -->"


class MarkerBlockTests(unittest.TestCase):
    def _src(self, tmp: Path, content: str, name: str = "src.md") -> str:
        path = tmp / name
        path.write_text(content, encoding="utf-8")
        return str(path)

    def test_creates_file_with_managed_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dest = tmp_path / "AGENTS.md"
            src = self._src(tmp_path, "RULE ONE")

            rc = marker_block.upsert(str(dest), src, MARKER)

            self.assertEqual(rc, 0)
            text = dest.read_text(encoding="utf-8")
            self.assertIn(BEGIN, text)
            self.assertIn(END, text)
            self.assertIn("RULE ONE", text)

    def test_appends_block_preserving_existing_user_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dest = tmp_path / "AGENTS.md"
            dest.write_text("# My project rules\n\nDo not break things.\n", encoding="utf-8")
            src = self._src(tmp_path, "MANAGED RULE")

            marker_block.upsert(str(dest), src, MARKER)

            text = dest.read_text(encoding="utf-8")
            # User content stays at the top; managed block is appended below it.
            self.assertTrue(text.startswith("# My project rules"))
            self.assertIn("Do not break things.", text)
            self.assertLess(text.index("Do not break things."), text.index(BEGIN))

    def test_rerun_is_idempotent_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dest = tmp_path / "AGENTS.md"
            src = self._src(tmp_path, "STABLE RULE")

            marker_block.upsert(str(dest), src, MARKER)
            first = dest.read_text(encoding="utf-8")
            rc = marker_block.upsert(str(dest), src, MARKER)
            second = dest.read_text(encoding="utf-8")

            self.assertEqual(rc, 0)
            self.assertEqual(first, second)  # no drift on re-run

    def test_update_replaces_block_preserving_content_around_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dest = tmp_path / "AGENTS.md"
            marker_block.upsert(str(dest), self._src(tmp_path, "OLD MANAGED"), MARKER)
            # Wrap the managed block with user content on BOTH sides.
            wrapped = "USER HEADER\n\n" + dest.read_text(encoding="utf-8").rstrip() + "\n\nUSER FOOTER\n"
            dest.write_text(wrapped, encoding="utf-8")

            marker_block.upsert(str(dest), self._src(tmp_path, "NEW MANAGED", name="src2.md"), MARKER)

            text = dest.read_text(encoding="utf-8")
            self.assertIn("USER HEADER", text)
            self.assertIn("USER FOOTER", text)
            self.assertIn("NEW MANAGED", text)
            self.assertNotIn("OLD MANAGED", text)  # in-place replacement, not duplication
            self.assertEqual(text.count(BEGIN), 1)

    def test_remove_strips_block_preserving_user_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dest = tmp_path / "AGENTS.md"
            dest.write_text("KEEP ME\n", encoding="utf-8")
            marker_block.upsert(str(dest), self._src(tmp_path, "MANAGED"), MARKER)

            marker_block.remove(str(dest), MARKER)

            text = dest.read_text(encoding="utf-8")
            self.assertIn("KEEP ME", text)
            self.assertNotIn(BEGIN, text)
            self.assertNotIn("MANAGED", text)

    def test_remove_deletes_file_that_was_only_the_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dest = tmp_path / "AGENTS.md"
            marker_block.upsert(str(dest), self._src(tmp_path, "MANAGED ONLY"), MARKER)

            marker_block.remove(str(dest), MARKER)

            self.assertFalse(dest.exists())

    def test_custom_marker_id_isolates_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dest = tmp_path / "AGENTS.md"
            marker_block.upsert(str(dest), self._src(tmp_path, "ALPHA"), "team-a")

            text = dest.read_text(encoding="utf-8")
            self.assertIn("<!-- team-a: BEGIN -->", text)
            self.assertNotIn(BEGIN, text)

    def test_cli_upsert_wiring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dest = tmp_path / "AGENTS.md"
            src = self._src(tmp_path, "CLI RULE")

            result = subprocess.run(
                [PYTHON, str(ROOT / "scripts" / "marker_block.py"), "upsert", "--file", str(dest), "--src", src],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("CLI RULE", dest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
