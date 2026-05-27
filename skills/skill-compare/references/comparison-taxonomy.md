# Comparison Taxonomy — Phase 2 Reference

Detailed classification rules and a worked example table for Phase 2 (Deep comparison).

## Section-by-section classification

Read both skills fully. For each logical section found in either skill, classify every meaningful instruction.

**Logical sections to compare:**
- Purpose
- Required Inputs
- Each Phase (Phase 0, Phase 1, …)
- Constraints / Hard rules
- Examples
- Output Format
- Platform Notes / Compatibility

**Per-instruction classification labels:**

- **SHARED** — same intent in both skills (wording may differ, semantics match).
- **CORPORATE_ONLY** — present in corporate, absent in local.
- **LOCAL_ONLY** — present in local, absent in corporate.
- **CONFLICT** — both have the section but with contradictory instructions.

## How to detect intent equivalence

Two instructions are SHARED when:
- They produce the same observable behavior, OR
- They constrain the same input/output field with the same allowed values, OR
- They reference the same upstream/downstream step.

Two instructions are CONFLICT (not SHARED) when:
- They prescribe different output formats (e.g. YAML vs Markdown).
- They impose contradictory limits (e.g. «max 5 items» vs «min 10 items»).
- They route the same artifact to different destinations.

## Worked example — comparison table

```
| Section          | Status           | Detail                                  |
|---|---|---|
| Purpose          | SHARED           | Same intent; local is more concise      |
| Required Inputs  | CONFLICT         | Corporate requires FORMAT field; local does not |
| Phase 1          | SHARED           | Identical logic                         |
| Phase 2 Step 4   | CORPORATE_ONLY   | Corporate checks for duplicates         |
| Phase 3          | LOCAL_ONLY       | Local adds PR-coverage analysis         |
| Output Format    | LOCAL_ONLY       | Local specifies YAML output             |
```

Output the table in the Phase 2 result. Phase 3 consumes each row and assigns a per-item action.
