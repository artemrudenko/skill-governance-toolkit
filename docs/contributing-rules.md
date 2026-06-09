# Contributing an org rule

How an adopter proposes a new **organization-specific** governance rule for the
deterministic engine, ships it safely (advisory-first), and earns promotion to a
stable, possibly floor-level, rule.

The toolkit splits **policy data** (configurable, no fork) from **detection
algorithms** (code, reviewed). Most org rules are policy data: a new dangerous
pattern, a new secret shape, a new env-exfil signature. Those ship through the
`config` mechanism with **no Python change** — see
[checks-reference.md § Configurable policy](checks-reference.md#configurable-policy-no-code-change).
A brand-new *kind* of detection (not just new data for an existing detector) needs
a code change and is out of scope for this guide; see
[checks-reference.md § New check types](checks-reference.md#new-check-types-code-change).

## The contribution path

### 1. Reserve a rule_id

Pick an **org prefix** — never the core families (`DISC`, `SKILL`, `SEC`, `REF`,
`SCR`, `MCP`, `HOOK`, `IGNORE`). Reusing a core prefix collides with the shipped
catalog on the next toolkit bump. Use a short org tag, e.g. `ACME001`, `ACME002`.
A reserved id is unique within your org catalog and stable across releases — once
published, never renumber it (tooling and suppressions key on the id).

### 2. Write test fixtures

Ship a **triggering** fixture (an asset that must fire the rule) and a **clean**
fixture (a near-miss that must NOT fire — the false-positive guard). A rule without
a clean fixture is incomplete: it cannot prove it is not over-broad. Keep fixtures
minimal and self-explanatory.

### 3. Justify severity and floor membership

State the severity (`info` / `low` / `medium` / `high`) and whether the rule should
join the **floor**. Be conservative:

- **Advisory (`medium`/`low`/`info`)** is the default for a contributed rule. It
  surfaces in reports and never blocks a pipeline.
- **Floor membership is reserved for core safety rules** (secrets, dangerous shell,
  hidden characters, traversal). A floor rule cannot be downgraded or
  inline-suppressed — that is a strong commitment. Org rules join the floor only
  after a track record, and only with governance-owner sign-off, because a floor
  addition is a **breaking change** for every pinned consumer (see
  [checks-reference.md § Rule lifecycle](checks-reference.md#rule-lifecycle--deprecation-policy)).

### 4. Ship advisory-first via config `patterns`

A data rule ships through the catalog's `config` block — no fork. Add the rule
metadata to your org catalog's `rules` list and the detection data to the matching
`config.patterns` bucket (`dangerous` / `secrets` / `env_exfil`). These **extend**
the shipped baseline; they never weaken it:

```json
{
  "rules": [
    {
      "rule_id": "ACME001",
      "severity": "medium",
      "title": "ACME: kubectl delete in an asset",
      "description": "Cluster-deletion commands must not be embedded in governed assets.",
      "stability": "candidate"
    }
  ],
  "config": {
    "patterns": {
      "dangerous": [
        {"label": "kubectl delete", "regex": "kubectl\\s+delete", "suggestion": "Avoid cluster deletion in assets.", "ignore_case": false}
      ]
    }
  }
}
```

Point the engine at your catalog via `AGENT_GOVERNANCE_RULES_PATH`, or layer a
`references/audit-config.*.json` overlay. Then **validate before CI**:

```bash
# Compile every org pattern against the ReDoS time budget
python3 scripts/agent_audit.py validate-config

# Confirm the catalog (including a malformed config block) loads
python3 scripts/agent_audit.py rules --format json
```

Full config schema, merge semantics, and overlay rules:
[checks-reference.md § Configurable policy](checks-reference.md#configurable-policy-no-code-change).

### 5. Run the advisory window, then propose promotion

Leave the rule advisory for **at least one minor release** so adopters see it in
reports without merges blocking. Then, if the false-positive rate is acceptable,
propose promotion (to `stable`, or — for a genuine safety rule — to `high`/floor)
with a **🔴 BREAKING** CHANGELOG entry and upgrade notes.

## Optional `stability` field

A contributed rule MAY carry an optional `stability` marker on its rule object to
signal lifecycle stage:

| Value | Meaning |
|---|---|
| `candidate` | New / contributed; may change or be withdrawn. A rule ships here. |
| `stable` | Proven over ≥1 release without breaking changes; safe to depend on. |

```json
{ "rule_id": "ACME001", "severity": "medium", "title": "…", "description": "…", "stability": "candidate" }
```

**This is a documented convention only — the engine does not read or enforce it.**
The catalog loader (`load_rule_catalog`) only reads `rule_id`, `severity`, `title`,
and `description` from each rule object; any other key (including `stability`) is
tolerated and ignored. Adding `stability` to a rule does **not** change validation
or behavior, so it is safe in an org catalog.

> The shipped core catalog does **not** carry `stability` on its rules — adding it
> there would change the catalog and is out of scope. The field is reserved for
> contributed org rules that want to record their lifecycle stage explicitly.
