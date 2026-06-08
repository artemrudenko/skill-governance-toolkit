# The Governance Gate — for authors

You landed here from a merge-request comment. This page tells you, in one screen,
what the gate checks and how to clear a finding.

## What the gate checks

Every MR that touches a governed asset (a `SKILL.md`, an agent, an `AGENTS.md`, an
MCP/plugin manifest, a command, a prompt, a runtime config) is scanned by a
deterministic, read-only engine. It blocks **only** on **high-severity findings
you introduced** versus the target branch — pre-existing findings are advisory and
never block your MR. The high-severity classes are: broken/missing skill
frontmatter, `allowed-tools:`, dangerous shell or unsafe git, inline secrets,
hidden/bidi/invisible characters, and dangerous instructions or secrets in a
non-skill asset. Full catalog: [checks-reference.md](checks-reference.md).

## The 3 ways to resolve a finding

1. **Fix the content** (default). Remove the secret, scope the dangerous command,
   delete the hidden character, retype the homoglyph in ASCII. This is almost
   always the right answer.
2. **Suppress inline** — for an **advisory** finding only (e.g. `SEC003`,
   `SEC012`). Add a marker on or above the line:
   `<!-- sgt-ignore: RULEID reason=... -->`.
3. **Central suppression** — for a **floor/high** finding, or anything you want
   tracked. Add an entry to `references/audit-ignore.json` with a `reason` and a
   recommended `expires`. It needs **CODEOWNER approval** — you cannot self-approve.

Not sure which? Run `sgt explain-finding` is not a thing — use the engine:
`python3 scripts/agent_audit.py explain-finding <RULEID>` prints the fix and the
correct suppression path. Details and break-glass:
[security-suppression-runbook.md](security-suppression-runbook.md).

## The one local command

Reproduce the exact CI block verdict before you push:

```bash
sgt gate --base main
```

It runs the same changed-only delta gate CI runs (`--fail-on-new high`) and exits
non-zero on the same findings. Green locally → green in CI.

## Links

- [checks-reference.md](checks-reference.md) — every rule, with triggering
  examples and clean fixes.
- [security-suppression-runbook.md](security-suppression-runbook.md) — false
  positives, inline vs central, SLA and break-glass.
- [agent-governance-engine.md](agent-governance-engine.md) — the pipeline, the
  finding-delta model, and the coverage matrix.
