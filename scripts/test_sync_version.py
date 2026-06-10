#!/usr/bin/env python3
"""Behavior tests for VERSION metadata synchronization."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


class SyncVersionBehaviorTests(unittest.TestCase):
    def run_sync(self, *args: str, root: Path = ROOT) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "sync_version.py"), "--root", str(root), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def write_minimal_tree(self, root: Path, version: str, derived_version: str) -> None:
        (root / ".claude-plugin").mkdir()
        (root / ".codex-plugin").mkdir()
        (root / "VERSION").write_text(version + "\n", encoding="utf-8")
        (root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "x", "version": derived_version}) + "\n",
            encoding="utf-8",
        )
        (root / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps(
                {
                    "metadata": {"version": derived_version},
                    "plugins": [{"version": derived_version}],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (root / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "x", "version": derived_version}) + "\n",
            encoding="utf-8",
        )
        (root / "gemini-extension.json").write_text(
            json.dumps({"name": "x", "version": derived_version}) + "\n",
            encoding="utf-8",
        )
        (root / "pyproject.toml").write_text(
            f'[project]\nname = "x"\nversion = "{derived_version}"\n',
            encoding="utf-8",
        )
        (root / "README.md").write_text(
            f"Install skill-governance-toolkit@{derived_version}\n"
            f"gemini extensions install ...@{derived_version}\n",
            encoding="utf-8",
        )
        (root / "CHANGELOG.md").write_text(f"# Changelog\n\n## [{version}] - test\n", encoding="utf-8")

    def test_current_project_version_metadata_is_in_sync(self) -> None:
        result = self.run_sync("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("version metadata ok", result.stdout)

    def test_check_succeeds_from_foreign_cwd_without_root_flag(self) -> None:
        # Default --root must resolve from the script location, not CWD.
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [PYTHON, str(ROOT / "scripts" / "sync_version.py"), "--check"],
                cwd=tmp,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("version metadata ok", result.stdout)

    def test_check_detects_drift_without_mutating_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_minimal_tree(root, "1.2.3", "9.9.9")
            original = (root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")

            result = self.run_sync("--check", root=root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("version metadata drift", result.stderr)
            self.assertEqual((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"), original)

    def test_sync_updates_derived_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_minimal_tree(root, "1.2.3", "9.9.9")

            result = self.run_sync(root=root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            codex = json.loads((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
            self.assertEqual(codex["version"], "1.2.3")
            self.assertIn("skill-governance-toolkit@1.2.3", (root / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
