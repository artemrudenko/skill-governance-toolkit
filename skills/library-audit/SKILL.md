---
name: library-audit
description: |
  Meta-validator for an entire skill library (operates on the collection, not one skill). Runs detect-only phases for handoff contracts, trigger uniqueness, clarification policy, token budget, naming, portability, multi-tool compatibility, security baseline, and metainfo coverage.
  Use when: «audit my skills», «audit the library», «library health check», «handoff audit»,
  «security audit», «secrets scan». Never edits files, never asks questions, idempotent.
  Output: markdown report at `out/library-audit/library-audit-{date}.md`.
  For per-skill scoring of ONE skill, use `skill-evaluate`.
compatibility: "Claude Code · GitHub Copilot · Cursor v2.2+ · OpenAI Codex CLI · Google Gemini CLI"
license: MIT
metainfo:
  category: [governance]
  tier: stable
  owner: artsiom
  added: "2026-05-23"
---

# Library Audit — 6-phase meta-validator across the whole skill collection

> **Skill type:** Detect-only — never edits any source file. Writes ONLY to OUTPUT_PATH_OVERRIDE (default `out/library-audit/library-audit-{date}.md`) + checkpoint state.

**Purpose:** comprehensive validation of a skill library — handoff contracts, token budget, naming convention, portability tagging, multi-tool compatibility, security baseline, and metainfo coverage (since 1.8.0). **Pure detect** mode: no file edits, no user clarification prompts, no mutations of any kind.

**Runtime notes:** Claude/Copilot/Cursor/Codex — normal workflow. Gemini — no sub-agent dispatch (this skill doesn't use Task; per-skill checks are batched tool calls — see Parallelization guidance).

## When to use

**Triggers:**
- General: «audit my skills», «check skill library», «skill governance health check»
- Phase 1 specific: «handoff audit», «trigger collision check», «clarification policy compliance»
- Phase 2 specific: «token audit», «budget hygiene», «context size check»
- Phase 3 specific: «naming audit», «verify naming convention»
- Phase 4 specific: «portability check», «multi-tool compatibility», «allowed-tools audit»
- Phase 5 specific: «security audit», «secrets scan», «check for credentials», «dangerous shell patterns»
- Phase 5.5 specific: «metainfo coverage», «category/tier audit»

**Always:**
- Before merging a new `SKILL.md` or after a major rewrite.
- After adding, renaming, or deleting a skill.
- Periodically (e.g. weekly) for libraries with > 10 skills.

**ESPECIALLY when:**
- Skill count crosses 20+ — the chance of accidental trigger collisions and naming drift grows nonlinearly.
- A new contributor onboarded a batch of skills — drive-by additions often miss handoff/naming conventions.
- Switching the toolkit to a new runtime (Copilot → Codex, etc.) — multi-tool compat findings surface portability gaps.

**Skip / Don't use for:**
- Quality of a single skill's content → use `skill-evaluate`.
- Overlap detection between local and corporate versions → use `skill-compare`.
- Cost-per-request reporting from your runtime → use the runtime's built-in `/cost` or equivalent.

**Don't skip when:**
- «The library is small, audit is overkill» — even 3-skill libraries can have hidden duplicate triggers; one detect-only run is cheap.
- «I just renamed one skill» — Phase 3 catches the dozens of stale references the rename leaves behind.

## Predecessor

**Required upstream:** none — independent validator, invoked directly by user phrase or scheduled job.

## Successor

**Default downstream:** terminal — write markdown report to `out/library-audit/library-audit-{date}.md`.
**Recommended follow-ups** (user-initiated, not auto-dispatched): `skill-evaluate` to score individual flagged skills · `skill-build-portable` to fix portability/multi-tool 🔴 findings.

---

## Phase 0 — Environment & rules setup

1. **Load handoff spec:** read `references/handoff-spec.md` (Phase 1 checks).
2. **Load budget spec:** read `references/budget-spec.md` (Phase 2 checks).
3. **Load naming spec:** read `references/naming-spec.md` (Phase 3 + 4 checks).
4. **Load security spec:** read `references/security-spec.md` (Phase 5 checks).
5. **Resolve skill directories:** default `SKILLS_DIRS = [skills/, .{tool}/skills/]`. Override via input param.
6. **Resolve agent directories:** default `AGENT_DIRS = [agents/, .{tool}/agents/]`. Phase 5 scans these too.

## Required inputs

All optional.

| Input | Type | Default | Description |
|---|---|---|---|
| `MODE` | enum: `full` / `handoff-only` / `budget-only` / `naming-only` / `portability-only` / `compat-only` / `security-only` / `metainfo-only` | `full` | Which phases to run |
| `OUTPUT_PATH_OVERRIDE` | path | `out/library-audit/library-audit-{TODAY}.md` | Where to write the report |
| `SKILLS_DIRS` | list of paths | `[skills/, .{tool}/skills/]` | Directories to scan |
| `STRICTNESS` | enum: `default` / `strict` / `permissive` | `default` | Severity matrix tuning |
| `WORD_TO_TOKEN_RATIO` | float | `1.3` | Phase 2 token-estimation heuristic |
| `VERBOSITY` | enum: `terse` / `standard` / `detailed` | `detailed` | Output depth. `terse` = roll-up table only. `standard` = previous (v1.4) format with category counts + per-finding row. `detailed` = full 4-part per-category blocks (What we check / What we found / Why it matters / How to fix) + per-finding remediation. |

---

## Parallelization guidance

Phases 1–5 are **embarrassingly parallel within phase** — per-skill checks (handoff refs, body length, name regex, frontmatter grep, secret scan) are independent across the N skills.

**Recommended pattern: batched tool calls in one message.** When ≥ 3 skills need checking in a single phase, emit ALL supporting `Read` / `Grep` / `Bash` tool uses in **one message** with multiple `tool_use` blocks — the host runs them concurrently; aggregation happens in your context after results return. Works on every supported runtime (Claude / Copilot / Cursor / Codex / Gemini).

**Do NOT** dispatch sub-agents via `Task` for per-skill parallelization: Gemini CLI has no sub-agent support, and cross-skill insights (trigger collisions, handoff asymmetry, naming drift) must surface in ONE context. Optional specialized sub-agent paths are acceptable only when the skill also documents a sequential fallback with the same output schema.

**Phase 6 (aggregate + report) is sequential** — depends on all prior phases.

## Workflow — 6 phases (plus 4.5 / 5.5 sub-phases)

### Phase 1 — Handoff validation

Apply 3 atomic passes per `references/handoff-spec.md`:

1. **Bidirectional handoff:** for each SKILL.md, every `Predecessor` / `Successor` reference must match its counterpart in the referenced skill.
2. **Trigger uniqueness:** all `description` trigger phrases must be unique across the library. Disambiguation by entity prefix is allowed when two skills share an action verb (e.g. `library-audit` vs `presentation-audit`).
3. **Clarification compliance (body-based, see `handoff-spec.md` Pass 1.3):**
   - Grep body for user-prompt signals. If none → pass clean.
   - If ≥1 found, scan `## Hard rules` for explicit policy:
     - Permit statement found → 🟢 (consistent self-declared role).
     - Forbid statement found but call sites exist → 🔴 H1.4 (self-contradiction).
     - Neither found → 🟡 H1.5 («role unclear — document clarification policy in Hard rules»).

### Phase 2 — Token budget

Apply 3 atomic passes per `references/budget-spec.md`:

1. **Measurement:** measure always-on context cost (project rules files + always-loaded indexes + auto-injected memory). Convert words → tokens via `WORD_TO_TOKEN_RATIO`.
2. **Claims-vs-actual:** if any documentation file claims a token saving («−31% context», «−7500 tokens»), compare against measured baseline. Threshold: ±20% deviation = 🟡; ±50% = 🔴.
3. **Per-skill body length:** for each SKILL.md, measure body length (excluding frontmatter). Boundaries echo the gate config (`body_budget`/`body_critical`, defaults **500**/**600**) — never hardcode a different number; see `references/budget-spec.md`:
   - ≤ 120 lines → 🟢 clean
   - 121–200 lines → 🟢 review-recommended (target ≤ 200)
   - 201–500 lines → 🟡 overload candidate, move detail to `references/`
   - 501–600 lines → 🟡 over budget (`body_budget`), extract aggressively
   - > 600 lines → 🔴 critical (`body_critical`), instructions in the middle will degrade

### Phase 3 — Naming validation

Apply 5 atomic checks (**N1**–**N5**) per `references/naming-spec.md`: closed-vocabulary verb, `{entity}-{action}[-{qualifier}]` pattern, kebab-case, ≤ 2 words after entity (action + optional qualifier), no brand-specific names. Any 🔴 violation in a new skill → block merge. Full rule table, severities, and rename guidance in the spec file.

### Phase 4 — Portability tag coverage

Apply 2 atomic checks:

| # | Check | Severity |
|---|---|---|
| **P1** | `compatibility:` or `portability:` field present in frontmatter | 🟡 |
| **P2** | Value is meaningful (compatibility lists supported runtimes; portability ∈ `{portable, hybrid, project-local}`) | 🟡 |

### Phase 4.5 — Multi-tool compatibility

Validates anti-patterns that break SKILL.md portability across Claude Code / Copilot / Cursor / Codex / Gemini. Apply 4 atomic checks (**MC1**–**MC4**) per skill: no `allowed-tools:` in frontmatter, no per-skill `rules/{tool}.md`, portability claim matches actual content, Task-orchestration awareness for Gemini. Full check table, detection commands, severity matrix, and per-check rationale in `references/multi-tool-compat-spec.md`.

### Phase 5 — Security validation

Apply 3 atomic passes per `references/security-spec.md`. Scans **both** `SKILLS_DIRS` (every `.md` under each skill — SKILL.md + `references/` + `assets/`) **and** `AGENT_DIRS` (every agent .md).

1. **Pass 5.1 — Secret patterns:** regex sweep for vendor credential formats (OpenAI / Anthropic / Slack / GitHub / AWS / Google) + private keys + Bearer tokens; honor documentation-placeholder allowlist. Findings **S1–S10**.
2. **Pass 5.2 — Dangerous shell patterns:** detect `rm -rf` on system paths, pipe-to-shell installers, `eval`, fork bombs, disk-wipe patterns, force push / `git reset --hard`, approval-bypass phrasing; skip anti-pattern headings. Findings **DS1–DS12**.
3. **Pass 5.3 — Credential file path reads:** flag references to `~/.aws/credentials`, `~/.ssh/id_rsa`, `~/.gnupg/`, `.netrc`, etc.; distinguish documentation from skill behavior. Findings **C1–C9**.

**Output discipline:** report MUST mask every matched secret (first 5 + last 3 chars; never print raw match). Full regex catalog, allowlists, and per-finding severity in the spec file.

### Phase 5.5 — Metainfo coverage (since 1.8.0)

Validates the `metainfo:` frontmatter sub-block introduced for installer
filtering and library coverage analytics. Apply 6 atomic checks per skill:

| # | Check | Severity |
|---|---|---|
| **M1** | `metainfo` block present in frontmatter | 🔴 |
| **M2** | `metainfo.category` present and non-empty array | 🔴 |
| **M3** | `metainfo.tier` present, value ∈ `{stable, preview, experimental, internal}` | 🔴 |
| **M4** | Every `category` value belongs to closed vocab in `docs/skill-authoring-standard.md` | 🟡 |
| **M5** | `metainfo.owner` set (handle or team) | 🟡 |
| **M6** | If `deprecated:` is set, `replaced_by:` must also be set | 🟡 |

**Why it matters:** the installer reads `metainfo` from `skills/INDEX.jsonl`
to decide which skills to copy. Skills without `metainfo` get a sentinel
`tier="unknown"` and are excluded from the default install — they
effectively become invisible to new users. Category drift (M4) silently
breaks `--category` filters across the company. Missing owner (M5) blocks
escalation when a skill misbehaves in production.

**Coverage report** (always emitted, even when 0 findings): table of
skills-by-category × skills-by-tier so the reader sees the library shape
at a glance. Surface orphans (no metainfo) at the top, then the matrix,
then the unknown-vocab list if any.

### Phase 6 — Aggregate + write report (4-part structured)

Compose per-skill records `{skill, phase, rule, severity, evidence}`, apply `STRICTNESS` overrides, compute per-category counts and verdict (🟢 healthy = 0 🔴 ∧ 🟡 ≤ 1; 🟡 attention = 0 🔴 ∧ 🟡 ≥ 2; 🔴 action required = any 🔴). Report has three layers:

1. **Layer 1 — Category roll-up** (always present): 10-second decision table, one row per category + Overall.
2. **Layer 2 — Per-category 4-part block** (`detailed` mode): for each of the 7 categories (incl. Metainfo coverage P5.5) — even 🟢 ones — emit *What we check / What we found / Why it matters / How to fix*.
3. **Layer 3 — Recommendations** (always present): impact-ordered remediation list.

**Full output template — exact tables, worked example for «Token budget», report frontmatter schema — lives in `assets/output-template-detailed.md`. Read that file when producing the report.**

### Verbosity contracts

- `terse` — Layer 1 only + Layer 3. Skip per-category blocks.
- `standard` — previous v1.4 format (roll-up + per-phase findings tables with `{skill, rule, severity, evidence, fix}` columns, no «Why it matters» rationale).
- `detailed` (default) — all three layers + per-category «Why it matters» rationale.

### Cross-cutting output rules

- **Why-it-matters rule:** every per-category «Why it matters» block MUST name the concrete downstream failure mode — what breaks if the user ignores findings in this category. No abstract «quality matters» — name the specific user impact.
- **Evidence rule:** every finding MUST cite skill name + file:line OR a specific quoted phrase. «Some skills have...» without naming is forbidden.
- **Fix rule:** every «How to fix» entry MUST name what to change, where (file:line or section), and what severity it removes.
- **Always-explain rule:** even when a category is 🟢 healthy with 0 findings, the «What we check / Why it matters» parts MUST appear — the reader of an audit needs to know what the auditor looked for, not just that it found nothing.

---

## Output

- `out/library-audit/library-audit-{TODAY}.md` — markdown report.

## State persistence (resumable runs)

This skill is multi-phase and may be interrupted (long library scans, slow disks,
process timeouts). It saves a checkpoint after every phase so it can resume.

| Phase | Checkpoint? | What is stored |
|---|---|---|
| P0 — env & rules setup | yes | resolved `SKILLS_DIRS`, `AGENT_DIRS`, rule specs loaded |
| P1 — handoff validation | yes | per-skill handoff findings |
| P2 — token budget | yes | per-skill body length, claims-vs-actual table |
| P3 — naming validation | yes | per-skill naming verdicts |
| P4 / P4.5 — portability + multi-tool compat | yes | per-skill flags |
| P5 — security validation | yes | per-file (skill + agent) secret/dangerous/credential hits (masked) |
| P5.5 — metainfo coverage | yes | per-skill M1–M6 findings + coverage matrix raw counts |
| P6 — aggregate + write report | no (terminal) | — |

- Default `RESUME=auto` (validator stays detect-only — never asks).
- State location: `${CWD}/.skill-state/library-audit/run-{utc-timestamp}.json`.
- See `$SGT_ROOT/references/checkpointing.md` for the schema and the helper CLI (shared repo-root reference, not skill-bundled — resolve `$SGT_ROOT` per `references/path-resolution.md`).

## Hard rules

- ❌ No file edits (other than the checkpoint state files and the final report).
- ❌ **Clarification policy:** never. No user clarification prompts regardless of phase (per the validator-skill contract).
- ✅ Idempotent — running twice on the same library produces identical output.
- ✅ Composable — can be called by a parent health-check skill with `MODE=full`.
- ✅ Resumable — interrupted runs continue from the last checkpoint when re-invoked.
- ✅ Naming gate: any 🔴 Phase 3 violation in a **new** SKILL.md blocks merge.
