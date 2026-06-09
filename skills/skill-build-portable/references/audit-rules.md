# Audit Rules — Phase 1 Detection Catalog

Full rule catalog used by `skill-build-portable` Phase 1. For each rule the skill records
`{location, violation, severity, transformation}` and feeds it into the Phase 2 plan.

Severity legend: 🔴 blocker (must apply) · 🟡 warning (recommended) · 🟢 informational.

---

## Frontmatter audit (F-rules)

| Rule | Detection | Severity | Transformation |
|---|---|---|---|
| **F1** Forbidden `allowed-tools:` | grep frontmatter | 🔴 | Remove the field. Move enumeration to body as advisory comment under «Hard rules» |
| **F2** Forbidden `type:`, `status:`, `last_updated:`, `last_verified:` | grep frontmatter | 🟡 | Remove (not part of agentskills.io spec) |
| **F3** Claude-only `paths:` | grep frontmatter | 🟡 | Remove; convert to runtime check in body, or split skill by path |
| **F4** Claude-only `hooks:`, `model:`, `effort:`, `context: fork`, `disable-model-invocation`, `user-invocable` | grep frontmatter | 🟡 if `KEEP_CLAUDE_FALLBACK=false` else preserved as comment | Remove or comment-out |
| **F5** Missing `description:` | grep frontmatter | 🔴 | STOP — cannot generate without source description |
| **F6** Description < 80 or > 1024 chars | char count | 🟡 | Flag for user attention; do not auto-rewrite |
| **F7** Missing `compatibility:` field | grep frontmatter | 🟡 | Add: `compatibility: "{TARGET_RUNTIMES list}"` |

## Body audit (B-rules)

| Rule | Detection | Severity | Transformation |
|---|---|---|---|
| **B1** Hardcoded org-specific paths | grep for known patterns (see `portability-rules.md` §Path-patterns) | 🔴 | Replace with `{outputs}/`, `out/`, or `{org}/` placeholder |
| **B2** Organization-specific names in body | grep for org keywords supplied in `PROJECT_STYLE` | 🟡 | Replace with `{your-org}` placeholder |
| **B3** ADR / internal doc references | grep `ADR-\d+`, `RFC-\d+`, links to `/docs/adr/` etc. | 🟡 | Strip references; preserve the *idea* but generalize wording |
| **B4** Tool-specific command syntax baked into body | grep `claude-cli`, `gh copilot`, `codex `, etc. | 🟡 | Generalize to «invoke this skill» or document each command per runtime |
| **B5** Per-skill `rules/{tool}.md` directory exists | `ls {skill_dir}/rules/` | 🟡 | Remove subdirectory; merge tool mappings into repo-level `references/{tool}-tools.md` |
| **B6** Body references `Task` / sub-agent dispatch without sequential fallback | grep body | 🟡 | Add optional-dispatch language plus a sequential fallback with the same output schema |
| **B7** Body claims «works everywhere» without supporting evidence | grep for portability claims | 🟡 | Replace with measured `compatibility:` field |

## Structure audit (S-rules)

| Rule | Detection | Severity | Transformation |
|---|---|---|---|
| **S1** Body > 500 lines | line count | 🟡 | Suggest splitting; do not auto-split |
| **S2** `description` lacks activation/exclusion scope | description inspection | 🟢 advisory | Suggest strengthening the **description** (Use-when / Not-for clauses); do NOT insert a body `## When to use` — it is optional (rules 0.5.0) |
| **S3** Missing `## Predecessor` / `## Successor` | header search | 🟢 informational | Suggest adding handoff documentation |

---

## How the rules feed Phase 2

Each violation becomes one entry in the ordered transformation list:

```
[<rule_id> / <location>] <action description>
```

Severity dictates Phase 2 confirmation gating:
- **Any 🔴 + `OUTPUT_MODE=in-place` + `FORCE=false`** → clarification confirmation after the diff preview (the only prompt in this skill).
- **Only 🟡 / 🟢** → proceed without prompt; warnings appear in the diff report.
