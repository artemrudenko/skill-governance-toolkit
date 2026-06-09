# GitLab Onboarding — Skill Governance Gate

Enable the skill-governance merge-request gate on a GitLab CI repo (hand-off doc for the team that owns the marketplace repo).

> Audience: platform-devops · Type: how-to · Prerequisite: a toolkit mirror reachable from your GitLab instance

## What this gate does

Every merge request that touches a governed asset (skill, agent, `AGENTS.md`,
MCP/plugin manifests, …) is audited by the toolkit's deterministic engine
(`agent_audit.py`, stdlib-only Python, no pip). Two jobs run:

| Job | Command | Effect |
|---|---|---|
| `skill-gate:block` | `audit-project . --changed-only --base $CI_MERGE_REQUEST_DIFF_BASE_SHA --profile release-ready --fail-on-new high` | **Newly introduced** high-severity findings (secrets, dangerous shell, broken frontmatter, `allowed-tools`) **fail the pipeline → block the merge**; pre-existing high findings on touched legacy assets do not block |
| `skill-gate:block` (suppression hygiene, same job) | `list-suppressions --root .` on every governed MR; `list-suppressions --expiring-within 30` only when the MR edits `references/audit-ignore.json` | **Expired** suppression → fails *every* governed MR; **soon-to-expire** entry → blocks only the MR that edits the suppression file ¹ |
| `skill-gate:advisory` | same audit with `--fail-on none --format json` + `post_mr_comment.py` | Never blocks; publishes `skill-audit.json` artifact + an idempotent MR comment |
| `noop` | `echo` on `$SGT_NOOP_IMAGE` | Always-green placeholder so every MR has a pipeline (see "Branch protection" below) |

> ¹ An expired entry means the floor finding it silenced has resurfaced — any merge
> inherits the hole, so every governed MR blocks until it is renewed or removed. A
> soon-to-expire entry gates only the author already touching suppressions (the
> right owner to renew it). Full policy: [security-suppression-runbook.md
> § Expiry enforcement](security-suppression-runbook.md#expiry-enforcement--what-blocks-which-mr).

Kill-switch: the org/project CI/CD variable **`SGT_FAIL_MODE=advisory`** downgrades
the block job to non-blocking fleet-wide — procedure and when to pull it:
[security-incident-runbook.md](security-incident-runbook.md).

`--changed-only` diffs the MR's committed HEAD against its merge-base with the
target branch (`$CI_MERGE_REQUEST_DIFF_BASE_SHA...HEAD`, a three-dot diff), so an
author is accountable only for the committed assets their MR touches — not for
legacy assets already in the marketplace. Uncommitted working-tree edits are not
in scope; the gate audits what the MR introduces.

### MR gate lifecycle

```mermaid
sequenceDiagram
    participant Author
    participant GitLab
    participant Gate as "Gate jobs (SHA-pinned toolkit)"
    participant Admin as "CI/CD admin"
    Author->>GitLab: open MR
    GitLab->>GitLab: evaluate rules:changes
    alt no governed path touched
        GitLab-->>Author: noop job only — pipeline green
    else governed path touched
        GitLab->>Gate: clone SGT_REPO@SGT_REF (CI_JOB_TOKEN) + verify SHA
        Gate->>Gate: block job — list-suppressions --root .
        Note over Gate: expired suppression → fail
        Gate->>Gate: block job — audit --changed-only --fail-on-new high
        Note over Gate: introduced high finding → fail
        Gate->>GitLab: advisory job — full JSON artifact + idempotent MR comment
        GitLab-->>Author: verdict + findings on the MR
        Author->>GitLab: fix the content
        Author->>GitLab: or inline sgt-ignore (advisory rules only)
        Author->>GitLab: or central audit-ignore.json + CODEOWNER approval (floor rules)
    end
    Admin-->>GitLab: SGT_FAIL_MODE=advisory — fleet kill-switch (incident only)
```

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
| `SGT_REPO` | URL of the toolkit repo on **your** GitLab host. Template placeholder: `https://gitlab-ci-token:${CI_JOB_TOKEN}@REPLACE-WITH-YOUR-GITLAB-HOST/your-group/skill-governance-toolkit.git` — replace the host/group with where your org mirrors the toolkit, keeping the `gitlab-ci-token:${CI_JOB_TOKEN}@` prefix (see "Clone auth" below). |
| `SGT_REF` | An **immutable 40-char commit SHA**, not a tag. Template placeholder: `REPLACE-WITH-40-CHAR-COMMIT-SHA`. Get the SHA of the toolkit release you want to pin with `git -C <toolkit> rev-parse HEAD`, or let `sgt ci-init --gitlab` fill it in for you (run from a toolkit checkout). |

Why a SHA, not a tag: a re-tagged release could silently change gate behaviour.
Pin a commit your org has reviewed and approved. Bump the SHA deliberately when
you adopt a newer toolkit version.

### 2a. Clone auth (private toolkit mirror)

The template clones the toolkit with the per-job **`CI_JOB_TOKEN`** GitLab
injects automatically — no PAT to provision or rotate. For a **private**
toolkit mirror, the toolkit project must additionally allow the consuming
repo(s) on its job-token allowlist:

> toolkit project → **Settings → CI/CD → Token Access** →
> **"Limit access to this project"** → add each marketplace repo.

Without that setting the clone fails with `HTTP 404` (GitLab hides private
projects from unauthorized tokens). On a public/internal-visibility mirror the
token is simply ignored and no setup is needed.

### 2b. Job images (egress-restricted runners)

The template's job images default to public Docker Hub (`python:3.12-slim`,
`alpine:3.20`), and the base job apt-installs `git` only when the image lacks
it. On an air-gapped or egress-restricted instance, override as group/project
CI/CD variables:

| Variable | Default | Override with |
|---|---|---|
| `SGT_IMAGE` | `python:3.12-slim` | An internal-registry image with **python3 + git** preinstalled (skips the apt-get step entirely) |
| `SGT_NOOP_IMAGE` | `alpine:3.20` | Any minimal internal image with a shell |

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

The **`rules:changes` path list** in the template must match the asset types the
engine governs (`agent_audit.py` `asset_type`). A path the engine audits but CI
ignores is a silent coverage gap. Current list:

| Path | Why governed |
|---|---|
| `skills/**`, `agents/**`, `commands/**`, `prompts/**` | Skill / agent / prompt bodies — the primary audited assets |
| `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md` | Always-on rules files injected into every agent turn |
| `gemini-extension.json`, `**/.mcp.json`, `**/mcp.json`, `**/plugin.json` | MCP / plugin manifests — the tool-exposure surface |
| `.claude/settings.json`, `.claude/settings.local.json`, `hooks/**` | Hook commands the host executes on agent events |
| `references/agent-audit-rules.json` | Rule catalog — control-plane, must not change ungoverned |
| `references/audit-ignore.json` | Suppression control-plane (also triggers the expiring-soon check) |
| `references/audit-config.*.json` | So the "config overlay is ignored" warning fires |

Keep the table in sync with `references/ci/gitlab-ci.yml` `rules:changes`.

**`GIT_DEPTH: 0`** is required so the MR merge-base commit is reachable for
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
  `CI_MERGE_REQUEST_DIFF_BASE_SHA` on a non-merge-request pipeline) → **exits 2
  (fails closed)** with a stderr notice instead of silently auditing the whole tree.
  Rationale and the full scoping matrix: [cli-reference.md § `audit-project` flags
  in depth](cli-reference.md#audit-project-flags-in-depth).
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

---

**Next:** [security-rollout-guide.md](security-rollout-guide.md) — staged rollout
(advisory → enforce) once the gate is wired.

## See also

- [security-incident-runbook.md](security-incident-runbook.md) — go here when the gate blocks merges fleet-wide (kill-switch + re-pin).
- [security-suppression-runbook.md](security-suppression-runbook.md) — go here when an author reports a false positive.
- [cli-reference.md](cli-reference.md) — go here for every engine flag, env var, and exit code.
- [checks-reference.md](checks-reference.md) — go here for what each rule detects and how to fix it.
- [github-onboarding.md](github-onboarding.md) — go here if the consuming repo lives on GitHub instead.
