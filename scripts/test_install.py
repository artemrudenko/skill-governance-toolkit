#!/usr/bin/env python3
"""Behavior tests for installer safety affordances."""

from __future__ import annotations

import re
import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
RUNTIME_MANIFEST = SCRIPTS_DIR / "runtime-manifest.txt"

# Files that must NEVER ship into an install target — dev/test/release tooling.
DEV_ONLY_NEVER_SHIP = (
    "install.sh",
    "sync_version.py",
    "audit.sh",
    "generate_subset_agents_md.py",
)
# Runtime files an end install must be able to find (CLI/MCP/skill smoke set).
RUNTIME_SMOKE = ("agent_governance_mcp.py", "sgt.py", "checkpoint.py", "agent_audit.py")

# Matches `scripts/<name>.py|sh` references inside instruction files.
_SCRIPT_REF_RE = re.compile(r"scripts/([A-Za-z0-9_.-]+\.(?:py|sh))")
# Matches a leading `from X` / `import X` module token.
_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)")


def _load_manifest() -> list[str]:
    names: list[str] = []
    for line in RUNTIME_MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names


class InstallBehaviorTests(unittest.TestCase):
    def test_project_dry_run_prints_plan_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            result = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts" / "install.sh"),
                    "--claude",
                    "--project",
                    f"--target-project={target}",
                    "--dry-run",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Dry-run install plan", result.stdout)
            self.assertIn("No files will be written", result.stdout.replace("no files", "No files"))
            self.assertFalse((target / "AGENTS.md").exists())
            self.assertFalse((target / ".claude").exists())
            self.assertFalse((target / "skills").exists())

    def test_root_installer_forwards_dry_run_in_yes_default_mode(self) -> None:
        result = subprocess.run(
            ["bash", str(ROOT / "install.sh"), "--yes-default", "--dry-run"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Dry-run install plan", result.stdout)

    def test_powershell_installer_accepts_dry_run_when_available(self) -> None:
        if not shutil.which("pwsh"):
            self.skipTest("pwsh not installed")
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(ROOT / "install.ps1"), "-YesDefault", "-DryRun"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Dry-run install plan", result.stdout)


class RuntimeManifestTests(unittest.TestCase):
    """The runtime whitelist is the single source of truth for what ships."""

    def test_manifest_exists_and_nonempty(self) -> None:
        self.assertTrue(RUNTIME_MANIFEST.exists(), "scripts/runtime-manifest.txt missing")
        self.assertTrue(_load_manifest(), "runtime manifest is empty")

    def test_manifest_entries_exist_on_disk(self) -> None:
        for name in _load_manifest():
            self.assertTrue((SCRIPTS_DIR / name).exists(), f"manifest lists missing script: {name}")

    def test_manifest_excludes_dev_only(self) -> None:
        names = set(_load_manifest())
        for dev in DEV_ONLY_NEVER_SHIP:
            self.assertNotIn(dev, names, f"{dev} must not be in the runtime manifest")
        leaked_tests = sorted(n for n in names if n.startswith("test_"))
        self.assertFalse(leaked_tests, f"test files in manifest: {leaked_tests}")

    def test_manifest_is_import_closed(self) -> None:
        """Every sibling module imported by a whitelisted script must also ship."""
        names = set(_load_manifest())
        local_modules = {p.stem for p in SCRIPTS_DIR.glob("*.py")}
        for name in names:
            if not name.endswith(".py"):
                continue
            for line in (SCRIPTS_DIR / name).read_text(encoding="utf-8").splitlines():
                m = _IMPORT_RE.match(line)
                if not m:
                    continue
                mod = m.group(1)
                if mod in local_modules:
                    self.assertIn(
                        f"{mod}.py", names,
                        f"{name} imports sibling '{mod}' but {mod}.py is not whitelisted",
                    )

    def test_skill_referenced_scripts_are_whitelisted(self) -> None:
        """No shipped instruction file may point at a script we don't install."""
        names = set(_load_manifest())
        referenced: set[str] = set()
        for sub in ("skills", "references", "agents", "commands"):
            base = ROOT / sub
            if not base.exists():
                continue
            for path in base.rglob("*.md"):
                text = path.read_text(encoding="utf-8", errors="ignore")
                referenced.update(m.group(1) for m in _SCRIPT_REF_RE.finditer(text))
        missing = sorted(referenced - names)
        self.assertFalse(missing, f"runtime files reference non-whitelisted scripts: {missing}")

    def test_dockerfile_scripts_are_whitelisted(self) -> None:
        names = set(_load_manifest())
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        for m in _SCRIPT_REF_RE.finditer(text):
            self.assertIn(m.group(1), names, f"Dockerfile copies non-whitelisted {m.group(1)}")


class InstallContentTests(unittest.TestCase):
    """A real install must carry runtime helpers but no dev/test/release tooling."""

    def _install_all(self, target: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(ROOT / "scripts" / "install.sh"),
             "--all", "--project", f"--target-project={target}", *extra],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def test_no_dev_files_land_in_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            r = self._install_all(target)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for pattern in ("test_*.py", "install.sh", "sync_version.py", "audit.sh"):
                hits = [str(p.relative_to(target)) for p in target.rglob(pattern)]
                self.assertFalse(hits, f"dev file '{pattern}' leaked into install: {hits}")

    def test_runtime_scripts_present_in_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            r = self._install_all(target)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for needed in RUNTIME_SMOKE:
                self.assertTrue(list(target.rglob(needed)), f"runtime script {needed} missing from install")


class UpgradeSafetyTests(unittest.TestCase):
    """--upgrade must never delete or clobber a user's own files."""

    USER_FILES = (
        "references/my-api.md",
        "commands/my-cmd.md",
        "agents/my-agent.md",
        ".claude/references/my-host-ref.md",
        ".gemini/commands/my-host-cmd.md",
    )

    def _install(self, target: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(ROOT / "scripts" / "install.sh"),
             "--all", "--project", f"--target-project={target}", *extra],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def test_user_owned_files_survive_fresh_and_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            for rel in self.USER_FILES:
                p = target / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("USER CONTENT", encoding="utf-8")
            r1 = self._install(target)
            self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
            r2 = self._install(target, "--upgrade")
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            for rel in self.USER_FILES:
                p = target / rel
                self.assertTrue(p.exists(), f"user file {rel} was deleted by --upgrade")
                self.assertEqual(p.read_text(encoding="utf-8"), "USER CONTENT",
                                 f"user file {rel} was clobbered")

    def test_toolkit_files_present_after_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self.assertEqual(self._install(target).returncode, 0)
            self.assertEqual(self._install(target, "--upgrade").returncode, 0)
            self.assertTrue(list(target.rglob("copilot-tools.md")),
                            "toolkit reference missing after upgrade")

    def test_user_file_named_like_ours_preserved_on_fresh(self) -> None:
        """A pre-existing user file colliding with our name keeps its content."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            collide = target / "references" / "copilot-tools.md"
            collide.parent.mkdir(parents=True, exist_ok=True)
            collide.write_text("USER OVERRIDE", encoding="utf-8")
            self.assertEqual(self._install(target).returncode, 0)
            # user's content must still be recoverable (ours conflict-renamed)
            self.assertEqual(collide.read_text(encoding="utf-8"), "USER OVERRIDE",
                             "user's same-named file was clobbered on fresh install")


if __name__ == "__main__":
    unittest.main(verbosity=2)
