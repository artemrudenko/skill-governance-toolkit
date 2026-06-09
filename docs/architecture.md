# Architecture Overview

How the Skill Governance Toolkit is structured and why — instruction layers, install contract, activation flow, and the design decisions behind them.

> Audience: adopters & contributors · Type: explanation · Prerequisite: none (start here after the [README](../README.md))

## Three instruction layers

These are the **instruction-loading** layers (what the agent reads, when) — not
to be confused with the audit engine's CLI / MCP / Docker **delivery** layers in
[agent-governance-engine.md](agent-governance-engine.md).

```
L1 — Project rules    (always-on, every turn)
L2 — Procedural skills (activated by trigger phrases)
L3 — Sub-agents       (dispatched via Task tool — host-dependent)
```

| Layer | File pattern | Loaded when | Scope |
|---|---|---|---|
| L1 | `AGENTS.md` | every turn | universal project rules |
| L2 | `skills/{name}/SKILL.md` | description matches user phrasing | bounded procedure |
| L3 | `agents/{name}.md` | orchestrator skill calls `Task` | specialized expertise |

The three layers map to three different loading mechanisms across all five
supported runtimes. AGENTS.md is the **single source of truth** — CLAUDE.md
and GEMINI.md are aliases via `@AGENTS.md` import; Copilot reads AGENTS.md
natively; Cursor v2.2+ auto-discovers it from project root.

## Source vs Target vs Runtime dirs

The installer (v1.6.1+) explicitly separates three directory roles:

- **SOURCE** — where the toolkit code lives (the cloned repo)
- **TARGET_PROJECT** — where YOUR project lives (cwd by default)
- **RUNTIME_DIR** — per-host install dir (`~/.{host}/` global OR
  `$TARGET_PROJECT/.{host}/` project)

The «root-first» layout (v1.6.2+) places `skills/`, `agents/`, `references/`,
`scripts/`, `commands/` at TARGET_PROJECT root in project-scope installs.
This lets Copilot/Cursor auto-discover from workspace root AND lets
`.codex-plugin/plugin.json`'s `./skills/` reference resolve correctly.
Per-host runtime dirs still get their own copies for host-specific
conventions (Claude reads `.claude/skills/`).

### Skill subset selection (since 1.8.0)

The installer applies a filter over `skills/INDEX.jsonl` before copying:

1. `resolve_skill_subset()` in `scripts/install.sh` calls
   `scripts/filter_skills.py` with the parsed `--category` / `--tier` /
   `--skill` flags (or runs the interactive menu if `--interactive`).
2. The helper reads `metainfo.category` and `metainfo.tier` from each
   index entry, intersects with the filter, and returns the surviving
   skill names.
3. `_copy_filtered_skills()` then copies only the matching subdirs and
   writes a **filtered `INDEX.jsonl`** to the destination (so
   `skill-find` in the target environment never reports skills that
   weren't installed).

Default tier filter is `stable,preview` — `experimental` and `internal`
require explicit opt-in. Default category filter is empty (all categories).
`--skill` is a hard list that overrides category and tier (explicit names
mean «I know what I want»).

## User-owned vs toolkit-owned files

The install contract distinguishes who can edit each file:

| File | Owner | Install behavior |
|---|---|---|
| `$TARGET_PROJECT/AGENTS.md` | **USER** | Append/replace block between markers (`marker_block.py`) |
| `$TARGET_PROJECT/CLAUDE.md` | **USER** | Same |
| `$TARGET_PROJECT/GEMINI.md` | **USER** | Same |
| `$TARGET_PROJECT/.github/copilot-instructions.md` | **USER** | Same |
| `$RUNTIME_DIR/AGENTS.md`, `$RUNTIME_DIR/CLAUDE.md`, etc. | **TOOLKIT** | Full file replace OK |

User content OUTSIDE the markers is NEVER modified by the installer across
fresh installs, upgrades, and uninstalls.

### Install scopes & file ownership

How the install / upgrade / uninstall contract divides ownership (semantics
verified against `scripts/install.sh` `_copy_owned_tree` and `sgt.py uninstall`):

```mermaid
flowchart TD
    SRC["SOURCE checkout<br/>(toolkit repo / pinned mirror)"] --> INST["installer<br/>install.sh / sgt init"]
    INST --> M["AGENTS.md · CLAUDE.md · GEMINI.md ·<br/>copilot-instructions.md<br/><b>USER-owned</b> — marker-block merge only"]
    INST --> O["root canonical dirs + runtime dirs<br/>skills/ agents/ references/ scripts/ docs/ .claude/ …<br/><b>toolkit-owned</b> — tracked in .sgt-owned sidecars"]
    UP["upgrade (re-run installer)"] -. "overwrites / prunes ONLY<br/>sidecar-tracked files;<br/>name collision → ours renamed<br/>*.skill-governance-toolkit.*" .-> O
    UN["sgt uninstall"] -. "removes ONLY sidecar-tracked files<br/>+ strips the marker block" .-> O
    UN -. "user content outside markers<br/>preserved" .-> M
    NEVER[".skill-state/ · out/ · any user file<br/><b>never touched</b> by install, upgrade, or uninstall"]
```

## Skill activation flow

```mermaid
sequenceDiagram
    actor U as User
    participant H as Host runtime
    participant S as Skill
    participant R as references/
    U->>H: «evaluate this skill»
    H->>H: scan INDEX.jsonl + description fields
    H->>S: activate skill-evaluate (best match)
    S->>R: load rubrics.md (Phase 1)
    S->>S: Phase 0..N
    S-->>U: structured report
```

Activation cost is determined by:
1. `INDEX.jsonl` size (fast-path discovery)
2. AGENTS.md size (always-on context)
3. Selected skill body size (loaded on activation)
4. references/ loaded on-demand by skill itself

## Resumable runs

Multi-phase skills checkpoint state to `${CWD}/.skill-state/{skill-name}/`
after every expensive phase, so a crashed / interrupted run resumes from the
last checkpoint. The canonical pattern, helper CLI, and the **authoritative
per-skill resume-mode defaults table** live in
[`references/checkpointing.md`](../references/checkpointing.md) — do not copy
that table here; it drifts.

## Parallelization model

Skills use **batched tool calls** (multiple `tool_use` blocks in one
message) for embarrassingly parallel work, NOT `Task` sub-agent dispatch.
Reason: Gemini CLI has no sub-agent support, so required `Task` would break
portability. Cross-skill insights (collision detection, cross-dim scoring)
also benefit from being in one agent context.

`Task` / sub-agent dispatch is still allowed as an optional specialized path
when a skill also defines a sequential fallback with the same output schema.
The sub-agent path is an acceleration or expertise layer, never a correctness
requirement.

See `AGENTS.md` § Parallelization patterns for the full rule.

## Versioning + upgrade safety

- Versions follow semver (X.Y.Z). Breaking changes (skill renames,
  manifest schema) → major or minor bump with explicit «🔴 BREAKING»
  markers in `CHANGELOG.md`.
- The append-with-markers install contract means upgrades NEVER destroy
  user content outside our markers — see [§ «User-owned vs toolkit-owned
  files»](#user-owned-vs-toolkit-owned-files) above.

## Locally verified properties

Unlike external integration metrics (which the toolkit reports as upstream
claims, never as verified — see the CRG caveat in
[`skills/integration-init/references/integrations.md`](../skills/integration-init/references/integrations.md)),
these structural-correctness properties ARE measured and reproducible here:

- **Every skill body within the configured body budget** — `bash scripts/audit.sh`
  prints the body-budget table.
- **0 hardcoded secrets** in skill / agent / reference files — `audit.sh`
  secret-pattern scan.
- **All JSON manifests valid** — `audit.sh` manifest phase.
- **Install smoke test passes** (fresh + idempotent re-run) — `audit.sh`
  install phase.

These are not performance benchmarks — they are structural invariants the
self-CI (`scripts/audit.sh`) enforces on every run.

## Why not multi-agent for skill management

We deliberately chose NOT to make sub-agent orchestration required for
the meta-skills. Reasons:

- **Sub-agent support is uneven.** Gemini CLI has none. Requiring agents
  breaks the «works in all 5 runtimes» promise.
- **Cross-skill insights need single context.** Trigger collisions,
  cross-dim scoring (D3+D4, D5 vs D9) require one agent holding all
  state. Sub-agent fragmentation loses this.
- **Skills already do the work procedurally.** library-audit → skill-evaluate
  → skill-build-portable IS the orchestration. Wrapping it in agents adds
  complexity without speed gain on small libraries.

If we add an orchestrator skill (e.g. `library-cleanup`), it stays a skill
(visible to all 5 runtimes). It may optionally dispatch specialized agents
on hosts that support them, but it must keep a sequential fallback.

## See also

- [agent-governance-engine.md](agent-governance-engine.md) — go here for the audit engine's CLI / MCP / Docker delivery layers
- [installation.md](installation.md) — go here to actually run the installer described above
- [checks-reference.md](checks-reference.md) — go here for every governance check the toolkit applies
- [`references/checkpointing.md`](../references/checkpointing.md) — go here for the canonical resumable-run pattern
- [skill-authoring-standard.md](skill-authoring-standard.md) — go here when authoring a new skill for this layout
