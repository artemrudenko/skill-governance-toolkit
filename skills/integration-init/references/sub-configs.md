# Phase 2 — Per-tool sub-configuration questions

Loaded by `integration-init` Phase 2. Full clarification definitions for each selected integration. Use `AskUserQuestion` only on hosts that provide it; otherwise ask plainly in chat. Skip any question already answered via CLI inputs (`USE_FORK`, `USE_MCP`, `BUILD_MODE`, `INSTALL_PRECOMMIT`).

---

## Phase 2a — code-review-graph sub-config

### Q-CRG-1: Variant

- ✓ **upstream main** (recommended default — battle-tested baseline)
- ○ **better-code-review-graph fork** — has 6 documented bug fixes; the fork's author has declared intent to archive when upstream merges PRs, so the fork is marked as time-limited. Pick this only if you need the fixes today and accept the risk.

If `USE_FORK=true` CLI input passed: skip the prompt, use fork.

### Q-CRG-2: Mode — MCP server or CLI

- ✓ **MCP** (recommended) — persistent server, instant queries, lower latency for active review. Trade-off: 28 tools add schema overhead per session (~12k tokens).
- ○ **CLI** — per-query startup, no persistent server, no schema overhead per session. Trade-off: re-init cost on every call.

Decision hint: MCP for interactive code review sessions; CLI for batch / scheduled checks / token-constrained sessions.

If `USE_MCP=mcp` or `USE_MCP=cli` CLI input passed: skip the prompt.

### Q-CRG-3: Enrichment extras (Python codebases)

- ✓ **Yes — install with `[enrichment]`** if codebase is Python-heavy. Adds Jedi for type inference / cross-file refs.
- ○ **No — base install** if codebase is mostly non-Python.

### Q-CRG-4: Initial build strategy

- ✓ **Full now** (recommended) — parse entire codebase now (10–30 min on large repos). After this, incremental updates take < 2 sec.
- ○ **Full later** — install + config now; run `code-review-graph build` manually when ready.
- ○ **Skip / iterative-only** — no upfront build; graph populates lazily as files are accessed.

If `BUILD_MODE` CLI input is one of `full-now` / `full-later` / `skip`: skip the prompt.

### Q-CRG-5: Supplementary pre-commit hook

- ✓ **Yes — install** standalone pre-commit hook (via `scripts/install-pre-commit-hook.sh`) that checks graph freshness before commit.
- ○ **No** — rely only on CRG's auto-installed post-edit hooks (sufficient for most cases).

If `INSTALL_PRECOMMIT=yes` or `=no` CLI input passed: skip the prompt. Gated on `.git/` presence (Phase 0 repo-context detection).

---

## Phase 2b — repomix sub-config

### Q-RPX-1: Initial config

- ✓ **Run `repomix --init`** to scaffold a default `repomix.config.json`.
- ○ **Skip config init** — use defaults via CLI flags.

---

## Phase 2c — serena sub-config

### Q-SRN-1: Languages

Multi-select. Each enables the corresponding language server install (`serena init --languages=...`):

- Python (Pyright)
- TypeScript / JavaScript (tsserver)
- Java (jdtls)
- Go (gopls)
- Rust (rust-analyzer)
- C / C++ (clangd)
- Ruby (solargraph)
- PHP (intelephense)
- C# (OmniSharp)
- Other supported LSP

At least one language must be selected — otherwise Phase 3 install is a no-op.

---

## Persistence

All answers are captured into the state file at end of Phase 2:

```json
{
  "phase": 2,
  "selected": ["crg", "repomix", "serena"],
  "crg": { "variant": "upstream", "mode": "mcp", "enrichment": true, "build": "full-now", "precommit": true },
  "repomix": { "init_config": true },
  "serena": { "languages": ["python", "typescript"] }
}
```
