# Tool-Name Mapping — GitHub Copilot

Skills in this repository use **Claude Code tool names** as the canonical reference. If you are running on GitHub Copilot (CLI or VS Code agent mode), translate as follows.

## Core tool mapping

| Skill references | Copilot equivalent | Notes |
|---|---|---|
| `Read` | `view` | Read a file's contents |
| `Write` | `create` | Create or overwrite a file |
| `Edit` | `edit` | Edit a file in place (`old_string` → `new_string`) |
| `Bash` | `bash` | Execute a shell command in the sandbox |
| `Grep` | `grep` | Search file contents |
| `Glob` | `glob` | Match files by pattern |
| `WebFetch` | `web_fetch` | Fetch a URL |
| `WebSearch` | — | No direct equivalent. Use `web_fetch` against a search engine URL, or skip the step |
| `Task` (subagent dispatch) | `agent` if available | Optional sub-agent dispatch. Tool/permission restrictions are taken from the agent file's `tools:` field when supported |
| `TodoWrite` | `sql` against built-in `todos` table | Copilot stores todos in an internal SQLite table |
| `AskUserQuestion` | plain chat clarification / host input tool if available | Canonical clarification concept, not a required API |
| `NotebookEdit` | — | Jupyter notebook editing not supported; treat as `view` + `create` |
| `SlashCommand` | `skill` | Skills are auto-discovered from installed plugins; no slash needed |

## Behavioral differences worth knowing

### Tool restrictions

- Claude Code can pre-approve listed tools; other tools remain subject to its permission settings.
- Copilot **silently ignores** `allowed-tools:`. A skill can receive different approval behavior across hosts.
- **Implication:** if a skill assumes restricted tool access for safety reasons, document those assumptions in the body — frontmatter alone won't enforce them on Copilot.

### Sub-agents

- Copilot agent-mode hosts may support sub-agent dispatch via `agent` tool. Tool restrictions defined in the agent file's `tools:` frontmatter **are honored** when dispatch is available.
- Only one level of sub-agent nesting is supported (an agent cannot spawn another agent).
- Skills must keep a sequential fallback for Copilot versions or modes that do not expose sub-agent dispatch.

### Path-scoped instructions

- Copilot supports `.github/instructions/*.instructions.md` files with an `applyTo:` glob in their frontmatter for path-scoped rules. This is **Copilot-only**.
- For universal path scoping, use **nested `AGENTS.md`** files instead — every supported tool reads the closest one in the directory tree.

## Setup notes

1. Copilot reads `AGENTS.md` natively (since 2025-08-28). No installation step needed.
2. Skills are auto-discovered from the workspace `skills/{name}/SKILL.md` directory (native since 2025-12-18) — Copilot needs **no plugin manifest**. Each skill's `description` field declares its trigger phrases; `.github/copilot-instructions.md` points Copilot at this mapping file.
3. For older Copilot versions that do not support `AGENTS.md`, the file `.github/copilot-instructions.md` exists as a fallback alias.
