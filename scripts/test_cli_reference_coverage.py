#!/usr/bin/env python3
"""Forcing-function guard: every long flag in the two MAIN entry points
(sgt.py + agent_audit.py) must appear in docs/cli-reference.md. cli-reference.md
claims to document every flag of these two CLIs; this catches the `--allow-dirty`
class of drift (a flag added to argparse but never written into the reference)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_CLIS = ("scripts/sgt.py", "scripts/agent_audit.py")
CLI_REFERENCE = ROOT / "docs" / "cli-reference.md"

# Flags intentionally omitted from the user-facing reference (none today). Add a
# flag here with a justification only if it is a deliberately-internal option.
ALLOWED_UNDOCUMENTED: set[str] = set()


def _argparse_long_flags() -> set[str]:
    flags: set[str] = set()
    for rel in MAIN_CLIS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for match in re.finditer(r'add_argument\(\s*"(--[a-z][a-z0-9-]+)"', text):
            flags.add(match.group(1))
    return flags


class CliReferenceCoverageTests(unittest.TestCase):
    def test_every_main_cli_flag_is_documented(self) -> None:
        reference = CLI_REFERENCE.read_text(encoding="utf-8")
        flags = _argparse_long_flags()
        self.assertGreater(len(flags), 10, "flag extraction looks broken")
        missing = sorted(f for f in flags if f not in reference and f not in ALLOWED_UNDOCUMENTED)
        self.assertEqual(
            missing, [],
            f"flags in sgt.py/agent_audit.py missing from docs/cli-reference.md: {missing}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
