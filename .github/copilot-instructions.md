# GitHub Copilot — Project Instructions

> The primary project instructions live in [`AGENTS.md`](../AGENTS.md) at repository root. Copilot reads `AGENTS.md` natively (since 2025-08-28). This file exists only for Copilot-specific extensions and as a fallback for older Copilot versions.

## Primary Instructions

Read [`AGENTS.md`](../AGENTS.md) at the repository root. Treat its rules as authoritative.

## Copilot-Specific Notes

- **Tool-name mapping:** When a skill references Claude Code tool names (`Read`, `Edit`, `Bash`, `Task`, etc.), translate them using [`references/copilot-tools.md`](../references/copilot-tools.md).
- **Skill discovery:** Skills are in `skills/{name}/SKILL.md`. Each skill's `description` field declares trigger phrases.
- **Sub-agents:** Sub-agents live in `agents/{name}.md` and are dispatched via the `agent` tool (Copilot's equivalent of Claude Code's `Task`).
- **Slash commands:** `/integration-init` activates the `integration-init` skill (the slash command keeps its `/integration-init` name to avoid collision with Claude Code's built-in `/init`). All other behavior is skill-triggered via natural-language phrases — see each `SKILL.md` `description` field.

## Path-Scoped Overrides

If you need to apply different rules to a subdirectory, drop a nested `AGENTS.md` there — Copilot reads the closest one in the directory tree (root file remains the base).
