# Phase 2 — Token Budget Spec

This spec is loaded by `library-audit` Phase 2.

## Word-to-token heuristic

Default ratio: `1.3 tokens per word` for English / mixed-language documentation. Override via the `WORD_TO_TOKEN_RATIO` input.

Formula:
```
estimated_tokens = round(word_count × ratio)
```

For CJK-heavy content, use `2.0`. For code-heavy markdown (lots of backticks and identifiers), use `1.6`.

## Pass 2.1 — Always-on context measurement

«Always-on» means content that loads into the agent's context **on every request**, before the user's first turn:

- Project rules files: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`
- Memory indexes that the runtime auto-injects
- Skill `description` fields (loaded for skill-routing budget; varies by runtime)

Compute:
1. Total words across always-on files.
2. Multiply by `WORD_TO_TOKEN_RATIO`.
3. Compare against the host's stated budget:
   - Claude Code: 1% of context window (≈ 2000 tokens for 200K windows, with 8000-token fallback). Context only — no finding keys off this figure; B2.1/B2.2 below use the 8000/4000 thresholds.
   - Copilot, Codex, Gemini: documented separately; default budget assumed at 8000 tokens for skill-description routing.

**Findings:**
- **B2.1** — Always-on cost exceeds 8000 tokens → 🔴 (instructions begin to be truncated)
- **B2.2** — Always-on cost between 4000 and 8000 tokens → 🟡 (review for extraction opportunities)
- **B2.3** — `AGENTS.md` exceeds 200 lines → 🟡 (Claude Code guidance threshold)

## Pass 2.2 — Claims-vs-actual reconciliation (OPTIONAL)

**Run only if a doc makes an explicit token-saving claim** (e.g. «−7500 tokens»,
«−31% context»). Most libraries make no such claim — in that case skip this pass
entirely (no findings, no scan). It exists to keep a stated number honest, not to
hunt for one.

When a claim exists: identify its baseline (`baseline:` / `prior measurement:`
annotation), re-measure with current files, and compute
`deviation_pct = (current − claimed) / claimed × 100`.

**Findings (only when a claim was present):**
- **B2.4** — Deviation within ±20% → 🟢
- **B2.5** — Deviation ±20–50% → 🟡
- **B2.6** — Deviation > ±50% → 🔴 (claim is materially wrong; update or retract)

## Pass 2.3 — Per-skill body length

For each `SKILL.md`, count body lines (excluding the YAML frontmatter block, which ends at the second `---` delimiter). Body = every line strictly after that closing `---`, INCLUDING any in-body horizontal-rule `---` lines — only the frontmatter delimiters are excluded.

**Thresholds are the single source of truth in the gate config**: defaults
`body_budget: 500` / `body_critical: 600` are hardcoded in the config block of
`scripts/agent_audit.py`, overridable via the `config` block in
`references/agent-audit-rules.json` (or a file pointed to by
`AGENT_GOVERNANCE_RULES_PATH`); `references/agent-audit-config.example.json` is
an optional example overlay. This table and `skill-evaluate` 3.1 must echo it,
never diverge. Defaults: budget **500**, critical **600**.

| Body lines | Severity | Action |
|---|---|---|
| ≤ 120 | 🟢 | Clean — no action |
| 121 – 200 | 🟢 | Review-recommended — target ≤ 200 |
| 201 – 500 | 🟡 | Overload candidate — move detail to `references/{topic}.md` |
| 501 – 600 | 🟡 | Over budget (`body_budget`) — extract aggressively |
| > 600 | 🔴 | Critical (`body_critical`) — instructions in the middle ignored by some hosts |

**Practical guidance:** body should contain **declarative phases and decision points**. Long procedures, edge-case catalogues, worked examples, and large templates belong in `references/`.

---

## Reporting

For each finding, the audit report must include:
- Skill name and path (or file path for always-on cost findings)
- Phase + rule identifier (B2.1–B2.6)
- Severity emoji
- Measured value vs threshold
- Suggested remediation
