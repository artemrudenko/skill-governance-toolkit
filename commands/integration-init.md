---
name: integration-init
description: Bootstrap the toolkit's optional integrations (code-review-graph, repomix, serena, plus the Claude-only secret-guard hook) — pick and install. Renamed from /init to avoid collision with Claude Code's built-in /init (which initializes CLAUDE.md from codebase analysis — a different operation).
argument-hint: "[--advise-only] [--with crg|repomix|serena|secret-guard|all]"
---

Activate the `integration-init` skill.

The skill will:
1. Detect environment (Python, npm, current runtime, already-installed integrations).
2. Ask which optional integrations to install.
3. For each selected, ask sub-config questions (variant, mode, build strategy).
4. Run installers or print commands (in `--advise-only` mode).
5. Verify each install, then inject per-integration documentation into `AGENTS.md` and `agents/code-reviewer.md` — only for tools actually installed.
6. Report next steps.

Note: `--with all` expands to the three cross-host tools (`crg,repomix,serena`) and EXCLUDES `secret-guard` (Claude-hook-specific — opt in by name only).

For non-interactive use, see `scripts/init.sh --help`.
