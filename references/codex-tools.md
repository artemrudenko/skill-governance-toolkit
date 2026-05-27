# Tool-Name Mapping — OpenAI Codex CLI

Skills in this repository use **Claude Code tool names** as the canonical reference. If you are running on OpenAI Codex CLI, translate as follows.

## Core tool mapping

| Skill references | Codex equivalent | Notes |
|---|---|---|
| `Read` | `read_file` | Read a file's contents |
| `Write` | `write_file` | Create or overwrite a file |
| `Edit` | `apply_patch` | In-place edit (patch-based) |
| `Bash` | `shell` | Execute a command in the sandbox |
| `Grep` | `shell` with `rg` / `grep` | Use the shell tool with ripgrep |
| `Glob` | `shell` with `find` | Use the shell tool |
| `WebFetch` | `web` | Fetch a URL |
| `WebSearch` | — | Use `web` against a search engine URL |
| `Task` (subagent dispatch) | `spawn_agent` | Dispatch a sub-agent file from `agents/` |
| `TodoWrite` | `update_plan` | Codex tracks plans natively via its plan tool |
| `AskUserQuestion` | `ask_user` | Multiple-choice user input |
| `Skill` tool (manual skill invocation) | — | Skills load natively from `skills/` — no explicit invocation tool; just follow the skill body once activated |

## Behavioral differences worth knowing

### Skill discovery

- Codex auto-discovers skills from `skills/` when the repo contains `.codex-plugin/plugin.json` declaring `"skills": "./skills/"`.
- Skills are activated when the user's phrasing matches the `description` field — same as Claude Code.

### Sub-agents

- Use `agents/{name}.md` for specialized roles. The agent's `tools:` frontmatter declares its allowed tools.
- Dispatch via `spawn_agent` from an orchestrator skill. Codex enforces the agent's tool restrictions.

### Tool restrictions

- Codex does **not** support a SKILL.md-level `allowed-tools:` whitelist. To restrict tools, use the agent layer (`agents/{name}.md` with `tools:` field).

### Slash commands

- Codex uses `$command-name` syntax (instead of `/command-name`). Slash commands defined in `commands/` will be auto-mapped at install time.

## Setup notes

1. Codex reads `AGENTS.md` natively. No installation step needed for the project rules layer.
2. To install the toolkit as a Codex plugin: run `codex plugins install` and select this repository, or use the marketplace flow declared in `.codex-plugin/plugin.json`.
