# Skill Governance Toolkit - User Guide

Universal meta-skill toolkit for teams adopting `AGENTS.md` and `SKILL.md`
standards. It helps discover, evaluate, compare, audit, and port agent skills
without forking source files per AI host.

This guide is the English companion to `docs/user-guide.ru.md`.

---

## What This Toolkit Contains

```mermaid
flowchart TB
    subgraph "Repository root"
        AGENTS["AGENTS.md<br/>single source of truth"]
        CLAUDE["CLAUDE.md -> @AGENTS.md"]
        GEMINI["GEMINI.md -> @./AGENTS.md"]
        COPILOT[".github/copilot-instructions.md"]
        README["README.md<br/>quick start"]
        UGEN["docs/user-guide.md<br/>this guide"]
        UGRU["docs/user-guide.ru.md<br/>Russian guide"]
        CHANGELOG["CHANGELOG.md"]
    end

    subgraph "skills/"
        FIND["skill-find"]
        EVAL["skill-evaluate"]
        COMP["skill-compare"]
        AUDIT["library-audit"]
        BUILD["skill-build-portable"]
        INIT["integration-init"]
    end

    subgraph "agents/"
        REVIEWER["code-reviewer"]
    end

    subgraph "scripts/"
        INDEX["build_index.py"]
        CHECKPOINT["checkpoint.py"]
        DOCTOR["doctor.py"]
        AUDITCLI["agent_audit.py"]
        MCP["agent_governance_mcp.py"]
    end

    subgraph "docs/"
        MCPDOC["agent-governance-mcp.md"]
        STANDARD["skill-authoring-standard.md"]
    end

    AGENTS --> FIND
    AGENTS --> EVAL
    AGENTS --> COMP
    AGENTS --> AUDIT
    AGENTS --> BUILD
    AGENTS --> INIT
    BUILD -.can dispatch.-> REVIEWER
    AUDITCLI --> MCP
```

---

## Component Status

| Component | Status | Meaning |
|---|---|---|
| Six meta-skills | `stable` | Ready for normal team use. Breaking changes should appear only in release notes. |
| `agents/code-reviewer.md` | `stable` | Read-only TypeScript-focused reviewer. Bash usage is limited to inspection. |
| `scripts/doctor.py` | `stable` | Fast local health check for setup, Git state, index freshness, and local artifacts. |
| CLI/MCP/Docker audit engine | `preview` | Covered by tests and useful today, but tool names and rule details may still change before the first tagged release. |
| Optional integrations | opt-in | CRG, repomix, and serena are installed only through `integration-init`; they are not baseline requirements. |

For a quick local readiness check, run:

```bash
python3 scripts/doctor.py
```

Use `--format json` in automation. The doctor fails only on actionable
problems, such as missing required files or stale `skills/INDEX.jsonl`.

Before publishing, opening a PR, or cutting a release, run:

```bash
bash scripts/audit.sh
python3 scripts/test_doctor.py
python3 scripts/test_agent_audit.py
python3 scripts/agent_audit.py audit-project . --profile release-ready --fail-on any --format json
docker build -t agent-governance-mcp:local .
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | docker run --rm -i --network none -v "$PWD:/workspace:ro" agent-governance-mcp:local
```

GitHub Actions runs the baseline checks in `.github/workflows/ci.yml`.

---

## Skill Map

| Need | Use |
|---|---|
| Find whether a useful skill already exists | `skill-find` |
| Score one `SKILL.md` across quality, safety, and writing dimensions | `skill-evaluate` |
| Compare a local skill with a corporate or upstream version | `skill-compare` |
| Audit the whole skill library | `library-audit` |
| Convert a host-specific skill into a portable one | `skill-build-portable` |
| Install optional integrations | `integration-init` |

Scope rule:

| Prefix | Scope |
|---|---|
| `skill-*` | One skill |
| `library-*` | Whole library |
| `integration-*` | Optional external tooling |

---

## Use Case 1 - Adopt an External Skill

When a teammate or upstream repository provides a `SKILL.md`, evaluate it
before adding it to your library.

```text
evaluate this skill
SKILL_TARGET=path/to/external/SKILL.md
```

Expected output:

| Section | Purpose |
|---|---|
| Summary table | One-line D1-D9 score overview |
| Per-dimension findings | Evidence, risk, and concrete improvement for each dimension |
| Safety gate | Blocks unsafe mutating skills even when the average score looks acceptable |
| Top 3 improvements | Highest-impact fixes |
| Verdict | Adopt, adopt after fixes, rewrite, or reject |

Decision guide:

| Verdict | Action |
|---|---|
| Green, safety clear | Adopt as-is |
| Yellow | Adopt after the top fixes |
| Orange | Prefer a better alternative or rewrite first |
| Red or safety gate triggered | Do not adopt until the safety issues are fixed |

---

## Use Case 2 - Create a New Skill

The toolkit does not include a boilerplate-first scaffolder. Start from a
working skill, trim it to the new purpose, then evaluate it.

Recommended flow:

1. Run `skill-find` for the need.
2. If a close match exists, use `skill-compare` instead of creating another skill.
3. If no match exists, create `skills/{name}/SKILL.md`.
4. Keep frontmatter portable: `name`, `description`, `compatibility`, `license`,
   and `metainfo`.
5. Add concrete trigger phrases to `description`.
6. Add workflow phases, hard rules, inputs, outputs, and verification.
7. Run `skill-evaluate`.
8. Fix the top findings until the score and safety gate are acceptable.
9. Run `library-audit`.
10. Rebuild `skills/INDEX.jsonl`.

Minimal shape:

```markdown
---
name: skill-example
description: |
  Does one specific workflow.
  Use when: "example trigger", "second trigger", "third trigger".
compatibility: "Claude Code, Copilot, Cursor, Codex, Gemini"
license: MIT
metainfo:
  category: governance
  tier: preview
---

# Skill Example

## When to use

- Use for ...
- Skip for ...

## Required inputs

| Input | Type | Default | Description |
|---|---|---|---|
| TARGET | path | required | File or directory to inspect |

## Workflow

### Phase 0 - Validate inputs
### Phase 1 - Read bounded context
### Phase 2 - Produce findings
### Phase 3 - Verify output

## Hard rules

- Keep the scope bounded.
- Do not edit files unless the user explicitly asks for edits.
```

---

## Use Case 3 - Audit a Skill Library

Use `library-audit` before releases and after major skill changes.

```text
audit my skills
```

It checks:

| Category | Examples |
|---|---|
| Handoff contracts | Trigger uniqueness, predecessor/successor consistency |
| Token budget | Always-on cost, oversized skill bodies |
| Naming | Kebab-case, closed-vocabulary verbs, `{entity}-{action}` pattern |
| Portability | Missing compatibility metadata, host-specific fields |
| Multi-tool compatibility | `allowed-tools:`, per-skill tool mappings, missing Gemini fallback |
| Security | Secrets, credential paths, dangerous shell, prompt-injection risks |
| Metainfo | Required `category` and `tier`, closed vocabulary compliance |

The report is written to:

```text
out/library-audit/library-audit-{YYYY-MM-DD}.md
```

Large runs checkpoint under:

```text
.skill-state/library-audit/
```

If the run stops midway, rerunning the skill can resume from the last
checkpoint.

---

## Use Case 4 - Deterministic Audit Engine: CLI, MCP, Docker

`library-audit` is an agent skill. The deterministic audit engine is a
separate read-only layer for CI, local checks, and MCP clients.

It should not replace human or LLM interpretation. It indexes project assets,
applies deterministic rules, and returns structured findings.

### CLI

```bash
# Discover agent-related assets
python3 scripts/agent_audit.py discover .

# Audit a full project
python3 scripts/agent_audit.py audit-project . --profile release-ready --format json

# Fail CI when high-severity findings exist
python3 scripts/agent_audit.py audit-project . --profile release-ready --fail-on high

# Audit one SKILL.md
python3 scripts/agent_audit.py audit-skill skills/skill-evaluate/SKILL.md

# Inspect rules
python3 scripts/agent_audit.py rules
python3 scripts/agent_audit.py explain-rule SKILL009
```

Profiles:

| Profile | Use |
|---|---|
| `security` | Safety-focused scan |
| `quality` | Structure, usability, and portability |
| `maintainability` | Broad regular maintenance scan |
| `release-ready` | Pre-release gate |

### MCP Server

Run locally:

```bash
python3 scripts/agent_governance_mcp.py
```

Example MCP config:

```json
{
  "mcpServers": {
    "agent-governance": {
      "command": "python3",
      "args": ["/path/to/skill-governance-toolkit/scripts/agent_governance_mcp.py"],
      "env": {
        "AGENT_GOVERNANCE_ROOT": "/path/to/project"
      }
    }
  }
}
```

Tools:

| Tool | Purpose |
|---|---|
| `discover_agent_assets` | Find `AGENTS.md`, `SKILL.md`, prompts, agent configs, aliases, and MCP/plugin configs |
| `audit_skill` | Audit one `SKILL.md` |
| `audit_project` | Audit a project and return structured findings |
| `explain_rule` | Explain one `rule_id` |
| `get_rule_catalog` | Return the rule catalog |

Path behavior:

- The server only accepts paths inside its configured root.
- `AGENT_GOVERNANCE_ROOT` sets the root explicitly.
- `AGENT_GOVERNANCE_RULES_PATH` can point to a custom rule catalog.
- A custom rule catalog must define every `rule_id` used by the engine.
- `AGENT_GOVERNANCE_DEBUG=1` enables tracebacks; without it, MCP errors are sanitized.

### Docker

Build the image:

```bash
docker build -t agent-governance-mcp:local .
```

Run against the current repository:

```bash
docker run --rm -i \
  --network none \
  -v "$PWD:/workspace:ro" \
  agent-governance-mcp:local
```

For strict CI file permissions:

```bash
docker run --rm -i \
  --network none \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace:ro" \
  agent-governance-mcp:local
```

MCP config through Docker:

```json
{
  "mcpServers": {
    "agent-governance": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "-v",
        "/path/to/repo:/workspace:ro",
        "agent-governance-mcp:local"
      ]
    }
  }
}
```

Inside Docker, pass project roots as `/workspace`.

Docker tradeoffs:

| Tradeoff | Impact |
|---|---|
| Requires Docker daemon | Not ideal for very small local checks |
| Host/container paths differ | Use `/workspace` inside the MCP call |
| macOS/Windows volume mounts may be slower | Fine for CI and most skill libraries |
| Files outside the repo are invisible | Mount extra paths explicitly if needed |
| Stdio MCP needs `-i` | Without stdin, the server exits immediately |

Recommended secure baseline:

```bash
docker run --rm -i --network none -v "$PWD:/workspace:ro" agent-governance-mcp:local
```

### GitHub Actions

The repository includes:

```text
.github/workflows/ci.yml
```

Jobs:

| Job | What it runs |
|---|---|
| `audit` | Shell audit, behavior tests, and release-ready audit gate |
| `docker` | Docker build, MCP `tools/list`, and Docker `audit_project /workspace` |

---

## Use Case 5 - Make a Skill Portable

Use `skill-build-portable` when a skill is tied to one host or organization.

Common issues:

| Issue | Example | Expected fix |
|---|---|---|
| Host-specific frontmatter | `allowed-tools:` | Remove from portable skills |
| Claude-only fields | `model`, `effort`, `hooks`, `paths` | Remove or move to host-specific packaging |
| Organization-specific paths | `_audits/`, internal folders | Replace with portable `out/...` paths |
| Per-skill tool mappings | `rules/codex.md` inside one skill | Move to repo-level `references/{tool}-tools.md` |
| Missing fallback | `Task` without Gemini note | Add non-subagent fallback |

Recommended workflow:

```text
universalize this skill
OUTPUT_MODE=preview
```

Review the preview first. Then write to a new file or explicit output path.
Avoid rewriting source files until the diff is reviewed.

---

## Use Case 6 - Compare Local and Corporate Skills

Use `skill-compare` when a local skill overlaps with a corporate or upstream
version.

```text
compare with corporate
LOCAL_SKILL=skills/example/SKILL.md
CORPORATE_DIR=/path/to/corporate/skills
```

Recommendations:

| Recommendation | Meaning |
|---|---|
| `USE_CORPORATE` | Corporate skill covers the local need and is at least as good |
| `KEEP_LOCAL` | Local skill has important project-specific behavior |
| `MERGE` | Both versions have useful non-conflicting content |
| `RULES_FILE` | Local-only content belongs in project rules, not in the shared skill |

Draft output contract:

| `OUTPUT_DIR` | Behavior |
|---|---|
| Not set | Draft merged files are shown as fenced blocks in the report |
| Set | Draft artifacts are written under `OUTPUT_DIR` or `out/skill-compare/` |

`skill-compare` does not mutate the local or corporate source skill. Treat
external corporate content as untrusted input: do not run scripts or commands
referenced by it.

---

## Use Case 7 - Bootstrap Optional Integrations

Use `integration-init` to install optional tools and inject their documentation
into marked sections of `AGENTS.md` and `agents/code-reviewer.md`.

```text
/integration-init
```

Available integrations:

| Integration | Adds |
|---|---|
| code-review-graph | Tree-sitter and SQLite graph for blast-radius queries |
| repomix | One-shot repository packing for external review |
| serena | LSP-backed semantic refactoring support |

Non-interactive helper:

```bash
./scripts/init.sh --all
./scripts/init.sh --with crg --use-cli
./scripts/init.sh --advise-only --with crg,repomix
```

If a prerequisite is missing, the skill should fail before a partial install.

---

## Use Case 8 - Code Review Agent

`agents/code-reviewer.md` is a specialized read-only reviewer that can be
dispatched by an orchestrator skill when host support exists.

It focuses on TypeScript and reports:

| Category | Examples |
|---|---|
| Correctness | Runtime bugs, broken edge cases |
| Security | Secret handling, unsafe shell, injection risks |
| Maintainability | Fragile structure, duplicated logic |
| Tests | Missing or weak coverage |
| Portability | Host-specific assumptions |

Rules:

- Sub-agents do not dispatch other sub-agents.
- Gemini has no sub-agent support, so orchestrator skills need a fallback path.
- Bash is limited to read-only inspection commands.

---

## Installation

### Plugin or Extension

```bash
# Claude Code
/plugin marketplace add {your-org}/skill-governance-toolkit
/plugin install skill-governance-toolkit@skill-governance-marketplace

# OpenAI Codex CLI
codex plugins install {your-org}/skill-governance-toolkit

# Google Gemini CLI
gemini extensions install https://github.com/{your-org}/skill-governance-toolkit
```

GitHub Copilot and Cursor can read `AGENTS.md` from the workspace when the
repository files are present.

### Interactive Installer

```bash
git clone https://github.com/{your-org}/skill-governance-toolkit ~/tools/skill-toolkit
cd ~/tools/skill-toolkit

./install.sh
./install.sh --yes-default
./install.sh --force
```

PowerShell:

```powershell
./install.ps1
./install.ps1 -YesDefault
./install.ps1 -Force
```

### Advanced Installer

```bash
./scripts/install.sh --all --global
./scripts/install.sh --claude --project --upgrade
./scripts/install.sh --help
```

### Selective Install

Install by category:

```bash
./scripts/install.sh --claude --project --category discovery
./scripts/install.sh --claude --project --category discovery,governance
```

Install by tier:

```bash
./scripts/install.sh --claude --project --tier stable
./scripts/install.sh --claude --project --tier stable,experimental
```

Install by exact skill name:

```bash
./scripts/install.sh --claude --project --skill skill-find,skill-evaluate
```

Open the interactive selector:

```bash
./scripts/install.sh --claude --project --interactive
```

Closed category vocabulary:

```text
code-review, docs, testing, governance, discovery, research, delivery
```

Tier behavior:

| Tier | Installed by default? | Contract |
|---|---|---|
| `stable` | Yes | Public behavior should remain stable |
| `preview` | Yes | Usable, but minor breaking changes are possible |
| `experimental` | No | Opt-in only |
| `internal` | No | Not for external distribution |

Inspect the current skill index:

```bash
python3 scripts/filter_skills.py --index skills/INDEX.jsonl --list-categories
```

---

## Upgrades

Read `CHANGELOG.md` before upgrading.

Plugin-managed install:

```bash
claude plugin uninstall skill-governance-toolkit --scope project
claude plugin marketplace remove skill-governance-marketplace --scope project
claude plugin marketplace add ./ --scope project
claude plugin install skill-governance-toolkit@skill-governance-marketplace --scope project
```

Script-managed install:

```bash
./scripts/install.sh --claude --project --upgrade
./scripts/install.sh --claude --project --force
```

Use `--upgrade` for normal clean upgrades. Use `--force` only when you want a
fresh copy of the managed target directories.

The upgrade process should not remove:

| Path | Why it is preserved |
|---|---|
| `.skill-state/` | Resumable run checkpoints |
| `out/` | Reports and quality-score logs |
| Custom text outside `<!-- skill-init: ... -->` markers | Project-specific instructions |

---

## Regular Maintenance

After adding, renaming, or significantly editing a skill:

```bash
python3 scripts/build_index.py
```

Weekly or before release:

```text
audit my skills
```

Before pushing:

```bash
bash scripts/audit.sh
python3 scripts/test_agent_audit.py
python3 scripts/agent_audit.py audit-project . --profile release-ready --fail-on any --format json
```

When Docker or MCP behavior changed:

```bash
docker build -t agent-governance-mcp:local .
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | docker run --rm -i --network none -v "$PWD:/workspace:ro" agent-governance-mcp:local
```

---

## Writing Rules for Skills

Keep skill bodies concise and single-language. English is recommended for
portable routing because most frontmatter parsers and embedding models are
tuned on English corpora.

Hard rules:

- Use one language per `SKILL.md` body.
- Prefer active voice and direct imperatives.
- Use tables for input and parameter specifications.
- Use bullets or numbered lists for enumerable content.
- Avoid duplicate sections and repeated paragraphs.
- Avoid filler phrases such as "It is important to note" and "In conclusion".

Run `skill-evaluate` on every new or heavily rewritten skill. Phase 3.6 checks
writing quality and can cap D1 when language mixing, filler density, or
duplicate paragraphs exceed thresholds.

---

## External MCP-Dependent Skills

This section is not about the built-in `agent-governance` MCP server. It is
about future user skills that depend on external MCP tools, for example
`mcp__slack__send_message` or `mcp__atlassian__create_issue`.

Current checks cover those dependencies indirectly through D2 completeness and
D6 portability. A future static check should verify:

| Check | Expected evidence |
|---|---|
| MCP usage detection | `mcp__*` patterns in the body |
| Setup documentation | `## Prerequisites` or `references/dependencies.md` |
| Graceful failure | Phase 0 fail-fast behavior when the MCP server is unavailable |
| Auth scopes | Documented tokens, scopes, and environment variables |

For now, any skill that needs an external MCP server should include a
`## Prerequisites` section explaining:

- Which MCP server is required.
- How to install or enable it.
- Which environment variables or scopes are needed.
- What the skill does when the connection is unavailable.

---

## What This Guide Does Not Cover

| Topic | Where to read |
|---|---|
| Audit engine internals and MCP config details | `docs/agent-governance-mcp.md` |
| Checkpoint schema and helper CLI | `references/checkpointing.md` |
| Full naming rules | `skills/library-audit/references/naming-spec.md` |
| D1-D9 scoring rubrics | `skills/skill-evaluate/references/rubrics.md` |
| Security regex catalog | `skills/library-audit/references/security-spec.md` |
| Tool-name mappings | `references/{claude,copilot,codex,gemini}-tools.md` |
| Russian version | `docs/user-guide.ru.md` |

---

## License

MIT. See `LICENSE`.
