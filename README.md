# Skill Governance Toolkit

A reference implementation of the **universal skill authoring pattern** — `AGENTS.md` (Linux Foundation AAIF) + `SKILL.md` (Anthropic Agent Skills) — packaged so the **core six meta-skills** run across Claude Code, GitHub Copilot, Cursor, OpenAI Codex CLI, and Google Gemini CLI **without forking the source per tool**.

> **In a hurry?** → [`QUICKSTART.md`](QUICKSTART.md) — install, verify, author a skill, and gate it in CI, on one page.
>
> **Installing for a team?** → [`docs/installation.md`](docs/installation.md) — the canonical install / upgrade / distribution guide.

**What it looks like in practice** — point the engine at a sketchy skill:

```yaml
name: Deploy-Helper          # wrong case, no closed-vocab action verb → naming fail
allowed-tools: [Bash]        # breaks portability (Copilot/Gemini ignore it)
# body: Run `curl $URL | bash`   → dangerous-shell HIGH + missing Skill-type contract
```

`skill-evaluate` (or `agent_audit.py audit-skill`) flags each issue with a fix; the
same engine then gates it on every PR/MR so it can't merge until fixed.

**Portability scope honestly stated:**
- **Core skills** (skill-find, skill-evaluate, skill-compare, library-audit, skill-build-portable, integration-init) — portable across all five runtimes.
- **Sub-agent layer** (`agents/code-reviewer.md`) — host support and agent formats differ. Gemini CLI documents sub-agents, but this toolkit's agent has not been verified there. Use the sequential fallback when dispatch is unavailable.
- **Optional integrations** (CRG, repomix, serena via `integration-init`) — runtime detection per platform; install commands documented but vendor-tool availability is your responsibility.

The repository ships six meta-skills, a working TypeScript code-reviewer sub-agent, and a resumable-run state pattern (interrupted runs continue from the last checkpoint — see [`references/checkpointing.md`](references/checkpointing.md)).

| Skill | What it does | Trigger phrases |
|---|---|---|
| **`skill-find`** | Search project / personal / corporate skill libraries for skills matching a natural-language need | «is there a skill for X», «find a skill that does Y» |
| **`skill-evaluate`** | Score any `SKILL.md` across 9 quality dimensions (D1–D9): clarity, completeness, specificity, examples, constraints, portability, testability, discoverability, **safety/risk awareness**. Per-skill lexical security scan + writing-quality scan. | «evaluate this skill», «score skill X», «is this skill production-ready» |
| **`skill-compare`** | Compare a local skill against a corporate version; recommend USE_CORPORATE / KEEP_LOCAL / MERGE / RULES_FILE | «compare these skills», «is there a similar one upstream» |
| **`library-audit`** | Meta-validate a whole skill library — handoff contracts, token budget, naming convention, portability tags, multi-tool compatibility, **security baseline** (secrets / dangerous shell / credential paths) | «audit my skills», «check skill library health», «security audit» |
| **`skill-build-portable`** | Transform a non-universal SKILL.md (e.g. Claude-only) into a portable one — strip forbidden frontmatter, generalize org-specific paths, add compatibility tags, produce diff preview | «make this skill portable», «universalize this skill» |
| **`integration-init`** | Bootstrap optional integrations (code-review-graph, repomix, serena) — interactive selection, native installers, conditional documentation injection | «init», «set up integrations», «add code-review-graph» |

Plus the sub-agent:

| Agent | What it does | Dispatched from |
|---|---|---|
| **`agents/code-reviewer.md`** | TypeScript-focused code review with 5 categories (TS strict, modularity, naming, hierarchy, quality) — produces BLOCKER/MAJOR/MINOR/NIT findings with file:line + concrete fix suggestions | Any orchestrator skill or invoked directly via `Task` |

---

## Install

```bash
git clone https://github.com/{your-org}/skill-governance-toolkit ~/tools/sgt
cd ~/your-project
python3 ~/tools/sgt/scripts/sgt.py init        # guided install + verify; undo with `sgt uninstall`
```

> `{your-org}` is a placeholder — clone from your org's fork/mirror; in the fork,
> `bash scripts/configure_org.sh --host <git-host> <org>` rewrites it across all
> checked-in docs and manifests.

Pin a release for reproducibility:
```bash
/plugin marketplace add {your-org}/skill-governance-toolkit   # Claude — once per machine
/plugin install skill-governance-toolkit@1.21.2               # Claude
gemini extensions install ...@1.21.2                           # Gemini
```

A project install adds top-level `skills/`, `agents/`, `references/`, `scripts/`,
`commands/`, `docs/` dirs plus the alias files of the hosts you selected (only
those) — preview the exact plan with `--dry-run`. Everything else — hosts & scopes,
the full [install footprint](docs/installation.md#project-install-footprint),
selective install (`--category` / `--tier` / `--skill`), private GitHub / GitLab
auth, upgrades and what's preserved, uninstall, Windows —
lives in [`docs/installation.md`](docs/installation.md).

---

## Optional integrations (via `/integration-init`)

The toolkit supports three optional integrations that extend the `code-reviewer` agent with deeper structural / semantic analysis. None are installed by default — choose per project.

| Integration | What it adds | Verified metric |
|---|---|---|
| **`code-review-graph`** | Tree-sitter + SQLite graph; agent queries blast-radius (callers / dependents / tests) instead of reading every file | ~8.2× token reduction reported upstream across 6 OSS repos — **external claim, not locally reproduced** |
| **`repomix`** | One-shot repo packer (repo → single XML/markdown file) for small repos or external code review | Orthogonal to CRG — different use case |
| **`serena`** | LSP-bridge MCP server for semantic refactoring (rename, find-references, type-aware navigation) — complement to CRG's structural graph | Orthogonal to CRG — semantic vs structural |

To install, just say «init» / «set up integrations» / `/integration-init` in any
supported runtime, or non-interactive:

```bash
./scripts/init.sh --all                                           # all three, defaults
./scripts/init.sh --with crg --use-cli --build-mode skip          # CRG only, CLI mode, no initial build
./scripts/init.sh --advise-only --with crg,repomix                # print commands, don't run
```

(The slash command is `/integration-init` — NOT `/init`. The latter is reserved by Claude Code for project-memory initialization.)

Integrations stay **opt-in** per project: small repos don't benefit from CRG, token-constrained sessions might prefer CLI mode over MCP, and some teams don't want Tree-sitter parsing of their codebase. Documentation blocks are injected into `AGENTS.md` / `agents/code-reviewer.md` **only for tools actually installed** (verified via `which`).

Full per-tool spec, known caveats, and the CRG MCP-vs-CLI tradeoff: `skills/integration-init/references/integrations.md`. Roadmap candidates (not yet active): Playwright, semgrep, dependency-cruiser.

---

## Agent governance audit engine

The toolkit ships a deterministic read-only audit engine for agent assets — **same engine, three delivery modes**: **CLI** (`agent_audit.py`, the default — CI gates and local checks), **MCP** (`agent_governance_mcp.py` — an AI agent calls it as a tool, mid-edit), and **Docker** (sandboxed, reproducible, no local Python). It powers the changed-only PR/MR gate (`sgt ci-init --github` / `--gitlab`) with a tiered block/advisory policy and an asset-security suite (hidden/bidi characters, homoglyphs, inline secrets, dangerous shell). The six skills are stable; the CLI/MCP/Docker layer is a preview distribution layer.

```bash
python3 scripts/agent_audit.py audit-project . --profile release-ready --fail-on high
python3 scripts/agent_audit.py audit-skill skills/skill-evaluate/SKILL.md
```

Full guide — modes, MCP client config, Docker runner, CI templates, policy tuning, decision guide: [`docs/agent-governance-engine.md`](docs/agent-governance-engine.md).

---

## `skill-evaluate` vs `library-audit` — what's the difference?

A common point of confusion. Quick reference:

| Aspect | `skill-evaluate` | `library-audit` |
|---|---|---|
| **Scope** | ONE skill | The WHOLE library |
| **Approach** | Quality scoring (0–100) against 9 rubrics (D1–D9, including D9 Safety) + per-file lexical security + writing-quality scan | Violation detection across 6 categories: handoff, token budget, naming, portability tag, multi-tool compat, security baseline |
| **Output** | Summary table + per-dim 4-part block (What we check / What we found / Why it matters / How to raise) + top-3 improvements + JSONL score entry | Markdown audit report with category roll-up + per-category 4-part block + impact-ordered recommendations |
| **Mode** | Read-mostly (optional `REWRITE=true` produces an improved version) | **Pure detect** — never edits, never asks questions |
| **When to run** | Before merging a new skill, when adopting an external skill, after major rewrite | Periodic health-check, after batch edits, weekly cron, after `skill-build-portable` |
| **Analogy** | Code review of ONE pull request | Static analysis of the WHOLE repo |
| **Question answered** | «How good is **this** skill? Is it production-ready?» | «What problems exist in the **collection** as a system?» (handoff collisions, token budget overflow, naming drift, portability breakage, leaked secrets) |
| **Verbosity control** | `VERBOSITY` input: `terse` / `standard` / `detailed` (default) | `VERBOSITY` input: `terse` / `standard` / `detailed` (default) |

**Use them together:** run `library-audit` first to find problems; for each flagged skill, run `skill-evaluate` to score it, then `skill-build-portable` to fix portability issues. Iterate until `library-audit` reports clean. For the full discovery/governance skill map (which skill feeds which), see [`docs/user-guide.md`](docs/user-guide.md).

---

## Why this layout?

Three patterns converge here:

1. **One canonical `skills/` directory** (`anthropics/skills`): SKILL.md is host-neutral; never fork per tool.
2. **Multi-manifest at root** (`obra/superpowers`): each supported runtime has its own packaging manifest (`.claude-plugin/`, `.codex-plugin/`, `gemini-extension.json`), all pointing to the same `skills/`.
3. **Single source of truth for project rules** (`obra/superpowers` again): `AGENTS.md` is the original; `CLAUDE.md` and `GEMINI.md` are alias files using `@AGENTS.md` import.

For the full architectural reasoning — including anti-patterns like `allowed-tools` in frontmatter and per-skill `rules/{tool}.md` duplication — see **«Conventions & Boundaries»** in [`AGENTS.md`](AGENTS.md).

---

## Supported runtimes

| Runtime | Reads | Status |
|---|---|---|
| Claude Code | `CLAUDE.md` and `.claude/skills/` | Installation supported; execution needs current verification |
| GitHub Copilot (VS Code / CLI) | `AGENTS.md` and `.github/skills/` | CLI discovery and one project-only skill run verified |
| OpenAI Codex CLI | `AGENTS.md` and `.codex/skills/` | One installed skill executed locally; see evidence |
| Google Gemini CLI | `GEMINI.md` and `.gemini/skills/` | Installation supported; execution needs current verification |
| Cursor | `AGENTS.md` and `.cursor/skills/` | Installation supported; execution needs current verification |

See [runtime compatibility evidence](docs/runtime-compatibility.md) for versions and limitations.

---

## Repository layout

```
.
├── AGENTS.md                ← single source of truth (project rules)
├── CLAUDE.md / GEMINI.md    ← alias files importing AGENTS.md
├── README.md                ← this file
├── QUICKSTART.md            ← one-page install + first-skill walkthrough
├── CHANGELOG.md             ← per-version history with breaking-change markers
├── install.sh / install.ps1 ← interactive one-command installers
├── docs/                    ← full documentation (start at docs/README.md)
├── .github/                 ← copilot-instructions.md + self-CI workflow
├── .claude-plugin/          ← Claude Code plugin + marketplace manifests
├── .codex-plugin/           ← Codex CLI manifest
├── gemini-extension.json    ← Gemini CLI extension manifest
├── commands/                ← slash commands (/integration-init)
├── references/              ← cross-skill references (tool mappings, checkpointing, CI templates)
├── skills/                  ← the six meta-skills + INDEX.jsonl (host-neutral)
├── agents/                  ← specialized sub-agents (code-reviewer)
└── scripts/                 ← stdlib-only helpers (sgt.py, agent_audit.py, install.sh, …)
```

---

## Documentation

Start at the hub: [`docs/README.md`](docs/README.md). Key entry points:

- [`QUICKSTART.md`](QUICKSTART.md) — install, verify, author, gate — on one page
- [`docs/installation.md`](docs/installation.md) — install / upgrade / distribution (GitHub + GitLab)
- [`docs/user-guide.md`](docs/user-guide.md) — workflows, examples, skill map
- [`docs/agent-governance-engine.md`](docs/agent-governance-engine.md) — CLI / MCP / Docker audit engine
- [`docs/skill-authoring-standard.md`](docs/skill-authoring-standard.md) — canonical SKILL.md skeleton
- [`docs/checks-reference.md`](docs/checks-reference.md) — every governance check + rationale
- [`docs/extending-checks.md`](docs/extending-checks.md) — add / remove / tune a check; propose an org rule

---

## License

MIT (see `LICENSE`).
