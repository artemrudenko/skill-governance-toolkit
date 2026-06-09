#!/usr/bin/env python3
"""Behavior tests for the `validate-config` subcommand (OPS3).

Runs the CLI via subprocess so load_config()'s lru_cache is always fresh — these
tests mutate on-disk overlay files, which an in-process cached config would miss."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import agent_audit

SCRIPT = str(Path(__file__).with_name("agent_audit.py"))


def _run(*args, env: dict[str, str] | None = None):
    run_env = dict(os.environ)
    if env:
        run_env.update(env)
    return subprocess.run(
        ["python3", SCRIPT, "validate-config", *args],
        capture_output=True, text=True, env=run_env,
    )


class ValidateConfigTests(unittest.TestCase):
    def test_clean_config_exits_zero(self):
        proc = _run()
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_redos_overlay_flagged(self):
        # Pathological exponential-backtracking regex within the length cap.
        # Hermetic: the overlay is written next to a TEMP copy of the catalog and
        # the CLI is pointed there via AGENT_GOVERNANCE_RULES_PATH — the real
        # references/ dir must never host this deliberately pathological regex
        # (a crashed run would leave the engine reconfigured for everyone).
        real = agent_audit.default_rules_path()
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / real.name
            shutil.copyfile(real, catalog)
            (Path(tmp) / "audit-config.redos-test.json").write_text(
                json.dumps({"patterns": {"dangerous": [{"label": "redos", "regex": "(a+)+$"}]}}),
                encoding="utf-8",
            )
            proc = _run(env={"AGENT_GOVERNANCE_RULES_PATH": str(catalog)})
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("redos", (proc.stdout + proc.stderr).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
