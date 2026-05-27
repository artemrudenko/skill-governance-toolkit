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
   - Claude Code: 1% of context window (≈ 2000 tokens for 200K windows, with 8000-token fallback).
   - Copilot, Codex, Gemini: documented separately; default budget assumed at 8000 tokens for skill-description routing.

**Findings:**
- **B2.1** — Always-on cost exceeds 8000 tokens → 🔴 (instructions begin to be truncated)
- **B2.2** — Always-on cost between 4000 and 8000 tokens → 🟡 (review for extraction opportunities)
- **B2.3** — `AGENTS.md` exceeds 200 lines → 🟡 (Claude Code guidance threshold)

## Pass 2.2 — Claims-vs-actual reconciliation

If any documentation file (changelog, ADR, design note) claims a token saving — e.g. «−7500 tokens» or «−31% context» — verify:

1. Identify the baseline the claim was measured against (look for `baseline:` or `prior measurement:` annotations).
2. Re-measure with the current files.
3. Compute deviation:
   ```
   deviation_pct = (current_savings − claimed_savings) / claimed_savings × 100
   ```

**Findings:**
- **B2.4** — Deviation within ±20% → 🟢
- **B2.5** — Deviation ±20–50% → 🟡
- **B2.6** — Deviation > ±50% → 🔴 (claim is materially wrong; update or retract)

## Pass 2.3 — Per-skill body length

For each `SKILL.md`, count body lines (excluding the YAML frontmatter block, which ends at the second `---` delimiter).

| Body lines | Severity | Action |
|---|---|---|
| ≤ 120 | 🟢 | Clean — no action |
| 121 – 200 | 🟢 | Review-recommended — check for extractable detail |
| 201 – 400 | 🟡 | Overload candidate — move detail to `references/{topic}.md` |
| 401 – 600 | 🔴 | Overload risk — split into multiple skills or aggressively extract |
| > 600 | 🔴 | Critical — instructions in the middle will be ignored by some hosts |

**Practical guidance:** body should contain **declarative phases and decision points**. Long procedures, edge-case catalogues, worked examples, and large templates belong in `references/`.

---

## Reporting

For each finding, the audit report must include:
- Skill name and path (or file path for always-on cost findings)
- Phase + rule identifier (B2.1–B2.6)
- Severity emoji
- Measured value vs threshold
- Suggested remediation
