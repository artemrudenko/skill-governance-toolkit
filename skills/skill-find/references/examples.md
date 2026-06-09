# Worked examples — skill-find

Three worked examples covering strong match, partial match (→ skill-compare), and no-match (→ create new).

## Example 1 — Strong match

**Input:** `NEED: "check the quality of a skill file and get a score"`

**Output:**

```
#1  skill-evaluate                                 [project]
    Match: 94%  ·  Quality: 91/100 🟢
    "Quality evaluator for SKILL.md files. Scores across 9 dimensions:
    clarity, completeness, specificity, examples, constraints, portability,
    testability, discoverability, safety..."
    ✓ Use directly — invoke with SKILL_TARGET=your-skill
```

## Example 2 — Partial match leading to skill-compare

**Input:** `NEED: "compare our test case skill with what the company uses"`

**Output:**

```
#1  skill-compare                                  [project]
    Match: 71%  ·  Quality: 88/100 🟢
    "Compare a local skill against similar skills in a corporate repository
    to find overlap, conflicts, and sync opportunities..."
    ~ Partial — run skill-compare to adapt for your context
```

## Example 3 — No match, suggest creation

**Input:** `NEED: "monitor API response times and alert on slowdowns"`

**Output:**

```
Result: No matching skills found across 3 source(s).
Closest: code-review (24%) — not a match

Suggested frontmatter:
---
name: api-latency-audit
description: |
  Monitors API endpoint response times and identifies regressions.
  Use when investigating latency issues, reviewing performance,
  or setting up threshold alerts.
  Capabilities: baseline comparison, trend analysis, regression
  detection, alert generation.
---
```

Note: suggested names must pass the naming-spec checks N1–N5 (closed-vocabulary action verb, `{entity}-{action}[-{qualifier}]` shape) — e.g. `monitor` is not a closed-vocab verb, so the suggestion uses `audit`.
