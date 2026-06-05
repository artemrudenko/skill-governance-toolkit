# Checks Reference

Complete catalog of every governance check this toolkit applies, with the
rationale behind each. Checks come from two engines:

| Engine | Implementation | Determinism | Where it runs |
|---|---|---|---|
| **Deterministic engine** | `scripts/agent_audit.py` (Python, stdlib-only) | 100% reproducible | CLI, CI gate, MCP, Docker |
| **LLM skills** | `skill-evaluate`, `library-audit` (Markdown procedures an agent executes) | Model-driven | Interactive agent sessions |

> Not to be confused with the **three instruction layers** (L1 `AGENTS.md` /
> L2 `SKILL.md` / L3 `agents/`) in [`architecture.md`](architecture.md) — that
> is the loading hierarchy; this page is about *checks*.

The deterministic engine is the CI blocker (fast, free, repeatable). The LLM
skills add depth a lexical engine cannot reach (semantic clarity, trigger-phrase
quality, cross-skill collisions). See
[§ Engine vs LLM skills](#engine-vs-llm-skills).

The runtime source of truth for engine rules is
[`references/agent-audit-rules.json`](../references/agent-audit-rules.json);
inspect any rule live with `agent_audit.py explain-rule <RULE_ID>`. This page
adds the *what it detects* and *why it matters* that the JSON omits.

---

## Deterministic engine rules

25 rules across two families: `DISC*` (project-level discovery) and `SKILL*`
(per-`SKILL.md`). Severity drives the CI gate: `--fail-on high` blocks a merge
on `high`; `medium`/`low`/`info` are advisory.

### Discovery rules (`DISC*`)

| Rule | Severity | Detects | Why it matters |
|---|---|---|---|
| DISC001 | info | More than one `AGENTS.md` instruction root in the tree | Nested instruction roots silently change which rules apply where; should be intentional |
| DISC002 | medium | `CLAUDE.md` / `GEMINI.md` / `.github/copilot-instructions.md` that does not import `AGENTS.md` | Aliases must stay thin imports, or per-tool instructions drift apart |

### Skill rules (`SKILL*`)

| Rule | Severity | Detects | Why it matters |
|---|---|---|---|
| SKILL001 | high | No YAML frontmatter block | Runtimes cannot discover the skill's `name`/`description` to route to it |
| SKILL002 | high | Missing required `name` or `description` | The Agent Skills standard minimum; without it the skill is unloadable |
| SKILL003 | medium | `description` shorter than the routing threshold | Sparse trigger phrases route poorly; the agent won't activate the skill |
| SKILL004 | high | `description` over 1024 characters | Exceeds the Agent Skills hard limit; parsers may reject or truncate |
| SKILL005 | medium | No `compatibility:` field | Toolkit requires explicit portability claims |
| SKILL006 | medium | No `license:` field | Portable reuse needs license metadata |
| SKILL007 | medium | No `metainfo:` block | `metainfo.category`/`tier` drive installer filtering and audits |
| SKILL008 | medium | `metainfo.category`/`tier` outside the closed vocabulary | Free-text values break `--category`/`--tier` selective install |
| SKILL009 | high | `allowed-tools:` present | Enforced by some hosts, ignored by others → silent cross-platform divergence |
| SKILL010 | medium | Claude-only / host-only frontmatter field | Tool-specific keys weaken the portability claim |
| SKILL011 | medium | Body longer than the line budget | Long bodies should push detail into `references/`, `scripts/`, `assets/` |
| SKILL012 | low | No "When to use" / activation section | Explicit activation + skip criteria reduce accidental triggering |
| SKILL013 | medium | No verification guidance | Skills should state how to confirm completion or quality |
| SKILL014 | high | Destructive shell, approval bypass, or unsafe git (`rm -rf`, `--force`, `reset --hard`) | Skills must not normalize dangerous operations into the agent's behavior |
| SKILL015 | high | Embedded secret or a path toward credentials | Skills must never carry tokens or steer agents at credential stores |
| SKILL016 | medium | External content (web, email, project docs) trusted without verification | Untrusted input treated as instructions enables prompt injection |
| SKILL017 | medium | Hardcoded home path or org-specific location | Absolute/org paths break portability across machines and teams |
| SKILL018 | medium | `Task` / sub-agent dispatch with no documented sequential fallback | Hosts differ on sub-agent support; dispatch must be optional, not required for correctness |
| SKILL019 | medium | Overbroad scope language ("scan all", universal-agent phrasing) | Skills should be narrow workflows, not catch-all agents |
| SKILL020 | low | No predecessor/successor workflow metadata | Handoff contracts are clearer when adjacent skills are declared |
| SKILL021 | medium | Missing `Skill type` declaration | Users need to know whether a skill is detect-only or mutating before trusting it |
| SKILL022 | medium | User prompt language without clarification policy, or prompt language contradicting `never asks` | Interactive behavior must be bounded so non-interactive and CI flows do not hang or guess |
| SKILL023 | high | Mutating skill missing preview, confirmation, verification, or exact write scope | Mutations need a visible safety contract before an agent edits files or external state |

### Profile scope

`--profile` filters which rules can fire. The severity gate (`--fail-on`)
applies after filtering.

| Profile | Rules applied | Use |
|---|---|---|
| `security` | Only the safety/portability subset: SKILL001, 002, 005–010, 014–017, 023 | Safety-focused scan |
| `quality` | All rules **except** SKILL015 | Structure, usability, portability |
| `maintainability` | All rules | Broad regular maintenance scan |
| `release-ready` | All rules | Pre-release gate (CI default) |

SKILL015 (secrets) is dropped from `quality` because secret scanning belongs to
the `security` and release gates, not the day-to-day structural pass.

---

## LLM skill criteria

These run inside an agent session, not in CI. They interpret meaning, not just
lexical patterns.

### `skill-evaluate` — 9 dimensions (D1–D9)

Scores one `SKILL.md`. Full rubric: [`skills/skill-evaluate/SKILL.md`](../skills/skill-evaluate/SKILL.md).

| Dim | Focus |
|---|---|
| D1 | Clarity (capped by Phase 3.6 on language mix / filler / duplicate paragraphs) |
| D2 | Completeness |
| D3 | Specificity |
| D4 | Examples |
| D5 | Constraints |
| D6 | Portability |
| D7 | Testability |
| D8 | Discoverability |
| D9 | Safety (capped by the Phase 3.5 lexical security scan; read-only skills get a D9 floor of 4) |

Total score is D1+…+D9 (max 45). A **safety gate** forces the verdict to 🔴 Red
when D9 ≤ 1 and the skill mutates state or ingests untrusted input, regardless of
the numeric score.

### `library-audit` — collection-level phases

Meta-validates a whole library: handoff contracts, trigger uniqueness,
clarification policy, token budget, naming, portability, multi-tool
compatibility, security baseline, and metainfo coverage (Phase 5.5).
Full procedure: [`skills/library-audit/SKILL.md`](../skills/library-audit/SKILL.md).

---

## Engine vs LLM skills

**Does the engine give the same depth of evaluation as the LLM skills? No — and
that is by design.** The two answer different questions:

- The **deterministic engine** answers *"is this structurally and safely valid?"*
  It is **as good as or better than** the LLM on objective, lexical facts —
  frontmatter presence, `allowed-tools`, secrets, dangerous shell, line budget —
  because it is exact and never hallucinates. About half the checks are of this
  kind.
- The **LLM skills** answer *"is this a **good** skill?"* They reach what a
  lexical engine cannot: whether trigger phrases actually route well (the engine
  only measures description *length*), whether prose is clear, whether two skills
  **collide** on triggers, whether a workflow is logically sound for its goal.

So the engine is **deliberately shallower on semantics and richer on
determinism**. Use the engine where reproducibility matters (a blocking merge
gate); use the LLM skills where judgement matters (authoring review). Running the
engine in CI and the LLM skills as an advisory/on-demand step is the intended
split — neither replaces the other.

| Question | Deterministic engine | LLM skills |
|---|---|---|
| Is the frontmatter present and valid? | ✅ exact | ✅ |
| Does `allowed-tools:` / a secret / `rm -rf` appear? | ✅ exact | ✅ |
| Is the body over budget? | ✅ exact (line count) | ✅ |
| Are the **trigger phrases actually good** for routing? | ⚠️ length only | ✅ semantic |
| Is the prose clear, single-language, filler-free? | ⚠️ partial | ✅ |
| Do two skills **collide** on triggers? | ❌ | ✅ (cross-skill) |
| Is the workflow logically sound for its goal? | ❌ | ✅ |

**Rule of thumb:** the engine answers *"is this structurally and safely valid?"*
deterministically — the right question for a blocking merge gate. The LLM skills
answer *"is this a good skill?"* — the right question for authoring review.
The CI gate runs the engine; route the LLM skills as an advisory or on-demand
step.

---

## Extending the checks

The dividing line is **data vs algorithm**: policy data lives in configuration;
detection algorithms stay in code. An organization can tune policy without
forking Python by pointing `AGENT_GOVERNANCE_RULES_PATH` at a custom catalog.

### Configurable policy (no code change)

Rule metadata (id, severity, title, rationale) lives in
[`references/agent-audit-rules.json`](../references/agent-audit-rules.json). The
same file accepts an **optional `config` block** that overrides built-in policy
data. Every key is optional; absent keys fall back to the shipped defaults.

```json
{
  "rules": [ /* … the full rule catalog … */ ],
  "config": {
    "thresholds": {
      "description_min": 80,
      "description_max": 1024,
      "body_budget": 500,
      "body_critical": 600
    },
    "vocabularies": {
      "categories": ["marketplace"],
      "tiers": ["lts"]
    },
    "profiles": {
      "quality_exclude": ["SKILL015"]
    },
    "patterns": {
      "dangerous": [
        {"label": "kubectl delete", "regex": "kubectl\\s+delete", "suggestion": "Avoid cluster deletion.", "ignore_case": false}
      ],
      "secrets": [
        {"label": "Example org token", "regex": "ARK-[A-Za-z0-9]{20,}"}
      ]
    }
  }
}
```

| Key | Merge semantics | Effect |
|---|---|---|
| `thresholds` | **override** per key | Tune SKILL003/004 length and SKILL011 body budgets |
| `vocabularies.categories` / `.tiers` | **extend** (union with defaults) | Add org categories/tiers without losing the closed vocab — SKILL008 |
| `profiles.security` | **override** the set | Define which rules the `security` profile keeps |
| `profiles.quality_exclude` | **override** the set | Define which rules the `quality` profile drops |
| `patterns.dangerous` / `.secrets` | **extend** (append to defaults) | Add org-specific SKILL014/015 detections without losing the baseline |

A ready-to-copy, validated example lives at
[`references/agent-audit-config.example.json`](../references/agent-audit-config.example.json).

The custom catalog must still define every `rule_id` the engine emits (the
`config` block does not relax that contract). Validate a custom catalog with
`agent_audit.py rules --format json` — it now reports a malformed `config` block,
not only a malformed rule list.

**Guardrails (pilot):** core safety rules SKILL001/002/009/014/015 have a severity
floor — a catalog that downgrades them below `high` is rejected at load. Config
`thresholds` must be positive integers and `patterns` regexes are validated and
length-capped. Narrow `profiles.security` only to **extend** coverage; weakening
it is discouraged (a subset-guard is planned).

**Traceability:** every audit report stamps `rules_version` (the catalog
`version`) and `engine_version`, so a verdict ties back to the exact policy and
engine that produced it.

### Separation of duties

Who may change the *standards* should differ from who authors the *skills* a
standard governs. The repo ships a root [`CODEOWNERS`](../CODEOWNERS) assigning
the policy (`agent-audit-rules.json`), the engine (`agent_audit.py`), the CI gate
template, and the security baseline to a governance owner group. This is the
human half of "the gate cannot weaken itself"; the severity floor is the engine
half. `CODEOWNERS` only *enforces* review when the project's branch protection
requires code-owner approval — enable that on the default branch. `audit.sh` P18
fails if `CODEOWNERS` stops covering the control-plane paths.

### New check types (code change)

Adding a brand-new *kind* of detection — not just new data for an existing rule —
requires a detector in [`scripts/agent_audit.py`](../scripts/agent_audit.py)
(`audit_skill` / `audit_project`) plus a catalog entry. This is deliberate: a
full config-driven rule DSL would be more complex and less safe than a small
Python function.
