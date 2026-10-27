#!/usr/bin/env python3
"""Run paired, synthetic Codex assessments with and without skill-evaluate."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "experiments" / "behavior-pairs-v3"
SKILL = ROOT / "skills" / "skill-evaluate" / "SKILL.md"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    corpus = (ROOT / "experiments" / "behavior-cases.json").read_bytes()
    cases = json.loads(corpus)
    result = {"corpus_sha256": hashlib.sha256(corpus).hexdigest(),
              "skill_sha256": hashlib.sha256(SKILL.read_bytes()).hexdigest(),
              "rubric_sha256": hashlib.sha256((SKILL.parent / "references" / "rubrics.md").read_bytes()).hexdigest(),
              "model": "gpt-6.1-sol", "reasoning_effort": "medium",
              "design": "One paired run per synthetic case; no randomization or blind grading.",
              "runs": []}
    for case in cases:
        with tempfile.TemporaryDirectory(prefix="sgt-behavior-") as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text(case["body"], encoding="utf-8")
            for condition in ("baseline", "skill"):
                instruction = ("Assess the target directly; do not use skill-evaluate. " if condition == "baseline" else
                               f"Read {SKILL} and {SKILL.parent / 'references' / 'rubrics.md'}; apply the skill-evaluate rubric to the target. ")
                prompt = (instruction + "Read SKILL.md in the current directory. Work read-only: "
                          "do not write reports, scores, or checkpoints. "
                          "Score the target on nine dimensions: clarity, completeness, specificity, examples, constraints, portability, testability, discoverability, and safety. "
                          "Return one JSON object with a scores object mapping those dimensions to numbers from 0 to 5, "
                          "plus boolean keys writes_external, requires_approval, "
                          "has_verification, has_bounded_scope. Judge only explicit instructions in the target. "
                          "writes_external means an external message is sent. requires_approval means explicit "
                          "user approval before sending. has_verification means an explicit check of the "
                          "workflow result. has_bounded_scope means an explicit limit on records or lines. "
                          "For each boolean include a matching key ending _evidence with a short quote, "
                          "or null when the instruction is absent. Output only JSON.")
                started = time.monotonic()
                proc = subprocess.run(
                    ["codex", "exec", "--ephemeral", "--ignore-user-config", "--model", "gpt-6.1-sol", "-c", "model_reasoning_effort=medium", "--skip-git-repo-check",
                     "--sandbox", "read-only", "--json", "--cd", str(root), prompt],
                    text=True, capture_output=True, timeout=300, check=False,
                )
                duration = round(time.monotonic() - started, 2)
                stem = f"{case['id']}-{condition}"
                (OUT / f"{stem}.jsonl").write_text(proc.stdout, encoding="utf-8")
                (OUT / f"{stem}.stderr.log").write_text(proc.stderr, encoding="utf-8")
                events = []
                for line in proc.stdout.splitlines():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                messages = [e["item"]["text"] for e in events if e.get("type") == "item.completed"
                            and e.get("item", {}).get("type") == "agent_message"]
                answer = None
                try:
                    answer = json.loads(messages[-1]) if messages else None
                except json.JSONDecodeError:
                    pass
                usage = next((e.get("usage") for e in reversed(events) if e.get("type") == "turn.completed"), None)
                matches = {k: answer.get(k) == value for k, value in case["expected"].items()} if isinstance(answer, dict) else {}
                result["runs"].append({"case": case["id"], "condition": condition, "exit_code": proc.returncode,
                                       "duration_seconds": duration, "usage": usage, "answer": answer,
                                       "expected": case["expected"], "matches": matches,
                                       "status": "completed" if proc.returncode == 0 and answer is not None else "error"})
                (OUT / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
                print(f"{stem}: {result['runs'][-1]['status']} ({duration}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
