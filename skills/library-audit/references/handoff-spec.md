# Phase 1 — Handoff Validation Spec

This spec is loaded by `library-audit` Phase 1.

## Pass 1.1 — Bidirectional handoff

For each `SKILL.md` in `SKILLS_DIRS`:

1. Parse the body for `## Predecessor` and `## Successor` sections.
2. For each named skill in those sections (e.g. «Required upstream: `research-frame`»), verify:
   - The named skill file exists in `SKILLS_DIRS`.
   - The named skill's own Predecessor/Successor section lists the current skill as the counterpart.

**Findings:**
- **H1.1** — Reference to non-existent skill → 🔴
- **H1.2** — Counterpart skill exists but does not list this skill back → 🟡 (asymmetric handoff)
- **H1.3** — Predecessor / Successor section completely missing → 🟡 (no documented contract)

## Pass 1.2 — Trigger uniqueness

Extract trigger phrases from each skill's `description` field (the «Triggers:», «Use when:», or «Activate when:» sub-clauses).

For each pair of skills, compute trigger-phrase overlap:
- If two skills have an **identical** trigger phrase → **🔴 collision**: the host cannot disambiguate.
- If two skills share an **action verb** but with **different entity prefixes** (e.g. `library-audit` vs `wiki-audit`) → acceptable; no finding.
- If two skills share an **entity-action** combination with only a qualifier differing → 🟡: review whether one should subsume the other.

## Pass 1.3 — Clarification compliance (body-based)

**Self-exclusion (meta-rule):** files inside `skills/library-audit/` are
**exempt** from Pass 1.3 scanning of their own bodies. The library-audit
skill documents how Pass 1.3 detection works — it contains the literal
strings `AskUserQuestion` and `Clarification policy` in its rule description AND a Hard-rules line
forbidding the call. Naive grep would self-flag every run. The
implementer MUST exclude `skills/library-audit/**` from Pass 1.3.
Analogous to security-spec.md self-exclusion for Phase 5.


Portability rules forbid `type:` / `skill_role:` in frontmatter (see
`skill-build-portable` F2), so this pass is **content-based** — it reads the
skill body, not the frontmatter.

**Detection (3 atomic steps):**

1. **Grep body for prompt signals**: `AskUserQuestion`, `ask the user`,
   `ask whether`, `otherwise ask`, `then ask`, or `Clarification policy`.
   If zero hits, the skill is non-interactive — pass clean, no finding.
2. If ≥1 hit, scan `## Hard rules` (or equivalent) for an explicit policy
   statement:
   - **Permit:** the section contains a line that allows clarification, e.g.
     «Clarification policy: permitted only in Phase 0 when NEED is missing»,
     «All AskUserQuestion calls are scoped to Phase 1 and Phase 2 only»,
     «AskUserQuestion permitted in gateway mode», etc.
   - **Forbid:** the section contains a line that explicitly disallows it,
     e.g. «Clarification policy: never» or «❌ No `AskUserQuestion` regardless of phase».
3. If `Permit` is found → 🟢 (skill declared role and uses clarification
   consistent with it). If `Forbid` is found but call sites exist → 🔴 H1.4
   (self-contradiction — skill bans the call but uses it anyway). If neither
   `Permit` nor `Forbid` and call sites exist → 🟡 H1.5 («role unclear —
   document the policy in Hard rules»).

The `Clarification policy:` declaration line itself is NOT a prompt call
site; H1.4 fires only when the policy forbids prompting AND an actual phase
instruction prompts the user.

**Findings:**
- **H1.4** — Skill declares «no clarification» in Hard rules but uses it
  in body → 🔴 (self-contradiction)
- **H1.5** — Skill prompts the user without an explicit Hard-rules policy
  statement → 🟡 («role unclear»)

**Why body-based:** A skill that follows the portability rules has no
frontmatter role marker. Forcing one would contradict
`skill-build-portable` F2. The Hard-rules section is the conventional place
for the skill author to declare clarification policy — and it's already
required by the standard skill structure.

---

## Reporting

For each finding, the audit report must include:
- Skill name and path
- Phase + rule identifier (H1.1 / H1.2 / ...)
- Severity emoji (🔴 / 🟡 / 🟢)
- One-sentence evidence (line number or quoted text)
- Suggested remediation (one line)
