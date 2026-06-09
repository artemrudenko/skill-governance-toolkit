---
name: skill-evaluate
description: |
  Quality evaluator for SKILL.md files. Scores any skill across 9 dimensions (D1–D9) including
  Safety (D9) — behavioral risk awareness: blast radius, prompt injection, rollback, idempotency.
  Complements `library-audit` Phase 5 (lexical secrets/dangerous shell).
  Use when: «evaluate skill X», «score this skill», «review SKILL.md»,
  «is this skill production-ready», «evaluate skill for safety», before merging a new skill or after major rewrites.
  Output: dimension table, top-3 improvements, optional rewritten version, entry in `out/scores/index.jsonl`.
compatibility: "Claude Code · GitHub Copilot · Cursor v2.2+ · OpenAI Codex CLI · Google Gemini CLI"
license: MIT
metainfo:
  category: [governance]
  tier: stable
  owner: artsiom
  added: "2026-05-23"
---

# Skill Evaluate

> **Skill type:** Detect-only by default — reads one SKILL.md, writes only checkpoint state and the documented score/report output. `REWRITE=true` produces an improved version as an explicit draft output; it never silently overwrites the source skill.

**Purpose:** score the quality of any SKILL.md across 9 measurable dimensions (D1–D9: clarity, completeness, specificity, examples, constraints, portability, testability, discoverability, safety), identify overload (> 200 lines without `references/`), verify frontmatter and body conformance to the universal Agent Skills standard. Return a scored report with concrete, section-specific improvements and an optional rewritten version. Persist the score to a JSONL index.

## When to use

**Always:**
- User explicitly asks: «evaluate skill X», «score this skill», «check skill quality».
- Before merging a new SKILL.md or after a major rewrite — pre-merge sanity check.
- When adopting an external skill from a public repository — quality gate.

**ESPECIALLY when:**
- Skill body exceeds 200 lines without a `references/` directory — overload signal.
- Frontmatter contains `allowed-tools:` (forbidden for portable skills).
- `description` is shorter than 80 chars or longer than 600 chars (sweet spot is 100–400). The 600-char ceiling is an advisory heuristic, intentionally stricter than the engine gate's `description_max` (1024) — don't "fix" the gap.
- Body lacks a `## When to Use` section, or that section lacks the canonical sub-structure.

**Skip / Don't use for:**
- File is a README, changelog, ADR, or design spec — not an instructional skill.
- Skill is marked `status: draft` / `WIP` in its header — evaluation is premature.
- The target file cannot be located after search — fail-fast with a report.
- Library-wide quality scan — use `library-audit` instead (this skill scores ONE skill at a time).

**Don't skip when:**
- «It's a small skill, quality is obvious» — D1–D9 scoring is objective and surfaces blind spots.
- «The description looks OK» — sweet-spot length is measurable, not visual.

## Predecessor

**Required upstream:** none — entry-point meta-skill. **Optional upstream:** `skill-find` (post-discovery), `skill-build-portable` (re-score after conversion), `library-audit` (follow-up on per-skill flag).

## Successor

**Default downstream:** terminal — emit dimension table + top-3 improvements + (optional) rewrite. Persist to `out/scores/index.jsonl`.

---

## Required inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `SKILL_TARGET` | string | required | Skill name (e.g. `skill-find`) or direct path to `SKILL.md` |
| `REWRITE` | boolean | `false` | If true, produce an improved version of the skill |
| `SAVE_SCORE` | boolean | `true` | If true, append result to `out/scores/index.jsonl` |
| `REPORT_PATH` | path | `out/skill-evaluate/{SKILL_TARGET}-{YYYY-MM-DD}.md` | Where Phase 6 writes the detailed report file (per AGENTS.md path conventions) |
| `VERBOSITY` | enum: `terse` / `standard` / `detailed` | `detailed` | Output depth. `terse` = summary table only. `standard` = previous (v1.4) format with rubric anchor + evidence. `detailed` = full 4-part per-dim blocks (What we check / What we found / Why it matters / How to raise the score). |

---

## Phase 0 — Locate and read

1. If `SKILL_TARGET` is a name (no path separator), search these locations in order:
   - `./skills/{SKILL_TARGET}/SKILL.md`
   - `./.{tool}/skills/{SKILL_TARGET}/SKILL.md`
   - `{SKILL_TARGET}/SKILL.md` (relative to current directory)
2. If `SKILL_TARGET` is a path: read it directly.
3. Read the **complete** file. Do not truncate.
4. Record total line count.
5. Verify the file contains instructional content (phases, steps, or rules). If it looks like documentation only — stop and report.
6. Check for adjacent directories:
   - `{SKILL_PARENT}/references/` — note contents if present.
   - `{SKILL_PARENT}/scripts/` — note executables if present.
   - `{SKILL_PARENT}/assets/` — note static resources if present.

---

## Parallelization guidance

- **Phase 1 (D1–D9) — do NOT parallelize.** Cross-dim insights (D3+D4 interaction, D5 vs D9, D9 caps from 3.5, D1 caps from 3.6, D8 caps from 3.7's semantic description↔body comparison) require all 9 dims in ONE context.
- **Phase 3 sub-checks — batch tool calls.** 3.0/3.0b/3.1/3.2/3.3/3.4/3.4b/3.5/3.6 are independent; emit supporting `grep`/`ls`/`Read` in ONE message with multiple `tool_use` blocks. Aggregate in context to apply caps. (3.7 and 3.8 are semantic — judge in context, not by regex.)
- **Phase 0 / 4 / 5 / 6 — sequential** (trivially fast or synthesis-dependent).
- **Never require `Task` / sub-agent dispatch for scoring correctness.** Optional specialized sub-agent paths are acceptable only when the skill also documents a sequential fallback with the same output schema. Do not use sub-agents for plain parallelization; use batched tool calls.

## Phase 1 — Dimension scoring

**Read `references/rubrics.md` now.** It contains the full scoring tables for D1–D9. Do not score any dimension without reading the rubrics first.

Score each dimension independently. Assign the **lowest score whose description fully applies** — do not round up. Record a one-sentence finding per dimension.

> **Nine dimensions total (D1–D9).** D8 — Discoverability — was added based on the empirical finding that activation rate with a well-formed description is ~90% vs ~20% with a vague one. D9 — Safety/Risk Awareness — was added because pretty-but-unsafe skills (well-structured Jira-ticket creators with no idempotency, no rollback, no prompt-injection awareness) were scoring 32/40 while being production-hazardous. D9 evaluates the design's awareness of six safety sub-concerns (blast radius, prompt injection, sensitive data, authz, rollback, idempotency). Read-only skills get a D9 floor of 4 — see the rubric.

---

## Phase 2 — Score calculation

```
Total  = D1 + D2 + D3 + D4 + D5 + D6 + D7 + D8 + D9    (max 45)
Score  = round(Total / 45 × 100)                         (0–100)
```

**Safety gate (D9 hard floor):** force the overall verdict to 🔴 **Red** (regardless of the numerical Score) if EITHER (a) D9 ≤ 1 AND the skill performs mutations or ingests untrusted input, OR (b) any 🔴 lexical security finding fired in Phase 3.5 (secret / dangerous-shell / credential-path hit). Branch (b) is required because a 🔴 secret hit caps D9 ≤ 2 (not ≤ 1), so condition (a) alone would miss it — leaving a leaked secret un-gated. Resolve this gate **after** Phase 3.5 completes (its findings feed branch (b)); persist the result in `safety_gate_triggered`. Rationale: a skill that mutates external state with zero safety awareness — or that leaks a credential — is unsafe regardless of how well-written it is. The verbose-output Why column for D9 must name this gate as the trigger.

**Risk tiers:**

| Score | Tier | Meaning |
|---|---|---|
| 80–100 | 🟢 Green | Production-ready |
| 60–79 | 🟡 Yellow | Usable; improve before scaling |
| 40–59 | 🟠 Orange | High inconsistency risk; refactor before wide adoption |
| 0–39 | 🔴 Red | Do not use in production; rewrite required |

---

## Phase 3 — Structural analysis

Run **regardless of score**. Eleven independent sub-checks; full catalog with
detection logic, thresholds, and D-score caps lives in
[`references/structural-analysis.md`](references/structural-analysis.md).
Each sub-check is detect-only; findings appear in the Phase 4 report.

| Sub-check | What it scans | Caps |
|---|---|---|
| 3.0 — Frontmatter compliance | `name`, `description` length, permitted/forbidden fields | feeds D6/D8 findings |
| 3.0b — Body structure | mandatory + recommended sections | feeds D1/D2 |
| 3.1 — Skill size & density | body line count, thresholds 120/200/500/600 (`body_budget`/`body_critical`) | feeds D1/D2 |
| 3.2 — Extractable content scan | proposals to move to `references/` | informational |
| 3.3 — Agent pattern identification | ReAct / ReWOO / CodeAct / Orchestrator / Evaluator-Optimizer / procedural | informational note only (no score impact) |
| 3.4 — Scripts efficiency | «run, don't read» pattern | feeds D6 |
| 3.4b — Multi-tool compatibility | aligned with library-audit Phase 4.5 | feeds D6 |
| 3.5 — Lexical security scan | reuses `skills/library-audit/references/security-spec.md` | **caps D9 ≤ 2 / 3 / 4** |
| 3.6 — Writing quality scan | language consistency, filler density, duplicate paragraphs, long prose | **caps D1 ≤ 3 / 4** |
| 3.7 — Activation coherence | `description` positive triggers vs body `Skip / When not to use` (semantic) | **caps D8 ≤ 3** |
| 3.8 — Negative-rule placement | passive prose prohibitions **outside** the canonical When-to-use sections (semantic) | 🔵 **info — never caps** |

**Self-exclusion:** `skills/skill-evaluate/**` files exempt from Phase 3.5 + 3.6 + 3.7 + 3.8 scanning of their own bodies (they document the patterns; would trivially self-flag).

**Info severity (3.8):** the first `info`-tier sub-check. Info findings land in the report's «Info (no action required)» section and the `info_flags` JSONL field; they **never cap a dimension** and never affect Score, tier, or the safety gate. Info is a promotion stage, not a verdict — see [`docs/extending-checks.md` → Info / experimental lane](../../docs/extending-checks.md#info--experimental-lane).

**Phase 3.5 dependency:** the security pattern catalog lives in the `library-audit` bundle (`security-spec.md`), shared to avoid drift. Resolve it as `$SGT_ROOT/skills/library-audit/references/security-spec.md` (see `references/path-resolution.md` for `$SGT_ROOT`). If `skill-evaluate` was installed **without** `library-audit` (`--skill skill-evaluate` alone), the catalog is absent — install both together (`--skill skill-evaluate,library-audit`) or Phase 3.5 runs in reduced mode (flag only inline-obvious secrets) and logs the degradation. Never silently skip the scan.

---

## Phase 4 — Output report (4-part structured)

Output has three layers. The default `VERBOSITY=detailed` emits all three;
`standard` skips Layer 2; `terse` keeps only Layer 1 + Layer 3.

| Layer | Content | Modes |
|---|---|---|
| 1. Summary table | Skill metadata + D1–D9 one-line findings + Total + verdict | all |
| 2. Per-dim 4-part blocks | For each D1–D9: What we check / What we found / Why it matters / How to raise | `detailed` only |
| 3. Verdict + Top 3 + supplementary sections | Overall verdict, Top 3 cross-dim improvements, frontmatter/body/lexical issues | all |

**The full output template — including the worked example for D4 — lives in
`assets/output-template-detailed.md`. Read that file when producing the
report.** It is the canonical specification for what each block looks like.
Body kept compact here; details there.

### Layer 1 — Summary table (always present)

```
### Skill Evaluation: {skill_name}
File:      {resolved_path}
Lines:     {line_count}
Pattern:   {detected agent pattern or "Procedural"}
Evaluated: {YYYY-MM-DD}
Verbosity: {VERBOSITY}

| # | Dimension      | Score | One-line finding |
|---|----------------|-------|------------------|
| D1 | Clarity         | N/5   | ... |
| D2 | Completeness    | N/5   | ... |
| D3 | Specificity     | N/5   | ... |
| D4 | Examples        | N/5   | ... |
| D5 | Constraints     | N/5   | ... |
| D6 | Portability     | N/5   | ... |
| D7 | Testability     | N/5   | ... |
| D8 | Discoverability | N/5   | ... |
| D9 | Safety          | N/5   | ... |
| **Total** | — | **N/45 · NN/100** · {tier} |
```

### Layer 2 — Per-dim 4-part blocks (only in `detailed` mode)

For EACH dim D1..D9 produce a 4-part block. Template + worked example for
D4 — see `assets/output-template-detailed.md` §Per-dim block.

### Layer 3 — Verdict, Top 3, supplementary sections (always present)

- **Overall verdict** — score + safety gate state + adopt decision.
- **Top 3 priority improvements** — cross-dim, impact-ordered. Each names
  the exact section, exact change, target score lift.
- **Frontmatter issues / Body structure issues / Extraction proposal /
  Scripts-Assets check / Lexical security / Agent pattern note** — emit
  whichever apply. See `assets/output-template-detailed.md` §Layer 3
  templates for exact format.
- **Info (no action required)** — `info`-tier findings (currently 3.8
  negative-rule placement). **Collapsed by default**: emit a one-line count
  (`🔵 N info findings — review only if the skill misbehaves on long runs`)
  and expand the detail only in `detailed` mode. Info never affects the
  Score, tier, or safety gate — it is advisory signal that accumulates for
  later promotion. See `assets/output-template-detailed.md` §Info section.

**Cross-cutting output rules (apply to all verbosity modes):**

- **Rubric anchor rule:** any reference to a rubric level MUST quote (or precisely paraphrase) the exact rubric text — no paraphrasing into vaguer language. This lets the reader audit scoring against `references/rubrics.md` directly.
- **Evidence rule:** every «What we found» / «Why» citation MUST name at least one specific signal — a line number, a section name, or a quoted phrase from the skill being evaluated. Never write «good structure» or «could be improved» — name the structure or the improvement target.
- **Improvement rule:** every «How to raise» / «Top 3» entry MUST name *what* to add, *where* (file:line or section name), and *why* it raises which dimension's score.
- **Why-it-matters rule (detailed mode):** every «Why this score matters» block MUST state the downstream consequence of staying at this score — what the user/adopter hits next. Avoid abstract platitudes («quality matters»). Concrete failure modes only.

---

## Phase 5 — Rewritten version (only if `REWRITE = true`)

Produce the complete improved SKILL.md.
- For every change, add an inline comment: `<!-- improved: added Required Inputs section — raises D2 from 2 to 5 -->`.
- If Phase 3 found extractable content, generate separate files (`references/{topic}.md`) and update SKILL.md to reference them.
- Do not change the skill's logic — only structure, portability, and standard compliance.

---

## Phase 6 — Score persistence (only if `SAVE_SCORE = true`)

Append exactly one line to `out/scores/index.jsonl` — valid JSON, no trailing comma:

```json
{"date":"YYYY-MM-DD","skill_name":"NAME","skill_path":"PATH","score":NN,"tier":"TIER","safety_gate_triggered":true|false,"lines":NNN,"pattern":"ReAct|ReWOO|Orchestrator-Workers|Evaluator-Optimizer|CodeAct|Procedural","has_frontmatter":true|false,"needs_references":true|false,"name_length":NN,"name_valid":true|false,"description_length":NNN,"description_in_sweet_spot":true|false,"description_answers_what":true|false,"description_answers_when":true|false,"forbidden_frontmatter":["allowed-tools","type"],"canonical_when_to_use":true|false,"activation_coherent":true|false,"has_scripts":true|false,"has_assets":true|false,"scripts_run_pattern":true|false|null,"dims":{"clarity":N,"completeness":N,"specificity":N,"examples":N,"constraints":N,"portability":N,"testability":N,"discoverability":N,"safety":N},"lexical_security":{"secret_hits":N,"dangerous_hits":N,"cred_path_hits":N,"d9_cap_applied":"none|2|3|4"},"writing_quality":{"language_mix_hits":N,"filler_hits":N,"duplicate_paragraph_hits":N,"long_prose_hits":N,"d1_cap_applied":"none|3|4"},"info_flags":{"negative_rule_placement":N},"top_issues":["issue1","issue2","issue3"]}
```

**`secret_hits` counting:** one hit per `(line, rule)` pair — a token matching two rules on one line counts twice.

Also write the detailed Phase 4 report to `REPORT_PATH` — in addition to the chat emission and the JSONL score line.

Confirm the line was written. Do not rewrite existing lines.

**Score is for the SOURCE skill, not the rewrite.** If `REWRITE=true` produced an improved version, that file is NOT auto-scored. To get a score for the rewrite, re-invoke `skill-evaluate` on the rewrite path. This keeps each JSONL entry traceable to exactly one immutable SKILL.md state.

---

## State persistence (resumable runs)

For large skills (long body, deep `references/`, or when `REWRITE=true` is requested),
the evaluation can take long enough that a crash is plausible. The skill checkpoints
between expensive phases so it can resume.

| Phase | Checkpoint? | What is stored |
|---|---|---|
| P0 — locate and read | no (cheap) | — |
| P1 — dimension scoring | yes | D1–D9 scores + per-dim findings |
| P2 — score calculation | no (derived from P1) | — |
| P3 — structural analysis | yes | frontmatter audit + body structure + extraction proposal + Phase 3.5 lexical security findings (masked) |
| P4 — output report | no (terminal for read-only mode) | — |
| P5 — rewritten version | yes (only if `REWRITE=true`) | drafted rewrite path |
| P6 — score persistence | no (single-line JSONL append) | — |

- Default `RESUME=auto` (read-mostly skill — never asks).
- State location: `${CWD}/.skill-state/skill-evaluate/run-{utc-timestamp}.json`.
- See `$SGT_ROOT/references/checkpointing.md` for the schema and the helper CLI (this is a shared repo-root reference, not a skill-bundled one — resolve `$SGT_ROOT` per `references/path-resolution.md`).

## Hard rules

- ✅ Score every dimension (D1–D9) before producing the report — no partial evaluations.
- ✅ Improvements must name the exact section and exact change.
- ✅ Resumable — interrupted runs continue from the last checkpointed phase.
- ✅ Phase 3.5 lexical security scan runs on EVERY evaluation, regardless of skill type. Read-only discovery skill, gateway, validator — all get scanned.
- ✅ Safety gate (D9 ≤ 1 on a mutating skill OR any 🔴 lexical finding) forces overall verdict to 🔴 Red regardless of numeric Score.
- ❌ Never invent score components beyond D1–D9 — if a new concern emerges, add a calibration tip to `references/rubrics.md`, do not invent a D10 ad-hoc.
- ❌ Never print a raw matched secret in the output — always mask to first-5 + last-3 chars (`sk-...REDACTED...XyZ`).
- ❌ Never edit the evaluated SKILL.md unless `REWRITE = true`.
