# Extending checks — where does my check go?

A single decision page for adding, removing, or tuning a check. The toolkit runs
checks on **two surfaces**; picking the wrong one is the most common mistake.
This page routes you to the right surface and the detailed doc for each step.

| Surface | Engine | Runs | Nature | Source of truth |
|---|---|---|---|---|
| **A — deterministic gate** | `agent_audit.py` + `references/agent-audit-rules.json` | per-MR CI, blocking | regex / structural — must be **false-positive-free** | [checks-reference.md](checks-reference.md) |
| **B — LLM-scored skills** | `skill-evaluate` (D1–D9), `library-audit` (phases) | on demand, advisory | **semantic judgement** | rubric / phase markdown in the skill bundle |

**The rule of thumb:** if a deterministic regex can decide it without crying wolf,
it belongs in the gate (A). If deciding needs reading meaning and judging intent,
it belongs in an LLM-scored skill (B). A semantic check forced into the gate
becomes a false-positive machine; a security invariant left to the LLM is not a
gate at all.

## Decision tree

```mermaid
flowchart TD
    Start["I want to add a check"] --> Q1{"Can a regex / structural\nrule decide it WITHOUT\nfalse positives?"}
    Q1 -- "No — needs semantic judgement" --> B["Surface B: LLM-scored skill"]
    Q1 -- "Yes" --> Q2{"Is it new DATA for an\nexisting detector\n(pattern / secret / signature)?"}
    Q2 -- "Yes" --> A1["Surface A · config overlay\n(no code)"]
    Q2 -- "No — a new KIND of detection" --> A2["Surface A · new code rule"]
    B --> Q3{"Scores ONE skill\nor the WHOLE library?"}
    Q3 -- "One skill" --> B1["skill-evaluate:\nnew D-dimension or 3.x sub-check"]
    Q3 -- "Cross-skill" --> B2["library-audit:\nnew phase / pass"]
```

## Surface A — deterministic gate

### A1. New data for an existing detector (no code change)

A new dangerous command, secret shape, env-exfil signature, MCP allow-server, or
hook denylist entry is **policy data**, not a new algorithm. Ship it through the
catalog `config` block / a `references/audit-config.*.json` overlay — no Python
fork.

```jsonc
// org catalog or audit-config overlay
"config": { "patterns": { "dangerous": [
  {"label": "kubectl delete", "regex": "kubectl\\s+delete", "suggestion": "No cluster deletion in assets.", "ignore_case": false}
] } }
```

Always validate before CI — the ReDoS budget guard rejects a catastrophic regex:

```bash
python3 scripts/agent_audit.py validate-config
python3 scripts/agent_audit.py rules --format json   # catalog still loads
```

Full schema + merge/overlay semantics: [checks-reference.md § Configurable policy](checks-reference.md#configurable-policy-no-code-change).
Governance for an **org** rule (reserve id, advisory-first, promotion): [contributing-rules.md](contributing-rules.md).

> Overlays load from the **pinned toolkit mirror**, not the audited repo — a
> consumer-side `audit-config.*.json` is ignored (the CI gate now warns when an MR
> edits one). See [security-rollout-guide.md § Where config overlays live](security-rollout-guide.md).

### A2. A new KIND of detection (code change)

A genuinely new detector (not just data) needs code:

1. Write a `scan_*` function emitting `finding(RULE_ID, …)`; register it in
   `checks_for` / the default scanner list (keyed by `asset_type`).
2. Add severity to `SEVERITY` (and `SEVERITY_FLOOR` only for core safety).
3. Add a catalog entry to `agent-audit-rules.json` — `title` + `description`;
   `description` is what `explain-finding <RULE>` shows the author, so write the
   actionable fix there.
4. Ship a **triggering** fixture and a **clean near-miss** fixture in
   `scripts/test_*.py` — a rule without a clean fixture cannot prove it is not
   over-broad.
5. Document the rule in [checks-reference.md](checks-reference.md).
6. `bash scripts/audit.sh` (P-phases) must stay green.

Detail: [checks-reference.md § New check types](checks-reference.md#new-check-types-code-change).

## Surface B — LLM-scored skills

A check here is a **rubric / phase entry in markdown** — the LLM executes it. No
code, no recompile. Add a worked example (a triggering case + a near-miss) as the
executable spec, then wire the scoring.

### B1. Per-skill — `skill-evaluate`

Two shapes:

- **A new D-dimension** (D1–D9): add to `references/rubrics.md` with a 0–5 scale,
  add the column to the Phase 4 summary table + JSONL `dims`, update Total math.
- **A new Phase 3 sub-check** (`3.x`) that **caps** a dimension: add the detection
  logic to `references/structural-analysis.md`, a row to the SKILL.md sub-check
  table, the cap wiring (the "do NOT parallelize" cross-dim note), a JSONL flag,
  and the self-exclusion if the skill's own body would self-flag.

Worked precedent — the `3.7` activation-coherence sub-check (description ↔ body
`When to use`, caps D8 ≤ 3) was added exactly this way; copy its shape.

### B2. Cross-skill — `library-audit`

Checks that need the **whole library** in one context (trigger collisions across
descriptions, handoff-contract asymmetry, naming drift, token budget). Add a phase
or pass to the relevant reference: `handoff-spec.md` (Phase 1), `security-spec.md`
(Phase 5), or the metainfo/portability phases. Never sub-agent-shard these — the
cross-skill insight must surface in one context.

## Removing or disabling a check

You rarely delete; you **scope** or **suppress**:

| Want | Mechanism | Surface |
|---|---|---|
| Stop a rule blocking, keep it visible | lower `severity` / move out of the gating profile (`--profile`, `profiles.quality_exclude`) | A |
| Silence one finding, one place | inline `<!-- sgt-ignore: RULE reason=… -->` (advisory rules only) | A |
| Silence a floor finding | central `references/audit-ignore.json`, CODEOWNER-gated, with `expires` | A |
| Turn the whole gate advisory (incident) | `SGT_FAIL_MODE=advisory` kill-switch | A |
| Drop a dimension / sub-check | delete its rubric / phase entry | B |
| Retire a rule permanently | deprecation policy (BREAKING CHANGELOG + upgrade notes) | A |

Suppression is not removal — an expired or CODEOWNER-gated suppression keeps an
audit trail. See [security-suppression-runbook.md](security-suppression-runbook.md)
and [checks-reference.md § Rule lifecycle](checks-reference.md#rule-lifecycle--deprecation-policy).

## See also

- [checks-reference.md](checks-reference.md) — every shipped check (engine rules + LLM dims) with rationale
- [contributing-rules.md](contributing-rules.md) — propose an org rule: reserve id, advisory-first, promotion
- [cli-reference.md](cli-reference.md) — `validate-config`, `rules`, `explain-finding`, `--profile`, `--fail-on*`
- [skill-authoring-standard.md](skill-authoring-standard.md) — the section shapes the checks score against
