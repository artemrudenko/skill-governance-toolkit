# The Governance Gate — for authors

You landed here from a merge-request comment. This page tells you, in one screen,
what the gate checks and how to clear a finding.

> Audience: skill author · Type: how-to · Prerequisite: none — this is the page the gate comment links to

## What the gate checks

Every MR that touches a governed asset (a `SKILL.md`, an agent, an `AGENTS.md`, an
MCP/plugin manifest, a command, a prompt, a runtime config) is scanned by a
deterministic, read-only engine. It blocks **only** on **high-severity findings
you introduced** versus the target branch — pre-existing findings are advisory and
never block your MR. The high-severity classes are: broken/missing skill
frontmatter, `allowed-tools:`, dangerous shell or unsafe git, inline secrets,
hidden/bidi/invisible characters, and dangerous instructions or secrets in a
non-skill asset. Full catalog: [checks-reference.md](checks-reference.md).

## Two checks, two moments — the gate is only half the story

A **green gate does not mean "good skill."** The deterministic engine that runs on
your MR checks **safety and structure** — it has no opinion on *quality*. Quality
(is it clear? specific triggers? enough examples?) is scored by the **LLM-run
`skill-evaluate`**, which you run **locally while authoring** — it never runs in
the MR gate (an LLM's judgment is non-deterministic and must not block a merge).

```text
Authoring (you, locally)                  MR / CI (automatic)
────────────────────────────             ────────────────────────────
skill-evaluate  (LLM)          ─push──▶   sgt gate / agent_audit.py (deterministic)
• quality: D1–D9                          • safety: SEC / REF / SCR / MCP / HOOK
• clarity, examples, triggers             • structure: frontmatter, naming, budgets
• non-deterministic — for authoring       • reproducible — blocks the merge
```

| | `skill-evaluate` (local, LLM) | The MR gate (CLI, deterministic) |
|---|---|---|
| Runs | you invoke it while writing | automatically on every MR |
| Answers | "is this a *good* skill?" (D1–D9) | "is this *safe and well-formed*?" |
| Blocks merge? | no | yes (on new high-severity findings) |

**So:** run `skill-evaluate` on your `SKILL.md` *before* you push for quality; the
gate then independently enforces safety/structure on the MR. The two are
complementary — neither replaces the other. Quality scoring details:
[user-guide.md § Use Case 1–2](user-guide.md).

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

Not sure which? Run `python3 scripts/agent_audit.py explain-finding <RULEID>` — it
prints the fix and the correct suppression path for that rule. Details and break-glass:
[security-suppression-runbook.md](security-suppression-runbook.md).

## Language of findings

Rule messages and suggestions are emitted in **English only** — the engine carries
no locale overlay. For non-English teams this is friction: the finding text on a
blocked MR is English even when the rest of the workflow is not.

Russian-speaking authors should read the bilingual
[user-guide.ru.md § Use case 4.5](user-guide.ru.md#use-case-45--проверки-безопасности-артефактов-и-delta-gate-с-1120)
for the suppression model in Russian, and [checks-reference.md](checks-reference.md)
for the rule catalog. For any specific finding,
`python3 scripts/agent_audit.py explain-finding <RULE_ID>` prints the fix and the
correct suppression path (the rule id and severity are language-neutral).

> **Future work:** a `references/agent-audit-rules.ru.json` message overlay is the
> planned full solution. Until then this acknowledgment plus the bilingual runbook
> is the documented minimum — there is no locale switch today.

## The one local command

Reproduce the exact CI block verdict before you push:

```bash
sgt gate --base main
```

It runs the same changed-only delta gate CI runs (`--fail-on-new high`) and exits
non-zero on the same findings. Green locally → green in CI.

## See also

- [checks-reference.md](checks-reference.md) — go here for every rule, with triggering examples and clean fixes.
- [security-suppression-runbook.md](security-suppression-runbook.md) — go here for false positives, inline vs central suppression, SLA and break-glass.
- [agent-governance-engine.md](agent-governance-engine.md) — go here for the pipeline, the finding-delta model, and the coverage matrix.
- [skill-authoring-standard.md](skill-authoring-standard.md) — go here for the canonical SKILL.md skeleton before you write a new skill.
- [user-guide.md](user-guide.md) — go here for the local quality workflow (`skill-evaluate`, scoring, rewrite).
