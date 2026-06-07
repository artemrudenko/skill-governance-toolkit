# Phase 3 — Structural Analysis (full sub-check catalog)

Loaded by `skill-evaluate` Phase 3. Each sub-check is detect-only; findings
land in the Phase 4 report and may cap specific D-scores.

---

## 3.0 — Frontmatter compliance

**`name` field:**
- Length ≤ 64 chars; matches regex `^[a-z0-9-]+$`; equals parent directory name.

**Permitted extension fields** (not in agentskills.io minimum, widely supported):

| Field | Use |
|---|---|
| `compatibility` | Free-text list of supported runtimes (e.g. `"Claude Code · GitHub Copilot · Cursor v2.2+ · OpenAI Codex CLI · Google Gemini CLI"`) |
| `license` | License of the skill content (e.g. `MIT`) |
| `portability` | Enum: `portable` / `hybrid` / `project-local` (alternative to `compatibility`) |

**Forbidden fields** (universal portability anti-patterns):

| Field | Why forbidden | Severity |
|---|---|---|
| `allowed-tools` | Claude Code treats as hard whitelist; other hosts ignore → silent inconsistency | 🔴 Critical |
| `type`, `status`, `last_updated`, `last_verified` | Not in `agentskills.io` spec; treated inconsistently across hosts | 🟡 Major |

**`description` length:**

| Length (chars) | Verdict |
|---|---|
| < 80 | 🔴 Too short — likely missing trigger phrases |
| 80 – 99 | 🟡 Acceptable, lean |
| **100 – 400** | 🟢 **Sweet spot** |
| 400 – 600 | 🟢 Slightly verbose |
| 600 – 1024 | 🟡 Over sweet spot |
| > 1024 | 🔴 Exceeds `agentskills.io` hard limit |

**Description must answer BOTH:**
1. **What does the skill do?** — action verb + scope visible
2. **When should the agent use it?** — trigger phrases verbatim, in user's language

## 3.0b — Body structure

Mandatory:
- `# {Skill Name}` H1 heading
- `**Purpose:**` — 1–2 sentence business context
- `## When to use` section with the four canonical subsections:
  - `**Always:**`
  - `**ESPECIALLY when:**`
  - `**Skip / Don't use for:**`
  - `**Don't skip when:**`

If missing or has alternative headers → flag 🟡 Major. Suggest renaming.

Recommended sections (each missing → 🟡 Minor):
- `## Required Inputs` (table)
- `## Phase 0..N` or `## Workflow` (for skills with explicit process)
- `## Hard rules`
- `## Stop conditions` / `## Success criteria`

## 3.1 — Skill size & density

Platform limits:
- Hard limit: **≤ 500 body lines** before instructions in the middle degrade.
- Recommended: **≤ 200 body lines** for high reliability.
- Below 120 lines → lean, no extraction needed.

| Body lines | Classification |
|---|---|
| ≤ 120 | Clean — no action |
| 121 – 200 | Review — check for extractable detail |
| 201 – 500 | Overload candidate — strongly recommend `references/` |
| > 500 | Critical — split immediately |

## 3.2 — Scan for extractable content

Identify content that belongs in `references/` rather than the core:

| Pattern in body | Target file |
|---|---|
| Pass-by-pass procedures, large worked examples, edge-case catalogs | `references/{topic}.md` |
| Output templates > 20 lines | `references/templates.md` |
| Scoring rubrics, threshold tables | `references/rubrics.md` |
| Long tool-name tables | repo-level `references/{tool}-tools.md` (NOT per-skill) |

If 3+ matches found → produce an **Extraction Proposal** in the output.

## 3.3 — Agent pattern identification

| Pattern | Signals in skill body |
|---|---|
| **ReAct** | «observe result before next step», «adapt based on output», iterative loop |
| **ReWOO** | «plan all steps first», «execute in parallel», «synthesize at end» |
| **CodeAct** | «write and run code», «iterate until tests pass», «sandbox» |
| **Orchestrator-Workers** | «delegate to subagents», `Task` tool, «parallel agents» |
| **Evaluator-Optimizer** | «generate then evaluate», «retry if criteria not met», «max N rounds» |
| **None / procedural** | Simple sequential steps, no looping or delegation |

If a pattern is detected → note it. If the wrong pattern is used for the task → suggest the right one with a one-sentence justification.

## 3.4 — Scripts efficiency check (Anthropic guidance)

If `scripts/` directory exists:
- ✅ Correct: body says «run `scripts/{name}.py`», «execute the script», «invoke `python scripts/...`».
- ❌ Anti-pattern: body says «read `scripts/{name}.py`», «follow the logic in scripts/...».

«**Scripts can run without loading their contents into context.** Tell the agent to run the script, not read it.» If anti-pattern detected → flag 🟡 Major.

Also check: scripts have no pip dependencies (stdlib only) — portability requirement.

## 3.4b — Multi-tool compatibility

Cross-checks aligned with `library-audit` Phase 4.5 (but for a single skill):

| Check | Detection | Severity |
|---|---|---|
| `allowed-tools:` absent | grep frontmatter | 🔴 if portability claimed; 🟡 otherwise |
| No per-skill `rules/{tool}.md` files | `ls {skill_dir}/rules/{tool}.md` | 🟡 (should use repo-level `references/`) |
| If body uses `Task` / sub-agent dispatch, documents sequential fallback | grep body | 🟡 if missing fallback |
| If body prompts the user, documents clarification policy + non-interactive override | grep body | 🟡 if missing policy or override |

## 3.5 — Lexical security scan (THIS skill)

**Load patterns from the canonical catalog:** read `$SGT_ROOT/skills/library-audit/references/security-spec.md` — the single source of truth shared with `library-audit` Phase 5 (resolve `$SGT_ROOT` per `references/path-resolution.md`). If `library-audit` was not installed alongside `skill-evaluate`, this catalog is absent — see the SKILL.md "Phase 3.5 dependency" note (install both, or run reduced mode and log it). Apply all three pass-sets, **scoped to the one SKILL.md being evaluated**, NOT the whole library:

- **Pass 3.5.1 — Secret patterns** (rule IDs S1–S10). See security-spec §Pass 5.1 for the regex catalog.
- **Pass 3.5.2 — Dangerous shell patterns** (rule IDs D1–D9). See security-spec §Pass 5.2 for the catalog.
- **Pass 3.5.3 — Credential file path reads** (rule IDs C1–C9). See security-spec §Pass 5.3 for the catalog.

This skill body deliberately does NOT spell the patterns inline — that would (a) duplicate the canonical doc and drift over time, (b) trigger false positives when the auditor scans this very SKILL.md. All literal patterns live in security-spec.md (which is self-excluded from Phase 5 scanning).

Honor allowlists from security-spec.md (anti-pattern headings, documentation placeholders, fenced code blocks).

**Output discipline:** every matched secret MUST be masked — first 5 + last 3 chars of the match. Never print the raw value in the report.

**D9 score caps from lexical findings** (applied AFTER initial D9 scoring from Phase 1):

- Any 🔴 secret hit (S-rules) → D9 ≤ 2
- Any 🔴 dangerous-shell hit (D-rules, not allowlisted) → D9 ≤ 3
- Any 🟡 credential-path read (C-rules) → D9 ≤ 4

Rationale: a beautifully designed skill with safety-aware sub-concerns (high initial D9) still loses points if its FILE contains a leaked credential or a destructive shell pattern. The design awareness didn't catch the implementation slip.

Findings land in the Phase 4 output's **«Lexical security»** section, separately from the D9 score itself — both signals matter.

## 3.6 — Writing quality scan (THIS skill)

**Self-exclusion (meta-rule):** files inside `skills/skill-evaluate/` are
**exempt** from Phase 3.6 scanning of their own bodies. This skill documents
the patterns it looks for (banned filler phrases listed verbatim, non-Latin
script ranges shown as regex examples) — it would trivially flag itself on
every run. The implementer MUST exclude `skills/skill-evaluate/**` from
the Phase 3.6 scan corpus. All other skills, references, and agents remain
in scope.

**Allowlist for ALL scans (3.6.1–3.6.4):** patterns inside fenced code
blocks (```), inline backtick spans, markdown table cells documenting
detection rules, and explicit «banned list» enumerations are skipped.
This lets any skill educate about anti-patterns without self-flagging.

Single-language, concise, non-redundant skill bodies route better, save
tokens, and read cleaner. This sub-phase runs four lexical checks against
the SKILL.md body (frontmatter excluded). Detect-only; findings cap D1.

| Pass | What we check | Detection | Severity |
|---|---|---|---|
| **3.6.1** | **Language consistency.** Body should use a single primary language. Non-Latin scripts mixed into a Latin-script body fragment routing accuracy and bloat tokens. | Regex sweep for Cyrillic, CJK, Arabic, Greek script ranges. If body has Latin majority + any of the above outside fenced code blocks or quoted user input → 🔴. Single non-Latin body is acceptable; mixing is the issue. | 🔴 |
| **3.6.2** | **Filler density.** Banned phrases that add ceremony but no information. Each adds 4–8 tokens of pure overhead. | Count occurrences from the catalog. ≥ 3 in body → 🟡; ≥ 6 → 🔴. | 🟡 / 🔴 |
| **3.6.3** | **Duplicate paragraphs.** Same multi-sentence block appearing ≥ 2 times in the body without explicit restatement marker. Sometimes intentional (Hard rules re-state); often unintentional copy-paste during refactor. | For each paragraph ≥ 30 chars, hash and count duplicates. Two identical → 🟡; three or more → 🔴. | 🟡 / 🔴 |
| **3.6.4** | **Long prose without breaks.** 5+ consecutive sentences in a single PROSE paragraph (no internal list / table / code-block / sub-heading break). **Lists (bulleted OR numbered) are NOT prose** — they ARE the break this rule rewards. | Detect contiguous list-item lines as lists, not prose. Then count sentence terminators in narrative paragraphs; flag > 5 sentences. | 🟡 |

**D1 score caps from lexical findings** (applied AFTER initial D1 scoring from Phase 1):

| Finding | D1 cap |
|---|---|
| Any 🔴 language-mix hit (3.6.1) | D1 ≤ 3 |
| Any 🔴 filler-density hit (3.6.2) | D1 ≤ 3 |
| Any 🔴 duplicate-paragraph hit (3.6.3) | D1 ≤ 3 |
| ≥ 2 🟡 hits across 3.6.2–3.6.4 | D1 ≤ 4 |

Rationale: D1 (Clarity) ultimately asks «can a fresh reader follow this skill?» — a skill that is multilingual, filler-heavy, or repeats itself answers «no» regardless of how clearly the phases are individually written.

Findings land in the Phase 4 output's **«Writing quality»** section, separately from the D1 score — both signals matter. See [AGENTS.md → Writing Style](../../../AGENTS.md#writing-style) for the project-level guidelines that inform these checks.
