#!/usr/bin/env python3
"""
checkpoint.py — resumable-run state helper for skill libraries.

Pure stdlib. See references/checkpointing.md for the contract.

Usage:
    checkpoint.py start         --skill NAME --inputs JSON
    checkpoint.py save-phase    --run-id ID  --phase LABEL --output JSON
    checkpoint.py complete      --run-id ID
    checkpoint.py fail          --run-id ID  --error "message"
    checkpoint.py list-resumable --skill NAME
    checkpoint.py load          --run-id ID

All commands accept --state-dir to override the default ${CWD}/.skill-state/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_id_now() -> str:
    # Microsecond precision avoids collisions under fast scripted invocation.
    # Format: run-2026-05-24T13-04-22-123456Z
    return "run-" + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")


def _state_dir(root: Path, skill: str) -> Path:
    return root / skill


def _find_run_file(root: Path, run_id: str) -> Path:
    matches = list(root.rglob(f"{run_id}.json"))
    if not matches:
        raise SystemExit(f"run_id not found: {run_id}")
    if len(matches) > 1:
        raise SystemExit(f"ambiguous run_id {run_id}: {len(matches)} matches")
    return matches[0]


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_start(args: argparse.Namespace) -> int:
    root = Path(args.state_dir)
    inputs = json.loads(args.inputs) if args.inputs else {}
    run_id = _run_id_now()
    state: dict[str, Any] = {
        "run_id": run_id,
        "skill": args.skill,
        "started_at": _now_iso(),
        "last_updated": _now_iso(),
        "inputs": inputs,
        "completed_phases": [],
        "phase_outputs": {},
        "next_phase": None,
        "completed_at": None,
        "error": None,
    }
    target = _state_dir(root, args.skill) / f"{run_id}.json"
    _atomic_write(target, state)
    print(run_id)
    return 0


def cmd_save_phase(args: argparse.Namespace) -> int:
    root = Path(args.state_dir)
    path = _find_run_file(root, args.run_id)
    state = _load(path)
    if args.phase in state["completed_phases"]:
        # Idempotent re-save replaces the prior output.
        pass
    else:
        state["completed_phases"].append(args.phase)
    state["phase_outputs"][args.phase] = (
        json.loads(args.output) if args.output else {}
    )
    state["last_updated"] = _now_iso()
    state["next_phase"] = args.next_phase
    _atomic_write(path, state)
    return 0


def cmd_complete(args: argparse.Namespace) -> int:
    root = Path(args.state_dir)
    path = _find_run_file(root, args.run_id)
    state = _load(path)
    state["completed_at"] = _now_iso()
    state["last_updated"] = state["completed_at"]
    state["next_phase"] = None
    _atomic_write(path, state)
    return 0


def cmd_fail(args: argparse.Namespace) -> int:
    root = Path(args.state_dir)
    path = _find_run_file(root, args.run_id)
    state = _load(path)
    state["error"] = args.error
    state["last_updated"] = _now_iso()
    _atomic_write(path, state)
    return 0


def cmd_list_resumable(args: argparse.Namespace) -> int:
    root = Path(args.state_dir)
    folder = _state_dir(root, args.skill)
    if not folder.exists():
        print("[]")
        return 0
    resumable: list[dict[str, Any]] = []
    cutoff = None
    if args.max_age_hours is not None:
        cutoff = datetime.now(timezone.utc).timestamp() - args.max_age_hours * 3600
    for f in sorted(folder.glob("run-*.json")):
        try:
            state = _load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if state.get("completed_at") is not None or state.get("error") is not None:
            continue
        # Stale-run filter (F-8)
        if cutoff is not None:
            last = state.get("last_updated") or state.get("started_at")
            if last:
                try:
                    ts = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=timezone.utc
                    ).timestamp()
                    if ts < cutoff:
                        continue
                except ValueError:
                    pass
        resumable.append(
            {
                "run_id": state["run_id"],
                "started_at": state.get("started_at"),
                "last_updated": state.get("last_updated"),
                "next_phase": state.get("next_phase"),
                "completed_phases": state.get("completed_phases", []),
            }
        )
    print(json.dumps(resumable, indent=2, ensure_ascii=False))
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    root = Path(args.state_dir)
    path = _find_run_file(root, args.run_id)
    print(json.dumps(_load(path), indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resumable-run state helper. See references/checkpointing.md."
    )
    parser.add_argument(
        "--state-dir",
        default=os.environ.get("SKILL_STATE_DIR", ".skill-state"),
        help="State root directory (default: ./.skill-state or $SKILL_STATE_DIR).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start", help="Start a new run; print the run_id.")
    p.add_argument("--skill", required=True)
    p.add_argument("--inputs", default="{}", help="JSON string of input params.")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("save-phase", help="Mark a phase complete and save output.")
    p.add_argument("--run-id", required=True)
    p.add_argument("--phase", required=True)
    p.add_argument("--output", default="{}", help="JSON string of phase output.")
    p.add_argument("--next-phase", default=None)
    p.set_defaults(func=cmd_save_phase)

    p = sub.add_parser("complete", help="Mark a run as fully completed.")
    p.add_argument("--run-id", required=True)
    p.set_defaults(func=cmd_complete)

    p = sub.add_parser("fail", help="Mark a run as failed (won't be resumed).")
    p.add_argument("--run-id", required=True)
    p.add_argument("--error", required=True)
    p.set_defaults(func=cmd_fail)

    p = sub.add_parser(
        "list-resumable",
        help="List runs without completed_at and without error.",
    )
    p.add_argument("--skill", required=True)
    p.add_argument(
        "--max-age-hours",
        type=float,
        default=None,
        help="Filter out runs whose last_updated is older than N hours (stale-run filter).",
    )
    p.set_defaults(func=cmd_list_resumable)

    p = sub.add_parser("load", help="Print the full state of a run.")
    p.add_argument("--run-id", required=True)
    p.set_defaults(func=cmd_load)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
