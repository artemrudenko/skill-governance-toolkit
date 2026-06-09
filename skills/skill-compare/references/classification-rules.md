# Classification Rules — Phase 3 Reference

Detailed criteria for classifying each row of the Phase 2 comparison table into a per-item action.

## For each CORPORATE_ONLY item

→ **LOCAL_SHOULD_ADOPT**
   if **all** of:
   - improves output quality,
   - is tool-agnostic,
   - applies to this project.

→ **SKIP**
   if **any** of:
   - specific to another team's domain,
   - contradicts an explicit local constraint,
   - is a tool reference that does not match this team's stack.

## For each LOCAL_ONLY item

→ **PROPOSE_TO_CORPORATE**
   if **all** of:
   - tool-agnostic,
   - improves quality for any team,
   - does not contain project-specific paths, names, or domain terminology.

→ **KEEP_AS_RULE**
   if: contains project-specific context (domain terms, file paths, team conventions).

→ **CREATE_RULES_FILE** trigger:
   When 3 or more LOCAL_ONLY items are classified as KEEP_AS_RULE, plan a `rules/{PROJECT_NAME}.md` file to hold all of them.

## For each CONFLICT

Do **not** resolve automatically. Present both versions side by side **in the report** and stop — the user decides which to keep, or whether to handle the conflict via the rules file. Never prompt (matches the Hard-rules clarification policy: produce a report and stop instead of prompting).

## Decision flow summary

```
CORPORATE_ONLY → LOCAL_SHOULD_ADOPT | SKIP
LOCAL_ONLY     → PROPOSE_TO_CORPORATE | KEEP_AS_RULE → (≥3 = CREATE_RULES_FILE)
CONFLICT       → defer to user (no auto-resolve)
SHARED         → no action
```

Phase 4 aggregates these per-item actions into one of four recommendations: USE_CORPORATE, KEEP_LOCAL, MERGE, RULES_FILE.
