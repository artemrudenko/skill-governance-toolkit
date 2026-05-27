# Examples — Worked Comparison Cases

## Example 1 — qa-test-cases vs create-test-cases (MERGE outcome)

**Local skill:** `skills/qa-test-cases/SKILL.md`
**Corporate match:** `corporate/skills/create-test-cases/SKILL.md` — High overlap

### Comparison (abridged)

| Section | Status | Detail |
|---|---|---|
| Purpose | SHARED | Same intent |
| GIVEN/WHEN/THEN format | SHARED | Identical rule |
| Phase 1 Step 3 | CORPORATE_ONLY | Corporate checks for duplicate ACs |
| Phase 2 | LOCAL_ONLY | PR diff analysis for coverage gaps |
| Output: `testrail-id` field | LOCAL_ONLY | Project-specific |
| Output format | CONFLICT | Corporate = Markdown; Local = YAML |

### Classification

- «Check for duplicate ACs» → **LOCAL_SHOULD_ADOPT** (universal quality improvement).
- «PR diff analysis» → **PROPOSE_TO_CORPORATE** (tool-agnostic, improves quality everywhere).
- «testrail-id field» → **KEEP_AS_RULE** (project-specific TestRail integration).
- Output format conflict → **present to user** (do not auto-resolve).

### Recommendation: MERGE

Actions:
1. Add «check for duplicate ACs» to local Phase 1.
2. Propose «PR diff analysis» to corporate via PR.
3. Create `rules/acme-billing.md` with the `testrail-id` field requirement.
4. Resolve the output format conflict (user decision required — `YAML` selected).
