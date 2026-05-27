# Output Templates — Phase 5 Reference

Full templated output blocks for the comparison report, the merged SKILL.md, and the project-specific rules file.

## Always output: comparison report

```
### Skill Compare Report: {local_skill_name}

Corporate match:    {corporate_skill_name}  ({overlap_tier} overlap)
Recommendation:     {USE_CORPORATE | KEEP_LOCAL | MERGE | RULES_FILE}

#### Comparison Summary
| Category         | Count | Key items                                |
|---|---|---|
| Shared           | N     | ...                                      |
| Corporate-only   | N     | ...                                      |
| Local-only       | N     | ...                                      |
| Conflicts        | N     | [list — must resolve before merge]       |

#### Recommended Actions (in order)
1. ...
2. ...
```

## If MERGE → produce merged SKILL.md

Combine both skills:
- Use the **corporate structure** as the base.
- Insert LOCAL_ONLY items classified as PROPOSE_TO_CORPORATE into the appropriate sections.
- Add an inline comment on each inserted line: `<!-- merged from local: {PROJECT_NAME} -->`.
- Move KEEP_AS_RULE items into the rules file instead (not into the merged SKILL.md).
- Resolve every CONFLICT before committing (Phase 3 defers conflict resolution to the user).

The merged file is a **DRAFT** — write it to a side-by-side location (not over the corporate source) and let the user review.

## If RULES_FILE (or MERGE with project additions) → produce `rules/{PROJECT_NAME}.md`

```markdown
# {PROJECT_NAME} Rules — {skill_name}

## Context
These rules extend the corporate `{corporate_skill_name}` skill with
project-specific constraints for {PROJECT_NAME}.

## Additional Inputs
[Any project-specific inputs not in corporate skill]

## Overrides
[Instructions that replace a corporate step for this project]
Syntax: `Override Phase N Step M: {new instruction}`

## Extensions
[Instructions added after a corporate phase — not replacing anything]
Syntax: `After Phase N: {instruction}`

## Constraints
[Project-specific do-not rules]

## Last updated: {date}
```

Append each KEEP_AS_RULE item into the appropriate section (Additional Inputs / Overrides / Extensions / Constraints) based on its semantics.
