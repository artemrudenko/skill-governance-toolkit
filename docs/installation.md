# Installation, upgrade & distribution

> Audience: consumer-repo maintainer · Type: how-to · Prerequisite: README overview

The one canonical document for getting the toolkit onto a machine, into a team,
and kept up to date. For a one-page tour of what the toolkit *does*, start with
[`QUICKSTART.md`](../QUICKSTART.md).

---

## Quick install

**Prerequisites:** `python3` ≥ 3.8 and `git` (and `bash`; on Windows use `install.ps1`
with PowerShell 7+). No pip packages — the toolkit is stdlib-only.

```bash
# Clone the toolkit once, anywhere:
git clone https://github.com/{your-org}/skill-governance-toolkit ~/tools/sgt

# Run the installer FROM your project (project scope installs into the current
# directory). Running it from inside the toolkit dir would self-install and skip.
cd ~/your-project
python3 ~/tools/sgt/scripts/sgt.py init        # guided: pick host + scope, then verifies
```

Or use the installer scripts directly:

```bash
~/tools/sgt/install.sh --dry-run   # preview — resolves filters + target, writes nothing
~/tools/sgt/install.sh             # interactive — asks host + scope, auto-detects upgrades
# or
~/tools/sgt/install.ps1 -DryRun    # PowerShell preview
~/tools/sgt/install.ps1            # PowerShell 7+ (Windows / macOS / Linux)
```

For non-interactive CI use: `./install.sh --yes-default` (Claude + project scope).

### The `sgt` facade

`sgt` (= `python3 <toolkit>/scripts/sgt.py`; after a project install: `./scripts/sgt.py`)
is the single entry point for the common workflows:

| Command | What it does |
|---|---|
| `sgt init` | Guided install (host + scope), then verifies what landed |
| `sgt doctor` | Local health check |
| `sgt skills` | List installed skills |
| `sgt audit` | Run the full self-audit (**toolkit checkout only** — `audit.sh` does not ship into an install; in a consumer project use `agent_audit.py audit-project .`) |
| `sgt new-skill <name> --category <vocab>` | Scaffold a governance-clean `SKILL.md` |
| `sgt ci-init --github` / `--gitlab` | Generate the changed-only PR/MR gate (toolkit SHA pre-filled when run from a toolkit checkout; from a consumer install pass `--ref <toolkit-sha>`) |
| `sgt uninstall [--dry-run]` | Remove toolkit-owned files; your content is preserved |

### Verify / troubleshoot an install

Before installing, publishing, or debugging a checkout, run the quick doctor:

```bash
python3 scripts/doctor.py
python3 scripts/doctor.py --format json
```

It checks required files, Git cleanliness, `skills/INDEX.jsonl` freshness,
skill category/tier coverage, local runtime install directories, and the
stdlib-only Python dependency contract. Warnings are informational; failures
return a non-zero exit code with the fix to run.

Unsure what to do after installing? Print the local next-step guide:

```bash
python3 scripts/sgt.py quickstart       # doctor summary + recommended next command
python3 scripts/quickstart.py --format json
```

### Manual copy alternative (only for a fresh, empty target)

```bash
cp -r AGENTS.md CLAUDE.md GEMINI.md README.md CHANGELOG.md \
      install.sh install.ps1 .github skills agents references scripts commands \
      docs .claude-plugin .codex-plugin gemini-extension.json \
      /path/to/your/project/
```

> ⚠ This blind `cp -r` **overwrites** any existing `AGENTS.md` / `CLAUDE.md` /
> `GEMINI.md` / `docs/` in the target — it does **not** do the marker-block merge
> or conflict-rename the installer uses. Use `./install.sh` (or `install.ps1`)
> for any target that already has content; reserve the manual copy for an empty repo.

---

## Hosts & scopes

You host the toolkit **once** — on GitHub or on your internal **GitLab** instance —
then team members install per their runtime. Two distribution models below — pick
one or combine. GitHub-flavored commands are shown first; the
[GitLab-hosting path](#private-gitlab) covers the same flow for a private GitLab mirror.

### Model A — Marketplace / plugin (recommended)

Three runtimes have plugin/marketplace mechanisms with shipped manifests; two runtimes
(Copilot, Cursor) read AGENTS.md natively from the project root without needing a
separate manifest.

| Runtime | Shipped manifest | How it loads |
|---|---|---|
| Claude Code | `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` | `/plugin install ...` from local or remote marketplace |
| OpenAI Codex CLI | `.codex-plugin/plugin.json` | `codex plugins install ...` |
| Google Gemini CLI | `gemini-extension.json` | `gemini extensions install ...` |
| GitHub Copilot | none (native) | Reads `AGENTS.md` + `.github/copilot-instructions.md` from project workspace |
| Cursor v2.2+ | none (native) | Auto-discovers `AGENTS.md` + `skills/` from project root |

For the two native-discovery runtimes, distribution is either «check the toolkit
into the project repo» or «install via dotfiles / git submodule».

#### Claude Code

```bash
# One-time per team member:
/plugin marketplace add {your-org}/skill-governance-toolkit
/plugin install skill-governance-toolkit@skill-governance-marketplace
```

The marketplace manifest at `.claude-plugin/marketplace.json` declares which skills
and agents are installed.

For private GitHub repos, team members need to authenticate `gh` CLI first:
```bash
gh auth login    # one-time
```

#### GitHub Copilot

Copilot reads `AGENTS.md` natively from the project root — **no installation step**.
To make skills available across all of a developer's projects:

```bash
# Option 1 — via gh extension (if your team uses gh CLI):
gh extension install {your-org}/skill-governance-toolkit

# Option 2 — drop the .github/copilot-instructions.md into target project root manually
```

Skills are auto-discovered when the workspace contains `skills/` and a manifest.
For team-wide push, add the toolkit as a git submodule in each repository, or fork
into an org-wide template repo used for new projects.

#### OpenAI Codex CLI

```bash
codex plugins install {your-org}/skill-governance-toolkit
```

The Codex CLI fetches the repo, reads `.codex-plugin/plugin.json`, and registers
skills + agents.

For Codex App (GUI), team members go to Plugins → Search → install the named plugin
(the org must publish it to the Codex marketplace first via `codex plugins publish`).

#### Google Gemini CLI

```bash
gemini extensions install https://github.com/{your-org}/skill-governance-toolkit
```

Gemini reads `gemini-extension.json` and registers the toolkit as a Gemini extension.
`GEMINI.md` imports `AGENTS.md` automatically.

For private repos, set `GEMINI_GH_TOKEN` env var with a PAT before running.

#### Cursor v2.2+

Cursor reads `AGENTS.md` natively from any project root and auto-discovers `skills/`.
To use the toolkit in a project:

```bash
git submodule add https://github.com/{your-org}/skill-governance-toolkit .skill-toolkit
# Then symlink or merge content into project root
```

For team-wide installation, distribute via the Cursor Plugin Marketplace (paid Cursor
plan) or via shared dotfiles.

### Model B — Bootstrap installer script

For teams that don't use plugin marketplaces (or want a single onboarding command),
the toolkit ships `scripts/install.sh`:

```bash
# Clone the toolkit anywhere:
git clone https://github.com/{your-org}/skill-governance-toolkit ~/tools/skill-toolkit
cd ~/tools/skill-toolkit

# Install for one runtime (global — all projects):
./scripts/install.sh --claude --global
./scripts/install.sh --copilot --global
./scripts/install.sh --codex --global
./scripts/install.sh --gemini --global
./scripts/install.sh --cursor --global

# Or install for everything at once:
./scripts/install.sh --all --global

# Or install per-project (local to current dir):
cd ~/projects/my-app
~/tools/skill-toolkit/scripts/install.sh --claude --project
```

The installer copies skills, agents, and project rules into each runtime's expected
location. Run `--help` for full flag list.

---

## Selective install

(Since 1.8.0.) By default the installer copies **every skill with
tier ∈ {stable, preview}**. As the corporate library grows past 10–20 skills, full
installs add unnecessary token cost on activation. Use these flags to scope the install:

```bash
# By category — closed vocab from docs/skill-authoring-standard.md.
# Examples below use categories actually present in the shipped corpus
# (governance, discovery). The other vocab values (code-review, docs,
# testing, research, delivery) become useful once your library adds
# skills carrying those tags — they currently match 0 skills.
./scripts/install.sh --claude --project --category discovery       # skill-find + skill-compare
./scripts/install.sh --claude --project --category governance      # all 6 meta-skills
./scripts/install.sh --claude --project --category discovery,governance  # union

# By tier — default is stable+preview; experimental/internal require explicit opt-in
./scripts/install.sh --claude --project --tier stable               # stable only, skip preview
./scripts/install.sh --claude --project --tier stable,experimental  # include experimentals

# By explicit skill name — overrides category and tier
./scripts/install.sh --claude --project --skill skill-find,skill-evaluate

# Interactive menu — pick from a list of categories with skill counts
./scripts/install.sh --claude --project --interactive
```

Managed indexes list the installed toolkit subset. A shared library can also
contain other skills, so `skill-find` checks files missing from its index.
The Copilot skill directory has no installer-created index; the installer preserves
any existing index and `skill-find` scans the directory when needed.

**Closed-vocab `--category` values:** `code-review` · `docs` · `testing` ·
`governance` · `discovery` · `research` · `delivery`. Adding a new category requires
a CHANGELOG entry — `library-audit` Phase 5.5 flags any value outside this list as drift.

**Tier semantics:**

| Tier | Default install? | Stability contract |
|---|---|---|
| `stable` | ✓ | Public API. Breaking changes require major version. |
| `preview` | ✓ | Likely stable, breaking changes possible in minor versions. |
| `experimental` | ✗ opt-in | Anything goes; trigger phrases may change. |
| `internal` | ✗ opt-in | Not for distribution; auditor checks for accidental leaks in manifests. |

Run `python3 scripts/filter_skills.py --index skills/INDEX.jsonl --list-categories`
to see the current corpus shape.

---

## Where files land & ownership

Each newly installed skill carries an ownership marker containing its file hashes.
An upgrade or uninstall preserves a skill when the marker is absent or its content changed.
The installer applies the same rule to managed `INDEX.jsonl` files.
Older installations have no marker, so the installer preserves their skill directories and indexes.
Review and back up each legacy path before moving it aside and reinstalling.
The installer reports preserved paths and does not automatically claim ownership.

Project documentation has a separate `docs/.sgt-docs-hashes.json` record.
The installer updates a document only when its current hash matches that record.
It preserves modified documents and writes incoming copies beside them.
If an incoming copy was changed locally, the installer preserves it and uses another name.
Older installs have no document hashes: their existing documents remain unverified and are preserved.
An identical pre-existing document is not claimed merely because its content matches.
Uninstall removes recorded documents only when their hashes still match.

| Runtime | Project rules read from | Skills loaded from | Sub-agents loaded from |
|---|---|---|---|
| Claude Code | `CLAUDE.md` (which `@AGENTS.md`) | `~/.claude/skills/` or `./.claude/skills/` | `~/.claude/agents/` or `./.claude/agents/` |
| Copilot | `AGENTS.md` (root) + `.github/copilot-instructions.md` | `./.github/skills/` or `~/.copilot/skills/` | Host-dependent; not verified by this toolkit |
| Codex CLI | `AGENTS.md` (root) | `~/.codex/skills/` or via `.codex-plugin/plugin.json` | Via `spawn_agent` with `agents/` |
| Gemini CLI | `GEMINI.md` (which `@./AGENTS.md`) | `./.gemini/skills/` or `~/.gemini/skills/` | — (toolkit agent not verified on Gemini) |
| Cursor v2.2+ | `AGENTS.md` (root, native) | `./.cursor/skills/` | Via the Cursor marketplace (no plugin manifest shipped — Cursor reads `AGENTS.md` + `agents/` natively) |

For a Gemini project install, trust the project in Gemini before running
`gemini skills list`. Gemini does not discover project skills in an untrusted folder.

Since 1.10.0 the installer ships only the runtime scripts listed in
[`scripts/runtime-manifest.txt`](../scripts/runtime-manifest.txt) — dev/test/release
tooling stays in the source repo. Skills that shell out to a toolkit script resolve
the install root per [`references/path-resolution.md`](../references/path-resolution.md)
(matters for plugin and global installs, where CWD is your project, not the install dir).

The installer tracks the files it owns in a `.sgt-owned` sidecar — see
[Upgrading & what's preserved](#upgrading--whats-preserved) for the exact ownership
contract, and [`docs/architecture.md`](architecture.md) for the install-contract design.

### Project-install footprint

A `--project` install places real files at your repo root — know the full list
before running it (`--dry-run` prints the exact plan):

- **Top-level dirs:** `skills/`, `agents/`, `references/`, `scripts/` (runtime
  whitelist only), `commands/`, and `docs/` (the toolkit's ~16 guide files,
  conflict-renamed if you have same-named docs) — plus a `.{host}/` dir per
  selected host.
- **Root alias files & manifests — selected hosts only** (since 1.20.0):
  `CLAUDE.md` + `.claude-plugin/` for `--claude`, `GEMINI.md` +
  `gemini-extension.json` for `--gemini`, `.github/copilot-instructions.md` for
  `--copilot`, `.codex-plugin/` for `--codex`. A claude-only install no longer
  plants the other hosts' files; pass several flags or `--all` for multi-host teams.
- **`AGENTS.md` (always):** a managed marker block with the **consumer variant**
  of the toolkit rules — skill table, authoring conventions, tool mapping —
  rewritten for *your* repo (since 1.20.0 it no longer carries the toolkit's own
  project description or its self-CI commands). Content outside the markers is
  never touched.
- **`.gitignore`:** `out/` and `.skill-state/` entries are appended if missing
  (audit reports and resumable-run state must stay untracked).

### First audit over an existing skill library

Toolkit-specific conventions (`metadata.sgt-*`, `compatibility:`, `license:`) are
*additions* to the open SKILL.md standard — a pre-existing, spec-conformant
library will trigger 🔴 findings for them on the first run. Start with
`STRICTNESS=permissive` so they report as advisories, annotate the library
(`sgt new-skill` scaffolds compliant frontmatter), then tighten. The CI gate is
delta-based — it blocks only findings *introduced* by an MR, so onboarding a
legacy library never produces an avalanche of blocked MRs.

`STRICTNESS` is an input to the interactive `library-audit` skill.
The deterministic CLI does not accept that input.
Use `sgt check` to inspect a single skill with separate format and policy results.

---

## Private GitHub

If the toolkit lives in a private org repo:

1. **GitHub PAT** with `repo` scope for each developer:
   - Claude Code: stored via `gh auth` or via `corporate-skills-token` env var (see `skill-find` configuration reference in `AGENTS.md`).
   - Codex / Gemini: standard `GH_TOKEN` env var works.
2. **Pin a release tag** for reproducibility:
   ```bash
   /plugin install skill-governance-toolkit@<tag>     # Claude
   gemini extensions install ...@<tag>                # Gemini
   ```
   (`<tag>` = a published release tag; the README Install section carries a
   version-pinned example that `scripts/sync_version.py` keeps current.)
3. **CI auto-update** — set up a CI job in each consuming project that opens a PR
   when the toolkit publishes a new tag. Pattern: scheduled `dependabot.yml` config
   pointing at the toolkit repo, or a custom workflow.

---

## Private GitLab

The toolkit works the same when hosted on an internal GitLab instance (the common
setup for corporate rollouts). The GitHub-specific pieces above map as follows:

1. **Clone URL** — replace the github.com URL everywhere with your internal host:

   ```bash
   git clone https://gitlab.example.com/{your-group}/skill-governance-toolkit ~/tools/skill-toolkit
   ```

   `scripts/configure_org.sh` automates the rewrite across the checked-in docs and
   manifests — `bash scripts/configure_org.sh --host gitlab.example.com {your-group}`
   substitutes both the org placeholder and every hardcoded `github.com` host
   (`--dry-run` previews the changes first).

2. **Auth** — pick one:
   - a **deploy token** (Settings → Repository → Deploy tokens, `read_repository`
     scope) for clone-only consumers and CI mirrors:
     `git clone https://{token-user}:{token}@gitlab.example.com/{your-group}/skill-governance-toolkit`;
   - `glab auth login --hostname gitlab.example.com` for developers using the
     `glab` CLI;
   - or a personal access token (`read_repository` scope) over plain HTTPS git.

   In consumer CI pipelines no token is needed at all: the shipped gate template
   clones via `https://gitlab-ci-token:${CI_JOB_TOKEN}@<host>/...` — just allowlist
   the consumer project on the toolkit project (Settings → CI/CD → Token Access).

3. **Pin a release** — same rule as GitHub: pin an immutable commit SHA (`SGT_REF`)
   in CI, a tag for interactive installs.

4. **CI auto-update** — Dependabot is GitHub-only. On GitLab use
   [Renovate-on-GitLab](https://docs.renovatebot.com/modules/platform/gitlab/) with
   the `customManagers` entry from
   [`docs/security-rollout-guide.md` § Renovate auto-bump](security-rollout-guide.md#renovate-auto-bump-of-sgt_ref)
   (point `packageNameTemplate` at your GitLab host), or a **scheduled pipeline**
   in each consuming repo that compares `SGT_REF` against the toolkit's current
   `main` SHA and opens an MR when it advances.

5. **Consumer MR gate** — `sgt ci-init --gitlab` writes the changed-only gate
   (`.gitlab-ci.yml` from `references/ci/gitlab-ci.yml`) into a consuming repo;
   full walkthrough in [`docs/gitlab-onboarding.md`](gitlab-onboarding.md).
   The toolkit repo itself ships a root `.gitlab-ci.yml` that runs
   the full self-CI (`scripts/audit.sh` + test suites) on every MR/push of a
   GitLab-hosted mirror — that file is the mirror's own CI, not the consumer gate.

---

## Keeping it updated

### Version source of truth

The root `VERSION` file is the only version number to edit by hand.
Derived copies live in plugin manifests, `pyproject.toml`, and pinned install
examples.

```bash
python3 scripts/sync_version.py          # update derived files from VERSION
python3 scripts/sync_version.py --check  # CI drift check
```

`scripts/audit.sh` runs the check, so release metadata drift fails CI before
publishing.

### Release notes (GitLab Releases)

Every `vX.Y.Z` tag push publishes a **GitLab Release** whose body is derived
from `CHANGELOG.md` by `scripts/extract_release_notes.py` — the CHANGELOG
section for that version, prefixed with a **gate-impact line** («🔴 BREAKING»
marker present → "previously-passing MRs may block after this `SGT_REF` bump";
absent → "none declared"). There is no hand-maintained notes file —
`CHANGELOG.md` stays the single authored source, and self-CI P37 guards that
the current `VERSION` always yields non-empty notes, so a tag can never publish
an empty release. Consumers reviewing an `SGT_REF` bump: read the Release pages
for the tag range first — the gate-impact line answers the blocking question
up front.

### Auto-bump in consuming repos

- **GitHub** — scheduled `dependabot.yml` pointing at the toolkit repo, or a custom
  workflow that opens a PR when a new tag is published (see [Private GitHub](#private-github)).
- **GitLab** — Renovate-on-GitLab with the `customManagers` entry from
  [`docs/security-rollout-guide.md` § Renovate auto-bump](security-rollout-guide.md#renovate-auto-bump-of-sgt_ref),
  or a scheduled pipeline that compares `SGT_REF` against the toolkit's `main` SHA
  (see [Private GitLab](#private-gitlab)).

---

## Upgrading & what's preserved

Two paths, choose by how the toolkit was installed:

### Path A — installed via `claude plugin install` (Claude Code marketplace)

```bash
# 1. uninstall the current version
claude plugin uninstall skill-governance-toolkit --scope project

# 2. if your marketplace points at a local repo that has new contents — re-add it
claude plugin marketplace remove skill-governance-marketplace --scope project
claude plugin marketplace add ./ --scope project

# 3. install the new version
claude plugin install skill-governance-toolkit@skill-governance-marketplace --scope project
```

Claude Code manages the filesystem for you — no leftover files.

### Path B — installed via `./install.sh` (interactive — recommended for newcomers)

The repo-root `./install.sh` is an interactive wrapper that auto-detects
existing installs and picks the right mode (fresh / upgrade / force) for you.

```bash
./install.sh                 # interactive — asks host + scope
./install.sh --force         # interactive, but wipe target dirs before copy
./install.sh --yes-default   # non-interactive: Claude + project scope (CI)
```

### Path C — advanced (`./scripts/install.sh` with explicit flags)

The underlying installer. Use directly when you want full control over host /
scope / mode without prompts:

```bash
./scripts/install.sh --claude --project --upgrade   # explicit clean upgrade
./scripts/install.sh --all --global --force         # wipe + reinstall everywhere
./scripts/install.sh --help                         # full flag list
```

If `--upgrade` leaves unexpected state (rare), `--force` wipes target dirs
entirely before installing.

**Always read [CHANGELOG.md](../CHANGELOG.md) before upgrading** — breaking
changes (skill renames, schema bumps) are marked **🔴 BREAKING** with
per-version upgrade notes.

### State preserved across upgrades

These directories are NEVER touched by upgrades and remain yours:

- `.skill-state/` — resumable-run checkpoints ([`references/checkpointing.md`](../references/checkpointing.md)).
- `out/` — audit reports and quality-score logs.
- Any AGENTS.md edits **outside** the `<!-- skill-init: ... -->` marker
  blocks (the markers themselves get re-injected by `integration-init`,
  the surrounding text stays).
- **Your own files in `scripts/`, `references/`, `commands/`** (since 1.10.0).
  The installer tracks the files it owns in a `.sgt-owned` sidecar and merges
  rather than mirror-deletes, so `--upgrade` refreshes toolkit files and removes
  ones it previously shipped — but never deletes files you added. A file you
  named exactly like one of ours is preserved; our copy lands beside it as
  `<name>.skill-governance-toolkit.<ext>`.

---

## Uninstall

```bash
python3 scripts/sgt.py uninstall --dry-run    # shows exactly what would be removed
python3 scripts/sgt.py uninstall              # removes ONLY toolkit-owned files; your content is preserved
```

Marketplace installs: `claude plugin uninstall skill-governance-toolkit --scope project`
(see [Path A](#path-a--installed-via-claude-plugin-install-claude-code-marketplace)).

---

## Windows

Use `install.ps1` (PowerShell 7+). On Unix it delegates to `./install.sh`; on
Windows it has a native Copy-Item path.

```powershell
./install.ps1                 # interactive
./install.ps1 -DryRun         # preview, writes nothing
./install.ps1 -Force          # force-wipe + reinstall
./install.ps1 -YesDefault     # non-interactive default
```

The installer fails fast with a clear message if `python3` is missing.

---

## See also

- [`QUICKSTART.md`](../QUICKSTART.md) — install, verify, author a skill, gate it in CI, on one page
- [`docs/gitlab-onboarding.md`](gitlab-onboarding.md) — consumer MR gate walkthrough (GitLab)
- [`docs/github-onboarding.md`](github-onboarding.md) — consumer PR gate walkthrough (GitHub)
- [`docs/architecture.md`](architecture.md) — three-layer architecture incl. the install contract / ownership model
- [`docs/README.md`](README.md) — documentation hub
