---
name: skill-build-portable
description: |
  Transforms a non-universal SKILL.md into a universal one that runs across Claude Code, Copilot,
  Cursor, Codex, and Gemini without per-tool forking. Audits the source skill for portability
  violations, proposes transformations, generates the portable version, and shows a side-by-side
  diff before writing.
  Use when: «make this skill portable», «universalize this skill», «convert to universal»,
  «portabilize», «refactor for cross-tool», «migrate skill to standard»,
  «strip Claude-only fields», «remove allowed-tools».
  Output modes: preview (no write) / new-file / in-place. Preserves functional logic.
compatibility: "Claude Code · GitHub Copilot · Cursor v2.2+ · OpenAI Codex CLI · Google Gemini CLI"
license: MIT
metainfo:
  category: [governance]
  tier: stable
  owner: artsiom
  added: "2026-05-23"
---

# Skill Build Portable

> **Skill type:** MUTATING — writes to SKILL.md files in `new-file` and `in-place` OUTPUT_MODE. Preview mode is detect-only. Always produces diff report before write.

**Purpose:** convert an existing `SKILL.md` (often Claude-Code-only or org-specific) into a portable skill that conforms to the universal AGENTS.md + Anthropic Agent Skills standard. The functional logic of the skill is preserved; only structure, frontmatter, and platform-coupled constructs are transformed.

**Runtime notes:** Claude/Copilot/Cursor/Codex — normal workflow. Gemini — no sub-agent dispatch (this skill doesn't use Task).

This skill is the **counterpart** of:
- `library-audit` — *detects* violations across a library (read-only, library-wide).
- `skill-evaluate` — *scores* one skill against 9 quality dimensions, including safety (read-mostly, single skill).
- `skill-build-portable` — *mutates* one skill into a portable form (writes, single skill).

## When to use

**Always:**
- User asks: «universalize this skill», «make it portable», «convert to portable form».
- After `library-audit` flagged a skill with 🔴 MC1 / MC2 / MC3 / MC4 findings.
- Before publishing an internal skill to a shared / corporate library.
- When migrating from a Claude-Code-only setup to a multi-runtime team.

**ESPECIALLY when:**
- Source skill has `allowed-tools:` in frontmatter.
- Source skill has a `rules/{tool}.md` subdirectory.
- Source skill body references org-specific paths (`/_audits/`, `/outputs/`, `materials/raw/`, organization names).
- Source skill uses Claude-only frontmatter fields (`paths:`, `hooks:`, `model:`, `effort:`, `context: fork`, `disable-model-invocation`).

**Skip / Don't use for:**
- The skill is already portable — run `library-audit` first to confirm; this skill refuses to write when source has zero violations.
- User wants only to *check* portability, not transform — use `library-audit` or `skill-evaluate` instead.
- Source uses Claude-only features the user *wants* to keep — choose `KEEP_CLAUDE_FALLBACK=true` to preserve them as documented Claude-only comments.

**Don't skip when:**
- «It's a small skill, conversion is obvious» — automated transformation surfaces edge cases users miss (e.g. forgotten Claude-only frontmatter fields, hardcoded paths).
- «I'll just rewrite by hand» — manual rewrites usually keep semantic logic but introduce subtle frontmatter drift. Run this skill, then code-review the diff.

## Predecessor

**Required upstream:** none — entry-point skill invoked directly by user phrase.
**Optional upstream:** `library-audit` (if violations were detected library-wide and user wants to fix one).

## Successor

**Default downstream:** terminal — produces transformed SKILL.md + diff report.
**Recommended follow-up:** `skill-evaluate` on the output to verify the conversion didn't degrade quality.

---

## Required inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `SKILL_TARGET` | string | required | Skill name (e.g. `research-build`) or full path to `SKILL.md` |
| `OUTPUT_MODE` | enum: `preview` / `new-file` / `in-place` | `preview` | `preview` — print diff only, no write; `new-file` — write to `{source_dir}/SKILL.portable.md` next to source; `in-place` — overwrite source (creates `.bak`) |
| `TARGET_RUNTIMES` | list | `[claude, copilot, cursor, codex, gemini]` | Which runtimes the output should support. If a subset (e.g. `[claude, copilot]`), some restrictions relax |
| `KEEP_CLAUDE_FALLBACK` | boolean | `false` | If `true`, Claude-only frontmatter fields are preserved as comments with explanation rather than removed |
| `FORCE` | boolean | `false` | If true, skip the final confirmation gate after previewing the diff. Only applies to `OUTPUT_MODE=in-place`; preview is still mandatory. |
| `PROJECT_STYLE` | path | none | Optional `.portable-style.md` declaring project-specific replacement rules (e.g. «replace `/internal-audits/` with `out/audits/`») |

---

## Workflow

Six explicit phases. The skill **never** writes to disk before Phase 3 has shown the diff
and Phase 4 has received user confirmation (in `in-place` mode, unless `FORCE=true`).
Phase 5 re-audits the output to prove portability.

### Phase 0 — Locate and read source

1. If `SKILL_TARGET` is a name (no path separator), search `./skills/{name}/SKILL.md`, `./.{tool}/skills/{name}/SKILL.md`, `{name}/SKILL.md`.
2. If `SKILL_TARGET` is a path: read directly. Record total line count.
3. Note adjacent directories (`references/`, `rules/`, `scripts/`, `assets/`) for Phase 1.
4. If source not found → stop with error. If no frontmatter → stop «not a valid SKILL.md».

### Phase 1 — Analyze (audit)

Run the full rule catalog — see [`references/audit-rules.md`](references/audit-rules.md) (F1–F7 frontmatter · B1–B7 body · S1–S3 structure). Path-pattern catalog lives in [`references/portability-rules.md`](references/portability-rules.md). For each rule, record `{location, violation, severity, transformation}`.

### Phase 2 — Plan transformations

Compose an ordered transformation list (one entry per violation), e.g. `[F1 / frontmatter:line 3] remove allowed-tools` · `[B1 / body:line 47] replace _audits/legacy-audit/ → out/legacy-audit/` · `[F7] add compatibility:` · etc. See [`references/examples.md`](references/examples.md) for full sample plans.

If the list contains any 🔴 **and** `OUTPUT_MODE=in-place`, mark the write as requiring a final confirmation gate unless `FORCE=true`. Do not prompt in this phase; Phase 3 must show the diff first.

### Phase 3 — Preview diff (always shown before any write)

Apply transformations in memory and render the full diff report — see [`references/output-template.md`](references/output-template.md) for the canonical skeleton (header · transformations applied · unified diff · residual concerns · post-transform checklist).

Transformation order: frontmatter rewrite (F1–F7) → body substitutions (B1–B4, B6–B7) → adjacent directory notes (B5) → activation-scope advisory (S2 — advisory note only, never inserts a body section). **Never** touch phase content, decision logic, or output formats — semantic preservation is mandatory.

If `OUTPUT_MODE=preview` → **stop here**, no file written.

### Phase 4 — Confirm + write

If `OUTPUT_MODE=in-place`, `FORCE=false`, and at least one 🔴 transformation is
queued, run the single clarification confirmation gate now, after the user has
seen the diff (this matches the Hard-rules clarification policy). Use `AskUserQuestion`
only on hosts that provide it; otherwise ask plainly in chat. Display the target
path, backup path, and transformation count. If the user declines, stop with no write.

- `OUTPUT_MODE=new-file` → write to `{source_dir}/SKILL.portable.md`.
- `OUTPUT_MODE=in-place` → create `{source}.bak`, then overwrite source.

Refuse to write if the transformation list is empty («already portable»).

### Phase 5 — Verify portability (re-audit the output)

Re-run Phase 1 on the freshly written file. Expected result: **zero findings other
than documented flag-only rules (F6 / B5 / S1), which must reappear under «Residual
concerns»**. Any other remaining 🔴/🟡 → flag in the diff report's «Residual concerns»
section and instruct the user to re-run or fix manually. This phase is what makes the skill **idempotent**:
running it twice on the same file must produce zero changes the second time.

---

## Hard rules

- ❌ **Never modify functional logic** — phase headers, decision tables, output formats, hard rules, examples must be preserved verbatim (modulo path substitutions).
- ❌ **Never change task semantics** — only structure / frontmatter / path substitutions. If a transformation would alter what the skill *does*, refuse and flag for manual review.
- ❌ Never auto-rewrite the `description` field — it is mission-critical for skill activation; surface length issues but require user to fix.
- ❌ Never auto-truncate or summarize the body to make it «more portable» — that's a different operation (skill quality refactor, not portability conversion).
- ❌ Never write to disk if `OUTPUT_MODE = preview`.
- ✅ Always produce a diff report — even when `OUTPUT_MODE = in-place`, show what changed before writing.
- ✅ Always create `.bak` before in-place writes.
- ✅ Always emit «Residual concerns» section — there are violations this skill **cannot** auto-fix and the user must review.
- ✅ **Idempotency:** running twice on the same skill must produce zero changes on second run. Phase 5 verifies this.
- ✅ **Post-transform checklist** (verify ALL after write): no `allowed-tools`, no Claude-only frontmatter, `compatibility:` present, tool names canonical, sequential fallback note where `Task` used, no org-specific paths.
- ✅ Resumable — checkpoint at P1, P2, P3 lets the user re-run after a crash without re-auditing or re-generating.
- ✅ If source has zero violations, refuse to write — report «already portable».
- ✅ **Clarification policy:** permitted ONLY as a single confirmation gate in Phase 4, after diff preview, when 🔴 transformations are queued AND `OUTPUT_MODE=in-place` AND `FORCE=false`. No other phase may prompt the user.

---

## State persistence (resumable runs)

This skill mutates source files when `OUTPUT_MODE=new-file|in-place`. Checkpointing
makes mid-transform crashes safe — audit findings and planned transformations are
persisted before any write happens.

| Phase | Checkpoint? | What is stored |
|---|---|---|
| P0 — locate and read source | no (cheap) | — |
| P1 — analyze | yes | all violations + transformations planned |
| P2 — plan transformations | yes | ordered transformation list |
| P3 — preview diff | yes (before write) | full target content as string + target path |
| P4 — write | no (terminal write step) | — |
| P5 — verify portability | no (read-only re-audit) | — |

- Default `RESUME=auto` — single-skill operation; resume selection is non-interactive. The only allowed prompt is the Phase 4 in-place confirmation gate.
- State location: `${CWD}/.skill-state/skill-build-portable/run-{utc-timestamp}.json`.
- The `.bak` from the previous successful write and the checkpoint JSON together let the user roll back in-place writes safely.

---

## References

- [`references/audit-rules.md`](references/audit-rules.md) — full F1–F7 / B1–B7 / S1–S3 catalog (loaded in Phase 1).
- [`references/portability-rules.md`](references/portability-rules.md) — path-pattern catalog and runtime-compatibility matrix.
- [`references/output-template.md`](references/output-template.md) — diff-report skeleton, residual-concerns templates, post-transform checklist.
- [`references/examples.md`](references/examples.md) — three canonical scenarios (Claude-only skill · already-portable no-op · `KEEP_CLAUDE_FALLBACK=true`).

---

## What this skill does NOT do

- **Quality scoring** — that's `skill-evaluate`. Run it after this skill to verify quality didn't regress.
- **Library-wide audit** — that's `library-audit`. Run it before this skill to identify candidates.
- **Renaming a skill** — file rename + reference updates are out of scope; user does that manually if needed.
- **Refactoring overlong skills** — extracting body into `references/` is a separate concern handled by `skill-evaluate` Phase 3.
- **Removing skill content** — only structural / portability transformations; semantic content is sacred.
- **Changing task semantics** — if a transformation would alter what the skill *does* (rules, decisions, outputs), refuse and flag for manual review.
