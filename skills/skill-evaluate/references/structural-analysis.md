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

**Required by this toolkit** (NOT by the universal standard — `name` and
`description` remain the only universal-standard requirements):

| Field | Requirement | Severity if missing |
|---|---|---|
| `metainfo` | Sub-block with `category` (non-empty array, closed vocab) and `tier` (`stable` / `preview` / `experimental` / `internal`) — required since 1.8.0; mirrors AGENTS.md rules 1 & 8 and engine rule `SKILL007` | 🟡 Major |

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

**`## When to use` / `## When not to use` are OPTIONAL (policy, since rules 0.5.0).**
Activation is driven by the frontmatter `description` (the routing surface);
exclusion triggers belong there, and hard rules in `AGENTS.md`. A **missing** body
activation section is **not** a finding — do not flag it, do not suggest adding it.
**If present**, the `## When to use` section *should* use the four canonical
subsections (`**Always:**` / `**ESPECIALLY when:**` / `**Skip / Don't use for:**` /
`**Don't skip when:**`) so [3.7](#37--activation-coherence-this-skill) can check its
coherence with the description — non-canonical headers on a present section →
🟡 Minor (rename), never Major.

Recommended sections (each missing → 🟡 Minor):
- `## Required Inputs` (table)
- `## Phase 0..N` or `## Workflow` (for skills with explicit process)
- `## Hard rules`
- `## Stop conditions` / `## Success criteria`

## 3.1 — Skill size & density

**Thresholds are the single source of truth in the gate config**: defaults
`body_budget: 500` / `body_critical: 600` are hardcoded in the config block of
`scripts/agent_audit.py`, overridable via the `config` block in
`references/agent-audit-rules.json` (or a file pointed to by
`AGENT_GOVERNANCE_RULES_PATH`); `references/agent-audit-config.example.json` is
an optional example overlay. Never hardcode a different boundary here or in
`library-audit`. Defaults: budget **500**, critical **600**. Recommended
authoring target: **≤ 200** lines.

| Body lines | Classification |
|---|---|
| ≤ 120 | Clean — no action |
| 121 – 200 | Review — recommended target ≤ 200 |
| 201 – 500 | Overload candidate — extract to `references/` |
| 501 – 600 | Over budget (`body_budget`) — 🟡 |
| > 600 | Critical (`body_critical`) — 🔴 split now |

**Why these numbers.** `≤ 120` = lean enough that nothing needs extracting. `≤ 200`
= the authoring target: past it, mid-body instruction adherence starts to fall on
several hosts, so detail belongs in `references/` (loaded on demand) rather than
the body (loaded every turn). `500` / `600` are the gate budget/critical lines and
are config-driven (above) — the `120` / `200` here are non-enforced authoring
guidance, not gate thresholds.

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

**Informational only — no score impact.** If a pattern is detected → note it; if the task clearly calls for a different pattern → suggest it in one sentence. Do NOT cap any dimension on this; pattern naming is too subjective to score consistently across runs. (If a future need makes it scoreable, give it explicit thresholds first.)

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
- **Pass 3.5.2 — Dangerous shell patterns** (rule IDs DS1–DS12). See security-spec §Pass 5.2 for the catalog.
- **Pass 3.5.3 — Credential file path reads** (rule IDs C1–C9). See security-spec §Pass 5.3 for the catalog.

This skill body deliberately does NOT spell the patterns inline — that would (a) duplicate the canonical doc and drift over time, (b) trigger false positives when the auditor scans this very SKILL.md. All literal patterns live in security-spec.md (which is self-excluded from Phase 5 scanning).

Honor allowlists from security-spec.md (anti-pattern headings, documentation placeholders, fenced code blocks).

**Output discipline:** every matched secret MUST be masked — first 5 + last 3 chars of the match. Never print the raw value in the report.

**D9 score caps from lexical findings** (applied AFTER initial D9 scoring from Phase 1):

- Any 🔴 secret hit (S-rules) → D9 ≤ 2
- Any 🔴 dangerous-shell hit (DS-rules, not allowlisted) → dimension D9 ≤ 3
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

**Threshold rationale (3.6.2 / 3.6.4).** These are **calibrated heuristics, not hard limits** — tune them if a corpus proves them wrong. Filler `≥3 → 🟡 / ≥6 → 🔴`: one or two stock phrases are noise tolerance; three signals a habit, six signals prose that should be rewritten. Long-prose `>5 sentences`: a single paragraph past ~5 sentences is where context-routing reliably starts skimming. They live here (LLM-applied, soft signals feeding D1) rather than in the gate config because they require judgement, not a deterministic count — unlike the body-length budget, which is a hard gate threshold and IS config-driven.

Findings land in the Phase 4 output's **«Writing quality»** section, separately from the D1 score — both signals matter. See [AGENTS.md → Writing Style](../../../AGENTS.md#writing-style) for the project-level guidelines that inform these checks.

## 3.7 — Activation coherence (THIS skill)

**Self-exclusion (meta-rule):** files inside `skills/skill-evaluate/` are **exempt** — this skill documents the check (its own body carries the worked-example strings) and would self-flag.

The `description` and the body's `## When to use` are two activation surfaces that load at different times: `description` routes activation (always in context); the body's `Skip / Don't use for` + `## When not to use` refine it *after* activation. They must agree on the **positive** scope — a body that excludes a case the description positively advertises makes the agent activate then abort, and erodes trust in the routing surface.

This is a **semantic** sub-check (the only one in Phase 3): read both regions and judge each Skip line, rather than matching a regex.

| Pass | What we check | Detection | Severity |
|---|---|---|---|
| **3.7.1** | **Activation coherence.** The body's `Skip / Don't use for` and `## When not to use` must only *narrow* (exclude a neighbour/subset the description never claimed), never *negate* a case the `description` positively triggers on. | Extract the description's positive triggers (the «when use it» clauses) and the body's Skip/When-not-to-use lines. For each Skip line, judge: does it remove an **advertised** case (🔴 contradiction) or bound an **unclaimed** one (no finding)? | 🔴 |

**D8 score cap from a coherence finding** (applied AFTER initial D8 scoring from the rubric):

| Finding | D8 cap |
|---|---|
| Any 🔴 contradiction (3.7.1) | D8 ≤ 3 |

Set the JSONL flag `activation_coherent: false` on a 🔴, `true` otherwise. On a contradiction, add a top_issue naming the exact pair (advertised trigger ↔ excluding Skip line). See [`rubrics.md` → D8 Activation-coherence gate](rubrics.md#activation-coherence-gate-caps-d8--3) for worked examples of contradiction vs legitimate narrowing.

Rationale: D8 (Discoverability) asks «will the right need activate this skill, and only the right need?» A description that advertises a case the body then refuses fails that test no matter how rich its trigger phrasing.

## 3.8 — Negative-rule placement (info)

**Self-exclusion (meta-rule):** files inside `skills/skill-evaluate/` are **exempt** — this skill documents the check (its own body carries the worked-example strings) and would self-flag.

**This is the first `info`-severity sub-check.** Its contract: a 3.8 finding is recorded in the `info_flags` JSONL field and the report's **«Info (no action required)»** section. It **does not cap** any dimension and does not affect the Score, tier, or safety gate. Info is a *stage*, not a verdict — a check that accumulates evidence here can later be promoted to a capping severity. See [extending-checks.md → Info / experimental lane](../../../docs/extending-checks.md#info--experimental-lane) for the contract and promotion path.

**Why this check exists.** A prohibition is the most fragile instruction exactly where it matters most. A positive instruction has a natural trigger — the task re-summons it. A negative rule («do not use this skill if…», «never delete without confirm») has no trigger: the thing it forbids never announces itself, so nothing re-activates the rule. On long runs, once the skill body scrolls out of the recent window or is summarized, a low-weight prohibition buried mid-body is simply gone. Inflating it with `YOU MUST` / `MANDATORY` is a losing arms-race: weight added to one section is salience stolen from every other. The fix is **location, not weight** — move each prohibition to the layer loaded at the moment its decision is made.

**Two kinds of «don't» — judged differently.** This is a **semantic** sub-check (like 3.7): read each negative rule in the body and classify its *form*, not match a regex.

| Form in body | Verdict | Recommended relocation |
|---|---|---|
| Negative boundary already in `description` (anti-trigger) | ✅ reward — no finding | — (already in the routing layer) |
| **Activation** prohibition as prose in a **non-canonical** section («do not use this skill if/when X» in `## Notes` or mid-Phase prose) | 🔵 info | move the scope into `description` (prevents *selection*; body loads only *after* the wrong choice is made) |
| **Safety/execution** prohibition as prose («never push to read-only», «always update this file») | 🔵 info | hoist to `AGENTS.md` (always-on, loaded every turn — survives long runs) |
| `Skip / Don't use for` or `## When not to use` content inside the **canonical** activation sections | ✅ no finding | — (the sanctioned in-body refinement — see scope-out below) |
| Executable **Phase-0 gate** (a check that fails fast with a message) | ✅ no finding | — (a gate *does* something at the moment of decision; it cannot be skipped) |
| **In-flow branch** conditional read at its point of use («on the fast path, skip if diff touches migrations») | ✅ no finding | — (read in the execution flow where it applies) |

**Scope-out — do NOT conflict with the structure checks.** The canonical activation sections are the **sanctioned** (optional, since rules 0.5.0) in-body home for negative scope: `## When to use` and all its subsections (including `**Skip / Don't use for:**` and `**Don't skip when:**`) and `## When not to use`. When present, their structure is governed by [3.0b](#30b--body-structure) and their coherence with the description by [3.7](#37--activation-coherence-this-skill). **3.8 never flags content inside them** — flagging a sanctioned section would pit one check against another. 3.8 fires only on prohibitions **outside** these sections.

**Defer to 3.7.** A `Skip` / `When not to use` line that *contradicts* the `description`'s positive scope is 3.7's concern (caps D8) — 3.8 does **not** double-flag it. 3.8 is about *placement of a stray prohibition*, not coherence.

**Detection.** Scan the body **excluding** the canonical sections named in Scope-out. Candidate lines: passive prohibitions (`do not use`, `don't use`, `never use this`, `не используй`, `не делай` — the Cyrillic entries are deliberate detection patterns for skills written in Russian, a sanctioned script mix exempt from the single-language rule) **not** inside a fenced code block and **not** part of a Phase-0 gate (no accompanying fail-fast action + message). For each candidate, judge the form per the table above. The robust form of a body-level «don't» is an executable gate; passive prose is the weak form this check surfaces.

| Pass | What we check | Detection | Severity |
|---|---|---|---|
| **3.8.1** | **Negative-rule placement.** Passive prose prohibitions buried in the body that would be more reliable in the `description` (activation) or `AGENTS.md` (safety/execution). | Semantic: classify each candidate prohibition by form; emit info for passive-prose activation/safety rules, none for description boundaries / Phase-0 gates / in-flow branches. | 🔵 info |

Set the JSONL flag `info_flags.negative_rule_placement` to the count of passive-prose prohibitions found (0 if none). Each finding names the line and the recommended layer. No dimension cap, ever.

**Worked examples** (the executable spec for this check) — see [`rubrics.md` → Negative-rule placement (info, 3.8)](rubrics.md#negative-rule-placement-info-38).
