#!/usr/bin/env python3
"""Behavior tests for installer safety affordances."""

from __future__ import annotations

import os
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

    def test_powershell_installer_real_project_install(self) -> None:
        """Execute the NON-dry-run native PS install path (copy + marker upsert),
        which the dry-run test exits before. Runs on a pwsh-capable runner (the
        ubuntu CI 'windows-parity' job); skips locally when pwsh is absent."""
        if not shutil.which("pwsh"):
            self.skipTest("pwsh not installed")
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                ["pwsh", "-NoProfile", "-File", str(ROOT / "install.ps1"),
                 "-YesDefault", "-TargetProject", tmp],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            target = Path(tmp)
            self.assertTrue((target / "AGENTS.md").exists(), "PS install did not write AGENTS.md")
            self.assertTrue((target / "skills").is_dir(), "PS install did not create skills/")
            self.assertIn(
                "skill-governance-toolkit: BEGIN",
                (target / "AGENTS.md").read_text(encoding="utf-8"),
                "PS install did not upsert the managed marker block",
            )


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

    def test_dockerfile_ships_engine_data_files(self) -> None:
        # The engine loads these JSON data files at runtime; the loaders tolerate
        # absence, so a missing COPY silently disables features (e.g. no
        # unicode-confusables.json -> SEC003 homoglyph detection dies) with no error.
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        for data_file in ("agent-audit-rules.json", "unicode-confusables.json", "audit-ignore.json"):
            self.assertIn(data_file, text,
                          f"Dockerfile must COPY references/{data_file} or its feature degrades silently in the image")


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

    def test_filtered_install_tailors_agents_md_and_skills(self) -> None:
        """A --skill subset install must (a) copy only the requested skill, and
        (b) run generate_subset_agents_md.py so the installed AGENTS.md carries the
        scoped notice and drops other skills' table rows. Covers the bash filter
        wiring (resolve_skill_subset → subset generator → marker upsert)."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            r = subprocess.run(
                ["bash", str(ROOT / "scripts" / "install.sh"),
                 "--claude", "--project", f"--target-project={target}", "--skill", "skill-find"],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            installed_skills = sorted(p.name for p in (target / "skills").iterdir() if p.is_dir())
            self.assertEqual(installed_skills, ["skill-find"], "subset install copied the wrong skills")
            agents = (target / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Scoped install notice", agents)
            self.assertIn("`skill-find`", agents)
            self.assertNotIn("| `library-audit` |", agents)

    def test_security_data_files_ship_into_install(self) -> None:
        """references/*.json data files must land in an install.

        The loaders tolerate absence (graceful degradation), so a silent
        non-ship would disable suppression/confusables/rules unnoticed. This
        guards the packaging contract for the control-plane data files.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            r = self._install_all(target)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for data_file in (
                "audit-ignore.json",
                "unicode-confusables.json",
                "agent-audit-rules.json",
            ):
                self.assertTrue(
                    list(target.rglob(data_file)),
                    f"security data file references/{data_file} missing from install",
                )


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

    def test_user_owned_skill_survives_fresh_and_upgrade(self) -> None:
        """A user's OWN skill dir in the install tree must survive fresh+upgrade.

        skills/ uses a different copy path than refs/commands/agents, so it needs
        its own coverage — a user skill that shares the tree with toolkit skills
        must not be deleted in the default (fresh) or --upgrade modes.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            user_skill = target / "skills" / "my-personal-skill" / "SKILL.md"
            user_skill.parent.mkdir(parents=True, exist_ok=True)
            user_skill.write_text("USER SKILL", encoding="utf-8")
            self.assertEqual(self._install(target).returncode, 0)
            self.assertEqual(self._install(target, "--upgrade").returncode, 0)
            self.assertTrue(user_skill.exists(), "user's own skill was deleted")
            self.assertEqual(user_skill.read_text(encoding="utf-8"), "USER SKILL",
                             "user's own skill was clobbered")
            # And the toolkit's skills landed alongside it.
            self.assertTrue((target / "skills" / "skill-find").exists(),
                            "toolkit skill missing after install")


class TargetProjectFlagTests(unittest.TestCase):
    def test_root_installer_accepts_target_project_flag(self) -> None:
        # install.ps1 forwards --target-project=<path> to the ROOT install.sh on
        # macOS/Linux; the root parser must accept it (it used to exit 1
        # "Unknown flag"), making -TargetProject unusable outside Windows.
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                ["bash", str(ROOT / "install.sh"), "--yes-default", "--dry-run",
                 f"--target-project={tmp}"],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Dry-run install plan", result.stdout)

    def test_target_project_tilde_is_expanded(self) -> None:
        # Bash does not tilde-expand `--target-project=~/x` (expansion after `=`
        # only happens in assignments); the documented usage example therefore
        # failed with cd's terse error. The handler must expand a leading ~/.
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "myapp").mkdir()
            env = dict(os.environ, HOME=str(home))
            result = subprocess.run(
                ["bash", str(ROOT / "scripts" / "install.sh"), "--claude",
                 "--project", "--target-project=~/myapp", "--dry-run"],
                cwd=ROOT, text=True, capture_output=True, check=False, env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Dry-run install plan", result.stdout)

    def test_target_project_missing_dir_fails_with_actionable_error(self) -> None:
        result = subprocess.run(
            ["bash", str(ROOT / "scripts" / "install.sh"), "--claude",
             "--project", "--target-project=/no/such/dir-xyz", "--dry-run"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target-project", (result.stdout + result.stderr).lower())


class CpFallbackPortabilityTests(unittest.TestCase):
    """Without rsync, _smart_copy must copy directory CONTENTS — identical on
    BSD and GNU cp. Plain `cp -R src/ dest` nests src inside an existing dest
    on GNU/Linux, producing a broken install. (The bug is GNU-only, so this is
    a true regression test on Linux CI and a contract pin on macOS.)"""

    def _path_without_rsync(self) -> str:
        farm = Path(tempfile.mkdtemp(prefix="no-rsync-bin."))
        seen: set[str] = set()
        for entry in os.environ.get("PATH", "").split(os.pathsep):
            d = Path(entry)
            if not d.is_dir():
                continue
            for binary in d.iterdir():
                if binary.name in seen or binary.name == "rsync":
                    continue
                if os.access(binary, os.X_OK) and not binary.is_dir():
                    try:
                        (farm / binary.name).symlink_to(binary)
                        seen.add(binary.name)
                    except OSError:
                        pass
        return str(farm)

    def test_install_without_rsync_does_not_nest_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            env = dict(os.environ, PATH=self._path_without_rsync())
            result = subprocess.run(
                ["bash", str(ROOT / "scripts" / "install.sh"), "--claude",
                 "--project", f"--target-project={target}"],
                cwd=ROOT, text=True, capture_output=True, check=False, env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            skill = target / ".claude" / "skills" / "skill-find"
            self.assertTrue((skill / "SKILL.md").exists(),
                            "skill content missing in cp-fallback install")
            self.assertFalse((skill / "skill-find").exists(),
                             "GNU cp nested the source dir inside the destination")


class GlobalScopeSafetyTests(unittest.TestCase):
    """--global writes to ~/.<host>/ — a user's personal skills/scripts there
    must survive the safe modes (fresh + --upgrade). HOME is redirected to a
    temp dir so the test never touches the real home."""

    def _install_global(self, home: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, HOME=str(home))
        return subprocess.run(
            ["bash", str(ROOT / "scripts" / "install.sh"), "--claude", "--global", *extra],
            cwd=ROOT, text=True, capture_output=True, check=False, env=env,
        )

    def test_user_skill_and_script_survive_global_fresh_and_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            user_skill = home / ".claude" / "skills" / "my-personal-skill" / "SKILL.md"
            user_script = home / ".claude" / "scripts" / "my-helper.py"
            for p, body in ((user_skill, "USER SKILL"), (user_script, "print('mine')")):
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(body, encoding="utf-8")
            r1 = self._install_global(home)
            self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
            r2 = self._install_global(home, "--upgrade")
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            self.assertTrue(user_skill.exists(), "user's global skill deleted by install")
            self.assertEqual(user_skill.read_text(encoding="utf-8"), "USER SKILL")
            self.assertTrue(user_script.exists(), "user's global script deleted by install")
            # Toolkit content landed too.
            self.assertTrue((home / ".claude" / "skills" / "skill-find").exists())


class PowerShellParityTests(unittest.TestCase):
    """install.ps1 (Windows-native path) must match bash install-safety guards.

    These are static-source invariants because the $IsWindows branch cannot be
    executed on CI/macOS (it delegates to bash there). They lock in the three
    parity fixes:
      H1 — a -TargetProject param so Windows users can install into their own repo
      H2 — a self-install guard so project scope never pollutes the toolkit's own dir
      H3 — skills/scripts are refreshed per-item, not by wiping the whole managed dir
           (so a global upgrade cannot delete the user's own skills)
    """

    PS1 = ROOT / "install.ps1"

    def setUp(self) -> None:
        self.text = self.PS1.read_text(encoding="utf-8")

    def _function_body(self, name: str) -> str:
        """Return the source between `function <name> {` and its matching close.

        Brace-counting is sufficient here — the installer functions don't embed
        literal unbalanced braces in strings.
        """
        start = self.text.index(f"function {name}")
        i = self.text.index("{", start)
        depth, j = 0, i
        while j < len(self.text):
            if self.text[j] == "{":
                depth += 1
            elif self.text[j] == "}":
                depth -= 1
                if depth == 0:
                    return self.text[i : j + 1]
            j += 1
        raise AssertionError(f"unbalanced braces in function {name}")

    def test_h1_target_project_param_exists(self) -> None:
        self.assertIn("$TargetProject", self.text,
                      "install.ps1 must expose a -TargetProject param (H1)")
        # And forward it to bash on the Unix delegation path.
        self.assertIn("--target-project", self.text,
                      "install.ps1 must forward --target-project to bash (H1)")

    def test_h2_self_install_guard_exists(self) -> None:
        self.assertIn("$selfInstall", self.text,
                      "install.ps1 must compute a self-install guard (H2)")
        # The marker-block upsert and per-host loop must both honour it.
        self.assertRegex(
            self.text, r"-not \$selfInstall",
            "marker-block / per-host install must be guarded by -not $selfInstall (H2)",
        )

    def test_h3_skills_refresh_is_per_skill_not_wholesale(self) -> None:
        body = self._function_body("Copy-FilteredSkills")
        # The whole-destination wipe is the data-loss bug: it deletes a user's
        # own sibling skills in a global ~/.<host>/skills on every auto-upgrade.
        self.assertNotIn(
            "Remove-Item -Recurse -Force $Dest", body,
            "Copy-FilteredSkills must not wipe the whole skills dir — refresh per skill (H3)",
        )

    def test_h3_runtime_scripts_not_wiped_on_upgrade(self) -> None:
        body = self._function_body("Copy-RuntimeScripts")
        # Upgrade must overwrite whitelisted scripts in place, never wipe the
        # whole scripts dir (which in global scope holds the user's own scripts).
        self.assertNotRegex(
            body, r"-in 'force','upgrade'.*\n\s*Remove-Item -Recurse -Force \$Dest",
            "Copy-RuntimeScripts must wipe only on force, not upgrade (H3)",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
