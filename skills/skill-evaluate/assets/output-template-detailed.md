# skill-evaluate — output template (`VERBOSITY=detailed`)

Canonical specification of every section the skill emits in detailed mode.
Body of `SKILL.md` references this file from Phase 4; the actual layout
lives here so the SKILL body stays under the token-budget threshold.

The structure has three layers — Summary, Per-dim 4-part blocks, Verdict +
Top 3 + supplementary sections. Each section below shows the exact format
and a worked example so producers cannot drift.

---

## Layer 1 — Summary table

Always emitted (every verbosity mode). Order: header → D1..D9 → Total.

```
### Skill Evaluation: {skill_name}
File:      {resolved_path}
Lines:     {line_count}
Pattern:   {detected agent pattern or "Procedural"}
Evaluated: {YYYY-MM-DD}
Verbosity: {VERBOSITY}

| # | Dimension      | Score | One-line finding |
|---|----------------|-------|------------------|
| D1 | Clarity         | 4/5   | Purpose precise; Phase 2 intro vague. |
| D2 | Completeness    | 3/5   | Phase 2 lacks empty-input stop condition. |
| D3 | Specificity     | 5/5   | All thresholds numeric. |
| D4 | Examples        | 3/5   | One happy-path example; templates with placeholders don't count. |
| D5 | Constraints     | 5/5   | Hard rules + per-phase stops present. |
| D6 | Portability     | 5/5   | Frontmatter clean, tool-name refs canonical. |
| D7 | Testability     | 4/5   | Output schema defined; no acceptance fixtures. |
| D8 | Discoverability | 5/5   | Description in sweet spot with rich triggers. |
| D9 | Safety          | 2/5   | Mutating skill; 1 of 6 safety sub-concerns addressed. |
| **Total** | — | **36/45 · 80/100** · 🔴 Red (Safety gate triggered — would be 🟢 Green by numeric tier alone) |
```

The «One-line finding» column is the same evidence that appears at the top of
each Layer-2 block — restated tersely so the table alone tells the story.

---

## Layer 2 — Per-dimension 4-part block (`detailed` mode only)

Produce one block per dim D1..D9, in order. Each block has exactly four
parts under fixed bold headings. No optional parts — if D9 lexical caps
apply, document them under «How to raise». If a dim is N/A (e.g. D9 floor
for read-only skills), state that under «What we found».

### Block template

```
## D{N} — {Dimension name} · {score}/5

**What we check:**
{The rule/criterion being evaluated, in 1–3 sentences. Anchor to the rubric
file by name (`references/rubrics.md` §D{N}). If the dim has subtleties
(D4 trap, D5 vs D9 distinction, etc.), name the subtlety here.}

**Rubric anchor (level {score}):** «{verbatim rubric description for the
matched level — quoted exactly from references/rubrics.md}»

**What we found in {skill_name}:**
- {Concrete finding 1 — name file:line, section, or quoted phrase from the
  skill being evaluated.}
- {Concrete finding 2.}
- {Concrete finding 3 — only if material.}

**Why this score matters:**
{One paragraph naming the downstream consequence of staying at this score.
What does the user/adopter hit next? Concrete failure mode, not abstract
quality talk. For mutating skills, relate to production risk. For D9
specifically, name the missing safety sub-concerns and what they mitigate.}

**How to raise to {score+1}/5:**
{Exact change — what to add, where (file:line or section name), what
target rubric description it satisfies. Score lift target stated
explicitly. Multiple steps when needed.}
```

### Worked example — D4

```
## D4 — Examples · 3/5

**What we check:**
Worked examples that demonstrate the skill on a specific input and show the
specific output produced. Placeholders (`<persona>`, `<KEY>`), format
specifications, and anti-pattern lists are conventions — they count toward
D3 (Specificity), not D4. See `references/rubrics.md` §D4 trap.

**Rubric anchor (level 3):** «1 example shown; covers happy path only»

**What we found in jira-ticket:**
- §Examples line 220: ONE worked example — creating a single Jira ticket
  from a one-page brief (happy path, input verbatim + output verbatim). ✓
- Line 145 has a `<persona>` template — this is a convention, NOT an
  example. Does not contribute to D4.
- No examples for edge cases (empty brief, malformed PDF, partial-success
  batch).

**Why this score matters:**
A skill with only happy-path examples cannot teach the reader (human or
agent) what the skill does at the edges. When a user hits an empty PDF or
a Jira API timeout, they cannot infer expected behavior from §Examples and
will likely guess wrong. For a mutating skill (creates external state),
this gap correlates with production incidents.

**How to raise to 4/5:**
Add a second worked example in §Examples showing behavior when the brief
PDF cannot be parsed. Include the exact error output the skill produces
and the recovery action (e.g. «stops the batch and reports `parse_error`
with file:line of the offending paragraph»). Keep input + output verbatim.
```

---

## Layer 3 — Verdict, Top 3, supplementary sections

### Verdict block

```
## Overall verdict — {tier}

**Score:** {N}/45 = {NN}/100 → would be {tier-by-numeric} by numeric tier alone.

**Safety gate:** {TRIGGERED | not triggered}. {If triggered: explain why —
D9 ≤ 1 AND skill is mutating, OR a 🔴 lexical security finding capped D9.
State that overall verdict is forced down, and what D9 floor is required
to lift the gate. If not triggered: 1 sentence confirming.}

**Adopt decision:** {✅ Ready | ⚠️ Conditional | ❌ Not yet}. {One sentence
naming the gating concern + the action needed before adoption.}
```

### Top 3 priority improvements

Always emitted. Cross-dim, impact-ordered. Each names exact section, exact
change, target score lift.

```
**Top 3 improvements:**
1. [Phase 2, line 91] add stop condition «If input list is empty, emit `result: []` and exit Phase 2». Raises D2: 3 → 4.
2. [§Examples] add second example covering parse-error path. Raises D4: 3 → 4.
3. [Phase 5 «Idempotency contract»] add new H3 declaring whether re-runs duplicate, no-op, or update. Raises D9: 2 → 3, lifts Safety gate.
```

### Supplementary sections (emit when relevant)

```
### Frontmatter issues
[List each finding from Phase 3.0 — field, why flagged, fix. «Clean» if 0.]

### Body structure issues
[List findings from Phase 3.0b — canonical sections present/missing.]

### Extraction proposal — only if 3+ items extractable
[Items + target reference path.]

### Scripts / Assets check — only if directories exist
[scripts/ patterns; assets/ inventory.]

### Lexical security — findings from Phase 3.5
[List each hit: rule_id (S/D/C), line number, masked snippet, suggested fix.
Mark as «clean» if 0 findings. If any findings cap D9 — name the cap.]

### Agent pattern note — only if pattern detected or different one suggested
[Detected pattern + recommendation if mismatched.]

### Info (no action required) — findings from Phase 3.8
[Collapsed by default — emit only the one-line count:
  🔵 {N} info findings — review only if the skill misbehaves on long runs.
In `detailed` mode, expand each: line number, the buried prohibition quoted,
and the recommended layer (description anti-trigger / AGENTS.md / Phase-0 gate).
Info NEVER affects Score, tier, or the safety gate. Omit the section entirely
when N = 0.]
```

---

## Mode contracts

- **`terse`** — Layer 1 (summary table) + Layer 3's Verdict + Top 3 +
  Lexical security + Info count line only. Skip Layer 2 (per-dim blocks)
  and most supplementary sections.
- **`standard`** — previous v1.4 format (Layer 1 expanded to 4-column
  table with rubric anchor + evidence column; no separate Layer 2
  blocks); full Layer 3.
- **`detailed`** (default) — all three layers in full.

---

## Cross-cutting rules (re-stated; SKILL.md is the canonical source)

- **Rubric anchor rule** — quote rubric level verbatim.
- **Evidence rule** — every claim cites file:line, section, or quoted phrase.
- **Improvement rule** — what / where / target score lift.
- **Why-it-matters rule** (detailed mode) — name downstream failure mode.
