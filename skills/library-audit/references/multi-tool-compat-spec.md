# Phase 4.5 — Multi-tool Compatibility Spec

Loaded by `library-audit` Phase 4.5. Validates anti-patterns that break
SKILL.md portability across Claude Code / GitHub Copilot / Cursor / OpenAI
Codex CLI / Google Gemini CLI.

## Atomic checks

| # | Check | Detection | Severity |
|---|---|---|---|
| **MC1** | `allowed-tools:` field is **absent** from frontmatter | grep `^allowed-tools:` | 🔴 if claimed portable; 🟡 if hybrid |
| **MC2** | No per-skill `rules/{tool}.md` files | `ls {skill_dir}/rules/{claude,copilot,gemini}.md` | 🟡 — should use repo-level `references/{tool}-tools.md` instead |
| **MC3** | Claimed portability matches actual content | If MC1 or MC2 failed but skill declares full portability → contradiction | 🔴 |
| **MC4** | Optional sub-agent fallback | If skill body uses `Task` / sub-agent dispatch but no sequential fallback with equivalent output contract | 🟡 |

## Rationale

### MC1 — Why `allowed-tools:` is poison for portability

Claude Code treats `allowed-tools` as a **hard whitelist** — any tool not
in the list is blocked at runtime. Copilot / Cursor / Codex **silently
ignore** the field. A skill that lists `allowed-tools: [Read, Grep]` will:

- Work on Claude Code (with only Read + Grep available).
- Run on Copilot / Cursor / Codex with **all** tools enabled — silently
  inconsistent semantics across runtimes.
- Break on Claude Code if it actually needs `Bash` later — the whitelist
  forbids it.

The portable solution is to omit `allowed-tools:` entirely and let the host
runtime enforce its own policy. Document required capabilities in prose
inside the body if needed.

### MC2 — Why per-skill `rules/{tool}.md` files cause drift

Per-skill `rules/{tool}.md` duplicates tool-name mappings across every
skill. With 10 skills × 3 runtimes (Claude / Copilot / Gemini) that's 30
files maintaining the same tool-name table. Renaming one tool means
editing 30 files; one update is missed and the library drifts silently.

The portable solution is ONE repo-level `references/{tool}-tools.md`
loaded once at session start. All skills reference the same mapping.

### MC3 — Portability claim vs actual content

If a skill's frontmatter declares `portability: portable` or lists every
runtime in `compatibility:` but the body contains MC1/MC2 violations, the
claim is false. Either fix the body or downgrade the claim to `hybrid` /
`project-local`. Silent false claims mislead downstream tools that filter
by compatibility.

### MC4 — Sub-agent dispatch must be optional

Gemini CLI does not support sub-agents, and some other hosts expose different
dispatch mechanisms. Skills that delegate via `Task` MUST NOT require that
path for correctness.

Required portable contract:

1. Mark the sub-agent dispatch as optional.
2. Document a sequential fallback («inline the agent instructions and produce
   the same finding schema»).
3. Keep the output contract equivalent enough that callers can consume either
   path.

Skills without either signal will silently fail on Gemini.

## Severity rules

- 🔴 if the skill's frontmatter declares it portable across all runtimes
  but the body violates MC1/MC2.
- 🟡 if `Task` / sub-agent dispatch appears without a documented fallback.
- 🟡 if the skill is hybrid or single-runtime and the violation is
  detectable but consistent with the declared scope.
