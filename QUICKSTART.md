# Quickstart — Skill Governance Toolkit

One page. For the full story see [`README.md`](README.md) and [`docs/user-guide.md`](docs/user-guide.md).

## What it is, in 30 seconds

A set of **meta-skills that check other skills**. You point it at a `SKILL.md`
(or a whole library) and it tells you what's wrong and how to fix it — frontmatter,
portability across AI tools, security patterns, writing quality — and gates those
checks in CI so a bad skill never merges.

**Before** — a skill you can't trust:
```yaml
---
name: Deploy-Helper          # wrong case, no closed-vocab action verb
allowed-tools: [Bash]        # breaks portability — Copilot/Gemini ignore it
---
Run `curl $URL | bash` to deploy.   # dangerous shell, no Skill-type contract
```
**After** — `skill-evaluate` / the audit engine flags exactly: naming (D-fail),
`allowed-tools` (portability), `curl|bash` (security high), missing `Skill type`
line (SKILL021). Fix them, and the same engine passes the PR gate green.

## Install (1 command)

```bash
git clone <toolkit-repo> ~/tools/sgt
cd ~/my-project
python3 ~/tools/sgt/scripts/sgt.py init        # guided: pick host + scope, then verifies
```

Non-interactive (CI / scripted):
```bash
python3 ~/tools/sgt/scripts/sgt.py init --host claude --scope project --yes
```

Prefer the raw installer? `~/tools/sgt/install.sh --claude --project` (or
`install.ps1` on Windows). Both are non-destructive — your `AGENTS.md` and files
are preserved (managed via markers).

## Verify it worked

```bash
python3 ~/tools/sgt/scripts/sgt.py doctor      # health check
python3 ~/tools/sgt/scripts/sgt.py skills      # list installed skills
```
Then just ask your agent a trigger phrase: «is there a skill for evaluating prompts?»

## Common tasks

| Goal | Command |
|---|---|
| Guided install + verify | `sgt init` |
| List installed skills | `sgt skills` |
| Health check | `sgt doctor` |
| Score a skill | invoke `skill-evaluate` on a `SKILL.md` (or `agent_audit.py audit-skill <path>`) |
| Audit the whole library | invoke `library-audit` (or `agent_audit.py audit-project .`) |
| **Scaffold a new skill** | `sgt new-skill prompt-evaluate --category governance` |
| **Set up the PR/MR gate** | `sgt ci-init --github` (or `--gitlab`) |
| **Remove the toolkit** | `sgt uninstall --dry-run` then `sgt uninstall` |

(`sgt` = `python3 <toolkit>/scripts/sgt.py`. After a project install it's at `./scripts/sgt.py`.)

## Add a skill in 3 steps

```bash
sgt new-skill prompt-evaluate --category governance   # 1. governance-clean skeleton
#   2. fill the TODOs, then check it:
#      invoke skill-evaluate on skills/prompt-evaluate/SKILL.md
python3 scripts/build_index.py                        # 3. re-index so the installer sees it
```

## Gate it in CI

```bash
sgt ci-init --github     # writes .github/workflows/skill-gate.yml, SHA pre-filled
sgt ci-init --gitlab     # writes .gitlab-ci.yml
```
The command prints the exact remaining setup (token scope, branch protection,
CODEOWNERS). Full walkthrough: [`docs/gitlab-onboarding.md`](docs/gitlab-onboarding.md).

## Lite adoption (small teams)

You don't have to adopt everything. A minimal path:

1. `sgt init` for one host.
2. Use `skill-find` + `skill-evaluate` interactively — skip CI, tiers, and metainfo
   ceremony until you actually have a library worth gating.
3. Add `sgt ci-init` only when more than one person edits skills.

Install just the discovery skills: `sgt init --category discovery --yes`.

## Undo

```bash
sgt uninstall --dry-run    # shows exactly what would be removed
sgt uninstall              # removes ONLY toolkit-owned files; your content is preserved
```
