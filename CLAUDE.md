@AGENTS.md

## Claude Code specifics

This project's rules live in `AGENTS.md` (single source of truth). The line above imports that file so Claude Code reads the same content as Copilot, Cursor, Codex, and Gemini.

If you need to add **Claude-Code-only** behavior (e.g. `paths:` frontmatter, hooks, subagent fork context), add it below this section — keep `AGENTS.md` portable.

### Skill activation hints (Claude Code only)

- Skills in `skills/` are auto-discovered from `SKILL.md` frontmatter.
- Trigger phrases for skill activation are in each skill's `description` field.
- To force-invoke a skill manually, use the `Skill` tool with the skill's `name`.
