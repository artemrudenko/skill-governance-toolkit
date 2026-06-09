# GitLab Onboarding — Skill Governance Gate

> Hand-off doc for the team that owns the AI Tools Marketplace GitLab repo.
> Goal: enable the skill-governance merge-request gate on GitLab CI.

## What this gate does

Every merge request that touches a governed asset (skill, agent, `AGENTS.md`,
MCP/plugin manifests, …) is audited by the toolkit's deterministic engine
(`agent_audit.py`, stdlib-only Python, no pip). Two jobs run:

| Job | Command | Effect |
|---|---|---|
| `skill-gate:block` | `audit-project . --changed-only --base $CI_MERGE_REQUEST_DIFF_BASE_SHA --profile release-ready --fail-on-new high` | **Newly introduced** high-severity findings (secrets, dangerous shell, broken frontmatter, `allowed-tools`) **fail the pipeline → block the merge**; pre-existing high findings on touched legacy assets do not block |
| `skill-gate:advisory` | same with `--fail-on none --format json` + `post_mr_comment.py` | Never blocks; publishes `skill-audit.json` artifact + an idempotent MR comment |
| `noop` | `echo` on `alpine` | Always-green placeholder so every MR has a pipeline (see "Branch protection" below) |

`--changed-only` diffs the MR's committed HEAD against its merge-base with the
target branch (`$CI_MERGE_REQUEST_DIFF_BASE_SHA...HEAD`, a three-dot diff), so an
author is accountable only for the committed assets their MR touches — not for
legacy assets already in the marketplace. Uncommitted working-tree edits are not
in scope; the gate audits what the MR introduces.

## Files involved

| File | Role |
|---|---|
| `references/ci/gitlab-ci.yml` | Copy-ready pipeline template (copy to repo root as `.gitlab-ci.yml`) |
| `scripts/agent_audit.py` | Audit engine the pipeline runs |
| `scripts/post_mr_comment.py` | Posts findings as an idempotent MR comment (urllib, no SDK) |
| `docs/user-guide.md` § "GitLab CI - Merge Request gate" | Full reference |

## Setup steps (on GitLab)

### 1. Copy the template to the marketplace repo root

```
references/ci/gitlab-ci.yml  →  <marketplace-repo>/.gitlab-ci.yml
```

Or `include:` it from an existing pipeline. (In the toolkit it lives under
`references/ci/` without a leading dot because it is a sample, not an active
config — that is why it is "invisible" to a root-level search.)

### 2. Fill in two variables in the template header

In `.gitlab-ci.yml`, `variables:` block:

| Variable | Set to |
|---|---|
| `SGT_REPO` | URL of the toolkit repo on **your** GitLab host. Template placeholder: `https://REPLACE-WITH-YOUR-GITLAB-HOST/your-group/skill-governance-toolkit.git` — set this to where your org mirrors the toolkit. |
| `SGT_REF` | An **immutable 40-char commit SHA**, not a tag. Template placeholder: `REPLACE-WITH-40-CHAR-COMMIT-SHA`. Get the SHA of the toolkit release you want to pin with `git -C <toolkit> rev-parse HEAD`, or let `sgt ci-init --gitlab` fill it in for you (run from a toolkit checkout). |

Why a SHA, not a tag: a re-tagged release could silently change gate behaviour.
Pin a commit your org has reviewed and approved. Bump the SHA deliberately when
you adopt a newer toolkit version.

### 3. Create a masked CI/CD variable

Settings → CI/CD → Variables → Add variable:

| Key | Value | Flags |
|---|---|---|
| `GITLAB_TOKEN` | Project/group access token with **`api`** scope | Masked, Protected |

Needed **only** for the advisory MR comment. Without it the poster is skipped
and the gate still works. The token is read by env-var **name**, never passed
on the command line.

### 4. Done

GitLab auto-provides the rest: `CI_API_V4_URL`, `CI_PROJECT_ID`,
`CI_MERGE_REQUEST_IID`, `CI_MERGE_REQUEST_DIFF_BASE_SHA`.

## Things to keep in sync

- **`rules.changes` path list** in the template must match the asset types the
  engine governs (`agent_audit.py` `asset_type`). A path the engine audits but
  CI ignores is a silent coverage gap. Current list: `skills/**`, `agents/**`,
  `commands/**`, `prompts/**`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`,
  `.github/copilot-instructions.md`, `gemini-extension.json`, `**/.mcp.json`,
  `**/mcp.json`, `**/plugin.json`, `.claude/settings.json`,
  `.claude/settings.local.json`, `hooks/**`, `references/agent-audit-rules.json`,
  `references/audit-ignore.json` (suppression control-plane), and
  `references/audit-config.*.json` (so the "config overlay is ignored" warning
  fires). Keep it in sync with `references/ci/gitlab-ci.yml` `rules:changes`.
- **`GIT_DEPTH: 0`** is required so the MR merge-base commit is reachable for
  the diff. Do not lower it.

## Branch protection ("Pipelines must succeed")

If you enable **Settings → Merge requests → "Pipelines must succeed"**, every MR
must have a passing pipeline before it can merge. But the gate jobs run **only**
when the MR touches a governed asset (`rules:changes`). An MR that touches no
governed asset produces **no pipeline at all** — and the merge blocks forever
waiting for a pipeline that never runs.

The template ships a `noop` job to close this gap: it is gated only on
`merge_request_event` (no `changes:` filter), so it always runs and always
passes. Every MR therefore has at least one green pipeline, while the real gate
jobs still run only on the MRs that touch governed assets. Do not add a
`changes:` filter to `noop` — that reintroduces the deadlock.

## Separation of duties (CODEOWNERS)

The repo ships a root `CODEOWNERS` (GitLab reads `CODEOWNERS`, `.gitlab/CODEOWNERS`,
or `docs/CODEOWNERS` — the root file covers both GitLab and GitHub). It gates the
control-plane paths — the rule catalog, the engine, the CI template, and the
suppression list (`references/audit-ignore.json`) — so an MR author can't
self-approve silencing their own security finding. Replace `@skill-governance-owners`
with your real group.

**This guarantee is advisory until you enforce it.** CODEOWNERS only *blocks* a
merge when the protected branch requires code-owner approval:

> **Settings → Repository → Protected branches** → on the default branch, enable
> **"Require approval from Code Owners"**.

(On GitHub the equivalent is **Settings → Branches → Branch protection rules** →
**"Require review from Code Owners"**.) Without this setting, the suppression list
and engine can be changed by the same author who edits a skill in the same MR.

## Troubleshooting

- **MR comment fails with `RemoteDisconnected: Remote end closed connection
  without response`** — a WAF or load balancer in front of your GitLab host is
  resetting connections whose User-Agent is the default `Python-urllib/x.y`.
  `post_mr_comment.py` sends an explicit `User-Agent: skill-governance-gate` and
  `Accept: application/json` to survive these hops; if your appliance is stricter,
  allowlist that User-Agent.

## Base-ref behaviour (edge cases)

- **Empty `--base`** with `--changed-only` (e.g. missing
  `CI_MERGE_REQUEST_DIFF_BASE_SHA` on the first pipeline of a new MR, or a
  non-merge-request pipeline) → **exits 2 (fails closed)** with a stderr notice.
  It refuses to silently audit the whole tree — a silent scope switch could both
  block unrelated MRs on legacy assets and, under `--fail-on none`, produce a
  green pipeline that audited nothing. Re-run on a merge-request pipeline, or
  drop `--changed-only` to audit the full project on purpose.
- **Non-empty but bad/unreachable ref** → exits 2 with a sanitized message.

## Verify locally before pushing

```bash
# Reproduce the exact CI block verdict (changed-only delta gate vs main).
# This is what the block job runs — only NEWLY introduced high findings fail.
sgt gate --base main

# Equivalent raw engine call (what `sgt gate` wraps):
python3 scripts/agent_audit.py audit-project . \
  --changed-only --base main --fail-on-new high --format text

# Preview the rendered MR comment without calling the API
python3 scripts/post_mr_comment.py skill-audit.json --dry-run
```

> The block job now uses **`--fail-on-new`** (the finding-delta gate), not absolute
> `--fail-on high`. Pre-existing findings stay advisory; only findings an MR
> *introduces* vs its base block the merge — so enabling the gate over a legacy
> repo doesn't avalanche. See [security-rollout-guide.md](security-rollout-guide.md).

## MR comment poster — config reference

| Flag | Source env var | Purpose |
|---|---|---|
| `--api-url` | `CI_API_V4_URL` | GitLab API base (auto-set in CI) |
| `--project-id` | `CI_PROJECT_ID` | Target project (auto-set in CI) |
| `--mr-iid` | `CI_MERGE_REQUEST_IID` | Target merge request (auto-set in CI) |
| `--token-env` | `GITLAB_TOKEN` | Env var **name** holding an `api`-scoped token |

Re-running a pipeline updates the same note (matched by a hidden HTML marker)
instead of stacking duplicates.
