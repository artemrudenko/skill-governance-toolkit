---
name: integration-init
description: |
  Interactive bootstrap for optional integrations. Asks which tools to add (code-review-graph,
  repomix, serena), runs their native installers, configures per-tool mode (MCP / CLI for CRG,
  initial build strategy), and injects per-integration documentation into AGENTS.md and
  agents/code-reviewer.md via paired markers — only for tools actually installed.
  Use when: «init», «initialize toolkit», «set up integrations», «add code-review-graph»,
  «add repomix», «add serena», «bootstrap toolkit», «configure integrations».
  Idempotent: re-running detects current install state and syncs documentation accordingly.
  Run with `--advise-only` for non-mutating dry preview.
compatibility: "Claude Code · GitHub Copilot · Cursor v2.2+ · OpenAI Codex CLI · Google Gemini CLI"
license: MIT
metainfo:
  category: [governance]
  tier: stable
  owner: artsiom
  added: "2026-05-23"
---

# Integration Init

> **Skill type:** MUTATING gateway — runs native installers (pipx/npm), injects documentation blocks into AGENTS.md + agents/code-reviewer.md via paired markers. Marker-block append semantics: existing user content OUTSIDE markers is NEVER modified.

**Purpose:** bootstrap optional integrations into the toolkit. Walk the user through a two-stage selection (which tools, then per-tool config), run native installers, and inject conditional documentation that reflects **actual install state** — never mention a tool that isn't installed.

This skill is a **gateway** (AskUserQuestion permitted per library-audit Phase 1.3).

**Runtime notes:** Interactive AskUserQuestion in Phase 1/2 only. For non-interactive use, `scripts/init.sh` is the bash fallback. Claude/Copilot/Cursor/Codex — full skill flow. Gemini — same skill flow but AskUserQuestion fallback to host prompts may differ.

## When to use

**Always:**
- First-time setup: user has just dropped the toolkit into a project and types «init», «initialize», «set up integrations».
- User explicitly asks to add a specific optional tool: «add code-review-graph», «install repomix», «add serena».
- After cloning the repo for a new team member — bootstrap their environment.

**ESPECIALLY when:**
- User has a large codebase (> 50 files) and code-reviewer agent is overflowing context — CRG addresses this directly.
- User runs multi-repo / monorepo setup — CRG's multi-repo daemon helps.
- User does external code review (reviewing third-party repos) — repomix gives one-shot context.

**Skip / Don't use for:**
- Production deployments where shell access is restricted — use `--advise-only` flag instead.
- User just wants to score one skill → use `skill-evaluate`.
- User just wants to audit library → use `library-audit`.
- User wants to convert a non-portable skill → use `skill-build-portable`.

**Don't skip when:**
- «I'll just `npm install` manually» — manual installs leave documentation out of sync. This skill keeps AGENTS.md, code-reviewer.md handoffs, and active install state in lock-step.

## Predecessor

**Required upstream:** none — entry-point skill invoked directly by user phrase or `/integration-init` slash command. (Gateway skill: no predecessor required.)

## Successor

**Default downstream:** terminal — emit installation report, suggest first-run command for each newly active integration.

---

## Required inputs

All optional; defaults drive interactive flow.

| Input | Type | Default | Description |
|---|---|---|---|
| `MODE` | enum: `auto-install` / `advise-only` | `auto-install` | `advise-only` prints commands instead of running them — safer on locked-down corporate machines |
| `WITH` | comma list | none | Non-interactive selection (e.g. `WITH=crg,repomix`); skips Phase 1 user prompt |
| `USE_FORK` | boolean | `false` | If `true` and CRG selected, install `better-code-review-graph` fork instead of upstream main |
| `USE_MCP` | enum: `mcp` / `cli` / `ask` | `ask` | For CRG: MCP server mode vs CLI mode; `ask` prompts via AskUserQuestion |
| `BUILD_MODE` | enum: `full-now` / `full-later` / `skip` / `ask` | `ask` | For CRG: initial graph build strategy |
| `INSTALL_PRECOMMIT` | enum: `yes` / `no` / `ask` | `ask` | For CRG: optional supplementary pre-commit hook (CRG already installs its own post-edit hook) |

---

## Workflow

### Phase 0 — Environment detection

Detect host runtime, package managers (`python3 ≥ 3.10`, `pipx`, `node`, `npm`), currently-installed integrations (`which {tool}`), and repo context (`AGENTS.md`, `agents/code-reviewer.md`, `.git/`). Hard-fail if a selected tool's prereq is missing — warn only if the prereq is for a tool not selected.

Full detection logic, prereq matrix, and state-snapshot schema → [`references/env-detection.md`](references/env-detection.md).

### Phase 1 — Ask which tools to install

If `WITH` input is provided, skip this phase and use that list. Otherwise **AskUserQuestion** with multi-select across `code-review-graph` · `repomix` · `serena`. If user selects nothing → emit no-op report and exit cleanly.

### Phase 2 — Per-tool configuration

For each selected tool, run sub-config via AskUserQuestion. Skip configs already answered via CLI inputs.

- **CRG:** Q-CRG-1 variant · Q-CRG-2 MCP/CLI · Q-CRG-3 enrichment · Q-CRG-4 build · Q-CRG-5 pre-commit
- **repomix:** Q-RPX-1 `--init` y/n
- **serena:** Q-SRN-1 languages multi-select

Full question definitions, options, and decision hints → [`references/sub-configs.md`](references/sub-configs.md).

### Phase 3 — Install (or advise)

For each selected integration with its sub-config: run install commands (`MODE=auto-install`) or print them (`MODE=advise-only`). Per-tool install state checkpointed after each tool completes (network failure recovery).

Per-tool install command sequences (CRG variants, repomix, serena) → [`references/integrations.md`](references/integrations.md) §Install commands.

### Phase 4 — Inject documentation (only for installed integrations)

For each **successfully verified** integration (see Phase 5 verify-before-inject in Hard rules), insert a marker block into `AGENTS.md` (outer marker `<!-- skill-init: integrations BEGIN/END -->`) and `agents/code-reviewer.md` (outer marker `<!-- skill-init: handoffs BEGIN/END -->`). Inner per-integration markers `<!-- skill-init: integration:{tool} BEGIN/END -->` are append-or-update or remove (if deselected on re-run). Use `marker_block.py` (atomic write) for all edits.

Full per-tool marker-block templates (AGENTS.md + code-reviewer handoffs, all three tools) → [`references/integrations.md`](references/integrations.md) §Documentation block template / §Handoff template.

### Phase 5 — Verify install

For each newly installed integration, run a verification command (`{tool} --version` / `which {tool}`). Verification result gates Phase 4 doc injection: pass → inject; fail → log error and skip injection for that tool. Suggest `--advise-only` re-run on failure to see commands.

### Phase 6 — Report

Emit final summary: `Selected:` / `Installed:` (with versions) / `Failed:` (with errors) / `Skipped:` (re-detected) / documentation blocks injected / next-step commands per active integration.

---

## State persistence (resumable runs)

Highest-risk skill for partial completion: a network failure mid-install can leave one of three tools half-installed and AGENTS.md out of sync with reality. Checkpointing makes each per-tool install atomic from the user's perspective.

| Phase | Checkpoint? | What is stored |
|---|---|---|
| P0 — environment detection | yes | detected runtime + package managers + currently-installed tools |
| P1 — ask which tools | yes | selected tools |
| P2 — per-tool configuration | yes | per-tool sub-config answers |
| P3 — install/advise | yes — **after each per-tool install completes** | install status per tool + version |
| P4 — inject documentation | yes | which marker blocks were updated |
| P5 — verify install | yes | per-tool verification results |
| P6 — report | no (terminal) | — |

- Default `RESUME=ask` (gateway skill — user expects prompts; if a prior run is unfinished, ask whether to resume).
- On resume: skip already-installed tools (verified via `which`); pick up at first unverified tool.
- State location: `${CWD}/.skill-state/integration-init/run-{utc-timestamp}.json`.

---

## Hard rules

- ❌ Never inject documentation for tools that are not actually installed (verified via `which`).
- ❌ Never modify content outside paired BEGIN/END markers.
- ❌ Never auto-install in `--advise-only` mode.
- ❌ Never overwrite user-customized content between markers without diff preview.
- ✅ **Verify-before-inject:** after `pipx install` / `npm install` etc., MUST run a verification command (e.g. `which {tool}` or `{tool} --version`). ONLY if verification passes, inject the per-tool documentation block. If verification fails, log the failure AND skip the doc injection for that tool.
- ✅ **Rollback for marker-block writes:** if a Phase 4 injection fails partway, the `marker_block.py` tool ensures atomic write — partial state is impossible. If a tool needs to be uninstalled, run `marker_block.py remove --file AGENTS.md --marker-id skill-init:integration:{tool}` to undo the block.
- ✅ **`--advise-only` mode** emits commands to stdout for user copy-paste; runs NO installers, injects NO docs. For locked-down environments where the skill cannot execute installers.
- ✅ Idempotent — re-running with no changes produces no diff.
- ✅ Re-running with a tool deselected removes its blocks from both files.
- ✅ Detection via `which {tool}` is authoritative — markers reflect reality, not user intent.
- ✅ All AskUserQuestion calls are scoped to Phase 1, Phase 2, and the resume prompt.
- ✅ Resumable — per-tool checkpoint in Phase 3 makes mid-install crashes recoverable without re-prompting the user.

---

## Examples

Three end-to-end walkthroughs (first install / advise-only / re-run with deselection) → [`references/examples.md`](references/examples.md).

---

## What this skill does NOT do

- **Uninstall binaries** — if you deselect a tool, only documentation is removed; uninstall the binary manually.
- **Configure tool-specific behavior beyond initial setup** — e.g. won't tune `repomix.config.json` rules or pick CRG embedding model.
- **Skill-level operations** — that's the job of `skill-find` / `skill-evaluate` / `skill-compare` / `library-audit` / `skill-build-portable`.
