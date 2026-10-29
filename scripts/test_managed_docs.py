#!/usr/bin/env python3
"""Regression tests for documentation updates and preservation."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from managed_docs import MARKER, install_docs, load_hashes, managed_unchanged
from sgt import _plan_install_dir

ROOT = Path(__file__).resolve().parents[1]


class ManagedDocsTests(unittest.TestCase):
    def test_project_installer_upgrade_and_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = root / "source", root / "project"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "assets", "__pycache__", "*.zip"))
            target.mkdir()
            guide = source / "docs" / "github-onboarding.md"
            guide.write_text("release one", encoding="utf-8")
            args = ["bash", str(source / "scripts" / "install.sh"), "--codex", "--project",
                    f"--target-project={target}", "--skill", "skill-find"]
            def run(*extra: str) -> subprocess.CompletedProcess[str]:
                result = subprocess.run(args + list(extra), cwd=target, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result
            run()
            guide.write_text("release two", encoding="utf-8")
            run("--upgrade")
            installed = target / "docs" / "github-onboarding.md"
            self.assertEqual(installed.read_text(), "release two")
            installed.write_text("my project edits", encoding="utf-8")
            guide.write_text("release three", encoding="utf-8")
            run("--upgrade")
            incoming = target / "docs" / "github-onboarding.skill-governance-toolkit.md"
            self.assertEqual(incoming.read_text(), "release three")
            incoming.write_text("my edits in alternate", encoding="utf-8")
            guide.write_text("release four", encoding="utf-8")
            run("--upgrade")
            self.assertEqual(installed.read_text(), "my project edits")
            self.assertEqual(incoming.read_text(), "my edits in alternate")
            self.assertEqual((target / "docs" / "github-onboarding.skill-governance-toolkit.1.md").read_text(), "release four")
            removal = subprocess.run([sys.executable, str(source / "scripts" / "sgt.py"), "uninstall",
                                      "--scope", "project", "--target-project", str(target), "--yes"],
                                     cwd=target, capture_output=True, text=True)
            self.assertEqual(removal.returncode, 0, removal.stdout + removal.stderr)
            self.assertEqual(installed.read_text(), "my project edits")
            self.assertEqual(incoming.read_text(), "my edits in alternate")

    def test_unchanged_owned_doc_updates_and_user_edits_survive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = root / "source", root / "project" / "docs"
            source.mkdir()
            (source / "guide.md").write_text("old", encoding="utf-8")
            install_docs(source, target)
            (source / "guide.md").write_text("new", encoding="utf-8")
            install_docs(source, target)
            self.assertEqual((target / "guide.md").read_text(), "new")
            self.assertFalse((target / "guide.skill-governance-toolkit.md").exists())
            (target / "guide.md").write_text("user edit", encoding="utf-8")
            (source / "guide.md").write_text("newer", encoding="utf-8")
            install_docs(source, target)
            alt = target / "guide.skill-governance-toolkit.md"
            self.assertEqual((target / "guide.md").read_text(), "user edit")
            self.assertEqual(alt.read_text(), "newer")
            alt.write_text("edited alternate", encoding="utf-8")
            (source / "guide.md").write_text("latest", encoding="utf-8")
            install_docs(source, target)
            self.assertEqual(alt.read_text(), "edited alternate")
            self.assertEqual((target / "guide.skill-governance-toolkit.1.md").read_text(), "latest")
            install_docs(source, target)
            self.assertFalse((target / "guide.skill-governance-toolkit.2.md").exists())
            self.assertEqual((target / "guide.md").read_text(), "user edit")
            _, files, _ = _plan_install_dir(root / "project", set(), [], None)
            self.assertNotIn(target / "guide.md", files)
            self.assertNotIn(alt, files)
            self.assertIn(target / "guide.skill-governance-toolkit.1.md", files)

    def test_legacy_and_identical_unowned_docs_are_not_claimed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = root / "source", root / "project" / "docs"
            source.mkdir()
            target.mkdir(parents=True)
            (source / "guide.md").write_text("new", encoding="utf-8")
            (target / "guide.md").write_text("old", encoding="utf-8")
            (target / ".sgt-owned").write_text("guide.md\n", encoding="utf-8")
            (source / "same.md").write_text("same", encoding="utf-8")
            (target / "same.md").write_text("same", encoding="utf-8")
            install_docs(source, target)
            hashes = load_hashes(target)
            self.assertNotIn("guide.md", hashes)
            self.assertNotIn("same.md", hashes)
            self.assertEqual((target / "guide.md").read_text(), "old")
            self.assertEqual((target / "guide.skill-governance-toolkit.md").read_text(), "new")
            _, files, _ = _plan_install_dir(root / "project", set(), [], None)
            self.assertNotIn(target / "guide.md", files)
            self.assertNotIn(target / "same.md", files)

    def test_corrupt_hash_manifest_fails_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = root / "source", root / "target"
            source.mkdir()
            target.mkdir()
            (source / "guide.md").write_text("new", encoding="utf-8")
            (target / "guide.md").write_text("custom", encoding="utf-8")
            (target / MARKER).write_text("{", encoding="utf-8")
            install_docs(source, target)
            self.assertEqual((target / "guide.md").read_text(), "custom")
            self.assertFalse(managed_unchanged(target, "guide.md", load_hashes(target)))


if __name__ == "__main__":
    unittest.main()
