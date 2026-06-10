# integration-init — worked examples

Three end-to-end walkthroughs covering the most common entry paths. Body of
`SKILL.md` references this file from §Examples; the actual transcripts live
here so the SKILL body stays under the token-budget threshold.

---

## Example 1 — First install, all three tools, defaults

```
User: /integration-init

integration-init: Detected runtime: Claude Code. Python 3.11.5, pipx, npm available.
           Currently installed: none.

Q1: Which integrations to install?
   → User selects: ☑ code-review-graph  ☑ repomix  ☑ serena

Q-CRG-1: Variant for code-review-graph?
   → upstream main

Q-CRG-2: MCP or CLI?
   → MCP

Q-CRG-3: Enrichment extras?
   → Yes (Python codebase)

Q-CRG-4: Initial build?
   → Full now

Q-CRG-5: Supplementary pre-commit hook?
   → Yes

Q-RPX-1: Run repomix --init?
   → Yes

Q-SRN-1: Serena languages?
   → ☑ Python  ☑ TypeScript

[Running installs...]
  ✓ pipx install code-review-graph[enrichment]==2.3.5       (pinned)
  ✓ code-review-graph install --platform claude-code        (MCP config written to ~/.claude/mcp/)
  ✓ code-review-graph build                                  (parsed 2,341 files in 14s)
  ✓ ./scripts/install-pre-commit-hook.sh                    (.git/hooks/pre-commit linked)
  ✓ npm install -g repomix@1.14.1                            (pinned)
  ✓ repomix --init                                           (repomix.config.json created)
  ✓ pipx install serena-agent==1.5.3                         (pinned)
  ✓ serena init --languages=python,typescript                (language servers ready)

[Updating documentation...]
  ✓ AGENTS.md: integrations block populated (3 sub-blocks)
  ✓ agents/code-reviewer.md: handoffs block populated (3 sub-blocks)

Done.
```

---

## Example 2 — Advise-only, just CRG

```
User: /integration-init --advise-only --with crg

integration-init: ADVISE-ONLY mode — no installs will run.

To install code-review-graph:
  1. pipx install code-review-graph==2.3.5
  2. code-review-graph install --platform claude-code
  3. code-review-graph build           # initial parse (~30s for 500-file project)

After these run, re-invoke /integration-init to update documentation.
```

---

## Example 3 — Re-run, deselecting serena

```
User: /integration-init

integration-init: Detected currently installed: code-review-graph (v2.3.3), repomix (v0.4.2), serena (v0.3.1).

Q1: Which integrations to keep installed?
   → User unselects: ☑ code-review-graph  ☑ repomix  ☐ serena

⚠ Removing serena documentation from AGENTS.md and code-reviewer.md.
  This skill does NOT uninstall the serena binary itself — run `pipx uninstall serena-agent` manually.

[Updating documentation...]
  ✓ AGENTS.md: removed integration:serena block
  ✓ agents/code-reviewer.md: removed handoff:serena block

Done. Serena binary still installed; remove with: pipx uninstall serena-agent
```
