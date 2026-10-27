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

### MC1 — Permission behavior varies by host

Claude Code can pre-approve the listed tools during skill invocation.
Other tools remain subject to the user's permission settings.
Other hosts may interpret or ignore this field differently.
Review the original permission effect before proposing a portable replacement.
A prose instruction does not enforce a host permission boundary.
See [Claude Code skill permissions](https://code.claude.com/docs/en/skills#pre-approve-tools-for-a-skill).

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

Hosts expose different sub-agent formats and dispatch mechanisms. Skills that delegate via `Task` MUST NOT require that
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
