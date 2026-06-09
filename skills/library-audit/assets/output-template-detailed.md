# library-audit — output template (`VERBOSITY=detailed`)

Canonical specification of every section the report contains in detailed
mode. Body of `SKILL.md` references this file from Phase 6; the actual
layout lives here so the SKILL body stays under the token-budget threshold.

Three layers — Roll-up, Per-category 4-part blocks, Recommendations. Each
section below shows the exact format and a worked example.

---

## Frontmatter of the generated report

```yaml
type: audit-report
audit_dimensions: [handoff, budget, naming, portability, multi-tool-compat, security, metainfo]
generated: {YYYY-MM-DD}
library_size: {N skills}
agents_scanned: {N agents}
overall_verdict: 🟢|🟡|🔴
verbosity: {terse|standard|detailed}
```

---

## Layer 1 — Category roll-up

Always present (every verbosity). One row per category + Overall row at bottom.

```
| Category | 🟢 OK | 🟡 Warn | 🔴 Fail | Verdict | One-line why |
|---|---|---|---|---|---|
| Handoff contracts (P1) | 5 | 1 | 0 | 🟢 healthy | One asymmetric handoff between skill-find ↔ skill-evaluate; non-blocking. |
| Token budget (P2) | 3 | 2 | 1 | 🔴 action required | integration-init body 612 lines (threshold 600); push examples to references/. |
| Naming convention (P3) | 6 | 0 | 0 | 🟢 healthy | All 6 names match closed vocabulary. |
| Portability tag (P4) | 6 | 0 | 0 | 🟢 healthy | All carry `compatibility:`. |
| Multi-tool compat (P4.5) | 5 | 1 | 0 | 🟢 healthy | skill-build-portable Task call without sequential fallback note (line 132). |
| Security (P5) | 6 | 0 | 0 | 🟢 healthy | No secrets, dangerous shell, or credential-path reads. |
| Metainfo coverage (P5.5) | 5 | 0 | 1 | 🔴 action required | 1 skill missing the `metainfo` block (M1) — excluded from default install. |
| **Overall** | — | — | — | **🔴** | Budget + metainfo categories require action. |
```

The «One-line why» column MUST cite the most material finding — file:line or
skill name. «All clean» only acceptable when 0/0/0; then write «No findings
— all N skills pass.».

---

## Layer 2 — Per-category 4-part block (`detailed` mode only)

Produce ONE block per category — INCLUDING 🟢 healthy ones (the
Always-explain rule). Format under fixed bold headings, no optional parts.

### Block template

```
## {Category name} (Phase N) · Verdict: {🟢|🟡|🔴}

**What we check:**
{1–3 sentences naming the rule/criterion. Anchor to the spec file
(references/handoff-spec.md, etc.). Threshold table inline if numerical.}

**What we found:**
{Per-skill table for measurable categories (Token budget); or list of
findings for rule-based ones (Handoff, Multi-tool). Empty-state for clean
categories: «No findings across N skills + M agents.»}

**Why it matters:**
{Paragraph naming the concrete downstream failure mode — what breaks if
the user ignores findings in this category. For mutating skills, relate
to production risk. No abstract «quality matters».}

**How to fix:**
{Ordered list of remediation actions — what to change, where (file:line
or section), what severity it removes. For clean categories: «No action.»}
```

### Worked example — Token budget (Phase 2)

```
## Token budget (Phase 2) · Verdict: 🔴 action required

**What we check:**
For each SKILL.md in the library, we measure body length (excluding YAML
frontmatter) and apply thresholds per `references/budget-spec.md`. We also
sum always-on context cost (project rules + auto-loaded indexes + skill
descriptions for routing). Threshold table:
- ≤ 120 lines → 🟢 clean
- 121–200 → 🟢 review-recommended (target ≤ 200)
- 201–500 → 🟡 overload candidate
- 501–600 → 🟡 over budget (`body_budget` — extract aggressively)
- > 600 → 🔴 critical (`body_critical` — instructions in middle ignored by some hosts)

**What we found:**
| Skill | Body lines | Severity | Detail |
|---|---|---|---|
| integration-init | 612 | 🔴 | Above the 600-line `body_critical`; examples section 320 lines is the bulk. |
| skill-evaluate | 487 | 🟡 | 201–500 overload candidate — already has `references/rubrics.md` but body still long. |
| skill-build-portable | 326 | 🟡 | Overload candidate; portability rules table could split. |
| skill-find | 293 | 🟡 | Overload candidate; no urgent action. |
| library-audit | 238 | 🟡 | Overload candidate. |
| skill-compare | 279 | 🟡 | Overload candidate. |

**Why it matters:**
Anthropic Agent Skills spec recommends ≤ 500 body lines because instructions
beyond that point are statistically more likely to be ignored or compressed
by the host's context-routing logic. A 612-line skill body means the user
loses guarantee that mid-body phases (e.g. install verification, error
handling) are read in full by the agent. For mutating skills (like
integration-init which writes to AGENTS.md and runs installers), this is
production-risky — the «verify install» Phase 5 sits exactly in the danger
zone.

**How to fix:**
1. **integration-init** — move the three full-flow examples (Phase 1
   first-install, advise-only, re-run-deselect) from §Examples into
   `references/examples.md`. Body drops ~135 lines, into the 🟡 range.
   (Highest-impact fix.)
2. **skill-evaluate** — move Phase 4 detailed-mode output template into
   `assets/output-template-detailed.md`. Body drops ~90 lines.
3. **skill-build-portable** — split the portability rules table from §Phase 1
   into `references/portability-rules.md` (already exists; merge in-body
   rule descriptions into it). Body drops ~50 lines.
```

### Worked example — clean category

```
## Naming convention (Phase 3) · Verdict: 🟢 healthy

**What we check:**
Every SKILL.md `name:` matches the pattern `{entity}-{action}[-{qualifier}]`
with `action` drawn from the closed vocabulary (find / audit / evaluate /
compare / build / extend / frame / ingest / mark / plan / query / init).
kebab-case only, no organization prefixes. See `references/naming-spec.md`.

**What we found:**
No findings — all 6 skills pass:
- integration-init (entity=integration, action=init)
- library-audit (entity=library, action=audit)
- skill-build-portable (entity=skill, action=build, qualifier=portable)
- skill-compare, skill-evaluate, skill-find (entity=skill)

**Why it matters:**
Naming drift fragments the user mental model. When two skills do the same
action under different verbs («skill-check» vs «skill-evaluate»), the host's
routing logic picks based on description fuzzy match — which can flip
unpredictably as descriptions evolve. Closed vocabulary removes the
ambiguity.

**How to fix:**
No action — naming hygiene is healthy. Re-check after every new skill
addition.
```

(Repeat the block pattern for the 5 remaining categories — Handoff,
Portability tag, Multi-tool compat, Security, Metainfo coverage. Even clean
ones get «What we check / Why it matters». The Metainfo coverage matrix
(category × tier) is always emitted, even at 0 findings.)

---

## Layer 3 — Recommendations

Always present. Cross-category, impact-ordered. Each line names category,
action, and impact tier.

```
## Recommendations (impact-ordered)

1. 🔴 [Token budget] Extract integration-init §Examples → `references/examples.md`. Closes the 612-line overload. **Impact: highest.**
2. 🔴 [Token budget] Extract skill-evaluate Phase 4 template → `assets/output-template-detailed.md`. Brings body into 🟡 range.
3. 🟡 [Handoff] Add skill-find as optional Predecessor in skill-evaluate's `## Predecessor` section. Restores bidirectional handoff symmetry.
4. 🟡 [Multi-tool compat] In skill-build-portable line 132, add a sequential fallback note for the `Task` invocation.
```

Aim for ≤ 10 recommendations; if more exist, list top 10 and note the
remainder count.

---

## Verbosity contracts

- **`terse`** — Layer 1 (roll-up) + Layer 3 (recommendations) only. Skip
  Layer 2 entirely.
- **`standard`** — previous v1.4 format: roll-up + per-phase findings
  tables with `{skill, rule, severity, evidence, fix}` columns. No
  «What we check / Why it matters» rationale.
- **`detailed`** (default) — all three layers + per-category 4-part blocks.

---

## Cross-cutting rules (re-stated; SKILL.md is the canonical source)

- **Why-it-matters rule** — every per-category «Why it matters» MUST name
  the concrete downstream failure mode. No abstract «quality matters».
- **Evidence rule** — every finding cites skill name + file:line OR a
  specific quoted phrase.
- **Fix rule** — every «How to fix» entry names what to change, where,
  what severity it removes.
- **Always-explain rule** — even 🟢 healthy categories get «What we check
  / Why it matters». The reader needs to know what the auditor looked
  for, not just that it found nothing.
