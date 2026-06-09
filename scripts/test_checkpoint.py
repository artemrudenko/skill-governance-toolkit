#!/usr/bin/env python3
"""Behavior tests for checkpoint.py — the resumable-run state helper AGENTS.md
declares a core contract. Exercises the full lifecycle (start → save-phase →
list-resumable → complete/fail), atomicity, idempotent re-save, the run-id
resolver, and the stale-run filter — none of which had a behavioral test."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
SCRIPT = ROOT / "scripts" / "checkpoint.py"


class CheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.state = Path(self._tmp.name) / ".skill-state"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(SCRIPT), "--state-dir", str(self.state), *args],
            text=True, capture_output=True, check=False,
        )

    def _start(self, skill: str = "library-audit", inputs: str = '{"scope":"all"}') -> str:
        result = self._run("start", "--skill", skill, "--inputs", inputs)
        self.assertEqual(result.returncode, 0, result.stderr)
        run_id = result.stdout.strip()
        self.assertTrue(run_id.startswith("run-"), run_id)
        return run_id

    def _load(self, run_id: str) -> dict:
        result = self._run("load", "--run-id", run_id)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_start_writes_schema_and_file_on_disk(self) -> None:
        run_id = self._start()
        path = self.state / "library-audit" / f"{run_id}.json"
        self.assertTrue(path.exists(), "checkpoint file not written")
        state = self._load(run_id)
        for key in ("run_id", "skill", "started_at", "inputs", "completed_phases",
                    "phase_outputs", "completed_at", "error"):
            self.assertIn(key, state)
        self.assertEqual(state["inputs"], {"scope": "all"})
        self.assertEqual(state["completed_phases"], [])

    def test_save_phase_records_output_and_next(self) -> None:
        run_id = self._start()
        self.assertEqual(
            self._run("save-phase", "--run-id", run_id, "--phase", "discover",
                      "--output", '{"found":3}', "--next-phase", "score").returncode, 0)
        state = self._load(run_id)
        self.assertEqual(state["completed_phases"], ["discover"])
        self.assertEqual(state["phase_outputs"]["discover"], {"found": 3})
        self.assertEqual(state["next_phase"], "score")

    def test_save_phase_is_idempotent(self) -> None:
        run_id = self._start()
        self._run("save-phase", "--run-id", run_id, "--phase", "discover", "--output", '{"v":1}')
        self._run("save-phase", "--run-id", run_id, "--phase", "discover", "--output", '{"v":2}')
        state = self._load(run_id)
        # Phase listed once; output replaced, not duplicated.
        self.assertEqual(state["completed_phases"], ["discover"])
        self.assertEqual(state["phase_outputs"]["discover"], {"v": 2})

    def test_list_resumable_includes_then_excludes_on_complete(self) -> None:
        run_id = self._start()
        listed = json.loads(self._run("list-resumable", "--skill", "library-audit").stdout)
        self.assertIn(run_id, [r["run_id"] for r in listed])
        self.assertEqual(self._run("complete", "--run-id", run_id).returncode, 0)
        after = json.loads(self._run("list-resumable", "--skill", "library-audit").stdout)
        self.assertNotIn(run_id, [r["run_id"] for r in after], "completed run must not be resumable")
        self.assertIsNotNone(self._load(run_id)["completed_at"])

    def test_failed_run_is_not_resumable(self) -> None:
        run_id = self._start()
        self.assertEqual(self._run("fail", "--run-id", run_id, "--error", "boom").returncode, 0)
        listed = json.loads(self._run("list-resumable", "--skill", "library-audit").stdout)
        self.assertNotIn(run_id, [r["run_id"] for r in listed])
        self.assertEqual(self._load(run_id)["error"], "boom")

    def test_unknown_run_id_fails_cleanly(self) -> None:
        result = self._run("load", "--run-id", "run-does-not-exist")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_list_resumable_empty_for_unknown_skill(self) -> None:
        result = self._run("list-resumable", "--skill", "never-ran")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])

    def test_atomic_write_leaves_no_tmp_file(self) -> None:
        run_id = self._start()
        self._run("save-phase", "--run-id", run_id, "--phase", "p", "--output", "{}")
        folder = self.state / "library-audit"
        self.assertEqual(list(folder.glob("*.tmp")), [], "atomic write left a .tmp artifact")


if __name__ == "__main__":
    unittest.main(verbosity=2)
