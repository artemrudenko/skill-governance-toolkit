# Tool-Name Mapping — Google Gemini CLI

Skills in this repository use **Claude Code tool names** as the canonical reference. If you are running on Gemini CLI, translate as follows.

## Core tool mapping

| Skill references | Gemini equivalent | Notes |
|---|---|---|
| `Read` | `read_file` | Read a file's contents |
| `Write` | `write_file` | Create or overwrite a file |
| `Edit` | `replace` | In-place edit (`old_string` → `new_string`) |
| `Bash` | `run_shell_command` | Execute a shell command |
| `Grep` | `run_shell_command` with `rg` / `grep` | Use shell with ripgrep |
| `Glob` | `run_shell_command` with `find` | Use shell |
| `WebFetch` | `web_fetch` | Fetch a URL |
| `WebSearch` | `google_search` | Native Gemini tool |
| `Task` (subagent dispatch) | — | **Gemini CLI does not support sub-agents.** Inline the agent's instructions into the skill body, or split into sequential skill invocations |
| `TodoWrite` | — | No native todo tool — keep todos in markdown inline |
| `AskUserQuestion` | `ask_user` | Multiple-choice user input |
| `Skill` tool | `activate_skill` | Gemini loads skill metadata at session start and activates the full body on demand |

## Behavioral differences worth knowing

### No sub-agents

This is the most significant difference. If a skill relies on the `Task` orchestration pattern (parallel fan-out, hierarchical delegation), it **will not work on Gemini CLI as written**. Two workarounds:

1. **Inline the agent's instructions** into the skill body — converts orchestration into a single linear flow.
2. **Sequential skill invocations** — the user manually invokes each step, or the skill returns a "next step" hint that the user accepts.

`library-audit` Phase 4.5 flags Task-dependent skills with a warning so you can plan ahead.

### Skill discovery

- Gemini reads `GEMINI.md` at session start. The shipped `GEMINI.md` imports `AGENTS.md` (line 1) and this tool-mapping file (line 2) using `@./path` syntax.
- Skill metadata (frontmatter only) loads at session start. Skill bodies activate on demand when the user's phrasing matches.

### Project rules

- Gemini does **not** read `AGENTS.md` directly — only `GEMINI.md`. The `@./AGENTS.md` import line bridges this.
- Maximum import recursion depth is 5 hops.

## Setup notes

1. Install via `gemini extensions install <git-url>` or by placing this repository's contents into your project.
2. The `gemini-extension.json` manifest declares `"contextFileName": "GEMINI.md"` so Gemini knows which file to read.
