# GitHub Onboarding — Skill Governance Gate

Enable the skill-governance pull-request gate on GitHub Actions — the GitHub counterpart of [gitlab-onboarding.md](gitlab-onboarding.md) (same engine, same delta semantics, same SHA pin).

> Audience: platform-devops · Type: how-to · Prerequisite: a toolkit mirror your workflows can clone

The template uses Node.js 24-based GitHub actions. Self-hosted runners need
Actions Runner 2.327.1 or newer. `actions/upload-artifact@v7` does not support
GitHub Enterprise Server; GHES users must adapt the artifact step to a supported
version and check their server and runner compatibility.

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

The org/repo **Actions variable** `SGT_FAIL_MODE=advisory` downgrades the gate to
non-blocking fleet-wide without editing the pinned template — procedure and when
to pull it: [security-incident-runbook.md](security-incident-runbook.md).

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
touches no governed asset does not run the job — a *required* check that never
starts blocks the merge forever. Pick one pattern and document it for your org:

1. **Keep the gate not-required** and enforce via CODEOWNERS review plus a
   required job that always runs (the common GitHub pattern).
2. **Make the gate required** and add an always-green companion job (or a
   `paths-ignore` mirror job) so unrelated PRs still get a passing check —
   the GitLab template closes the same gap with its explicit `noop` job.

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
  **fails closed** (exit non-zero) rather than silently auditing the whole tree —
  rationale: [cli-reference.md § `audit-project` flags in depth](cli-reference.md#audit-project-flags-in-depth).

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

---

**Next:** [security-rollout-guide.md](security-rollout-guide.md) — staged rollout
(advisory → enforce) once the gate is wired.

## See also

- [security-incident-runbook.md](security-incident-runbook.md) — go here when the gate blocks merges fleet-wide (kill-switch + re-pin).
- [security-suppression-runbook.md](security-suppression-runbook.md) — go here when an author reports a false positive.
- [cli-reference.md](cli-reference.md) — go here for every engine flag, env var, and exit code.
- [checks-reference.md](checks-reference.md) — go here for what each rule detects and how to fix it.
- [gitlab-onboarding.md](gitlab-onboarding.md) — go here if the consuming repo lives on GitLab instead.
