#!/usr/bin/env python3
"""Behavior tests for the `validate-config` subcommand (OPS3).

Runs the CLI via subprocess so load_config()'s lru_cache is always fresh — these
tests mutate on-disk overlay files, which an in-process cached config would miss."""
from __future__ import annotations
import json
import subprocess
import unittest
from pathlib import Path

import agent_audit

SCRIPT = str(Path(__file__).with_name("agent_audit.py"))


def _run(*args):
    return subprocess.run(
        ["python3", SCRIPT, "validate-config", *args],
        capture_output=True, text=True,
    )


class ValidateConfigTests(unittest.TestCase):
    def test_clean_config_exits_zero(self):
        proc = _run()
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_redos_overlay_flagged(self):
        # Pathological exponential-backtracking regex within the length cap.
        refs = agent_audit.default_rules_path().parent
        overlay = refs / "audit-config.redos-test.json"
        overlay.write_text(
            json.dumps({"patterns": {"dangerous": [{"label": "redos", "regex": "(a+)+$"}]}}),
            encoding="utf-8",
        )
        try:
            proc = _run()
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("redos", (proc.stdout + proc.stderr).lower())
        finally:
            overlay.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
