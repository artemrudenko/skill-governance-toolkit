#!/usr/bin/env python3
"""Behavior tests for configure_org.sh — a script that runs in-place sed
substitutions over .claude-plugin/marketplace.json and README.md. Untested
before: only `bash -n` syntax checking existed. These tests pin substitution
coverage, dry-run, idempotency, org validation (incl. sed-delimiter '#' and
'/'), missing-target skipping, and the new `--host` flag for non-GitHub
(e.g. private GitLab) orgs.

The script resolves its repo root from its own location
(`dirname "${BASH_SOURCE[0]}"/..`), so each test copies the script into a
temp tree (`<tmp>/scripts/configure_org.sh`) next to fixture targets and
runs that copy — never the real repo files.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REAL_SCRIPT = ROOT / "scripts" / "configure_org.sh"

# Fixtures mirror the shape of the real distribution artifacts.
MARKETPLACE_FIXTURE = """\
{
  "name": "skill-governance-marketplace",
  "owner": {
    "name": "REPLACE-ME-ORG",
    "url": "https://github.com/REPLACE-ME-ORG/skill-governance-toolkit"
  },
  "plugins": [
    {
      "name": "skill-governance-toolkit",
      "source": "./"
    }
  ]
}
"""

README_FIXTURE = """\
# Skill Governance Toolkit

```
/plugin marketplace add {your-org}/skill-governance-toolkit
gemini extensions install https://github.com/{your-org}/skill-governance-toolkit
git clone https://github.com/{your-org}/skill-governance-toolkit ~/tools/skill-toolkit
```
"""

SENTINELS = ("REPLACE-ME-ORG", "{your-org}")


class ConfigureOrgTestBase(unittest.TestCase):
    """Builds a disposable repo-shaped tree and runs the copied script in it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        scripts_dir = self.root / "scripts"
        scripts_dir.mkdir()
        self.script = scripts_dir / "configure_org.sh"
        shutil.copy(REAL_SCRIPT, self.script)

        plugin_dir = self.root / ".claude-plugin"
        plugin_dir.mkdir()
        self.marketplace = plugin_dir / "marketplace.json"
        self.marketplace.write_text(MARKETPLACE_FIXTURE, encoding="utf-8")
        self.readme = self.root / "README.md"
        self.readme.write_text(README_FIXTURE, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.script), *args],
            cwd=str(self.root), text=True, capture_output=True, check=False,
        )

    def _snapshot(self) -> dict[str, str]:
        return {
            "marketplace": self.marketplace.read_text(encoding="utf-8"),
            "readme": self.readme.read_text(encoding="utf-8"),
        }


class SubstitutionTests(ConfigureOrgTestBase):
    def test_substitution_applied_to_all_targets(self) -> None:
        result = self._run("acme-corp")
        self.assertEqual(result.returncode, 0, result.stderr)
        market = self.marketplace.read_text(encoding="utf-8")
        readme = self.readme.read_text(encoding="utf-8")
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, market)
            self.assertNotIn(sentinel, readme)
        self.assertIn('"name": "acme-corp"', market)
        self.assertIn("https://github.com/acme-corp/skill-governance-toolkit", market)
        self.assertIn("acme-corp/skill-governance-toolkit", readme)

    def test_result_is_valid_json(self) -> None:
        self._run("acme-corp")
        parsed = json.loads(self.marketplace.read_text(encoding="utf-8"))
        self.assertEqual(parsed["owner"]["name"], "acme-corp")

    def test_no_sed_backup_files_left_behind(self) -> None:
        self._run("acme-corp")
        self.assertFalse(list(self.root.rglob("*.bak")), "stray sed -i backups left")


class DryRunTests(ConfigureOrgTestBase):
    def test_dry_run_writes_nothing(self) -> None:
        before = self._snapshot()
        result = self._run("--dry-run", "acme-corp")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._snapshot(), before, "--dry-run must not write")
        self.assertIn("WOULD replace", result.stdout)


class IdempotencyTests(ConfigureOrgTestBase):
    def test_second_run_changes_nothing_and_exits_cleanly(self) -> None:
        first = self._run("acme-corp")
        self.assertEqual(first.returncode, 0, first.stderr)
        after_first = self._snapshot()
        second = self._run("acme-corp")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self._snapshot(), after_first, "re-run must be a no-op")


class ValidationTests(ConfigureOrgTestBase):
    INVALID_ORGS = (
        "bad#org",        # '#' is the sed delimiter — must never reach sed
        "bad/org",        # path separator
        "a" * 40,         # > 39 chars
        "has space",
        "in;jection",
    )

    def test_invalid_orgs_rejected_and_files_untouched(self) -> None:
        before = self._snapshot()
        for org in self.INVALID_ORGS:
            with self.subTest(org=org):
                result = self._run(org)
                self.assertEqual(result.returncode, 2, f"must reject {org!r}")
                self.assertIn("Invalid org name", result.stderr)
                self.assertEqual(self._snapshot(), before)

    def test_leading_hyphen_org_rejected(self) -> None:
        # A leading-hyphen value is indistinguishable from a flag; the parser
        # rejects it as an unknown flag before validation. Either way: nonzero
        # exit and no mutation.
        before = self._snapshot()
        result = self._run("-leading")
        self.assertNotEqual(result.returncode, 0, "must reject '-leading'")
        self.assertEqual(self._snapshot(), before)

    def test_no_args_shows_usage(self) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Usage:", result.stderr)


class MissingTargetTests(ConfigureOrgTestBase):
    def test_missing_targets_skipped_without_failure(self) -> None:
        self.readme.unlink()
        result = self._run("acme-corp")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skipped (missing)", result.stdout)
        # the surviving target is still patched
        self.assertNotIn("REPLACE-ME-ORG", self.marketplace.read_text(encoding="utf-8"))

    def test_all_targets_missing_still_exits_zero(self) -> None:
        self.readme.unlink()
        self.marketplace.unlink()
        result = self._run("acme-corp")
        self.assertEqual(result.returncode, 0, result.stderr)


class HostFlagTests(ConfigureOrgTestBase):
    """New feature: --host <base-host> rewrites the hardcoded github.com host
    so a private-GitLab org ends up with working URLs."""

    def test_host_replaces_github_host_in_all_targets(self) -> None:
        result = self._run("--host", "gitlab.example.com", "acme-corp")
        self.assertEqual(result.returncode, 0, result.stderr)
        market = self.marketplace.read_text(encoding="utf-8")
        readme = self.readme.read_text(encoding="utf-8")
        self.assertNotIn("github.com", market)
        self.assertNotIn("github.com", readme)
        self.assertIn("https://gitlab.example.com/acme-corp/skill-governance-toolkit", market)
        self.assertIn("https://gitlab.example.com/acme-corp/skill-governance-toolkit", readme)

    def test_full_base_url_is_normalized_to_bare_host(self) -> None:
        # Scheme + trailing slash are stripped so existing "https://" prefixes
        # in the files are not doubled.
        result = self._run("--host", "https://gitlab.example.com/", "acme-corp")
        self.assertEqual(result.returncode, 0, result.stderr)
        market = self.marketplace.read_text(encoding="utf-8")
        self.assertIn("https://gitlab.example.com/acme-corp", market)
        self.assertNotIn("https://https://", market)
        self.assertNotIn("gitlab.example.com//acme-corp", market)

    def test_no_host_flag_keeps_github_urls(self) -> None:
        self._run("acme-corp")
        self.assertIn("github.com", self.marketplace.read_text(encoding="utf-8"))
        self.assertIn("github.com", self.readme.read_text(encoding="utf-8"))

    def test_invalid_hosts_rejected_and_files_untouched(self) -> None:
        before = self._snapshot()
        for host in ("has space.example.com", "bad#host", 'quo"te', "quo'te", ""):
            with self.subTest(host=host):
                result = self._run("--host", host, "acme-corp")
                self.assertEqual(result.returncode, 2, f"must reject host {host!r}")
                self.assertIn("Invalid host", result.stderr)
                self.assertEqual(self._snapshot(), before)

    def test_host_flag_requires_a_value(self) -> None:
        result = self._run("acme-corp", "--host")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            self.marketplace.read_text(encoding="utf-8"), MARKETPLACE_FIXTURE,
            "bare --host must not mutate anything",
        )

    def test_host_dry_run_writes_nothing(self) -> None:
        before = self._snapshot()
        result = self._run("--dry-run", "--host", "gitlab.example.com", "acme-corp")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._snapshot(), before)

    def test_host_rerun_is_idempotent(self) -> None:
        self._run("--host", "gitlab.example.com", "acme-corp")
        after_first = self._snapshot()
        second = self._run("--host", "gitlab.example.com", "acme-corp")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self._snapshot(), after_first)


if __name__ == "__main__":
    unittest.main(verbosity=2)
