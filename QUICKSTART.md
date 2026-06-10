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

## Install (one-time clone, then one command)

**Prerequisites:** `python3` ≥ 3.8 and `git` (and `bash`; on Windows use `install.ps1` with PowerShell 7+). No pip packages — the toolkit is stdlib-only. The installer fails fast with a clear message if `python3` is missing.

```bash
git clone https://github.com/{your-org}/skill-governance-toolkit ~/tools/sgt
cd ~/my-project
python3 ~/tools/sgt/scripts/sgt.py init        # guided: pick host + scope, then verifies
```

> Hosted on a private **GitLab** instance? Same flow — clone from your internal
> host (`git clone https://gitlab.example.com/{your-group}/skill-governance-toolkit ~/tools/sgt`),
> authenticating via `glab auth login`, a PAT, or a read-only deploy token. See
> [`docs/installation.md` § Private GitLab](docs/installation.md#private-gitlab).

Full install / upgrade / distribution guide (hosts & scopes, selective install,
private-repo auth, what upgrades preserve, Windows): [`docs/installation.md`](docs/installation.md).

Non-interactive (CI / scripted):
```bash
python3 ~/tools/sgt/scripts/sgt.py init --host claude --scope project --yes
```

Prefer the raw installer? `~/tools/sgt/scripts/install.sh --claude --project` (or
`~/tools/sgt/install.ps1` on Windows). The host/scope flags belong to
`scripts/install.sh`; the root `~/tools/sgt/install.sh` is the interactive wrapper
(no `--claude`/`--project` flags). Both are non-destructive — your `AGENTS.md` and
files are preserved (managed via markers).

**What lands in your repo:** a project install adds top-level `skills/`, `agents/`,
`references/`, `scripts/`, `commands/` and `docs/` dirs, the alias files/manifests
of the hosts you selected (only those), a managed `AGENTS.md` block, and `out/` +
`.skill-state/` entries in `.gitignore`. Preview the exact plan with `--dry-run`;
full list: [`docs/installation.md` § Project-install footprint](docs/installation.md#project-install-footprint).

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

> **First audit of a pre-existing library?** Run with `STRICTNESS=permissive` —
> toolkit additions to the open standard (`metainfo:`, `compatibility:`) report
> as advisories instead of a wall of 🔴. Details:
> [`docs/installation.md` § First audit over an existing skill library](docs/installation.md#first-audit-over-an-existing-skill-library).

## Add a skill in 3 steps

```bash
sgt new-skill prompt-evaluate --category governance   # 1. governance-clean skeleton
#   2. fill the TODOs, then check it:
#      invoke skill-evaluate on skills/prompt-evaluate/SKILL.md
python3 scripts/build_index.py                        # 3. re-index so the installer sees it
```

The canonical SKILL.md skeleton — required frontmatter, `metainfo` schema, naming
vocab, body budget: [`docs/skill-authoring-standard.md`](docs/skill-authoring-standard.md).

## Gate it in CI

```bash
sgt ci-init --github     # writes .github/workflows/skill-gate.yml (SHA auto-filled from a toolkit checkout)
sgt ci-init --gitlab     # writes .gitlab-ci.yml (clones the toolkit via CI_JOB_TOKEN — no PAT needed)
```
> From a **project-local install** `sgt` can't auto-resolve the toolkit's pinned
> SHA — pass `--ref <toolkit-sha>`, or run `ci-init` from your toolkit checkout
> against the project (`<toolkit>/scripts/sgt.py --root . ci-init --github`).

The command prints the exact remaining setup (token scope, branch protection,
CODEOWNERS). Full walkthrough: [`docs/gitlab-onboarding.md`](docs/gitlab-onboarding.md).

The gate scans **every** governed asset (skills, agents, MCP/plugin configs,
hooks, referenced scripts) for content-security issues — hidden/bidi characters
and homoglyph typosquats (`SEC001`–`SEC003`), inline secrets and dangerous shell
(`SEC010`–`SEC012`), unsafe references (`REF*`/`SCR*`), MCP server consistency
(`MCP*`), and hook commands (`HOOK*`). It blocks only on findings an MR
**introduces**, so it can be turned on over an existing library without an
avalanche. Reproduce the exact CI verdict locally before pushing:

```bash
sgt gate --base main     # same delta-gate verdict the CI block job uses
```
Blocked by a false positive? See [`docs/gate-for-authors.md`](docs/gate-for-authors.md)
(linked from every MR comment) — fix, inline-suppress an advisory rule, or
request a CODEOWNER-gated central suppression.

The gate checks **safety + structure** only — it has no opinion on *quality*. For
quality (clarity, examples, D1–D9), run the LLM-based `skill-evaluate` **locally
while authoring**; it never runs in the MR gate. A green MR ≠ a high-quality skill.
See [`docs/gate-for-authors.md` § Two checks, two moments](docs/gate-for-authors.md).

**CLI vs MCP vs Docker?** The audit engine is one engine in three forms: **CLI**
for CI/local (default), **MCP** for an agent to audit while you edit, **Docker**
for sandboxed/reproducible runs. Decision guide:
[`docs/agent-governance-engine.md` § Which one do I use?](docs/agent-governance-engine.md#which-one-do-i-use-decision-guide).

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
