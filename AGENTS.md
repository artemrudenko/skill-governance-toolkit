# AGENTS.md — Skill Governance Toolkit

> Universal project rules for AI coding agents working in this repository.
> This is the **single source of truth**. `CLAUDE.md` and `GEMINI.md` are aliases that import this file. Copilot reads it natively.

---

## Project Overview

This repository is a **skill-governance toolkit** for any team adopting the `AGENTS.md` + `SKILL.md` open standards (Linux Foundation AAIF · Anthropic Agent Skills). It ships six meta-skills that operate on other skills:

| Skill | What it does |
|---|---|
| `skill-find` | Discovers skills across project / personal / corporate libraries matching a natural-language need |
| `skill-evaluate` | Scores any SKILL.md across 9 quality dimensions (D1–D9, including D9 Safety) + per-skill lexical security + writing-quality scan, returns improvements |
| `skill-compare` | Compares a local skill against a corporate version, recommends USE / KEEP / MERGE / RULES_FILE |
| `library-audit` | Meta-validates an entire skill library — handoff contracts, token budget, naming, portability, multi-tool compatibility, security baseline (secrets / dangerous shell / credential paths) |
| `skill-build-portable` | Transforms a non-universal SKILL.md (Claude-only or org-specific) into a portable cross-tool one — produces diff preview before write |
| `integration-init` | Interactive bootstrap for optional integrations (code-review-graph, repomix, serena) — runs native installers, injects per-tool documentation only for actually-installed integrations |

Plus `agents/code-reviewer.md` — a working TypeScript-focused sub-agent (5 categories, severity-tiered findings) dispatchable from any orchestrator skill via `Task`.

The toolkit itself follows the universal pattern it enforces — it can be loaded into Claude Code, GitHub Copilot, Cursor, Codex CLI, or Gemini CLI without per-tool source forking.

---

## Stack & Architecture

- **Language:** Markdown (skills, agents, rules) + Python 3 stdlib (optional helper scripts)
- **Layout (per Anthropic Agent Skills spec):**
  ```
  AGENTS.md                       ← L1 universal rules (this file)
  CLAUDE.md                       ← @AGENTS.md alias
  GEMINI.md                       ← @./AGENTS.md alias
  .github/copilot-instructions.md ← Copilot-specific alias
  skills/{name}/SKILL.md          ← L2 procedural skills
  skills/{name}/references/       ← long-form details, on-demand
  skills/{name}/scripts/          ← executable helpers (stdlib-only)
  skills/{name}/assets/           ← static resources
  agents/{name}.md                ← L3 specialized sub-agents
  references/{tool}-tools.md      ← ONE tool-name mapping per repo
  .{tool}-plugin/plugin.json      ← per-tool packaging manifests
  ```

---

## Conventions & Boundaries

### Skill authoring rules (enforced by `library-audit`)

1. **Only `name` and `description` are required by the Agent Skills standard** in frontmatter — these are the minimum that any portable parser must accept. **The toolkit additionally requires** `compatibility:`, `license:`, and a `metainfo:` sub-block (since 1.8.0) — see `docs/skill-authoring-standard.md` § metainfo for the schema. Top-level org-specific fields are forbidden (they break portability claims); all extensions live under `metainfo:`.
2. **Never use `allowed-tools:` in multi-host skills.** Claude Code treats it as a hard whitelist; Copilot / Cursor / Codex silently ignore it. The skill will behave differently across platforms with no warning.
3. **Tool-name mapping lives at repo root** in `references/{copilot,codex,gemini}-tools.md` — never duplicated inside each skill. A skill that needs `Read` simply says `Read`; the runtime translates.
4. **`SKILL.md` body: target ≤ 200 lines; gate budget 500, hard limit 600** (configurable via `body_budget` / `body_critical` in the audit config — the single source of truth; `skill-evaluate` 3.1 and `library-audit` budget-spec echo it, never diverge). Push detail into `references/`. Push executables into `scripts/`. Push static templates into `assets/`.
5. **`description` is mission-critical** — write 2–5 explicit trigger phrases in the user's natural language. Skill descriptions are how the agent decides when to activate.
6. **Naming convention:** `{entity}-{action}[-{qualifier}]`, kebab-case, ≤ 3 words after the entity. Closed-vocabulary action verbs: `find`, `audit`, `evaluate`, `compare`, `build`, `extend`, `frame`, `ingest`, `mark`, `plan`, `query`, `init`. Optional qualifier disambiguates within the same verb (e.g. `skill-build-portable` vs `skill-build`).
7. **Discovery / scan skills require a bounded scope parameter.** Open-ended «scan all» without `SCOPE_WINDOW` (last N sessions, since YYYY-MM-DD, sprint X) must fail-fast in Phase 0.
8. **`metainfo.category` and `metainfo.tier` are required** (since 1.8.0). Closed-vocab categories: `code-review` · `docs` · `testing` · `governance` · `discovery` · `research` · `delivery`. Tier enum: `stable` · `preview` · `experimental` · `internal`. The installer reads these from `skills/INDEX.jsonl` to support `--category`/`--tier`/`--skill` selective install. New skills should start at `tier: preview`; promote to `stable` after ≥1 release without breaking changes. `library-audit` Phase 5.5 enforces both presence and closed-vocab compliance.

### Sub-agent rules

- Sub-agents live in `agents/{name}.md` using the same SKILL.md frontmatter shape **plus a `tools:` field** declaring least-privilege tool access.
- Only an orchestrator skill (one declaring `Task` access in body, not frontmatter) may dispatch sub-agents. **Sub-agents cannot dispatch sub-agents.**
- Use `handoffs:` field to declare named transitions to peer agents.

### Path & data conventions

- Audit reports → `out/{skill-name}/{skill-name}-{YYYY-MM-DD}.md` (override path is a per-skill input parameter).
- Skill quality scores → `out/scores/index.jsonl` (one JSON object per line).
- Never commit `out/` to source control.
- **Resumable-run state** → `${CWD}/.skill-state/{skill-name}/run-{utc-ts}.json` (one file per skill invocation). Multi-phase skills checkpoint here after every expensive phase so an interrupted run can resume. The state directory is `.gitignored`. Full schema and helper CLI: see [`references/checkpointing.md`](references/checkpointing.md) and [`scripts/checkpoint.py`](scripts/checkpoint.py).

---

## Build & Test Commands

This is a documentation-driven repository — there is no compile step. Validation is done by the skills themselves:

```bash
# Audit the entire skill library — handoff, budget, naming, portability, multi-tool compat
# Trigger: «skill audit» / «check skills»
#
# Output: out/library-audit/library-audit-{date}.md

# Score one skill across 9 dimensions (D1–D9, includes D9 Safety)
# Trigger: «evaluate skill X» / «score skill X»
#
# Output: dimension table + top-3 improvements + (optional) rewrite

# Inspect the corpus shape — categories, tiers, orphans (since 1.8.0)
python3 scripts/filter_skills.py --index skills/INDEX.jsonl --list-categories

# Aggregate info-tier evidence (e.g. 3.8) across scored skills — promotion view
python3 scripts/filter_skills.py --index out/scores/index.jsonl --info-summary

# Self-CI for the toolkit (runs the full P1–P36 suite: index freshness, metainfo
# coverage matrix, audit-engine behavior tests, doctor/quickstart/installer/CLI,
# version sync, MR poster, audit config, CODEOWNERS (incl. the enforcement plane),
# marker_block, sub-check catalog, rationale coverage, info-summary, secret-guard
# + backfill, ps1 syntax + content parity, checkpoint state, pre-commit-hook
# installer, init.sh, subset AGENTS.md rewriter, onboarding SHA pinning,
# self-CI phase-range consistency, and build_index parser unit tests). P35
# asserts this very range stays in sync.
bash scripts/audit.sh
```

If `scripts/` directories contain Python helpers, run them with `python3` and stdlib only — **no pip dependencies allowed** (portability requirement).

### Script & reference path resolution

A skill that shells out to a toolkit script (`scripts/*.py|sh`) or reads a shared
reference (`references/*.md`) MUST resolve the install root first — the runtime
CWD is the user's project, not the install dir. Resolution order: `$CLAUDE_PLUGIN_ROOT`
→ `$SGT_ROOT` → CWD walk-up for a `scripts/`+`skills/` pair (the active `AGENTS.md`
dir) → `$CODEX_HOME` → `$PWD`. Full contract and a copy-paste bash resolver:
[`references/path-resolution.md`](references/path-resolution.md).
Only whitelisted runtime scripts ship into installs — see [`scripts/runtime-manifest.txt`](scripts/runtime-manifest.txt).

---

## Code Style

- Markdown: ATX headings (`#`), fenced code blocks with language hints, tables for parameter specs.
- YAML frontmatter: 2-space indent, no tabs, kebab-case keys.
- Names: kebab-case for skills/agents/files; snake_case for input parameters (`SKILL_TARGET`, `MODE`, `SCOPE_WINDOW`).

## Parallelization patterns

Skills that scan many files or run many independent checks should use
**batched tool calls** — emit multiple `Read` / `Grep` / `Bash` tool uses
in a SINGLE message with multiple `tool_use` blocks. The host runs them
concurrently; results return in the same turn for aggregation.

This works on every supported runtime (Claude / Copilot / Cursor / Codex /
Gemini) because all five support batched tool calls within one turn.

**Do NOT use `Task` sub-agent dispatch to parallelize work:**
- Gemini CLI does not support sub-agents — required `Task` breaks portability.
- Cross-context insights (collision detection, cross-dim scoring) are lost
  when work is sharded across isolated sub-agent contexts.

`Task` is reserved for **specialized expertise** dispatch (e.g. code-reviewer
agent for TypeScript review), not for parallelizing work that an agent can
do itself with batched tool calls.

`Task` / sub-agent dispatch is allowed only as an optional path: the skill
must also document a sequential fallback that produces the same output schema.
Never require sub-agents for correctness.

The library-audit and skill-evaluate skills include explicit
"Parallelization guidance" sections — read them when authoring new skills
in the same pattern.

## Writing Style

Every SKILL.md and reference file ships into the agent's context on every relevant turn. Concise, single-language, non-redundant content routes better and costs fewer tokens. `skill-evaluate` Phase 3.6 enforces these rules lexically; this section explains the reasoning.

**Hard rules:**
- **Single language per skill body.** Pick one primary language (English recommended for cross-tool routing accuracy and token efficiency — most agent frontmatter parsers and embedding models are tuned on English corpora). Do NOT mix scripts (Cyrillic / CJK / Arabic) into a Latin-script body. A skill written entirely in another language is acceptable; mixing fragments routing.
- **Active voice, direct imperatives.** «Read the file» beats «The file should be read». Passive voice adds ~30% tokens with no information gain.
- **Tables for parameter specs.** Use `| Input | Type | Default | Description |` tables, not multi-paragraph prose describing each input.
- **Lists over prose for enumerable content.** 5+ items written as prose paragraphs lose context-routing accuracy; render them as bullets or numbered lists.
- **Unique sections.** Restate a rule across multiple sections only when explicitly needed for cross-reference (e.g. Hard rules deliberately re-state a phase-level constraint). Unintentional copy-paste during refactor → flag and consolidate.

**Banned filler phrases** (each adds 4–8 overhead tokens with zero information):
«As we discussed» · «It's important to note» · «Please be aware» · «Make sure to» · «Don't forget to» · «In conclusion» · «To summarize» · «As mentioned earlier» · «It should be noted» · «Needless to say» · «It is worth mentioning».

**Brevity heuristics:**
- One sentence per idea. Compound sentences with «and» / «but» joining unrelated ideas should split.
- 4-sentence cap per paragraph. Longer paragraphs become invisible to context-routing logic.
- Code block + 1-line caption beats 5-sentence description of what the code does.

**Verification:** run `skill-evaluate` on any new or rewritten skill — Phase 3.6 surfaces violations. D1 (Clarity) is capped automatically when language mix, filler density, or duplicate paragraphs exceed thresholds.

---

## Security & Privacy

- Corporate skill repositories are accessed read-only — never push back without explicit user confirmation.
- Token-bearing config keys (e.g. `corporate-skills-token`) must reference **env var names**, never inline secret values.
- Skills must not embed organization-specific paths or domain terminology — those go in `rules/{project}.md` overrides (see `skill-compare` Phase 5).

---

## Tool-Name Translation Across Platforms

Skills in this repository use **Claude Code tool names** as the canonical reference (`Read`, `Write`, `Edit`, `Bash`, `Grep`, `Glob`, `Task`, `WebFetch`, `WebSearch`, `TodoWrite`, `AskUserQuestion`). `AskUserQuestion` is a canonical clarification concept; hosts without a structured question tool ask plainly in chat or fail fast in non-interactive mode.

If you're running on a different platform, your runtime translates these to its native tools. The full mapping is in:

- [`references/copilot-tools.md`](references/copilot-tools.md) — GitHub Copilot CLI / Copilot in VS Code
- [`references/codex-tools.md`](references/codex-tools.md) — OpenAI Codex CLI
- [`references/gemini-tools.md`](references/gemini-tools.md) — Google Gemini CLI

This is the **«one mapping per repo»** pattern (pioneered by `obra/superpowers`) — never duplicate tool tables inside individual SKILL.md files.

---

## Where to Place Things — Decision Table

| You have… | Goes in… | Activation |
|---|---|---|
| Always-on rule for the whole project | This file (`AGENTS.md`) | On every request |
| Multi-step procedure for a specific kind of task | `skills/{name}/SKILL.md` | When `description` matches user phrasing |
| Specialized role with restricted tools | `agents/{name}.md` | Dispatched via `Task` from an orchestrator skill |
| Slash command with a fixed name | `commands/{name}.md` | When user types `/name` |
| One-off prompt | Inline in chat | Single use |

---

## Optional integrations

The toolkit supports optional integrations that extend `code-reviewer` and other agents with deeper analysis capabilities. Install via the `/integration-init` slash command or `integration-init` skill — only installed integrations appear below.

> **Marker convention:** the `<!-- skill-init: ... -->` markers below are deliberate **runtime contracts** the integration-init skill greps for. They keep the legacy `skill-init:` prefix so existing AGENTS.md files from earlier toolkit versions continue to work without re-injection. Do not rename them.

<!-- skill-init: integrations BEGIN -->
<!-- No integrations active. Run /integration-init or invoke the integration-init skill to add code-review-graph, repomix, or serena. -->
<!-- skill-init: integrations END -->

See `skills/integration-init/references/integrations.md` for the full per-tool catalog (CRG, repomix, serena, future Playwright).

---

## Further Reading

- `README.md` — quick start for adopting this toolkit in a new project
- `skills/{any}/SKILL.md` — see how skills are structured in practice
- [`docs/contributing-rules.md`](docs/contributing-rules.md) — propose an org governance rule (advisory-first, reserved id, `stability` marker)
- [agentskills.io/specification](https://agentskills.io/specification) — the open SKILL.md standard
- [agents.md](https://agents.md) — the open AGENTS.md format
