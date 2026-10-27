#!/usr/bin/env python3
"""Measure selected rules against the manually labelled synthetic corpus."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from agent_audit import audit_skill, engine_version, rule_catalog  # noqa: E402


def run() -> dict:
    corpus = (ROOT / "experiments" / "security-corpus.jsonl").read_bytes()
    rows = [json.loads(line) for line in corpus.decode("utf-8").splitlines() if line.strip()]
    results = []
    for row in rows:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "sample-evaluate"
            folder.mkdir()
            declared = row.get("declared_mcp")
            extra = f'  sgt-requires-mcp: "{declared}"\n' if declared else ""
            skill = folder / "SKILL.md"
            skill.write_text(
                '---\nname: sample-evaluate\ndescription: A sample skill for testing selected security checks. '
                'Use this skill when evaluating an isolated labelled security example.\n'
                'compatibility: Python 3\nlicense: MIT\nmetadata:\n'
                '  sgt-category: "governance"\n  sgt-tier: "preview"\n' + extra +
                '---\n\n# Sample\n\n> **Skill type:** Detect-only.\n\n' + row["body"] + '\n',
                encoding="utf-8",
            )
            report = audit_skill(skill, root=folder)
            actual = row["rule"] in {finding["rule_id"] for finding in report["findings"]}
            results.append({"id": row["id"], "rule": row["rule"],
                            "expected": row["expected"], "actual": actual,
                            "correct": actual == row["expected"]})
    totals = {}
    for row in results:
        stats = totals.setdefault(row["rule"], {"tp": 0, "tn": 0, "fp": 0, "fn": 0})
        key = ("tp" if row["actual"] else "fn") if row["expected"] else ("fp" if row["actual"] else "tn")
        stats[key] += 1
    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "corpus_sha256": hashlib.sha256(corpus).hexdigest(), "engine_version": engine_version(),
            "engine_sha256": hashlib.sha256((ROOT / "scripts" / "agent_audit.py").read_bytes()).hexdigest(),
            "rules_sha256": hashlib.sha256((ROOT / "references" / "agent-audit-rules.json").read_bytes()).hexdigest(),
            "rules_version": rule_catalog()["version"], "scope": "synthetic examples, selected rule per case",
            "counts": totals, "cases": results}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if "--verify" in sys.argv and any(not case["correct"] for case in result["cases"]):
        raise SystemExit(1)
