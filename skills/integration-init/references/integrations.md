# Optional Integrations — Detailed Specs

Loaded by `integration-init` Phase 3-4. Per-integration: what it is, why integrate, install / verify / init commands, MCP vs CLI tradeoffs (CRG), known caveats, and the documentation block template injected into AGENTS.md.

---

## code-review-graph (CRG)

### What it is

Production-ready Python tool that parses your repository with Tree-sitter (24 languages + Jupyter notebooks), stores structural relationships in a SQLite graph (vertices = functions/classes/files; edges = calls/imports/inherits/tests), and exposes graph queries via FastMCP server (28 tools, 5 prompts, 3 slash commands) or CLI commands.

**Headline metric — external, unreproduced claim:** ~8.2× average token reduction across 6 real open-source repositories, **reported by the CRG upstream project's eval-runner — NOT reproduced by this toolkit**. Treat it as illustrative («non-trivial reduction is achievable when the agent uses graph queries»), never as a guarantee: per-repo results vary with codebase shape (depth, fan-out, language), small repos (< 50 files) often see overhead exceed savings, and MCP mode carries ~12k tokens of schema overhead per session (see tradeoff table below). If you need verified numbers, run the upstream eval methodology (`code-review-graph eval --all`) on your own representative repos.

### Why integrate

Default AI code review reads each touched file plus each imported file in full. On PRs with 50+ files, context exhausts within ~10 minutes. CRG replaces «read everything» with «query blast-radius» — agent asks «who calls this changed function», «which tests cover it», «what depends on it» and gets a constant-token answer.

### Install commands

| Variant | Command |
|---|---|
| Upstream, pinned (recommended default) | `pipx install "code-review-graph==${SGT_CRG_VERSION}"` |
| With Python enrichment (adds Jedi) | `pipx install "code-review-graph[enrichment]==${SGT_CRG_VERSION}"` |
| Fork (better-code-review-graph, time-limited) | `pipx install git+https://github.com/n24q02m/better-code-review-graph@${SGT_CRG_FORK_REF}` |
| Via pip (if pipx unavailable) | `pip install --user "code-review-graph==${SGT_CRG_VERSION}"` |

Never install a floating `latest` — `scripts/init.sh` carries the pinned
known-good default for `SGT_CRG_VERSION` (and `SGT_CRG_FORK_REF`); bump the
env var deliberately, after review.

After install:
```bash
code-review-graph install                              # auto-detects platform (MCP mode)
# OR explicit:
code-review-graph install --platform claude-code       # one of: codex / claude-code / cursor / windsurf / zed / continue / opencode / antigravity / qwen / qoder / kiro / copilot / copilot-cli / gemini-cli
code-review-graph install --no-mcp                     # CLI mode: rules injection instead of an MCP server (matches init.sh --use-cli)
```

This writes MCP config or rules injection into the host's expected location. Restart the editor afterward.

### Verify commands

```bash
code-review-graph --version           # confirm binary present
code-review-graph build --check       # confirm graph state consistent (no parse, fast)
code-review-graph status              # show indexed file count + last update time
```

### Initial build commands

```bash
code-review-graph build                # full initial parse (10-30 min on large repos)
code-review-graph build --incremental  # incremental (default after first full build)
```

### MCP mode vs CLI mode — tradeoff

| Aspect | MCP mode | CLI mode |
|---|---|---|
| Latency | Instant queries (server warm) | ~1-3 s per query (re-init each time) |
| Token cost per session | ~12k tokens schema overhead (28 tools) | None |
| Persistent state | Yes — graph stays loaded | No — reloads from SQLite each call |
| Best for | Interactive code review sessions | Batch / scheduled / token-constrained sessions |
| Setup complexity | Higher (MCP server config) | Lower (CLI binary) |
| Editor restart required | Yes (after `install`) | No |

Decision hint:
- Active developer doing many reviews per day → **MCP**
- Periodic CI check or single-session audit → **CLI**
- Cowork session with long context window → **CLI** (avoid schema overhead)

### Known caveats (verified 2026-05-15)

⚠ **Upstream main has 6 documented bugs** (per `better-code-review-graph` fork README):
1. Broken multi-word `search_for_pattern` (fails on space-separated queries)
2. Empty `callers_of` resolution for many real function refs
3. 500K+ char output explosions (no pagination) on large repos
4. ONNX + cloud dual-mode embedding edge cases
5. Invalid PostToolUse hooks
6. Tool surface bloat (9 tools when 5 sufficed)

**Mitigation strategies:**
- Track fork's status — if its PRs merge upstream, the issues resolve automatically.
- For time-sensitive pilots: use the fork (set `USE_FORK=true` in integration-init).
- For long-term stability: stay on upstream main; check release notes for these specific bug references.

⚠ **MCP token economics:** 28 tools = ~12k tokens schema overhead per session. For Cowork-style long sessions or token-constrained runtimes, prefer CLI mode.

⚠ **Setup overhead:** Initial build on large repo can take 10-30 min. Subsequent incremental updates are < 2 seconds.

⚠ **Edge confidence «AMBIGUOUS»:** On dynamic codebases (heavy reflection, `eval`, dynamic imports), ~30% of edges may be flagged AMBIGUOUS. Filter or human-review them.

⚠ **Default recall = 1.0, precision = 0.4** — intentionally conservative; many false positives, but no missed dependencies. Correct trade-off for security-critical review; surprising for developers expecting «high precision» defaults.

⚠ **No vendor SLA** — community-supported open-source. Bug fixes depend on maintainer responsiveness.

### Update graph — keeping it fresh

CRG installs a **post-edit / post-commit hook** automatically when you run `code-review-graph install`. The hook re-indexes only changed files via SHA-256 diff (incremental update < 2 seconds).

**Supplementary pre-commit hook** (optional, installed by `scripts/install-pre-commit-hook.sh`):
- Runs `code-review-graph build --check` before commit.
- Blocks commit if graph is stale.
- Recommended for teams that want a hard guarantee the graph reflects the working tree.

### Documentation block template (AGENTS.md)

```markdown
<!-- skill-init: integration:crg BEGIN -->
### code-review-graph (active)
- **Variant:** {upstream main | fork better-code-review-graph}, v{version}
- **Mode:** {MCP server | CLI mode}
- **Languages:** Python · TypeScript · JavaScript · Go · Rust · Java · Ruby · C/C++ · Zig · Powershell · Julia · Svelte · Nix · {others — 24 total}
- **Use when:** code review of PRs touching > 20 files; cross-module dependency questions; blast-radius analysis; «who calls X» / «what depends on Y» / «which tests cover Z»
- **Invocation pattern (MCP mode):** the agent calls MCP tools `review-pr`, `review-delta`, `callers_of`, `dependents_of`, `test_coverage_for` automatically when context requires structural reasoning
- **Invocation pattern (CLI mode):** the agent runs `code-review-graph query "{question}"` as a shell command
- **Known caveats:** see `skills/integration-init/references/integrations.md` §CRG
- **Update graph:** auto on file save (CRG hook); supplementary pre-commit hook {installed via scripts/install-pre-commit-hook.sh | not installed}
- **Verify:** `code-review-graph --version` · `code-review-graph build --check`
<!-- skill-init: integration:crg END -->
```

### Handoff template (code-reviewer.md)

> **Comment-form only.** `code-reviewer.md` declares `handoffs: []` and requires every
> non-comment handoff target to resolve to an `agents/{target}.md` file. Integrations are
> not dispatchable agents, so the injected lines below are `#`-prefixed YAML comments
> (matching the existing marker style) — human-facing documentation, never dispatch targets.
> The same rule applies to the repomix and serena templates.

```yaml
  # <!-- skill-init: handoff:crg BEGIN -->
  # - target: code-review-graph
  #   label: "Blast-radius analysis (CRG)"
  #   condition: "PR touches > 20 files OR cross-module changes detected OR Modularity.M3 (cycle) flagged"
  #   invocation: |
  #     MCP mode: call review-pr / callers_of / dependents_of as needed
  #     CLI mode: code-review-graph query "{specific question}"
  # <!-- skill-init: handoff:crg END -->
```

---

## repomix

### What it is

NPM-based tool that packs a repository into a single XML / markdown / plain-text file optimized for LLM ingestion. Stdlib-only (Node), no external services.

### Why integrate

Orthogonal to CRG — different use case:
- **CRG** = persistent graph, queryable, incremental, for active code review on a known codebase.
- **repomix** = one-shot snapshot, no setup state, for **small repos** or **external code review** (reviewing a third-party PR, evaluating an open-source library, packing a project for shared context).

You can install both; they don't conflict.

### Install commands

```bash
npm install -g "repomix@${SGT_REPOMIX_VERSION}"   # global install, pinned (recommended)
# OR via npx (no install):
npx repomix --version
```

### Verify commands

```bash
repomix --version
repomix --help
```

### Initial config command

```bash
cd $PROJECT_ROOT
repomix --init                  # creates repomix.config.json with defaults
```

The config file lets you tune:
- Include / exclude patterns
- Output format (XML / markdown / plain)
- File-size limits
- Compression options

### Verify commands

```bash
repomix --version
repomix --output context.xml    # pack current project to context.xml
```

### Known caveats

- Large repos (> 10k files) produce huge output files. Use `--include` / `--ignore` patterns aggressively.
- Output is a snapshot — does not incrementally update. Re-run for fresh state.

### Documentation block template (AGENTS.md)

```markdown
<!-- skill-init: integration:repomix BEGIN -->
### repomix (active)
- **Version:** {detected version}
- **Config:** {repomix.config.json present at project root | not yet initialized}
- **Use when:** packing the project for one-shot LLM context (e.g. reviewing entire small repo at once); preparing external repo for code-reviewer agent input; sharing project context with another team
- **Invocation:** `repomix --output {file}` from project root
- **Update:** re-run `repomix` whenever you need a fresh snapshot — no incremental mode
- **Verify:** `repomix --version`
<!-- skill-init: integration:repomix END -->
```

### Handoff template (code-reviewer.md)

```yaml
  # <!-- skill-init: handoff:repomix BEGIN -->
  # - target: repomix
  #   label: "Pack repo context (one-shot)"
  #   condition: "Reviewing an external repository not indexed by CRG, OR small repo (< 100 files) where full context is feasible"
  #   invocation: "repomix --output {tmp path} --include={pattern}; then read that file as context"
  # <!-- skill-init: handoff:repomix END -->
```

---

## serena (LSP-bridge MCP server)

### What it is

Python-based MCP server that bridges to Language Server Protocol (LSP) servers — Pyright (Python), tsserver (TypeScript), gopls (Go), rust-analyzer (Rust), etc. Provides semantic-aware operations: rename, go-to-definition, find-references, type-aware navigation.

### Why integrate

Orthogonal to CRG:
- **CRG** = structural graph (Tree-sitter syntax) — fast, broad, AMBIGUOUS edges on dynamic code.
- **serena** = semantic understanding (LSP) — slower per-query, but precise on types and references; handles dynamic code that confuses Tree-sitter.
- Combined: CRG for blast-radius, serena for «is this rename safe across all type instantiations».

### Install commands

```bash
# PyPI package is `serena-agent` (`serena-mcp` does not exist on PyPI);
# the installed CLI entry point is `serena`.
pipx install "serena-agent==${SGT_SERENA_VERSION}"
```

### Initial setup commands

```bash
serena init --languages=python,typescript    # install language servers for selected langs
```

Available language flags: `python` · `typescript` · `javascript` · `java` · `go` · `rust` · `c-cpp` · `ruby` · `php` · `csharp` · `other-supported-lsp`.

### Verify commands

```bash
serena --version
serena status                  # lists active LSP servers
```

### Known caveats

- Each LSP server has its own runtime requirements (e.g. Pyright needs Python; gopls needs Go installed).
- First-query latency can be 1-3 seconds while LSP server warms up.
- Some LSP servers consume significant memory on large codebases (tsserver on 10k+ TS files → 1 GB+).
- Editor restart required after install for MCP config to take effect.

### Documentation block template (AGENTS.md)

```markdown
<!-- skill-init: integration:serena BEGIN -->
### serena (active)
- **Version:** {detected version}
- **Languages:** {selected language servers}
- **Use when:** semantic refactoring (rename across files), type-aware navigation, cross-instantiation safety checks; complements CRG's structural blast-radius with type-level precision
- **Invocation:** MCP — serena exposes `rename_symbol`, `find_references`, `goto_definition`, `type_at_cursor` tools
- **Update:** LSP servers update independently — re-run `serena init` after major language toolchain upgrades
- **Verify:** `serena --version` · `serena status`
<!-- skill-init: integration:serena END -->
```

### Handoff template (code-reviewer.md)

```yaml
  # <!-- skill-init: handoff:serena BEGIN -->
  # - target: serena
  #   label: "Semantic refactor / type-aware refs"
  #   condition: "Rename operation flagged; cross-module type changes; CRG returned AMBIGUOUS edges for dynamic code"
  #   invocation: "MCP: rename_symbol / find_references / type_at_cursor"
  # <!-- skill-init: handoff:serena END -->
```

---

## secret-guard (opt-in PreToolUse hook)

### What it is

A standalone Python 3 (stdlib-only) **Claude Code PreToolUse hook** that inspects Bash command strings before they run and BLOCKS the obvious secret-read / secret-exfiltration patterns: reading `~/.aws/credentials`, `~/.ssh/id_*`, `~/.kube/config`, `.env` files, dumping secret-looking env vars (`printenv`/`env`), or piping any of those into a network tool (`curl`/`wget`/`nc`/…). It ships as a skill asset: `skills/integration-init/assets/secret-guard-hook.py`.

> ⚠ **Claude-Code-only.** Hooks are a Claude Code mechanism. Copilot / Cursor / Codex / Gemini have no equivalent — this integration is NOT portable and MUST NOT be documented in the portable `AGENTS.md` body. It is offered only in the Claude-only path.
>
> ⚠ **Opt-in / not default.** Unlike CRG / repomix / serena, secret-guard is never installed automatically. The user must explicitly request it and register it in `.claude/settings.json` themselves (or confirm the skill may edit that file).

### Honest framing — defense-in-depth, NOT a security boundary

This hook is a **best-effort tripwire**, not a control surface. A determined skill bypasses it trivially (read the file from Python, encode the path, shell out indirectly). Installing it does **NOT** permit relaxing the SEC / SCR / HOOK audit gates — those remain authoritative. Never weaken a gate "because the hook will catch it." The same disclaimer is restated at the top of the hook script.

### Why integrate

A cheap extra layer for teams running semi-trusted skills: it stops the most common accidental or naive-malicious `cat ~/.aws/credentials | curl …` before the shell runs, surfacing a clear block message to the user. It pairs with — does not replace — the static audit gates.

### Install commands

There is no installer binary — the hook is already shipped with the skill. "Installing" means registering it in Claude Code's settings:

1. Resolve the hook path inside your install (`skills/integration-init/assets/secret-guard-hook.py`; under a plugin/global install resolve `$SGT_ROOT` per `references/path-resolution.md`).
2. Add a `hooks.PreToolUse` matcher to `.claude/settings.json` (project) or `~/.claude/settings.json` (global):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT:-.}/skills/integration-init/assets/secret-guard-hook.py"
          }
        ]
      }
    ]
  }
}
```

Adjust the `command` path to the absolute location of the shipped hook in your install. The hook reads the tool-call JSON on STDIN; exit 0 allows, exit 2 blocks.

### Configure guarded paths

The hook guards a sensible default set (`~/.aws/credentials`, `~/.ssh/id_*`, `~/.kube/config`, `.env`, `.netrc`, `.npmrc`, `.pgpass`, …). Extend it without editing the script via the `SGT_GUARD_PATHS` env var — colon- OR comma-separated path fragments:

```bash
export SGT_GUARD_PATHS="/etc/myapp/secret.token,/srv/keys/deploy.pem"
```

### Verify commands

```bash
# Should BLOCK (exit 2) and print a redacted message:
echo '{"tool_name":"Bash","tool_input":{"command":"cat ~/.aws/credentials"}}' \
  | python3 skills/integration-init/assets/secret-guard-hook.py; echo "exit=$?"

# Should ALLOW (exit 0):
echo '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}' \
  | python3 skills/integration-init/assets/secret-guard-hook.py; echo "exit=$?"
```

### Known caveats

- **Bypassable by design** — see the honest-framing note above. Treat any "pass" as "did not match a known-bad pattern," never as "safe."
- **Bash-only** — non-Bash tool calls (Read/Write/Edit) are not inspected; allowed unconditionally.
- **False positives possible** — a legitimate `cat .env.example` for a literal example file may trip the `.env` matcher. Run such commands outside the agent, or scope `matcher` more tightly.
- **Redaction is best-effort** — the hook masks matched secret substrings before logging, but does not redact arbitrary inline secrets it did not match on.

### Documentation block template (Claude-only — NOT AGENTS.md)

Because this is Claude-only, the doc block is injected into the **Claude-only path** (e.g. `CLAUDE.md` below the «Claude Code specifics» section), never into the portable `AGENTS.md` body. The marker keeps the legacy `skill-init:` prefix per repo convention.

```markdown
<!-- skill-init: integration:secret-guard BEGIN -->
### secret-guard hook (active — Claude Code only, defense-in-depth)
- **What:** PreToolUse Bash hook blocking obvious secret-read / exfil commands
- **Path:** `skills/integration-init/assets/secret-guard-hook.py`
- **Registered in:** `.claude/settings.json` → `hooks.PreToolUse` (matcher `Bash`)
- **NOT a security boundary** — bypassable; does NOT relax SEC/SCR/HOOK gates
- **Configure:** `SGT_GUARD_PATHS` env var (colon/comma-separated extra paths)
- **Verify:** `echo '{"tool_name":"Bash","tool_input":{"command":"cat ~/.aws/credentials"}}' | python3 <path>/secret-guard-hook.py` → exit 2
<!-- skill-init: integration:secret-guard END -->
```

There is no `code-reviewer.md` handoff for this integration — it is a passive runtime guard, not a dispatchable analysis target.

---

## Future integrations (roadmap, not yet active)

The following are out of scope for the initial init flow but tracked for future addition:

### playwright

**Why deferred:** Playwright is browser E2E testing infrastructure. It would integrate logically only when a `test-generator` sub-agent is built (currently exists only as a handoff target in `code-reviewer.md`). Will be added in a future integration-init phase when test-generator lands.

Anticipated install: `npm install -g @playwright/test && npx playwright install`.

### Other candidates (tracked but no active plan)

- `semgrep` — pattern-based static analysis (alternative pattern-rule layer to CRG's graph queries)
- `dependency-cruiser` — TS/JS-specific import graph (subset of CRG functionality, lighter setup)

If user demand emerges for these — add them via the same multi-stage clarification pattern used for CRG.
