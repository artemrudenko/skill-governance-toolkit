# Skill Governance Toolkit

A reference implementation of the **universal skill authoring pattern** — `AGENTS.md` (Linux Foundation AAIF) + `SKILL.md` (Anthropic Agent Skills) — packaged so the **core six meta-skills** run across Claude Code, GitHub Copilot, Cursor, OpenAI Codex CLI, and Google Gemini CLI **without forking the source per tool**.

> **In a hurry?** → [`QUICKSTART.md`](QUICKSTART.md) — install, verify, author a skill, and gate it in CI, on one page.
>
> **One-command setup:** `python3 <toolkit>/scripts/sgt.py init` (guided install + verify). Undo any time with `sgt uninstall`.

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
- **Sub-agent layer** (`agents/code-reviewer.md`) — works on Claude Code, Copilot, Cursor, Codex via their respective sub-agent / task tools. **Gemini CLI has no sub-agent support** — the agent's instructions must be inlined or the skill must fall back to linear flow.
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

## Optional integrations (via `/integration-init`)

The toolkit supports three optional integrations that extend the `code-reviewer` agent with deeper structural / semantic analysis. None are installed by default — choose per project.

| Integration | What it adds | Verified metric |
|---|---|---|
| **`code-review-graph`** | Tree-sitter + SQLite graph; agent queries blast-radius (callers / dependents / tests) instead of reading every file | ~8.2× token reduction reported upstream across 6 OSS repos — **external claim, not locally reproduced**. See [`docs/benchmarks.md`](docs/benchmarks.md) for caveats. |
| **`repomix`** | One-shot repo packer (repo → single XML/markdown file) for small repos or external code review | Orthogonal to CRG — different use case |
| **`serena`** | LSP-bridge MCP server for semantic refactoring (rename, find-references, type-aware navigation) — complement to CRG's structural graph | Orthogonal to CRG — semantic vs structural |

### How to install

In any supported runtime, just say:
> «init»  /  «set up integrations»  /  `/integration-init`

(The slash command is `/integration-init` — NOT `/init`. The latter is reserved by Claude Code for project-memory initialization, a different operation.)

`integration-init` activates, walks you through:
1. **Which tools** — multi-select (any combination).
2. **Per-tool config** — for CRG, asks: variant (upstream main / fork), mode (MCP / CLI), enrichment extras (Python Jedi), initial build (full now / later / skip), supplementary pre-commit hook.
3. **Install** — runs `pipx`, `npm`, or `pip` natively (or prints commands in `--advise-only` mode).
4. **Documentation injection** — adds per-integration blocks to `AGENTS.md` and `agents/code-reviewer.md` **only for tools actually installed** (verified via `which`).

Or non-interactive:
```bash
./scripts/init.sh --all                                           # all three, defaults
./scripts/init.sh --with crg --use-cli --build-mode skip          # CRG only, CLI mode, no initial build
./scripts/init.sh --advise-only --with crg,repomix                # print commands, don't run
```

### Why a separate skill, not bundled into AGENTS.md

The decision is **opt-in** per project:
- Small repos don't benefit from CRG (overhead > savings).
- Token-constrained sessions might want CLI mode over MCP.
- Some teams don't want Tree-sitter parsing of their codebase (compliance / IP concerns).

By keeping integrations conditional, the toolkit stays useful in **every** project without forcing infrastructure.

### Future integrations (roadmap, not yet active)

- **Playwright** — E2E browser testing. Will be added when the `test-generator` sub-agent (currently a handoff target) is implemented.
- **semgrep**, **dependency-cruiser** — alternative pattern-rule and import-graph layers. On the candidate list if user demand emerges.

See `skills/integration-init/references/integrations.md` for full per-tool spec including known caveats (CRG has 6 documented upstream bugs as of 2026-05-15) and CRG MCP-vs-CLI tradeoff.

---

## Agent governance audit engine

The toolkit also ships a deterministic read-only audit engine for agent assets —
**same engine, three delivery modes:**

- **CLI** (`agent_audit.py`) — a human or script runs it; best for CI gates and local checks. **Default choice.**
- **MCP** (`agent_governance_mcp.py`) — an AI agent calls it as a tool, mid-edit, in your editor/chat client.
- **Docker** — sandboxed, reproducible, no local Python (`--network none`, read-only mount).

Not sure which? → [`docs/agent-governance-engine.md` § Which one do I use?](docs/agent-governance-engine.md#which-one-do-i-use-decision-guide)

**Status:** the six skills are stable; the CLI/MCP/Docker audit engine is a
preview distribution layer intended for CI and cross-client tool calls.

```bash
python3 scripts/agent_audit.py discover .
python3 scripts/agent_audit.py audit-project . --profile release-ready --format json
python3 scripts/agent_audit.py audit-project . --profile release-ready --fail-on high
python3 scripts/agent_audit.py audit-project . --changed-only --base origin/main --fail-on high
python3 scripts/agent_audit.py audit-skill skills/skill-evaluate/SKILL.md
```

For a merge/pull-request gate in a consuming marketplace repo, copy the matching
template — both run `--changed-only` (only the assets the MR/PR touches, so legacy
assets never block an unrelated change) with a tiered block/advisory policy:

- **GitLab** → `references/ci/gitlab-ci.yml` as `.gitlab-ci.yml`. Step-by-step
  setup (env vars, pinned SHA, masked token): [`docs/gitlab-onboarding.md`](docs/gitlab-onboarding.md).
- **GitHub** → `references/ci/github-pr.yml` as `.github/workflows/skill-gate.yml`.
  Findings surface inline on the PR diff as annotations; the full JSON is uploaded
  as an artifact.

> The toolkit's own `.github/workflows/ci.yml` is **self-CI** (whole-tree audit +
> test suite) — don't copy it as a consumer gate; use `github-pr.yml` instead.

Tune policy via the `config` block (template: `references/agent-audit-config.example.json`)
and protect who can change the standards with the root `CODEOWNERS`. See the user
guide and `docs/checks-reference.md` for details.

For interactive AI clients, run the same engine as a stdio MCP server:

```bash
export AGENT_GOVERNANCE_ROOT=/path/to/project
python3 scripts/agent_governance_mcp.py
```

For reproducible local/CI use, build the Docker runner and mount the target
project read-only:

```bash
docker build -t agent-governance-mcp:local .
docker run --rm -i --network none -v "$PWD:/workspace:ro" agent-governance-mcp:local
```

Details and MCP client config examples: [`docs/agent-governance-engine.md`](docs/agent-governance-engine.md).
Rule metadata lives in [`references/agent-audit-rules.json`](references/agent-audit-rules.json);
the Python engine contains the detector logic.

**Asset-security suite (since 1.12.0)** — the gate also scans non-skill assets for
dangerous instructions / secrets (`SEC010`–`SEC012`), hidden/bidi characters
(`SEC001`/`SEC002`), and homoglyph typosquats (`SEC003`), and blocks only on
findings an MR *introduces* (`--fail-on-new`). Author and operator docs:

- [`docs/cli-reference.md`](docs/cli-reference.md) — complete `agent_audit.py` + `sgt` subcommand / flag / env-var / exit-code reference.
- [`docs/extending-checks.md`](docs/extending-checks.md) — decision tree for adding / removing / tuning a check: deterministic gate vs LLM-scored skill.
- [`docs/gate-for-authors.md`](docs/gate-for-authors.md) — one-page author entry point (linked from every MR comment).
- [`docs/security-suppression-runbook.md`](docs/security-suppression-runbook.md) — false positives, inline vs central suppression, SLA + break-glass.
- [`docs/security-rollout-guide.md`](docs/security-rollout-guide.md) — enable the suite over an existing library without an avalanche.
- [`docs/security-incident-runbook.md`](docs/security-incident-runbook.md) — `SGT_FAIL_MODE=advisory` kill-switch when the gate blocks everything.

### Health check

Before installing, publishing, or debugging a checkout, run the quick doctor:

```bash
python3 scripts/doctor.py
python3 scripts/doctor.py --format json
```

It checks required files, Git cleanliness, `skills/INDEX.jsonl` freshness,
skill category/tier coverage, local runtime install directories, and the
stdlib-only Python dependency contract. Warnings are informational; failures
return a non-zero exit code with the fix to run.

---

## Quick start (one command)

If you are unsure where to begin, print the local next-step guide:

```bash
python3 scripts/sgt.py quickstart
python3 scripts/quickstart.py
python3 scripts/quickstart.py --format json
```

It runs the doctor summary first, then shows the recommended next command and
a short map from user intent to the right skill.

The `sgt.py` facade is the single entry point for the common workflows so you
don't have to remember every script:

| Command | What it does |
|---|---|
| `sgt init` | Guided install (host + scope), then verifies what landed |
| `sgt doctor` | Local health check |
| `sgt skills` | List installed skills |
| `sgt audit` | Run the full self-audit |
| `sgt new-skill <name> --category <vocab>` | Scaffold a governance-clean `SKILL.md` |
| `sgt ci-init --github` / `--gitlab` | Generate the changed-only PR/MR gate (SHA pre-filled) |
| `sgt uninstall [--dry-run]` | Remove toolkit-owned files; your content is preserved |

```bash
python3 scripts/sgt.py init            # guided setup + verify
python3 scripts/sgt.py doctor
python3 scripts/sgt.py skills
python3 scripts/sgt.py new-skill prompt-evaluate --category governance
python3 scripts/sgt.py ci-init --github
python3 scripts/sgt.py uninstall --dry-run
```

```bash
cd /path/to/skill-governance-toolkit
./install.sh --dry-run        # preview — resolves filters and target paths, writes nothing
./install.sh                  # interactive — asks host + scope, auto-detects upgrades
# or
./install.ps1 -DryRun         # PowerShell preview
./install.ps1                 # PowerShell 7+ (Windows / macOS / Linux)
```

For non-interactive CI use: `./install.sh --yes-default` (Claude + project scope).

Then use a skill in any supported tool:

> «Is there a skill for evaluating prompt quality?»

The host's runtime sees `skill-find`'s description, activates it, returns ranked matches.

**Manual copy alternative** (only for a fresh, empty target):
```bash
cp -r AGENTS.md CLAUDE.md GEMINI.md README.md CHANGELOG.md \
      install.sh install.ps1 .github skills agents references scripts commands \
      docs .claude-plugin .codex-plugin gemini-extension.json \
      /path/to/your/project/
```

> ⚠ This blind `cp -r` **overwrites** any existing `AGENTS.md` / `CLAUDE.md` /
> `GEMINI.md` / `docs/` in the target — it does **not** do the marker-block merge
> or conflict-rename the installer uses. Use `./install.sh` (or `install.ps1`)
> for any target that already has content; reserve the manual copy for an empty repo.

---

## Distribution & installation — for internal team rollout

You host the toolkit **once on GitHub**, then team members install per their runtime. Two distribution models below — pick one or combine.

### Version source of truth

The root [`VERSION`](VERSION) file is the only version number to edit by hand.
Derived copies live in plugin manifests, `pyproject.toml`, and pinned install
examples.

```bash
python3 scripts/sync_version.py          # update derived files from VERSION
python3 scripts/sync_version.py --check  # CI drift check
```

`scripts/audit.sh` runs the check, so release metadata drift fails CI before
publishing.

### Model A — Marketplace / plugin (recommended)

Three runtimes have plugin/marketplace mechanisms with shipped manifests; two runtimes (Copilot, Cursor) read AGENTS.md natively from the project root without needing a separate manifest.

| Runtime | Shipped manifest | How it loads |
|---|---|---|
| Claude Code | `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` | `/plugin install ...` from local or remote marketplace |
| OpenAI Codex CLI | `.codex-plugin/plugin.json` | `codex plugins install ...` |
| Google Gemini CLI | `gemini-extension.json` | `gemini extensions install ...` |
| GitHub Copilot | none (native) | Reads `AGENTS.md` + `.github/copilot-instructions.md` from project workspace |
| Cursor v2.2+ | none (native) | Auto-discovers `AGENTS.md` + `skills/` from project root |

For the two native-discovery runtimes, distribution is either «check the toolkit into the project repo» or «install via dotfiles / git submodule».

#### Claude Code

```bash
# One-time per team member:
/plugin marketplace add {your-org}/skill-governance-toolkit
/plugin install skill-governance-toolkit@skill-governance-marketplace
```

The marketplace manifest at `.claude-plugin/marketplace.json` declares which skills and agents are installed.

For private GitHub repos, team members need to authenticate `gh` CLI first:
```bash
gh auth login    # one-time
```

#### GitHub Copilot

Copilot reads `AGENTS.md` natively from the project root — **no installation step**. To make skills available across all of a developer's projects:

```bash
# Option 1 — via gh extension (if your team uses gh CLI):
gh extension install {your-org}/skill-governance-toolkit

# Option 2 — drop the .github/copilot-instructions.md into target project root manually
```

Skills are auto-discovered when the workspace contains `skills/` and a manifest. For team-wide push, add the toolkit as a git submodule in each repository, or fork into an org-wide template repo used for new projects.

#### OpenAI Codex CLI

```bash
codex plugins install {your-org}/skill-governance-toolkit
```

The Codex CLI fetches the repo, reads `.codex-plugin/plugin.json`, and registers skills + agents.

For Codex App (GUI), team members go to Plugins → Search → install the named plugin (the org must publish it to the Codex marketplace first via `codex plugins publish`).

#### Google Gemini CLI

```bash
gemini extensions install https://github.com/{your-org}/skill-governance-toolkit
```

Gemini reads `gemini-extension.json` and registers the toolkit as a Gemini extension. `GEMINI.md` imports `AGENTS.md` automatically.

For private repos, set `GEMINI_GH_TOKEN` env var with a PAT before running.

#### Cursor v2.2+

Cursor reads `AGENTS.md` natively from any project root and auto-discovers `skills/`. To use the toolkit in a project:

```bash
git submodule add https://github.com/{your-org}/skill-governance-toolkit .skill-toolkit
# Then symlink or merge content into project root
```

For team-wide installation, distribute via the Cursor Plugin Marketplace (paid Cursor plan) or via shared dotfiles.

### Model B — Bootstrap installer script

For teams that don't use plugin marketplaces (or want a single onboarding command), the toolkit ships `scripts/install.sh`:

```bash
# Clone the toolkit anywhere:
git clone https://github.com/{your-org}/skill-governance-toolkit ~/tools/skill-toolkit
cd ~/tools/skill-toolkit

# Install for one runtime (global — all projects):
./scripts/install.sh --claude --global
./scripts/install.sh --copilot --global
./scripts/install.sh --codex --global
./scripts/install.sh --gemini --global
./scripts/install.sh --cursor --global

# Or install for everything at once:
./scripts/install.sh --all --global

# Or install per-project (local to current dir):
cd ~/projects/my-app
~/tools/skill-toolkit/scripts/install.sh --claude --project
```

The installer copies skills, agents, and project rules into each runtime's expected location. Run `--help` for full flag list.

### Installing a subset of skills (since 1.8.0)

By default the installer copies **every skill with tier ∈ {stable, preview}**. As the corporate library grows past 10–20 skills, full installs add unnecessary token cost on activation. Use these flags to scope the install:

```bash
# By category — closed vocab from docs/skill-authoring-standard.md.
# Examples below use categories actually present in the shipped corpus
# (governance, discovery). The other vocab values (code-review, docs,
# testing, research, delivery) become useful once your library adds
# skills carrying those tags — they currently match 0 skills.
./scripts/install.sh --claude --project --category discovery       # skill-find + skill-compare
./scripts/install.sh --claude --project --category governance      # all 6 meta-skills
./scripts/install.sh --claude --project --category discovery,governance  # union

# By tier — default is stable+preview; experimental/internal require explicit opt-in
./scripts/install.sh --claude --project --tier stable               # stable only, skip preview
./scripts/install.sh --claude --project --tier stable,experimental  # include experimentals

# By explicit skill name — overrides category and tier
./scripts/install.sh --claude --project --skill skill-find,skill-evaluate

# Interactive menu — pick from a list of categories with skill counts
./scripts/install.sh --claude --project --interactive
```

Each install dir gets a **filtered `INDEX.jsonl`** listing exactly the installed subset, so `skill-find` in the target environment never reports skills that aren't actually there.

**Closed-vocab `--category` values:** `code-review` · `docs` · `testing` · `governance` · `discovery` · `research` · `delivery`. Adding a new category requires a CHANGELOG entry — `library-audit` Phase 5.5 flags any value outside this list as drift.

**Tier semantics:**

| Tier | Default install? | Stability contract |
|---|---|---|
| `stable` | ✓ | Public API. Breaking changes require major version. |
| `preview` | ✓ | Likely stable, breaking changes possible in minor versions. |
| `experimental` | ✗ opt-in | Anything goes; trigger phrases may change. |
| `internal` | ✗ opt-in | Not for distribution; auditor checks for accidental leaks in manifests. |

Run `python3 scripts/filter_skills.py --index skills/INDEX.jsonl --list-categories` to see the current corpus shape.

### Private GitHub repo — auth setup

If the toolkit lives in a private org repo:

1. **GitHub PAT** with `repo` scope for each developer:
   - Claude Code: stored via `gh auth` or via `corporate-skills-token` env var (see `skill-find` configuration reference in `AGENTS.md`).
   - Codex / Gemini: standard `GH_TOKEN` env var works.
2. **Pin a release tag** for reproducibility:
   ```bash
   /plugin install skill-governance-toolkit@1.14.1    # Claude
   gemini extensions install ...@1.14.1                # Gemini
   ```
3. **CI auto-update** — set up a CI job in each consuming project that opens a PR when the toolkit publishes a new tag. Pattern: scheduled `dependabot.yml` config pointing at the toolkit repo, or a custom workflow.

### What ends up where after installation

| Runtime | Project rules read from | Skills loaded from | Sub-agents loaded from |
|---|---|---|---|
| Claude Code | `CLAUDE.md` (which `@AGENTS.md`) | `~/.claude/skills/` or `./.claude/skills/` | `~/.claude/agents/` or `./.claude/agents/` |
| Copilot | `AGENTS.md` (root) + `.github/copilot-instructions.md` | Skills auto-discovered from workspace | Via `agent` tool with `agents/` |
| Codex CLI | `AGENTS.md` (root) | `~/.codex/skills/` or via `.codex-plugin/plugin.json` | Via `spawn_agent` with `agents/` |
| Gemini CLI | `GEMINI.md` (which `@./AGENTS.md`) | `~/.gemini/skills/` | — (no sub-agent support) |
| Cursor v2.2+ | `AGENTS.md` (root, native) | `./.cursor/skills/` | Via `.cursor-plugin/plugin.json` (when distributed via Cursor marketplace) |

---

## Upgrading from a previous version

Two paths, choose by how the toolkit was installed:

### Path A — installed via `claude plugin install` (Claude Code marketplace)

```bash
# 1. uninstall the current version
claude plugin uninstall skill-governance-toolkit --scope project

# 2. if your marketplace points at a local repo that has new contents — re-add it
claude plugin marketplace remove skill-governance-marketplace --scope project
claude plugin marketplace add ./ --scope project

# 3. install the new version
claude plugin install skill-governance-toolkit@skill-governance-marketplace --scope project
```

Claude Code manages the filesystem for you — no leftover files.

### Path B — installed via `./install.sh` (interactive — recommended for newcomers)

The repo-root `./install.sh` is an interactive wrapper that auto-detects
existing installs and picks the right mode (fresh / upgrade / force) for you.

```bash
./install.sh                 # interactive — asks host + scope
./install.sh --force         # interactive, but wipe target dirs before copy
./install.sh --yes-default   # non-interactive: Claude + project scope (CI)
```

Windows users: `./install.ps1` (PowerShell 7+). On Unix it delegates to
`./install.sh`; on Windows it has a native Copy-Item path.

```powershell
./install.ps1                 # interactive
./install.ps1 -Force          # force-wipe + reinstall
./install.ps1 -YesDefault     # non-interactive default
```

### Path C — advanced (`./scripts/install.sh` with explicit flags)

The underlying installer. Use directly when you want full control over host /
scope / mode without prompts:

```bash
./scripts/install.sh --claude --project --upgrade   # explicit clean upgrade
./scripts/install.sh --all --global --force         # wipe + reinstall everywhere
./scripts/install.sh --help                         # full flag list
```

If `--upgrade` leaves unexpected state (rare), `--force` wipes target dirs
entirely before installing.

**Always read [CHANGELOG.md](CHANGELOG.md) before upgrading** — breaking
changes (skill renames, schema bumps) are marked **🔴 BREAKING** with
per-version upgrade notes.

### State preserved across upgrades

These directories are NEVER touched by upgrades and remain yours:
- `.skill-state/` — resumable-run checkpoints (`references/checkpointing.md`).
- `out/` — audit reports and quality-score logs.
- Any AGENTS.md edits **outside** the `<!-- skill-init: ... -->` marker
  blocks (the markers themselves get re-injected by `integration-init`,
  the surrounding text stays).
- **Your own files in `scripts/`, `references/`, `commands/`** (since 1.10.0).
  The installer tracks the files it owns in a `.sgt-owned` sidecar and merges
  rather than mirror-deletes, so `--upgrade` refreshes toolkit files and removes
  ones it previously shipped — but never deletes files you added. A file you
  named exactly like one of ours is preserved; our copy lands beside it as
  `<name>.skill-governance-toolkit.<ext>`.

> Since 1.10.0 the installer ships only the runtime scripts listed in
> [`scripts/runtime-manifest.txt`](scripts/runtime-manifest.txt) — dev/test/release
> tooling stays in the source repo. Skills that shell out to a toolkit script
> resolve the install root per [`references/path-resolution.md`](references/path-resolution.md)
> (matters for plugin and global installs, where CWD is your project, not the install dir).

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

**Use them together:** run `library-audit` first to find problems; for each flagged skill, run `skill-evaluate` to score it, then `skill-build-portable` to fix portability issues. Iterate until `library-audit` reports clean.

```
                          discovery / governance
                                  │
       ┌──────────────────────────┴──────────────────────────┐
       │                                                     │
   skill-find                                            library-audit
   (what exists?)                                        (what's broken?)
       │                                                     │
       ▼                                                     ▼
   skill-evaluate                              skill-build-portable
   (how good is it?)                           (fix portability of one skill)
       │                                                     │
       ▼                                                     ▼
   skill-compare                                      [re-run library-audit]
   (vs corporate?)
```

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
| Claude Code | `CLAUDE.md` (with `@AGENTS.md` import) + `skills/` + `.claude-plugin/` | ✓ native |
| GitHub Copilot (VS Code / CLI) | `AGENTS.md` + `.github/copilot-instructions.md` + `skills/` (since 2025-12-18) | ✓ native |
| OpenAI Codex CLI | `AGENTS.md` + `skills/` (via `.codex-plugin/`) | ✓ native |
| Google Gemini CLI | `GEMINI.md` (imports `AGENTS.md`) + `skills/` (via `gemini-extension.json`) | ✓ native |
| Cursor (v2.2+) | `AGENTS.md` + `skills/` (auto-discovered) | ✓ native, no manifest needed |

---

## Repository layout

```
.
├── AGENTS.md                          ← single source of truth (project rules)
├── CLAUDE.md                          ← @AGENTS.md alias + Claude-specific extensions
├── GEMINI.md                          ← @./AGENTS.md alias + tool-mapping import
├── README.md                          ← this file (English quick start)
├── docs/                              ← documentation moved here for v1.7.0+
│   ├── user-guide.md                  ← English user guide with workflows + examples
│   ├── user-guide.ru.md               ← Russian user guide with workflows + mermaid diagrams
│   ├── agent-governance-engine.md        ← CLI/MCP/Docker audit engine guide
│   ├── checks-reference.md            ← every governance check + rationale (engine rules + LLM dims)
│   ├── extending-checks.md            ← decision tree: where a new check goes (gate vs LLM skill)
│   ├── architecture.md                ← three-layer architecture, install contract, parallelization
│   ├── skill-authoring-standard.md    ← canonical SKILL.md skeleton
│   ├── contributing-rules.md          ← propose an org governance rule (advisory-first + stability marker)
│   └── benchmarks.md                  ← external claim caveats (CRG 8.2× etc.)
├── CHANGELOG.md                       ← per-version history with breaking-change markers
├── LICENSE                            ← MIT
├── install.sh                         ← interactive one-command installer (bash, recommended)
├── install.ps1                        ← interactive installer (PowerShell 7+ — Win/macOS/Linux)
├── .gitignore
│
├── .github/
│   └── copilot-instructions.md        ← Copilot-specific note + alias to AGENTS.md
│
├── .claude-plugin/
│   ├── plugin.json                    ← Claude Code plugin manifest
│   └── marketplace.json               ← Claude Code marketplace catalog
│
├── .codex-plugin/plugin.json          ← Codex CLI manifest
├── gemini-extension.json              ← Gemini CLI extension manifest
│
├── commands/                          ← slash commands
│   └── integration-init.md            ← /integration-init (renamed from /init to avoid Claude Code built-in collision)
│
├── references/                        ← repo-level references (cross-skill)
│   ├── claude-tools.md                ← Claude Code dialect reference (identity + extensions)
│   ├── copilot-tools.md               ← Read→view, Edit→edit, Task→agent
│   ├── codex-tools.md                 ← Read→read_file, Task→spawn_agent
│   ├── gemini-tools.md                ← Read→read_file + no-sub-agent warning
│   └── checkpointing.md               ← canonical resumable-run state pattern
│
├── skills/                            ← procedural skills (host-neutral)
│   ├── INDEX.jsonl                    ← fast-path discovery for skill-find
│   ├── skill-find/SKILL.md            ← discovery
│   ├── skill-evaluate/                ← per-skill quality + safety scoring
│   │   ├── SKILL.md
│   │   ├── references/rubrics.md      ← D1–D9 scoring tables + calibration tips
│   │   └── assets/output-template-detailed.md   ← detailed-mode output spec
│   ├── skill-compare/SKILL.md         ← local-vs-corporate 1:1
│   ├── library-audit/                 ← library-wide governance
│   │   ├── SKILL.md
│   │   ├── references/
│   │   │   ├── handoff-spec.md        ← Phase 1 (handoff contracts)
│   │   │   ├── budget-spec.md         ← Phase 2 (token budget)
│   │   │   ├── naming-spec.md         ← Phase 3/4 (naming + portability tag)
│   │   │   └── security-spec.md       ← Phase 5 (secrets / dangerous shell / cred paths)
│   │   └── assets/output-template-detailed.md   ← detailed-mode report spec
│   ├── skill-build-portable/          ← portability migration
│   │   ├── SKILL.md
│   │   └── references/portability-rules.md
│   └── integration-init/              ← bootstrap optional integrations
│       ├── SKILL.md
│       └── references/
│           ├── integrations.md        ← CRG / repomix / serena spec
│           └── examples.md            ← three worked walkthroughs
│
├── agents/                            ← specialized sub-agents
│   └── code-reviewer.md               ← TypeScript reviewer (5 categories, severity tiers)
│
└── scripts/                           ← stdlib-only helpers
    ├── build_index.py                 ← regenerate skills/INDEX.jsonl
    ├── checkpoint.py                  ← resumable-run state helper (start/save-phase/complete/list)
    ├── install.sh                     ← multi-runtime installer (advanced; flags-driven)
    ├── init.sh                        ← bash fallback for integration-init (CI/non-interactive)
    └── install-pre-commit-hook.sh     ← optional pre-commit graph-freshness check (CRG)
```

---

## Resumable runs

Every multi-phase skill in this toolkit (library-audit, skill-evaluate, skill-build-portable, integration-init, skill-compare) writes a JSON checkpoint after each expensive phase to `${CWD}/.skill-state/{skill-name}/run-{utc-ts}.json`. If a run is interrupted — crash, timeout, manual abort — the next invocation can pick up where it stopped, skipping completed phases.

| Skill | Resume mode default | Why |
|---|---|---|
| `library-audit`, `skill-evaluate`, `skill-build-portable`, `skill-compare` | `auto` | Validator / read-mostly skills stay detect-only; resume silently to preserve idempotency. |
| `integration-init` | `ask` | Gateway skill — the user expects an interactive prompt and benefits from picking which prior run to resume. |

Override per invocation by passing `RESUME=new` to force a fresh run, or `RESUME=ask` to be prompted unconditionally.

The state directory is gitignored. Operators can prune old completed runs with:
```bash
find .skill-state -name 'run-*.json' -mtime +30 -delete
```

Full pattern reference: [`references/checkpointing.md`](references/checkpointing.md). Helper CLI: [`scripts/checkpoint.py`](scripts/checkpoint.py) (stdlib only — `python3 scripts/checkpoint.py --help`).

---

## Maintenance

### Regenerate the skill index

After adding, renaming, or significantly editing a skill, refresh `INDEX.jsonl`:
```bash
python3 scripts/build_index.py
```

This is what `skill-find` uses for fast lookups. Without it, `skill-find` falls back to scanning every `SKILL.md` individually.

### Run a library audit

```
"Audit my skills."
```

The host activates `library-audit`, which runs all phases (P0–P6, including P4.5 multi-tool compatibility and P5.5 metainfo coverage) and writes `out/library-audit/library-audit-{date}.md`.

### Add a new skill

1. Create `skills/{your-skill}/SKILL.md` with required frontmatter:
   - `name` — `{entity}-{action}[-{qualifier}]` (kebab-case, closed verb vocab — see `docs/skill-authoring-standard.md` §0)
   - `description` — 1–2 sentence WHAT + trigger phrases + output (sweet spot 100–400 chars)
   - `compatibility` — runtimes the skill supports
   - `license` — usually `MIT`
   - `metainfo:` block (since 1.8.0) — `category` (from closed vocab), `tier` (default `preview` for new skills), `owner`, `added` (today's date)
2. Run `skill-evaluate` on it to verify quality.
3. Run `library-audit` to verify it doesn't introduce handoff, naming, or metainfo coverage violations.
4. Run `python3 scripts/build_index.py` to refresh `skills/INDEX.jsonl`. After this the installer will see the new skill via `--category` / `--tier` filters.

**New skills should start at `tier: preview`** — only promote to `stable` after the skill has shipped through ≥1 release without breaking changes. Skills can also be `tier: experimental` for incubation (not installed by default).

### Convert an existing non-portable skill

```
"Universalize skills/legacy-skill/SKILL.md"
```

The host activates `skill-build-portable`, audits the source, produces a diff preview. Approve, then re-run with `OUTPUT_MODE=new-file` or `OUTPUT_MODE=in-place`.

---

## License

MIT (see `LICENSE`).
