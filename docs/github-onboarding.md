# GitHub Onboarding — Skill Governance Gate

> Hand-off doc for the team that owns the AI Tools Marketplace GitHub repo.
> Goal: enable the skill-governance pull-request gate on GitHub Actions.
> This is the GitHub counterpart of [`gitlab-onboarding.md`](gitlab-onboarding.md) — same engine, same delta semantics, same SHA pin.

## What this gate does

Every pull request that touches a governed asset (skill, agent, `AGENTS.md`,
MCP/plugin manifests, …) is audited by the toolkit's deterministic engine
(`agent_audit.py`, stdlib-only Python, no pip). The workflow runs:

| Step | Command | Effect |
|---|---|---|
| Block | `audit-project . --changed-only --base "origin/$GITHUB_BASE_REF" --profile release-ready --fail-on-new high` | **Newly introduced** high-severity findings (secrets, dangerous shell, broken frontmatter, `allowed-tools`) **fail the job → block the merge**; pre-existing high findings on touched legacy assets do not block |
| Annotate | same with `--fail-on none --format github` | Never blocks; renders every finding inline on the PR diff as a GitHub annotation (with rule title) |
| Artifact | same with `--format json` | Uploads `skill-audit.json` for download/inspection |
| Suppression hygiene | `list-suppressions --root .` (+ `--expiring-within 30` on suppression PRs) | Blocks on expired suppressions; warns on soon-to-expire ones |

`--changed-only` diffs the PR's committed HEAD against its merge-base with the
base branch (`origin/$GITHUB_BASE_REF...HEAD`, a three-dot diff), so an author is
accountable only for the committed assets their PR touches — not for legacy
assets already in the marketplace. Uncommitted working-tree edits are not in
scope; the gate audits what the PR introduces.

## Files involved

| File | Role |
|---|---|
| `references/ci/github-pr.yml` | Copy-ready workflow (copy to repo as `.github/workflows/skill-gate.yml`) |
| `scripts/agent_audit.py` | Audit engine the workflow runs |
| `CODEOWNERS` | Gates the suppression list so an author can't self-approve silencing a finding |

> The engine's `--format github` emits GitHub workflow commands directly, so PR
> annotations and the JSON artifact share one code path and cannot drift.

## Setup steps (on GitHub)

### 1. Copy the template into the consuming repo

```bash
cp references/ci/github-pr.yml .github/workflows/skill-gate.yml
```

### 2. Fill in two values in the template header

| Variable | Set to |
|---|---|
| `SGT_REPO` | Clone URL of your toolkit mirror, e.g. `https://github.com/your-org/skill-governance-toolkit.git` |
| `SGT_REF` | An **immutable 40-char commit SHA** (never a tag) so a re-tagged release can't silently change gate behaviour |

Generate the workflow with the SHA already pinned via the facade. Run this
**from a toolkit checkout** — `ci-init` fills in that checkout's HEAD SHA for you:

```bash
# from inside the toolkit repo:
python3 scripts/sgt.py ci-init --github --output .github/workflows/skill-gate.yml
```

From a consumer install (no toolkit checkout on hand) pass the toolkit's SHA
explicitly — `git -C <toolkit> rev-parse HEAD`, **not** a bare `git rev-parse
HEAD`, which would resolve *your* project's HEAD and break the gate on every PR:

```bash
python3 scripts/sgt.py ci-init --github --ref "$(git -C /path/to/toolkit rev-parse HEAD)" --output .github/workflows/skill-gate.yml
```

### 3. (Optional) Kill-switch variable

Set the org or repo **Actions variable** `SGT_FAIL_MODE=advisory` to downgrade
the gate to non-blocking fleet-wide **without editing the pinned template**. The
engine honors it automatically (exit 0 even on a blocking finding).

### 4. Done

Open a PR that adds a high-severity finding (e.g. an `allowed-tools:` line) and
confirm the gate job fails and the finding is annotated on the diff.

## Branch protection ("Require status checks")

GitHub only blocks a merge when a check is a **required status check**:

1. **Settings → Branches → Branch protection rules → add/edit the rule for your default branch.**
2. Enable **Require status checks to pass before merging**.
3. Add **`skill-governance-gate`** (the workflow `name:`) to the required checks.
4. Enable **Require branches to be up to date before merging** so the gate runs
   against the current base.

Because the workflow uses `on: pull_request` with a `paths:` filter, a PR that
touches no governed asset does not run the job. If you make the check *required*,
add a always-green companion job (or use `paths-ignore` strategy) so unrelated
PRs are not blocked waiting on a check that never starts. The GitLab template
solves this with an explicit `noop` job; on GitHub the common pattern is to keep
the gate **not** required and instead enforce via CODEOWNERS review + a required
job that always runs. Pick one and document it for your org.

## Separation of duties (CODEOWNERS)

The suppression list (`references/audit-ignore.json`) must be code-owner-gated so
an MR author cannot self-approve silencing their own finding. Ensure the
consuming repo's `CODEOWNERS` covers it, e.g.:

```
references/audit-ignore.json   @your-org/governance-owners
references/agent-audit-rules.json @your-org/governance-owners
```

The toolkit's own `scripts/audit.sh` P18 enforces this for the toolkit repo;
mirror the same ownership in the consuming repo.

## Base-ref behaviour (edge cases)

- `--changed-only` requires a non-empty `--base`. The template fetches
  `origin/$GITHUB_BASE_REF` explicitly and uses `fetch-depth: 0` so the merge-base
  is reachable. A shallow clone breaks the three-dot diff — keep `fetch-depth: 0`.
- On the very first push of a new branch with no base resolvable, the engine
  **fails closed** (exit non-zero) rather than silently auditing the whole tree.

## Verify locally before pushing

```bash
# Reproduce the exact CI block verdict (changed-only delta gate vs main).
python3 scripts/sgt.py gate --base main

# Equivalent raw engine call (what `sgt gate` wraps):
python3 scripts/agent_audit.py audit-project . \
  --changed-only --base origin/main --profile release-ready --fail-on-new high

# Preview the inline annotations the PR will show:
python3 scripts/agent_audit.py audit-project . \
  --changed-only --base origin/main --profile release-ready --fail-on none --format github
```

## GitHub vs GitLab: known difference

The GitLab template additionally posts a **single idempotent, severity-grouped MR
comment** via `scripts/post_mr_comment.py` (GitLab Notes API). The GitHub template
surfaces findings as **inline PR annotations + a downloadable JSON artifact**
instead — it does not post a consolidated PR comment. The blocking verdict,
delta semantics, SHA pin, and suppression hygiene are identical across both
platforms; only the advisory comment presentation differs. If your team needs a
consolidated GitHub PR comment, post `skill-audit.json` via the GitHub REST API
in a follow-up step (a `pull_request` comment), or rely on the annotations.
