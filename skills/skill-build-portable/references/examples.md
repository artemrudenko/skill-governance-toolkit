# Examples — `skill-build-portable` in action

Three canonical scenarios. Each shows source excerpt → resulting diff report.

---

## Example 1 — Claude-only skill with `allowed-tools` and hardcoded paths

**Source `SKILL.md` (excerpt):**
```yaml
---
name: my-audit
description: Audit something.
type: skill
status: active
allowed-tools:
  - Read
  - Grep
paths:
  - "src/**/*.ts"
---

Audit logic. Output → `_audits/internal/my-audit-{date}.md`.
```

**Output (`OUTPUT_MODE=preview`):**
```
# Portable Skill Build — my-audit

Transformations applied (5):
  🔴 F1 · frontmatter:5 · remove allowed-tools (non-portable hard whitelist)
  🟡 F2 · frontmatter:3 · remove type:, status: (not in agentskills.io spec)
  🟡 F3 · frontmatter:8 · remove paths: (Claude-only; document in body if path-scope matters)
  🔴 B1 · body:line 1 · replace _audits/internal/ → out/audits/internal/
  🟡 F7 · add compatibility: field

Description too short (16 chars). Required ≥ 80 to score well on D8 (discoverability).
Manual expansion suggested — this skill did not auto-rewrite descriptions.
```

---

## Example 2 — Already-portable skill (no-op)

**Source has:** `name`, `description`, `compatibility`, `license`, body with universal paths, no `allowed-tools`.

**Output:**
```
# Portable Skill Build — skill-find

Transformations applied (0):
  ✓ No violations detected — source is already portable.

Skill not written (no changes to apply). Re-run `skill-evaluate` to verify quality.
```

This is also the **idempotency proof**: a second run on an already-transformed file
must always produce zero changes.

---

## Example 3 — `KEEP_CLAUDE_FALLBACK=true` preserves Claude-only optimizations

**Source:**
```yaml
---
name: research-build
description: ...
model: opus
effort: high
context: fork
---
```

**Output frontmatter:**
```yaml
---
# claude-only: the following fields are honored only by Claude Code.
# Other runtimes will ignore them silently.
#   model: opus
#   effort: high
#   context: fork
name: research-build
description: ...
compatibility: "Claude Code · GitHub Copilot · Cursor v2.2+ · OpenAI Codex CLI · Google Gemini CLI"
license: MIT
---
```

The comment block sits *inside* the frontmatter (YAML comments after the opening
`---` are legal) — placing it before the opening `---` would make the frontmatter
undetectable to parsers that require `---` on line 1.

This way the optimization is documented (a Claude Code user can re-enable it by
uncommenting) without breaking other runtimes that would otherwise silently
ignore the fields.
