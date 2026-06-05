# Claude Code — Dialect Reference

This file is **not a tool-name mapping** (skills already use Claude Code tool names as the canonical reference). Instead, it documents Claude Code-specific frontmatter fields, tool behaviors, and dialect features that go beyond the universal Agent Skills standard.

**Use this file when:** you're writing a Claude-only optimization and need to know which fields will be ignored by other runtimes.

## Canonical tool names

Skills use these names directly (no translation needed in Claude Code):

| Tool | Purpose |
|---|---|
| `Read` | Read a file's contents |
| `Write` | Create or overwrite a file |
| `Edit` | In-place edit (`old_string` → `new_string`) |
| `Bash` | Execute a shell command in the sandbox |
| `Grep` | Search file contents (ripgrep-backed) |
| `Glob` | Match files by pattern |
| `WebFetch` | Fetch a URL |
| `WebSearch` | Search the web |
| `Task` | Dispatch a sub-agent; portable skills still need a sequential fallback |
| `TodoWrite` | Manage task list (rendered as widget in some hosts) |
| `AskUserQuestion` | Multiple-choice user input; canonical form of a clarification gate |
| `NotebookEdit` | Edit Jupyter notebook cells |
| `Skill` | Manually invoke a skill |
| `SlashCommand` | Invoke a defined slash command |

---

## Claude Code-specific frontmatter fields

These fields are **honored by Claude Code only** — other runtimes silently ignore them. Use them sparingly; if a field is essential to skill behavior, document the fallback in the body for non-Claude hosts.

| Field | Purpose | Honored by |
|---|---|---|
| `allowed-tools` | **Hard whitelist** — listed tools are the only ones the skill can call. Blocks all others. | Claude Code only — Copilot/Cursor/Codex ignore (**dangerous: skill silently behaves differently across runtimes**) |
| `when_to_use` | Trigger phrases (supplementary to `description`) | Claude Code only |
| `argument-hint` | Autocomplete hint for slash-command invocation | Claude Code only |
| `arguments` | Named positional args | Claude Code only |
| `disable-model-invocation` | If `true`, skill cannot be auto-invoked — manual only | Claude Code only |
| `user-invocable` | If `false`, hides skill from `/` menu | Claude Code only |
| `model` | Per-skill model override (`opus` / `sonnet` / `haiku`) | Claude Code only |
| `effort` | Reasoning effort: `low` / `medium` / `high` / `xhigh` / `max` | Claude Code only |
| `context: fork` | Run this skill in a separate sub-agent context | Claude Code only |
| `agent` | Named sub-agent type to use | Claude Code only |
| `hooks` | Skill lifecycle hooks (pre/post invocation) | Claude Code only |
| `paths` | Glob patterns for path-scoped activation | Claude Code only |
| `shell` | Default shell for `Bash` calls (`bash` / `powershell`) | Claude Code only |

### Recommendation

If a skill **really needs** Claude-only fields:

1. **Declare it explicitly** in frontmatter:
   ```yaml
   compatibility: "Claude Code only (uses paths-scoped activation)"
   ```
2. **Document the manual fallback** in the body so Copilot/Codex/Gemini users know how to invoke equivalently.
3. **Run `library-audit` Phase 4.5** — it flags skills with `allowed-tools` and other Claude-only fields when they claim portability.

---

## Behavioral notes specific to Claude Code

### Context budget

- Skill descriptions are loaded into context for routing. Claude Code budget: ~1% of context window, fallback 8000 chars.
- Body activates **fully** on trigger and stays in context for the rest of the session — keep ≤ 500 lines.

### Hierarchy of project rules

Claude Code reads files in this order (later overrides earlier):
```
Managed policy   → /Library/Application Support/ClaudeCode/CLAUDE.md (org-wide)
Project          → ./CLAUDE.md or ./.claude/CLAUDE.md
User             → ~/.claude/CLAUDE.md
Local            → ./CLAUDE.local.md  (gitignored)
```
All discovered files are **concatenated**, not overridden. `CLAUDE.local.md` is appended after `CLAUDE.md` in the same directory.

### Imports

Claude Code supports `@path/to/file` imports inside `CLAUDE.md`. Both relative and absolute paths allowed. Max recursion depth: **5 hops**.

This is how the shipped `CLAUDE.md` imports `AGENTS.md` — one-liner that keeps universal rules in a single source of truth.

### Path-scoped rules

Rules can be scoped via YAML frontmatter:
```yaml
---
paths:
  - "src/api/**/*.ts"
  - "src/billing/**/*.ts"
---
```
Rules without a `paths:` field apply unconditionally. This feature is **Claude-only**. For universal path scoping, use **nested `AGENTS.md`** files instead.

### Skill discovery locations

Claude Code looks here (highest precedence first):
| Scope | Path |
|---|---|
| Enterprise | (managed settings path) |
| Personal | `~/.claude/skills/<name>/SKILL.md` |
| Project | `./.claude/skills/<name>/SKILL.md` |
| Plugin | `<plugin-root>/skills/<name>/SKILL.md` |

In monorepos, Claude Code also walks **up** the directory tree from the file being edited and discovers nested `.claude/skills/`.

### Sub-agent dispatching

Sub-agents are dispatched via the `Task` tool. The agent file's `tools:` frontmatter declares its allowed tools (least-privilege).

**One-level nesting only** — a sub-agent cannot dispatch another sub-agent. This is enforced by the runtime.

---

## When NOT to use Claude-specific fields

- Building a skill intended for cross-team / cross-platform adoption → stick to universal fields (`name`, `description`, `compatibility`, `license`).
- Publishing to a marketplace where consumers may use different runtimes → universal only.
- Internal team has standardized on multiple runtimes (e.g. some devs use Copilot, others Claude Code) → universal only.

## When Claude-specific fields are fine

- Internal team is 100% on Claude Code with no plans to switch.
- The optimization is significant (e.g. `model: haiku` for a frequently-called validator saves real money) and the skill is internal.
- You're prototyping — universalize before publishing.
