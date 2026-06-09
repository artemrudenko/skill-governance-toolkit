# Phase 3 — Naming Convention Spec

This spec is loaded by `library-audit` Phase 3 (naming) and Phase 4 (portability tag coverage).

## Closed-vocabulary action verbs

A skill name must be of the form `{entity}-{action}[-{qualifier}]`, where `{action}` is drawn from the **closed vocabulary**:

| Verb | Meaning |
|---|---|
| `find` | Discover or search (read-only) |
| `audit` | Validate / detect violations (read-only, never edits) |
| `evaluate` | Score against a rubric |
| `compare` | Side-by-side analysis of two artifacts |
| `build` | Create a new artifact from inputs |
| `extend` | Add to an existing artifact in place |
| `frame` | Define scope or constraints before execution |
| `ingest` | Import content from external source into structured store |
| `mark` | Apply state transition (e.g. mark-delivered, mark-complete) |
| `plan` | Produce an execution plan to be reviewed before action |
| `query` | Lookup against a structured knowledge store |
| `init` | Bootstrap / one-time setup with environment detection (gateway skills only) |

Skills using verbs outside this set (e.g. `skill-fix`, `skill-improve`, `skill-handle`) → **🔴 N1 violation**. The fix is either to rename (preferred) or to argue for adding a new verb to the closed vocabulary (rare; requires explicit deliberation).

## Pattern

```
{entity}-{action}[-{qualifier}]
```

The cap is **≤ 2 words after the entity** (action + optional qualifier) — enforced by N2's regex, which allows at most 2 hyphens.

Examples:
- `skill-find` — entity `skill`, action `find` ✓
- `library-audit` — entity `library`, action `audit` ✓ (audits the collection, not one skill)
- `research-build` — entity `research`, action `build` ✓
- `presentation-extend` — entity `presentation`, action `extend` ✓
- `skill-evaluate` — entity `skill`, action `evaluate` ✓
- `wiki-audit` — entity `wiki`, action `audit` ✓ (entity prefix disambiguates from `library-audit`)

Anti-examples:
- `audit-skills` — verb first → 🔴 N2 violation
- `skill_audit` — underscore → 🔴 N3 violation
- `SkillAudit` — camelCase → 🔴 N3 violation
- `library-audit-detail-mode-v2` — too many parts (> 2 hyphens) → 🔴 N2 violation
- `presentation-restructure-aggressively` — passes N2's shape but words are overlong → 🟡 N4 advisory
- `acme-library-audit` — organization prefix → 🔴 N5 violation (skills should be vendor-neutral)

## Five atomic checks (Phase 3)

| # | Check | Detection | Severity |
|---|---|---|---|
| **N1** | Verb is in closed vocabulary | Parse `name` → extract action part → check membership | 🔴 |
| **N2** | Pattern `{entity}-{action}[-{qualifier}]` — 2-3 parts (≤ 2 words after entity), hyphens only | Regex `^[a-z][a-z0-9]+(-[a-z0-9]+){1,2}$` | 🔴 |
| **N3** | kebab-case only | Regex `^[a-z][a-z0-9-]*$` | 🔴 |
| **N4** | Length advisory for names that PASS N2's shape | Any single word > 12 chars OR total name > 30 chars | 🟡 |
| **N5** | No organization-specific prefix | Reject names embedding org/brand identifiers (case-by-case) | 🔴 |

Any 🔴 violation in a new SKILL.md blocks merge.

## Portability tag (Phase 4)

Skills should declare their cross-tool portability in frontmatter. Two acceptable formats:

**Format A — `compatibility:` field** (lists supported runtimes verbatim):

```yaml
compatibility: "Claude Code · GitHub Copilot · Cursor v2.2+ · OpenAI Codex CLI · Google Gemini CLI"
```

**Format B — `portability:` enum** (declares portability tier):

```yaml
portability: portable    # works everywhere with no runtime-specific tweaks
# or
portability: hybrid      # works everywhere but has runtime-specific fast paths
# or
portability: project-local   # tied to one runtime / one organization's infra
```

| # | Check | Severity |
|---|---|---|
| **P1** | One of `compatibility:` or `portability:` is present | 🟡 |
| **P2** | If `portability:`, value is in `{portable, hybrid, project-local}` | 🟡 |

P-class findings are warnings, not blockers — but a library where most skills lack portability tags is itself a signal worth surfacing.

## Adding a new verb

If a genuinely new action concept emerges (not a synonym of an existing verb), propose:

1. The verb name (single English word, lowercase).
2. A one-sentence definition.
3. At least two real skill names that would use it.
4. Why no existing verb suffices.

Update this file, then re-run `library-audit` to confirm no false positives.
