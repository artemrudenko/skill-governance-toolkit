# Portability Rules — Full Catalog

Loaded by `skill-build-portable` Phase 1. This file defines every transformation rule with detection logic, severity, and rewrite specification.

## Path patterns to substitute (Rule B1)

Common organization-specific paths and their portable substitutes. Extend this table via `PROJECT_STYLE` input.

| Source pattern | Replacement | Reason |
|---|---|---|
| `_audits/` | `out/audits/` | Underscore-prefix is org-specific convention |
| `outputs/` (top-level) | `out/` | Universal naming |
| `materials/raw/` | `out/sources/` | Org-specific knowledge layout |
| `materials/sources-md/` | `out/sources-md/` | Same |
| `delivered/` | `out/delivered/` | Org-specific publication workflow |
| `pipeline/1-incoming/` | `out/incoming/` | Org-specific pipeline naming |
| `pipeline/2-curated/` | `out/curated/` | Same |
| `pipeline/3-synthesis/` | `out/synthesis/` | Same |
| `brain/concepts/` | `out/concepts/` | Org-specific knowledge layout |
| `brain/lessons/` | `out/lessons/` | Same |
| `brain/playbooks/` | `out/playbooks/` | Same |
| `planning/sessions/` | `out/sessions/` | Org-specific |
| `planning/research/` | `out/research/` | Same |

## Frontmatter field rules

### F1 — `allowed-tools:` removal (🔴 BLOCKER)

```yaml
# REMOVE THIS:
allowed-tools:
  - Read
  - Grep
  - Bash
```

**Why:** Claude Code treats this as a **hard whitelist** — blocks all tools not listed. Copilot / Cursor / Codex **silently ignore** it. A skill with `[Read, Grep]` allowed will behave consistently on Claude but have full tool access on Copilot. Silent divergence is the worst kind of bug.

**Transformation:** remove the field. If the original intent was security / scope-limiting, add a `## Hard rules` paragraph in the body:

> «**Tool restrictions (informational):** this skill operates as a read-only auditor. Even though there is no runtime enforcement, do not invoke `Write`, `Edit`, or `Bash`-with-mutations in this skill.»

### F2 — `type:`, `status:`, `last_updated:`, `last_verified:` removal (🟡)

These fields are not part of the agentskills.io specification. Some hosts ignore them; some accept them but with undefined semantics. They migrate **out** of SKILL.md frontmatter.

If the skill genuinely needs tracking metadata, use a sidecar file (`{skill_dir}/.metadata.yml`).

### F3 — `paths:` removal (🟡)

This is Claude-Code-only path-scoped activation. Other runtimes ignore it.

**Transformation:** remove the field. If path-scope is essential, document the constraint in the body as «**Activation scope:** this skill is intended for files matching `src/**/*.ts`» — users on other runtimes can manually scope their invocation.

For universal path scoping, use **nested `AGENTS.md`** files at the directory boundary instead.

### F4 — Other Claude-only fields (🟡 unless `KEEP_CLAUDE_FALLBACK=true`)

Fields to flag for removal (or preservation as comments if `KEEP_CLAUDE_FALLBACK=true`):
- `hooks:` — skill lifecycle hooks (Claude Code only)
- `model:` — per-skill model override (Claude Code only)
- `effort:` — reasoning effort tier (Claude Code only)
- `context: fork` — subagent context (Claude Code only)
- `disable-model-invocation:` — manual-only flag (Claude Code only)
- `user-invocable:` — slash-menu visibility (Claude Code only)
- `argument-hint:`, `arguments:` — autocomplete (Claude Code only)
- `when_to_use:` — supplementary triggers (Claude Code only; merge content into `description:`)
- `shell:` — default shell (Claude Code only)

### F5 — Missing `description:` (🔴 STOP)

A skill without a description cannot be activated by any runtime. This is unrecoverable — stop and report the source is malformed.

### F6 — Description length (🟡)

| Length (chars) | Action |
|---|---|
| < 80 | Flag — too short; manual expansion needed |
| 80 – 99 | Note — acceptable but lean |
| 100 – 400 | ✓ Sweet spot |
| 400 – 600 | ✓ Acceptable, slightly verbose |
| 600 – 1024 | Flag — over sweet spot |
| > 1024 | 🔴 Flag — exceeds agentskills.io hard limit; manual truncation required |

**Why no auto-rewrite:** description is mission-critical for activation. Truncation can remove a key trigger phrase. User must rewrite.

### F7 — Missing `compatibility:` field (🟡)

**Transformation:** add
```yaml
compatibility: "<TARGET_RUNTIMES joined by · >"
```

Example: `compatibility: "Claude Code · GitHub Copilot · Cursor v2.2+ · OpenAI Codex CLI · Google Gemini CLI"`

If `TARGET_RUNTIMES` is a subset, list only the included runtimes.

## Body rules

### B1 — Hardcoded org-specific paths (🔴)

Apply the substitution table at the top of this file. Apply globally (every occurrence in the body).

After substitution, scan again for any **inline path** that looks org-specific (single-token prefixes followed by `/`). Surface these as residual concerns for user review.

### B2 — Organization-specific names (🟡)

If `PROJECT_STYLE` declares org keywords (`acme`, `example-org`, `umbrella-corp`), grep body for these and replace with `{your-org}` placeholder.

### B3 — ADR / RFC / internal doc references (🟡)

Grep for patterns:
- `ADR-\d+`
- `RFC-\d+`
- `\[\[.+\]\]` (wiki-style internal links)
- relative paths to `docs/adr/`, `docs/rfc/`, `docs/specs/`

**Transformation:** strip the reference; preserve the *idea*. Example:

```diff
- Apply 3 atomic passes per `references/handoff-spec.md` (ADR-008 §3 compliance).
+ Apply 3 atomic passes per `references/handoff-spec.md`.

- See [[concepts/skill-authoring]] for full guidelines.
+ See the SKILL.md authoring guidelines.
```

### B4 — Tool-specific command syntax in body (🟡)

If the body says «run `claude /skill foo`», that breaks on other runtimes. Generalize to «invoke skill `foo`».

Common patterns to neutralize:
- `claude` CLI invocations → «the host runtime»
- `gh copilot` → «the host runtime»
- `codex `, `gemini ` → same
- Specific keyboard shortcuts (`⌘K`, `Ctrl+L`) → remove

### B5 — Per-skill `rules/{tool}.md` (🟡)

If `{skill_dir}/rules/claude.md`, `{skill_dir}/rules/copilot.md`, etc. exist:

**Output behavior:**
1. Do NOT delete those files (this skill does not delete files).
2. List their contents in the «Residual concerns» section of the report.
3. Recommend: merge tool-mapping logic into the **repo-level** `references/{tool}-tools.md` (one file per tool, shared by all skills).
4. Recommend: remove the per-skill `rules/` directory after merge.

### B6 — `Task` orchestration without Gemini fallback (🟡)

If body uses `Task` tool for sub-agent dispatch, insert a fallback note:

```markdown
> **Gemini CLI users:** Gemini does not support sub-agents. Inline the agent's instructions
> into this skill body manually, or split into sequential skill invocations.
```

Place this note near the first occurrence of `Task` in the body.

### B7 — Portability claims without evidence (🟡)

Grep for claims like «works everywhere», «portable across tools», «universal».

**Transformation:** replace with a reference to the `compatibility:` field:

```diff
- This skill works everywhere — Claude, Copilot, Cursor, all of them.
+ See the `compatibility:` field above for supported runtimes.
```

## Structure rules

### S1 — Body > 500 lines (🟡)

Surface as a residual concern. Do NOT auto-split — splitting requires semantic decisions only the skill author can make. Suggest: «extract Phase N detail → `references/{topic}.md`».

### S2 — Missing canonical `## When to use` (🟡)

If body has no `## When to use` section with the four canonical sub-sections (`Always` / `ESPECIALLY when` / `Skip` / `Don't skip when`), insert a skeleton:

```markdown
## When to use

**Always:**
<!-- Fill in trigger phrases and primary use cases. -->

**ESPECIALLY when:**
<!-- Fill in high-impact cases that prevent rationalization-away. -->

**Skip / Don't use for:**
<!-- Fill in neighbor-skill disambiguation. -->

**Don't skip when:**
<!-- Fill in counter-rationalization for skill underuse. -->
```

Insert above the first `## Phase 0` or `## Required Inputs` section. If neither exists, insert immediately after the first H1 + Purpose block.

### S3 — Missing `## Predecessor` / `## Successor` (🟢 informational)

Not a portability issue, but good hygiene. Note in residual concerns. Do not insert skeletons (these require knowledge of the skill ecosystem the author hasn't yet documented).

## Output diff format

Diff uses unified format with these conventions:
- Frontmatter changes shown first.
- Body changes shown grouped by section, in document order.
- Long unchanged blocks collapsed as `[unchanged]`.
- Path substitutions called out explicitly with both source and target.

## Residual concerns severity

| Severity | Meaning | Action |
|---|---|---|
| 🔴 | Source is unfixable by this skill | Stop or write with warning |
| 🟡 | Recommended manual review | Always include in residual concerns |
| 🟢 | Informational | Optional inclusion |
