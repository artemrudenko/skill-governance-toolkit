# Changelog

All notable changes to the Skill Governance Toolkit. The version line
format is `[X.Y.Z] — YYYY-MM-DD — short headline`. Format follows
[Keep a Changelog](https://keepachangelog.com/) with `Added` / `Changed` /
`Removed` / `Fixed` sections per release.

Breaking changes are marked **🔴 BREAKING** — read the Upgrade notes for
each before upgrading. A **rule severity escalation or floor addition** counts as
breaking even when no new rule is added: it makes previously-advisory findings
start blocking on the next `SGT_REF` bump (see
[checks-reference.md § Rule lifecycle](docs/checks-reference.md#rule-lifecycle--deprecation-policy)).

---

## [1.14.0] — 2026-06-09 — single source of truth for thresholds + rationale coverage

A consistency/rationality pass from a full cross-corpus rule review. Removes
threshold drift, makes every gate rule justify itself, and trims two
over-engineered checks. No deterministic gate behavior changes (SKILL011 budget
500 / critical 600 unchanged); the rules catalog is untouched.

### Added
- **Gate-rule rationale coverage guard (self-CI P25).** Every gate rule must carry
  a `why` (catalog `title` + `description`) **and** a `checks-reference.md`
  rationale row, else self-CI fails. A check you cannot justify is a candidate for
  removal — `test_rationale_coverage.py`.
- **Body-length single-source guard (`test_audit_config.py`).** The prose tables in
  `skill-evaluate` 3.1, `library-audit` budget-spec, and the authoring standard
  must echo the gate config's `body_budget` / `body_critical`; the stale `401`
  boundary can never resurface.

### Changed
- **One source of truth for body-length thresholds.** The gate config
  (`body_budget=500`, `body_critical=600`) is canonical; the three doc tables that
  had drifted (one used a `401–600` boundary, another `>500 critical`) now echo it:
  `≤200` target · `201–500` overload · `501–600` over-budget 🟡 · `>600` critical 🔴.
  AGENTS.md rule 4 now points at the config instead of stating `≤ 500`.
- **`description` length bounds documented.** `description_min=80` /
  `description_max=1024` were only in code — now referenced in the authoring
  standard (with the 100–400 sweet spot), pointing at the config as source.
- **New authoring-standard rule:** "Single source of truth for thresholds &
  vocabularies" — define once (config for thresholds, standard for vocab),
  reference everywhere else.
- **`skill-evaluate` 3.3 (agent-pattern ID) is informational only** — removed from
  dimension scoring (too subjective to score consistently; was already effectively
  advisory).
- **`library-audit` Pass 2.2 (claims-vs-actual) is OPTIONAL** — runs only when a doc
  makes an explicit token-saving claim; skipped entirely otherwise.

---

## [1.13.0] — 2026-06-09 — info severity lane + optional activation sections

Adds a zero-impact `info` reporting lane for R&D-grade checks and its first
resident (3.8 negative-rule placement), and **relaxes the body activation
sections to optional** — activation is driven by the frontmatter `description`,
exclusion triggers live there, and standalone hard rules go in `AGENTS.md`.
Rules catalog bumped `0.4.0 → 0.5.0`.

### Added
- **`info` severity (skill-evaluate, Surface B).** Info findings record to a new
  `info_flags` JSONL field and a collapsed «Info (no action required)» report
  section. They **never** cap a dimension, Score, tier, or the safety gate — a
  promotion stage for checks that need evidence before they enforce. Contract and
  promotion path: [`docs/extending-checks.md` § Info / experimental lane](docs/extending-checks.md#info--experimental-lane).
- **3.8 — Negative-rule placement (info).** Surfaces passive prose prohibitions
  placed *outside* the canonical activation sections that would be more reliable
  in `description` (activation) or `AGENTS.md` (safety/execution). Scoped out of
  the sanctioned `## When to use` / `## When not to use` sections, and defers
  coherence to 3.7 — no check-vs-check conflict.
- **Self-CI phase P24.** `test_skill_evaluate_catalog.py` guards catalog↔section
  sync, the info-never-caps contract, and the 3.8 scope-out boundary.

### Changed
- **Body `## When to use` / `## When not to use` are now OPTIONAL.** `description`
  is the canonical home for activation and exclusion triggers. `skill-evaluate`
  3.0b no longer flags a missing section (present sections still structure- and
  coherence-checked by 3.0b/3.7). `skill-build-portable` S2 **no longer inserts**
  a skeleton — it advises strengthening the `description` instead. Authoring
  standard skeleton marks the sections optional.

### Removed
- **Gate rule `SKILL012`** ("Missing `## When to use` section", advisory `low`) —
  retired in rules `0.5.0`. Non-breaking for pipelines (it never blocked; removal
  only removes a finding). Tooling that keys on the `SKILL012` id should drop it.
  See [checks-reference.md § Retired rules](docs/checks-reference.md#retired-rules).

---

## [1.12.0] — 2026-06-09 — asset-security suite

Extends the deterministic engine from skill-structure checks to a **content
security** scan over every governed asset, plus a **finding-delta gate** so the
new rules can be enabled over a legacy library without an avalanche of failures.
Rules catalog bumped `0.1.0 → 0.4.0`.

### Added
- **Per-asset content security pipeline.** Non-skill assets (MCP configs, plugin
  manifests, agents, commands, prompts, runtime configs) are now scanned for
  dangerous instructions (`SEC010`), inline secret values (`SEC011`), and
  credential-file paths (`SEC012`). The asset-type → checks routing lives in
  `agent_audit.py` `checks_for`.
- **Reference-safety rules (`REF001`–`REF004`).** Asset bodies are scanned for
  unsafe references: a referenced shipping script not in the runtime manifest
  (`REF001`), a link target that traverses/escapes the repo root (`REF002`,
  high/floor), an external URL not in the allowlist (`REF003`), and a dangling
  in-repo link (`REF004`). Resolution mirrors `safe_read_asset`; anchors,
  `mailto:`, and gitignored output dirs are excluded.
- **Referenced-script content scan (`SCR001`–`SCR003`).** Scripts that an asset
  body references are read and scanned for an env-var exfiltration heuristic
  (`SCR001` — explicitly low-recall, absence ≠ safe), dangerous shell (`SCR002`),
  and secret references (`SCR003`). In changed-only mode a changed script is
  scanned only when some asset references it (changed or not) — never a blanket
  `scripts/` sweep, and never a standalone changed script no asset loads, so the
  scope matches whole-tree exactly (a self-contained test fixture is not flagged).
- **MCP tool↔server consistency (`MCP001`/`MCP002`).** A skill using `mcp__server__*`
  must declare the server in `metainfo.requires.mcp` (or the org `allow_mcp_servers`
  allowlist); used-but-undeclared is `MCP001` (high), declared-but-unused is `MCP002`
  (low). `mcp__` tokens inside fenced/inline code or detection-context lines are
  ignored. MCP server `command + args` are also joined and dangerous-scanned so a
  payload split across argv elements is caught.
- **Hook-command audit (`HOOK001`/`HOOK002`).** `.claude/settings*.json`, `plugin.json`
  `hooks` blocks, and `hooks/*` scripts are a new governed `hook` asset type; each
  hook command is scanned for dangerous shell (`HOOK001`) and secret/env-exfil
  (`HOOK002`). CI `rules:changes` extended to cover the hook paths.
- **Hidden-character scan (`SEC001`/`SEC002`) on every asset.** Catches bidi
  controls / direction marks (`SEC001`) and invisible/format/tag/variation
  characters (`SEC002`) used to smuggle instructions past a human reviewer. The
  dangerous/secret scans **NFKC-normalize** first, so fullwidth lookalikes cannot
  bypass `SEC010`/`SKILL014`.
- **Homoglyph confusable scan (`SEC003`).** Flags a Latin-majority word or URL
  host hiding a Cyrillic/Greek look-alike. Language-safe: pure foreign words,
  diacritics, and a `metainfo.language` declaration never trip it; URL/host
  tokens are flagged regardless of declared language.
- **Finding-delta gate (`--fail-on-new`).** Blocks only on findings **introduced**
  vs `--base` (the key excludes line, so a moved-but-identical finding stays
  pre-existing). Pre-existing findings are advisory. This is what lets a team
  enable the suite over an existing repo. See `docs/security-rollout-guide.md`.
- **Ignore-list (central + inline).** `references/audit-ignore.json` (CODEOWNERS-
  gated) can suppress **any** rule with a required `reason` + optional `expires`;
  inline `<!-- sgt-ignore: RULEID reason=... -->` markers suppress **advisory**
  rules only. Fail-safe visibility rules surface a suppression that did not apply:
  `IGNORE001` (expired/bad date), `IGNORE002` (missing reason), `IGNORE003`
  (inline marker on a floor rule).
- **Namespaced config + overlay.** The catalog `config` block tunes thresholds,
  vocabularies, profiles, dangerous/secret pattern packs, and allowlists; sibling
  `references/audit-config.*.json` overlays deep-merge on top.
- **`validate-config`** subcommand — compiles org config/overlay patterns against
  a ReDoS time budget before they reach CI.
- **`--format github`** — emits `::error` / `::warning` workflow annotations so
  findings surface inline on a GitHub PR diff.
- **`SGT_FAIL_MODE=advisory` fleet kill-switch.** A single org/project CI variable
  forces a non-blocking exit 0 across every pipeline — the 5-minute mitigation
  when the gate misbehaves, with no template edit or CODEOWNERS bottleneck. See
  `docs/security-incident-runbook.md`.
- **`sgt gate [--base main]`** — reproduces the exact CI block verdict locally
  (changed-only delta gate, `--fail-on-new high`). `sgt gate --check-setup`
  verifies CODEOWNERS wiring.
- **`sgt ci-init` scaffolding hardening.** Also scaffolds the suppression list and
  a `CODEOWNERS` stub so the gate cannot weaken itself.
- **New docs:** `docs/security-suppression-runbook.md` (false-positive handling +
  OPS5 SLA/break-glass), `docs/security-rollout-guide.md` (enable over a legacy
  library), `docs/security-incident-runbook.md` (OPS2: gate blocking everything),
  `docs/gate-for-authors.md` (OPS9: one-page author entry point linked from the MR
  comment footer). Engine + checks docs gained per-asset pipeline, finding-delta,
  config-resolution, and ignore-decision Mermaid diagrams plus a coverage matrix.

### Changed
- The block job and `sgt gate` now use `--fail-on-new` (delta) instead of
  absolute `--fail-on high` — pre-existing findings no longer block unrelated MRs.

## [1.11.1] — 2026-06-08 — GitLab gate hardening from real-world adoption

Two fixes surfaced by a team running the GitLab CI gate in production.

### Fixed
- **MR comment poster survives WAF / load balancers.** `post_mr_comment.py` now
  sends an explicit `User-Agent: skill-governance-gate` and `Accept:
  application/json`. Some appliances reset connections whose User-Agent is the
  default `Python-urllib/x.y` (`RemoteDisconnected: Remote end closed connection
  without response`) while letting curl through — the non-default header gets the
  API call past them.
- **Every MR gets a pipeline under "Pipelines must succeed".** The GitLab
  template (`references/ci/gitlab-ci.yml`, also emitted by `sgt ci-init --gitlab`)
  now ships an always-green `noop` job gated only on `merge_request_event`. The
  gate jobs run only when an MR touches a governed asset; without the placeholder,
  an MR touching no governed asset produced no pipeline at all and — with branch
  protection's "Pipelines must succeed" enabled — blocked the merge forever.

### Added
- GitLab onboarding doc: "Branch protection" and "Troubleshooting" sections
  documenting the `noop` job and the WAF reset behaviour.

## [1.11.0] — 2026-06-07 — developer experience: `sgt init / uninstall / new-skill / ci-init`

Adoption-friction fixes from a real-user UX review. The `sgt` facade is now the
single entry point for the whole lifecycle, so you don't navigate a flag matrix
or remember individual scripts.

### Added
- **`sgt init`** — one guided command: detects host CLIs on PATH to suggest a
  default, asks host + scope (or `--yes` for non-interactive/CI), delegates to the
  installer, then runs an explicit install-verification step ("did it work?").
- **`sgt uninstall [--dry-run]`** — the precise inverse of install that **never
  deletes user content**: marker blocks removed content-preservingly, skills by
  toolkit INDEX name, agents/references/commands via their `.sgt-owned` sidecars,
  scripts by manifest name, and full-file copies only when byte-identical to
  source. Closes the "no clean way to undo" trust gap. `--dry-run` prints the plan.
- **`sgt new-skill <entity-action[-qualifier]> --category <vocab>`** — scaffolds a
  detect-only `SKILL.md` that is governance-clean by construction (valid
  frontmatter, naming, `Skill type` contract) and passes `audit-skill --fail-on
  medium` out of the box. Validates the name + category, refuses to overwrite.
- **`sgt ci-init --github | --gitlab`** — generates the changed-only PR/MR gate
  from the shipped template with the toolkit's current HEAD SHA and origin URL
  pre-filled, writes it to the conventional path, and prints the exact remaining
  setup (token scope, branch protection, CODEOWNERS).
- **`QUICKSTART.md`** — a one-page install → verify → author → gate → uninstall
  guide, linked from the top of the README, with a "lite adoption" path for small
  teams.

### Changed
- README now leads with the one-command setup, a before/after example, and an
  `sgt` command table; both user guides document the new commands (EN + RU).
- All new commands are covered by `test_sgt.py` (P14 self-CI), including an
  install→uninstall integration test asserting user files survive.

---

## [1.10.0] — 2026-06-07 — install-safety hardening: runtime whitelist, non-destructive upgrade, path-resolution contract

### Added
- **Runtime script whitelist** — `scripts/runtime-manifest.txt` is now the single
  source of truth for which scripts ship into an install. Only runtime/CLI/MCP
  helpers and their transitive imports are copied; dev/test/release tooling
  (`test_*.py`, `install.sh`, `sync_version.py`, `audit.sh`,
  `generate_subset_agents_md.py`) is never shipped. A `--all --project` install
  drops from 26 to 13 scripts per dir and stops scattering 45 test-file copies.
- **Path-resolution contract** — `references/path-resolution.md` defines how a
  skill resolves the install root before shelling out to a script or reading a
  shared reference: `$CLAUDE_PLUGIN_ROOT` → `$CODEX_HOME` → `$SGT_ROOT` → the
  active `AGENTS.md` dir → `$PWD`. Fixes script/reference resolution under plugin
  and global installs, where the runtime CWD is the user's project, not the
  install dir. Codex has no plugin-root variable — the contract anchors on
  `$CODEX_HOME` per the official Codex skill pattern.
- **Guard tests** (`scripts/test_install.py`) — the runtime manifest is asserted
  import-closed; every script referenced by a shipped skill/reference/agent/
  command or the Dockerfile must be whitelisted; no dev/test file may land in an
  install; runtime CLI/MCP scripts must be present after install. Plus static
  PowerShell parity guards and user-content-survival tests (global scope +
  skills tree).
- **GitHub consumer PR-gate template** — `references/ci/github-pr.yml` runs the
  changed-only gate on `pull_request`, blocks on high-severity findings, and
  surfaces every finding as an inline GitHub annotation on the PR diff (the
  GitLab template already did the equivalent via MR comment). The toolkit's own
  `.github/workflows/ci.yml` is now clearly marked self-CI, not a consumer gate.

### Fixed
- **🟠 Data loss on `--upgrade`.** Previously `rsync --delete` removed a user's
  own files from `scripts/`, `references/`, `commands/` (project root AND per-host
  dirs) on upgrade. The installer now copies these via an ownership-tracked merge
  (`.sgt-owned` sidecar): toolkit files are refreshed, files we previously shipped
  but dropped are removed, and **the user's own files are never deleted**. A user
  file colliding with one of our names is preserved — our copy lands beside it as
  `<name>.skill-governance-toolkit.<ext>` (same contract as `docs/`).
- **🔴 Release packaging.** `scripts/runtime-manifest.txt` and
  `references/path-resolution.md` — both load-bearing (the installer reads the
  manifest to decide what ships; `AGENTS.md`/`checkpointing.md` link the resolver)
  — were untracked. They are now committed so a clean checkout / archive installs.
- **Docker engine version.** The image now `COPY`s `VERSION`, so MCP/Docker audit
  reports are stamped with the real `engine_version` instead of `"unknown"`.
- **Portability.** The GitLab CI template and onboarding doc no longer embed an
  org-internal GitLab hostname — they ship a `REPLACE-WITH-YOUR-GITLAB-HOST`
  placeholder (per the AGENTS.md "no org-specific domains" rule).
- **🟠 Windows installer parity (`install.ps1`).** The native-Windows path now
  matches bash where it previously diverged:
  - **H1** — adds a `-TargetProject` parameter (and forwards `--target-project`
    to bash). Project scope now defaults to the current working directory, not
    the toolkit repo — so a Windows user can install into their own app, the
    same as `cd ~/app; .../install.sh`. Previously native-Windows project scope
    could only target the toolkit's own clone.
  - **H2** — adds the `SOURCE == TARGET_PROJECT` self-install guard. Running
    from inside the toolkit dir no longer upserts managed marker blocks into the
    toolkit's own AGENTS.md/CLAUDE.md/GEMINI.md nor scatters `.{host}/` dupes
    into the source — the same protection bash already had.
  - **H3** — skills and runtime scripts are refreshed per item instead of by
    wiping the whole managed dir. A global `upgrade` (auto-detected on re-run)
    can no longer delete the user's own skills/scripts in `~/.<host>/`.
  Static parity guards in `test_install.py` lock these in (the `$IsWindows`
  branch can't run on Linux/macOS CI, which delegates to bash).
- **CI gate fails closed on an empty `--changed-only` base.** `agent_audit.py`
  now exits 2 with a clear message when `--base` is empty (e.g. unset
  `CI_MERGE_REQUEST_DIFF_BASE_SHA`) instead of silently auditing the whole tree —
  which could block unrelated MRs on legacy assets or pass green having checked
  nothing meaningful.
- **MR-comment poster hardening (`post_mr_comment.py`).** Surfaces the GitLab
  error response body on HTTP failures (so a wrong-scope token is diagnosable),
  and escapes Markdown table cells so finding text from an audited asset cannot
  break the table or inject markup into the rendered MR note.
- **Skill path resolution.** `skill-find`, `integration-init`, `library-audit`,
  and `skill-evaluate` now point at `$SGT_ROOT/scripts/…` and
  `$SGT_ROOT/references/…` (per the new contract) instead of bare relative paths
  that break under plugin/global installs. `skill-evaluate` documents its
  Phase 3.5 dependency on the `library-audit` bundle for selective installs.
- **Doc accuracy.** Corrected stale phase counts (README library-audit "5
  phases" → P0–P6; AGENTS.md audit.sh "10 phases" → P0–P19), aligned the RU
  guide's CRG `8.2×` figure with the "external, not locally reproduced" stance,
  linked the previously-orphaned `docs/gitlab-onboarding.md`, warned that the
  manual `cp -r` install overwrites user-owned root files, and synced the
  `code-reviewer` escalation table with its empty `handoffs:` (roadmap agents
  are not dispatchable).

### Changed
- `AGENTS.md` documents the script/reference path-resolution rule and points at
  the runtime manifest.
- `install.ps1` mirrors all of the above (whitelist copy + ownership-safe merge)
  so the Windows-native path matches bash exactly.

### Upgrade notes
- No action required. The first `--upgrade` after this release stops deleting your
  own `scripts/`/`references/`/`commands/` files and trims previously-shipped
  dev/test tooling from install dirs. Skills that shell out to toolkit scripts
  should follow `references/path-resolution.md` for plugin/global installs.

---

## [1.9.0] — 2026-06-05 — governance-contract checks (SKILL021–023) + pilot-hardening + security baseline parity

### Added
- **Audit-engine governance contract checks.** The deterministic engine now
  enforces three rules that were previously documented but not checked:
  `SKILL021` (required `Skill type` declaration), `SKILL022` (explicit and
  non-contradictory clarification policy), and `SKILL023` (mutating skills
  must document preview/confirmation/verification/write scope). Behavior tests
  cover all three rules.
- **Portable clarification/sub-agent policy.** `Clarification policy` is now the
  preferred contract label (`AskUserQuestion policy` remains accepted for
  legacy skills), and `Task`/sub-agent dispatch is allowed only as an optional
  specialized path with a sequential fallback and equivalent output schema.
- **Security baseline pattern parity.** `agent_audit.py` now covers the full
  documented minimum secret/dangerous-command baseline from
  `security-spec.md`, including Slack/GitHub App/Bearer/generic secret
  patterns, credential-store paths, `.env` read attempts, disk-wipe patterns,
  and fork-bomb/block-device writes. `audit.sh` now imports the engine's
  pattern catalog instead of carrying a second regex list.

- **`marker_block` behavior tests** (`scripts/test_marker_block.py`, wired as
  `audit.sh` P19) covering the installer's "we never overwrite your files"
  guarantee: managed-block create, append-preserving-user-content, byte-for-byte
  idempotent re-run, in-place update preserving content around the markers,
  uninstall preserving user content, delete-when-only-block, and custom marker id.
- **Pilot-hardening — separation of duties.** Root `CODEOWNERS` assigns the audit
  policy, the engine, the CI gate template, and the security baseline to a
  governance owner group, so a skill author cannot change the standards that
  govern them in the same MR. `audit.sh` P18 fails if `CODEOWNERS` stops covering
  those control-plane paths. (Enforced only when branch protection requires
  code-owner approval.)
- **Pilot-hardening — config example.** `references/agent-audit-config.example.json`
  is a ready-to-copy, validated `config` block (thresholds, vocabularies,
  profiles, patterns) so orgs can adopt configurable standards without
  reverse-engineering the schema. Covered by a behavior test.
- **Pilot-hardening — CI trigger/coverage sync.** The GitLab template's `changes:`
  list now matches every governed asset type (`commands/**`, `prompts/**`,
  `.mcp.json`, `plugin.json`, `CLAUDE.md`/`GEMINI.md`, the catalog) so a governed
  file can no longer dodge the gate by placement; the toolkit is pinned by an
  immutable commit SHA (verified post-checkout) instead of a movable tag.
- **Pilot-hardening — severity floor.** `load_rule_catalog` now rejects a catalog
  that downgrades a core safety rule (SKILL001/002/009/014/015) below `high`,
  preventing accidental (or deliberate) gate-weakening when an org tunes
  severities.
- **Pilot-hardening — config validation.** `load_config` validates `thresholds`
  (positive integers) and `_compile_patterns` rejects invalid/oversized org
  regexes with a sanitized error instead of an opaque `re.error` mid-audit. The
  `rules` command now surfaces a malformed `config` block, not only the audit
  path.
- **Pilot-hardening — base-ref fallback.** `audit-project --changed-only` with an
  empty `--base` (e.g. missing `CI_MERGE_REQUEST_DIFF_BASE_SHA`) falls back to a
  full audit instead of exiting 2 — the gate fails on governance, not infra.
- **Pilot-hardening — verdict provenance.** Every `audit-skill`/`audit-project`
  report now carries `engine_version` and `rules_version`, so a verdict is
  traceable to the policy and engine that produced it.
- **Externalized audit policy** via an optional `config` block in the rule
  catalog (`references/agent-audit-rules.json`). Organizations can override
  `thresholds` (description length, body budgets), extend `vocabularies`
  (categories/tiers), redefine `profiles` (security set, quality exclusions),
  and extend `patterns` (dangerous/secret packs for SKILL014/015) — all without
  forking Python. Detection algorithms stay in code; only policy data is
  configurable. Resolved by `agent_audit.load_config()`; schema and merge
  semantics documented in `docs/checks-reference.md` § Extending the checks.
- **Audit config behavior tests** in `scripts/test_audit_config.py`, wired into
  `scripts/audit.sh` as P17.
- **`docs/checks-reference.md`** — full catalog of every governance check
  (engine rules + LLM dimensions) with rationale and an explicit
  engine-vs-LLM-depth comparison; a coverage test asserts every engine
  `rule_id` is documented.
- **`--changed-only` merge-request scope** for `agent_audit.py audit-project`.
  Diffs the working tree against `--base` (a git ref, default `origin/main`)
  via a three-dot diff and scopes findings — including DISC alias findings — to
  the changed assets only, so an MR author is accountable for the entities they
  touch. A bad or unreachable `--base` ref exits 2 with a sanitized message.
- **`references/ci/gitlab-ci.yml`** — copy-ready GitLab CI template with a
  tiered merge-request gate: a blocking `skill-gate:block` job
  (`--fail-on high`) and a non-blocking `skill-gate:advisory` job that publishes
  `skill-audit.json` and posts an MR comment.
- **`scripts/post_mr_comment.py`** — stdlib-only (`urllib`) poster that renders
  the audit JSON into a single, idempotent GitLab MR note grouped by severity,
  matched by a hidden marker so re-runs update in place. Reads the API token
  from an environment variable by name; `--dry-run` previews without the API.
- **MR comment poster behavior tests** in `scripts/test_post_mr_comment.py`,
  wired into `scripts/audit.sh` as P16.
- **`--changed-only` behavior tests** in `scripts/test_agent_audit.py` covering
  scope filtering, empty/`None` scope, the git diff helper, CLI wiring, and
  sanitized handling of an invalid base ref.
- **`scripts/doctor.py`** — quick stdlib-only health check for local
  readiness. It reports required files, Git cleanliness, `skills/INDEX.jsonl`
  freshness, skill category/tier coverage, local runtime directories, and the
  empty Python dependency contract. Supports text and JSON output.
- **Doctor behavior tests** in `scripts/test_doctor.py`, wired into
  `scripts/audit.sh` as P11.
- **`scripts/quickstart.py`** — concise next-step guide that combines the
  doctor summary with common commands and an intent-to-skill decision tree.
  JSON output is available for wrappers.
- **Quickstart behavior tests** in `scripts/test_quickstart.py`, wired into
  `scripts/audit.sh` as P12.
- **Installer dry-run plan mode** for `install.sh`, `install.ps1`, and
  `scripts/install.sh`. It resolves filters and target paths, prints planned
  project/runtime writes, and exits before mutating files.
- **Installer behavior tests** in `scripts/test_install.py`, wired into
  `scripts/audit.sh` as P13.
- **`scripts/sgt.py`** — stable stdlib-only CLI facade for common local
  workflows: `doctor`, `quickstart`, `skills`, and `audit`.
- **`sgt.py` behavior tests** in `scripts/test_sgt.py`, wired into
  `scripts/audit.sh` as P14.
- **Root `VERSION` source of truth** plus `scripts/sync_version.py` for
  derived version metadata in plugin manifests, `pyproject.toml`, and README
  install pins. `scripts/audit.sh` now checks drift as P15.
- **Version sync behavior tests** in `scripts/test_sync_version.py`.

### Changed
- **Skill contract cleanup.** `skill-evaluate` now declares its `Skill type`;
  `skill-compare` is explicitly non-interactive when inputs are missing or
  candidate selection is ambiguous; `skill-build-portable` uses a documented
  `FORCE` input and confirms only after the diff preview; `integration-init`
  now states that content inside managed marker blocks is toolkit-owned.

## [1.8.1] — 2026-05-25 — install.ps1 parity + commands/ in per-host + subset-aware AGENTS.md

Patch release. Addresses ten issues surfaced by external review of v1.8.0,
of which four were blocking Windows users and selective-install
correctness, the rest were docs / wording / link drift.

### Fixed
- **Windows install.ps1 reached parity with bash installer.** v1.8.0
  shipped without `-Category` / `-Tier` / `-Skill` / `-Interactive`
  parameters in `install.ps1`, so Windows users could not use selective
  install at all. Now: full parity. The Unix delegation path forwards
  the new flags into `install.sh`; the Windows-native path mirrors
  `resolve_skill_subset()` via `scripts/filter_skills.py`, generates
  a filtered `INDEX.jsonl` per install, and respects the same default
  tier policy (`stable,preview`). Subset-aware AGENTS.md generation is
  also wired in (see below).
- **`commands/` is now copied into per-host install dirs**
  (`.claude/`, `.codex/`, `.gemini/`, `.cursor/`). Previously only the
  project-root canonical layout received `commands/`; per-host
  installs were missing the slash-command files (e.g.
  `/integration-init`). Codex's `plugin.json` declares
  `"commands": "./commands/"` — without the dir, the slash command
  resolved to nothing on per-host installs.
- **Subset-aware `AGENTS.md` for selective installs.** When
  `--category` / `--tier` / `--skill` reduce the install to fewer
  skills than the full corpus, the marker block in the project's
  `AGENTS.md` previously still advertised all six skills, misleading
  the agent into trying to route to skills that weren't installed.
  New helper `scripts/generate_subset_agents_md.py` produces a trimmed
  copy whose skill table contains only installed rows, plus an
  explicit «Scoped install notice» listing which rows were omitted.
  Both `install.sh` and `install.ps1` use it; canonical AGENTS.md is
  unchanged on disk.
- **README + user-guide selective-install examples now match the
  shipped corpus.** v1.8.0 examples used `--category code-review` and
  `--category docs,testing` — neither category contained any skill in
  the shipped corpus (governance / discovery only), so the commands
  failed with `No skills match the filter`. Replaced with working
  examples (`discovery`, `governance`, union) and a footnote that the
  other vocab values activate when matching skills are added.
- **`audit.sh` Phase 8 now FAILS on INDEX.jsonl drift instead of
  warning.** Since 1.8.0 the installer's `--category` / `--tier` /
  `--skill` filters read this file. Stale index ⇒ wrong subset
  installed silently. CI must catch this.
- **`docs/skill-authoring-standard.md`** — three references to
  «`library-audit` Phase 8» corrected to «Phase 5.5» (matching the
  actual phase number introduced in 1.8.0).
- **`skills/library-audit/SKILL.md`** title corrected from «5-phase» to
  «6-phase» (Phase 5.5 + security baseline are no longer hidden in the
  count).
- **`agents/code-reviewer.md` handoffs** — removed dangling references
  to `test-generator` and `arch-reviewer` agents that don't exist in
  the repo. Set `handoffs: []` with a comment explaining that those
  agents are roadmap, not shipped. Re-add them in their own PR with
  end-to-end dispatch verified first.
- **`docs/user-guide.ru.md`** — fixed two broken relative links:
  `[AGENTS.md](AGENTS.md#…)` → `[AGENTS.md](../AGENTS.md#…)` and
  `[CHANGELOG.md](CHANGELOG.md)` → `[CHANGELOG.md](../CHANGELOG.md)`.
  The user-guide lives in `docs/`, so root-relative paths needed `..`.
- **`.claude-plugin/marketplace.json`** — replaced ambiguous
  `{your-org}` placeholders with explicit `REPLACE-ME-ORG` sentinels
  and added a `_NOTICE` field pointing at the new helper. New script
  `scripts/configure_org.sh` does a one-shot, validated substitution
  across `marketplace.json` and `README.md` so publishers can run
  `bash scripts/configure_org.sh acme-corp` instead of hand-editing.

### Added
- **`scripts/generate_subset_agents_md.py`** — generates a
  subset-aware copy of AGENTS.md by filtering the skill summary
  table against installed skill names. Used by both installers when
  a filter is active. Stdlib only.
- **`scripts/configure_org.sh`** — validated find-and-replace of
  `REPLACE-ME-ORG` / `{your-org}` sentinels in distribution
  manifests. `--dry-run` flag for inspection-first workflow. Rejects
  invalid GitHub usernames (anti-shell-injection sanity check).
- **Self-pollution guard in `install.sh` (two layers).** If
  TARGET_PROJECT resolves to SOURCE (user ran the installer from
  inside the toolkit dir without `--target-project=...`):
  1. `ensure_project_root_user_files` bails out instead of letting
     `marker_block.py` embed a managed block INTO the canonical
     source AGENTS.md / CLAUDE.md / GEMINI.md / copilot-instructions.md.
     This recursive self-pollution was the root cause of «full install
     showed 8 skill rows» during 1.8.1 testing — the bug had silently
     corrupted the shipped source AGENTS.md by line 230 during 1.8.0
     dev.
  2. The per-host loop (`install_claude` / `install_codex` /
     `install_gemini` / `install_cursor`) also bails — those create
     `.{host}/` subdirs and copy skills/agents/references/scripts/
     commands/ into them. Without this guard, installing into the
     source dir produced `.claude/` with a 47-file duplicate of the
     toolkit, which leaked into the published v1.8.1 zip (368K vs
     expected ~200K). A cleanup of the polluted source AGENTS.md and
     `.claude/` is bundled in this release.

### Fixed (continued — installer correctness)
- **`ensure_project_root_user_files` was aborting on a tail
  expression.** The cleanup line was `[[ ... ]] && rm -f $tmp_agents`
  — when `$tmp_agents` was unset (full install, subset path not
  taken), the `[[ -n "" ]]` part returned 1, the `&&` short-circuited,
  the function exited 1, and `set -e` killed the whole installer
  before any per-host install ran. Fix: convert the tail to a
  defensive `if` block with explicit `return 0` at function end.

### Upgrade notes
- **No breaking changes.** Existing v1.8.0 install invocations work
  identically; the new behaviours engage only on selective installs
  or on per-host installs (where the missing `commands/` was the
  bug).
- Publishers: replace the `REPLACE-ME-ORG` sentinel before tagging
  a release (`bash scripts/configure_org.sh <your-org>`). The
  marketplace manifest will not function with the sentinel left
  in place.

---

## [1.8.0] — 2026-05-25 — metainfo block + selective install + library coverage matrix

Minor release. Backward-compatible: existing `install.sh --claude --project`
flows install the same six skills as before (now via the new filter path
with `tier=stable,preview` default — which matches all current skills).

### Added
- **`metainfo:` frontmatter sub-block** (required for every SKILL.md going
  forward). Namespaced sub-field — top-level frontmatter stays reserved
  for the Agent Skills standard so portability claim and `library-audit`
  Phase 4 continue to hold. Required fields: `category` (closed vocab,
  array, 1–3 values), `tier` (enum `stable | preview | experimental |
  internal`). Optional: `owner`, `added` (ISO date), `deprecated` /
  `replaced_by`. Full spec in `docs/skill-authoring-standard.md`
  § metainfo. Applied to all 6 existing skills (all `governance` + `discovery`
  where relevant; `skill-find` / `skill-compare` carry both).
- **Closed-vocab category list:** `code-review`, `docs`, `testing`,
  `governance`, `discovery`, `research`, `delivery`. Adding a new
  category requires a CHANGELOG entry and a `library-audit` Phase 5.5
  pass. `library-audit` flags any value outside this list as drift.
- **`scripts/filter_skills.py`** — Python helper that reads
  `skills/INDEX.jsonl`, applies `--category` / `--tier` / `--skill`
  filters, and emits matching skill names. Used by `install.sh` to drive
  selective install. Also has `--list-categories` (interactive menu data
  source) and `--filtered-index` (writes filtered INDEX.jsonl to dest).
- **`install.sh` selective install flags:**
  - `--category NAME[,NAME]` — filter by `metainfo.category`. Union
    semantics (skill installed if it has ≥1 matching category).
  - `--tier NAME[,NAME]` — filter by `metainfo.tier`. Default
    `stable,preview`. `experimental` and `internal` require explicit
    opt-in.
  - `--skill NAME[,NAME]` — hard list. Overrides category and tier
    filters (explicit ⇒ user knows what they want).
  - `--interactive` — TTY-required menu showing categories with skill
    counts and tier distribution. Sets `--category` from user pick.
  - Filtered `INDEX.jsonl` is written to each install dir so
    `skill-find` in the target environment never reports skills that
    aren't installed.
- **`scripts/build_index.py`** now extracts `metainfo` into INDEX.jsonl
  entries. Inline YAML flow-style lists `[a, b]` are now parsed (needed
  for `category:` arrays). Orphan skills without `metainfo` are still
  indexed but get a sentinel `tier="unknown"` so the default install
  filter drops them — opt-in via `--tier unknown`.
- **`library-audit` Phase 5.5 — metainfo coverage.** 6 atomic checks
  (M1–M6) per skill: metainfo present (🔴), category non-empty (🔴),
  tier in enum (🔴), category in closed vocab (🟡), owner set (🟡),
  deprecation contract (🟡). Always emits a skills-by-category ×
  skills-by-tier matrix even when 0 findings.
- **`scripts/audit.sh` Phase 9** — mirrors library-audit P5.5 for the
  toolkit's own self-CI. Logs the coverage matrix on every run so any
  drift surfaces immediately in CI output.

### Changed
- **Default install behaviour:** `install.sh --claude --project` (no
  filter) now installs only `tier=stable,preview` skills, not literally
  «all skills under skills/». In the current corpus this is identical
  (all 6 skills are tier=stable), but `experimental` / `internal` skills
  added in future releases will require explicit opt-in.
- **`install.sh` install routines** (`install_claude` / `install_codex`
  / `install_gemini` / `install_cursor` /
  `ensure_project_root_canonical_dirs`) now use the new
  `_copy_filtered_skills` helper instead of `_smart_copy
  "$SOURCE/skills/" "$dest/skills/"`. Behavior unchanged when no filter
  is set, but a filtered INDEX.jsonl is always written.
- **`docs/skill-authoring-standard.md`** updated with the metainfo
  schema, closed vocab, validation rules, and a worked example.
- **`AGENTS.md`** §Skill authoring rules now mentions metainfo as
  required (rule #8) and clarifies that top-level org-specific fields
  are forbidden (everything goes under `metainfo:`).
- **README.md** gained an «Installing a subset of skills» subsection
  with command examples and the tier semantics table.
- **`docs/user-guide.ru.md`** gained Variant D — selective install
  examples in Russian.
- **`docs/architecture.md`** gained a «Skill subset selection» note
  describing the `resolve_skill_subset` → `filter_skills.py` →
  `_copy_filtered_skills` chain.

### Fixed
- `scripts/build_index.py` previously could not parse YAML flow-style
  inline arrays — `category: [a, b]` would arrive as the literal string
  `"[a, b]"`. Extended `_coerce` to recognize and split flow-style
  lists. Documented in the function docstring.

### Upgrade notes
- **No breaking changes for users.** Existing `install.sh` invocations
  produce the same result on the current corpus.
- **For skill authors:** new skills MUST include a `metainfo:` block
  (`category`, `tier`). Re-run `python3 scripts/build_index.py` after
  any frontmatter edit. `library-audit` Phase 5.5 will flag missing
  blocks in the next library audit.
- **Re-install** via `./install.sh` or `./scripts/install.sh --upgrade`
  to refresh `skills/INDEX.jsonl` in each install dir (the filtered
  index now travels with the install).

---

## [1.7.1] — 2026-05-25 — Installer & docs hygiene (post-1.7.0 review fixes)

Patch release addressing six issues surfaced by external review of v1.7.0.
No new features, no breaking changes — installer ergonomics + documentation
drift cleanup only.

### Fixed
- **`scripts/install.sh --help` now exits 0** (previously exited 1 because
  `usage()` was the only exit path). CI wrappers that conditioned on the
  exit code of `--help` no longer see a false-negative failure. Split into
  `usage()` (pure print) + `usage_and_exit STATUS` (error / help dispatch).
- **`scripts/init.sh --build-mode` now validates input.** Previously, any
  string was accepted at parse time (`--build-mode invalid` set
  `BUILD_MODE=invalid`), then the `case` in `install_crg()` had no default
  branch — so the build strategy silently disappeared after CRG was
  installed. Now: `_validate_build_mode` rejects unknown values at parse
  with exit code 2; the `case` also gained a defensive default that fails
  loudly. Interactive flow (`interactive_crg_config`) also validates.
- **`scripts/init.sh install_crg()` adds a `pipx` preflight check.**
  Previously, the CRG branch invoked `pipx install …` directly while the
  Serena branch had a `has pipx` guard (line 227). Asymmetry meant missing
  `pipx` produced a noisy late failure for CRG only. Now symmetrical:
  same hint, same early-return contract. Skipped under `--advise-only`
  and `--dry-run` (no actual install happens in those modes).
- **`scripts/install.sh --help` text corrected.** Old text claimed project
  root `AGENTS.md` is "refused if differs" and that `--force` "makes a
  `.bak`". Both predate v1.6.x — actual behaviour for the four user-owned
  root files (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`,
  `.github/copilot-instructions.md`) is marker-block upsert: content
  outside the BEGIN/END markers is preserved verbatim, no `.bak`, no
  overwrite-refusal. Help text now describes the actual contract; same
  edit applied to the file-header comment block.
- **`skills/skill-evaluate/SKILL.md` Purpose line.** Said "8 measurable
  dimensions" while frontmatter and the rest of the body already reference
  D1–D9 (D9 Safety was added in 1.6.x). Now reads "9 measurable
  dimensions (D1–D9: clarity, completeness, specificity, examples,
  constraints, portability, testability, discoverability, safety)".
- **`.github/copilot-instructions.md`** referenced a non-existent skill
  name `bootstrap-integrations` when describing the `/integration-init`
  slash command. The actual skill is `integration-init`. Updated text
  clarifies that the slash command name keeps its `/integration-init`
  form to avoid collision with Claude Code's built-in `/init`, while the
  skill name is the same as the slash command (no rename).

### Verified
- `scripts/audit.sh`: 8/8 phases pass, 0 failures / 0 warnings.
- `install.sh --help`: exit code 0 ✓
- `install.sh --bogus-flag`: exit code 1 ✓
- `init.sh --build-mode invalid`: exit code 2 with clear error ✓
- `init.sh --build-mode full-now --advise-only --with crg`: accepted ✓
- `skills/INDEX.jsonl`: hash unchanged from 1.7.0 (frontmatter not
  touched — body-only Purpose fix doesn't affect indexed fields).

### Upgrade notes
- No breaking changes. Re-install via `./install.sh` or
  `./scripts/install.sh --upgrade` to pick up the patched scripts and
  doc strings. Skill body / frontmatter contracts unchanged.

---

## [1.7.0] — 2026-05-25 — Documentation layer + skill body budgets + honest benchmarks

### Added
- **`docs/` folder** (3 new + 1 moved file) — canonical reference layer:
  - `docs/skill-authoring-standard.md` — canonical `SKILL.md` skeleton,
    body-length budget table, Detect-only vs Mutating tag rules, AskUserQuestion
    policy template, external-content trust model, cross-skill consistency
    rules. Single source of truth for «how to author a skill in this toolkit».
  - `docs/architecture.md` — three-layer model (rules / skills / sub-agents),
    SOURCE vs TARGET_PROJECT vs RUNTIME_DIR install contract, user-owned vs
    toolkit-owned files table, skill activation flow (mermaid),
    parallelization model, «why not multi-agent for skill management» FAQ.
  - `docs/benchmarks.md` — **honest benchmark posture.** Documents CRG ~8.2×
    token-reduction claim as «external upstream metric, not locally
    reproduced». Lists the structural-correctness properties that ARE
    locally verifiable via `scripts/audit.sh`. Replaces previous tendency
    to cite the 8.2× figure without caveats.
  - `docs/user-guide.ru.md` (moved from root) — Russian user guide; install,
    triggers, common workflows.
- **`scripts/audit.sh`** Phase 6 body-budget enforcement integrated into
  self-CI. CI fails if any skill body exceeds 400 lines.
- **«Skill type» + «Runtime notes» frontmatter blocks** required in every
  skill body (Detect-only vs Mutating tag, Gemini sub-agent caveat).
  Documented in `docs/skill-authoring-standard.md`. Currently informational;
  `library-audit` Phase 1 will enforce in a future release.
- **`install.sh ensure_docs_copied()`** — copies `docs/*.md` to
  `TARGET_PROJECT/docs/`. Conflict-rename semantics: if `architecture.md`
  exists in user's `docs/`, our file is renamed to
  `architecture.skill-governance-toolkit.md`. User docs are NEVER deleted
  or overwritten (verified by smoke test).

### Changed
- **All six skill bodies shrunk below the 250-line threshold.** Detail
  extracted to per-skill `references/` files (load on demand, not on
  activation). Body sizes post-1.7.0:
  | Skill | Was | Now | Delta |
  |---|---|---|---|
  | skill-evaluate     | 400 | 257 | −143 |
  | skill-find         | 295 | 191 | −104 |
  | skill-compare      | 280 | 144 | −136 |
  | library-audit      | 297 | 210 | −87  |
  | skill-build-portable | 328 | 181 | −147 |
  | integration-init   | 318 | 163 | −155 |
  Activation-time token cost ↓ ~40% across the meta-skill suite without
  losing any logic — every rule, rubric, example moved to `references/`.
- **CRG honesty pass.** README + `docs/benchmarks.md` no longer present the
  8.2× figure as «verified». Wording changed to «upstream claim — not
  reproduced locally; see docs/benchmarks.md». Aligns with the project's
  «honest portability scope» principle in §1 of README.
- **Self-CI hardened** (`scripts/audit.sh`). Phase 6 now enforces body
  budgets (target ≤ 250, fail at 400). Phase 7 secret scan unchanged
  (still 0 hits). 8/8 phases pass on this release.

### Fixed
- **`skill-evaluate` Phase 3 sub-checks extracted** to
  `references/structural-analysis.md` (previously inlined 80+ lines of
  rubric prose in body). Body now references rubric by ID.
- **`skill-find`, `skill-compare`, `library-audit`, `skill-build-portable`,
  `integration-init`** all received parallel sub-agent extraction passes —
  long catalogs, rubrics, examples moved to dedicated reference files.
  Skill body now serves as «procedure outline»; detail is loaded only
  when the agent reads the reference file mid-phase.

### Upgrade notes
- **No breaking changes for users.** All public skill triggers, output
  paths, and frontmatter contracts are unchanged.
- **For skill authors:** new authoring template at
  `docs/skill-authoring-standard.md`. Existing skills in your library
  don't need to migrate immediately — `library-audit` will continue to
  accept the pre-1.7.0 format. The «Skill type» + «Runtime notes»
  blocks become recommended in 1.7.0, enforced in a future release.
- **`docs/` install behavior:** if your project already has `docs/`
  with files we'd overwrite, OUR files are renamed
  (`{name}.skill-governance-toolkit.md`). Your originals are untouched.

---

## [1.6.2] — 2026-05-25 — Install runtime fixes + root-first layout + self-CI

### Fixed (real runtime bugs from external auditor)
- 🔴 **`scripts/init.sh run()` argument splitting broken.** Previous code
  passed commands as single quoted strings (`run "pipx install foo"`) to a
  `run()` function that calls `"$@"`. Bash treated the whole string as ONE
  command name → «command not found». User saw «Installed: crg» as success
  while nothing actually installed. **Fix:** all 11 `run` invocations now
  use separate tokens (`run pipx install foo`). Tested: `--with crg --use-cli
  --build-mode skip --advise-only` now logs correct «[would run] pipx install
  code-review-graph» — tokens preserved.
- 🔴 **--project install missing root canonical dirs.** Plugin manifests
  (`.codex-plugin/plugin.json`) reference `./skills/` relative to project
  root; Copilot/Cursor auto-discover skills/ from workspace root. But the
  installer placed skills/ ONLY at `.{host}/skills/` per-runtime, so the
  «./skills/» references in manifests pointed at nothing. **Fix:** new
  `ensure_project_root_canonical_dirs()` places skills/, agents/, references/,
  scripts/, commands/, AND manifests at TARGET_PROJECT root for --project
  scope. Per-host `.{host}/skills/` copies still made for host-specific
  conventions (Claude reads `.claude/skills/`).
- 🔴 **install.ps1 not marker-block aware.** Bash uses
  `scripts/marker_block.py` to safely upsert toolkit content between markers
  in user-owned files; PowerShell branch used raw `Copy-Item -Force`,
  destroying user content on upgrade. **Fix:** PowerShell now invokes
  `marker_block.py` via Python (auto-detects `python3` or `python`).
  Parity with Bash. Fallback to direct copy with WARN only if Python
  missing entirely.

### Added
- **`scripts/audit.sh`** — self-CI runner. 8 phases:
  - P1 bash syntax (all .sh files)
  - P2 Python helpers compile
  - P3 JSON manifest validity (4 manifests + INDEX.jsonl)
  - P4 install.sh smoke test (fresh + idempotent re-run)
  - P5 init.sh argv hygiene (no eval, no single-string run calls)
  - P6 per-skill body-length budget
  - P7 secret-pattern scan
  - P8 INDEX.jsonl freshness
  Self-dogfood: `bash scripts/audit.sh` against the toolkit itself returns
  0 warnings / 0 failures on v1.6.2.

### Known limitations (acknowledged trade-offs, not blocked)
- **Skill bodies 280–400 lines** — all 6 in budget-spec.md «review-recommended»
  zone (≤400). Auditor flagged as worth shrinking further; we keep current
  sizes because aggressive extraction degrades D8 discovery routing accuracy.
- **CRG 8.2× token-reduction claim** — externally reported by CRG project;
  no local eval artifact in toolkit. Tagged in CHANGELOG as «external claim».

### Verified
`scripts/audit.sh` self-dogfood: 8/8 PASS, 0 warnings, 0 failures.

### Upgrade from 1.6.1
- Non-destructive — `./install.sh` (or `./scripts/install.sh --upgrade`)
  picks up the run() fixes + adds root canonical dirs without overwriting
  user content (marker-block contract from 1.6.1 still in force).

---

## [1.6.1] — 2026-05-25 — Install contract rewrite + append-with-markers

### Fixed (real bugs from external tester)
- 🔴 **Quick start crash on identical-file copy.** Running `./install.sh
  --yes-default` from inside the toolkit dir failed with `cp: AGENTS.md
  and AGENTS.md are identical`. Fix: `_copy_file` and `_upsert_marker_block`
  detect `[[ "$src" -ef "$dest" ]]` and log «skipping (source==destination)»
  instead of erroring out.
- 🔴 **User content destruction risk.** Previous installer would overwrite
  `$TARGET_PROJECT/AGENTS.md` unconditionally on project install,
  wiping any user-specific project rules. **Fix:** new append-with-markers
  contract — see «Architecture» below.
- 🔴 **Single-runtime project installs missing root AGENTS.md.**
  `--copilot --project`, `--cursor --project`, `--codex --project` each
  placed only their per-host files; project root AGENTS.md (the universal
  entry point all four read natively or via @import) was absent. **Fix:**
  `ensure_project_root_user_files()` runs ONCE per install (regardless of
  which hosts are selected), upserting the four user-owned files at project
  root via marker blocks.
- 🔴 **PowerShell ↔ bash divergence.** install.ps1 only placed AGENTS.md at
  parent dir; bash put it inside `.claude/` for @import resolution. Fixed —
  PowerShell now matches bash semantics.
- 🔴 **init.sh `eval "$@"` security issue.** Was a shell-injection vector
  for crafted CLI parameters. Replaced with direct `"$@"` invocation.
- 🔴 **init.sh `set -u` crash on empty `installed=()` array.**
  `--dry-run --with serena` without pipx prereq → installs nothing →
  iterator over empty array triggered unbound variable error. Fixed with
  empty-array check before iteration.
- 🟡 **README overclaim «manifests for all five»** — actually 3 manifests
  (Claude / Codex / Gemini) + 2 native-discovery (Copilot / Cursor). README
  table now lists exactly what ships per host.

### Added — new architectural contract
- **`scripts/marker_block.py`** (~190 LoC, stdlib-only Python). Idempotent
  insert/replace/remove of a managed content block bounded by markers
  `<!-- skill-governance-toolkit: BEGIN -->` … `<!-- ... END -->`. Three
  paths: missing file → create with block; existing file no markers →
  append at end (user content preserved at top); existing file with markers
  → replace content between markers (idempotent on re-run).
- **`--target-project=PATH` flag** in `scripts/install.sh` — explicitly
  separate SOURCE (toolkit dir), TARGET_PROJECT (where YOUR code lives),
  RUNTIME_DIR (per-host install location). Default TARGET_PROJECT=cwd.

### Architecture — append-with-markers for user-owned files

The four files at `$TARGET_PROJECT` root are now USER-OWNED:
`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`.
The installer NEVER overwrites them. It manages a single named block
delimited by markers. User edits OUTSIDE the markers are preserved across:
- fresh installs (on existing user files)
- upgrades (re-runs replace only block content)
- uninstall (`marker_block.py remove` strips the block, restores user content)

Files INSIDE runtime dirs (`~/.claude/AGENTS.md`, `~/.gemini/GEMINI.md`,
etc.) remain toolkit-owned and are still full-file replaced — users don't
edit those directly.

### Verified
3 parallel sub-agents ran independent test matrices (24 scenarios total):
- 8/8 install variants PASS (5 hosts × 2 scopes + wrapper + global)
- 5/5 user-content preservation PASS (fresh / re-install / upgrade /
  contract-violation / uninstall) — «UNCONDITIONAL GREEN, ship confidently»
- 6/6 regression PASS (eval removal, empty array, source==target,
  --force, marker_block standalone, Codex agents field)

### Upgrade from 1.6.0
- The new install contract is non-destructive — re-run `./install.sh` and
  the toolkit's block auto-updates between markers; nothing else changes.
- For consumers who edited `$TARGET_PROJECT/AGENTS.md` between markers
  (against the contract): content there is overwritten on upgrade (as
  designed). Backup before upgrading if uncertain.

---

## [1.6.0] — 2026-05-25 — Stabilization release (tester findings fixed)

### Fixed
- 🔴 **scripts/init.sh promised injection it never did.** The `inject_marker_block`
  function existed but was never called from `main()`; the main loop logged
  «injecting $tool block (template TBD by user customization)» without
  actually doing anything. Documentation now matches behavior:
  - init.sh scope clarified to env-detect + native installer invocation +
    marker-block REMOVAL for deselected tools.
  - When a tool IS installed, init.sh emits an explicit warning that
    documentation injection is OUT OF SCOPE and the user must run
    `/integration-init` via the host runtime for full injection.
  - Removed the misleading «template TBD» log line.
- 🔴 **Claude global install layout was broken.** `scripts/install.sh
  install_claude()` copied `AGENTS.md` to `$(dirname "$dest")` — for global
  scope that meant `~/AGENTS.md`, but `CLAUDE.md` at `~/.claude/CLAUDE.md`
  uses `@AGENTS.md` import which resolves relative to its own location
  (`~/.claude/AGENTS.md`). The import would fail to find AGENTS.md, so
  project rules wouldn't load. **Fix:** AGENTS.md now copied to `$dest`
  (next to CLAUDE.md). For project scope, ALSO copied to project root so
  Copilot/Cursor/Codex/Gemini can read it natively from cwd.
- 🔴 **Codex manifest missing `agents` field.** `.codex-plugin/plugin.json`
  declared `skills` and `commands` but not `agents`, contradicting the
  README claim that Codex registers skills + agents from the manifest.
  Added `"agents": "./agents/"`.

### Changed
- **README portability claim refined.** Was «runs in all five environments
  without forking», now honestly scoped:
  - Core skills (6) — portable across all 5 runtimes ✓
  - Sub-agent layer (`code-reviewer.md`) — works on 4 of 5; Gemini CLI has
    no sub-agent support, requires inline fallback
  - Optional integrations — runtime detection per platform; vendor tools
    are user's responsibility

### Notes (acknowledged trade-offs, not fixed)
- **Skill body sizes** — all 6 in 279–400 line range (🟡 candidate per
  budget-spec); descriptions 532–986 chars. Reviewer flagged these as
  «overloaded vs own rules». They're within hard thresholds; further
  extraction would degrade discovery routing accuracy (D8). Documented in
  the audit as acceptable trade-off.
- **Cursor plugin manifest** — Cursor auto-discovers from AGENTS.md +
  skills/; no separate manifest shipped. For marketplace distribution
  (paid Cursor plan), a Cursor manifest would be a future addition.

### Upgrade from 1.5.8
- **MUST re-install** to pick up `install.sh` fix (AGENTS.md location).
  `./scripts/install.sh --claude --global --upgrade` (or `--project`) will
  fix existing installs. Or use `./install.sh` (interactive) with auto-detection.
- Existing Claude installs may have a stale `~/AGENTS.md` (global) or stale
  project-root `AGENTS.md` — safe to keep or remove.

---

## [1.5.8] — 2026-05-25 — Documentation consistency audit

### Fixed
- **README — repository layout tree** was stale. Now reflects current state:
  install.sh + install.ps1 at root, user-guide.ru.md, CHANGELOG.md,
  commands/integration-init.md, integration-init skill dir, assets/
  folders under skill-evaluate + library-audit, library-audit references/security-spec.md, scripts/init.sh.
- **README — skill table top description** said skill-evaluate scores
  «8 quality dimensions». Updated to 9 (D1–D9 including D9 Safety) and
  added mention of per-skill lexical security + writing-quality scan.
  library-audit description updated to include security baseline.
- **README — skill-evaluate vs library-audit table**: «8 rubrics (D1–D8)»
  → «9 rubrics (D1–D9 + safety)»; «4 rule families» → «6 categories»
  enumerated (handoff / budget / naming / portability / multi-tool /
  security); output description updated to mention 4-part blocks.
- **README — quick start** rewritten to lead with `./install.sh` /
  `./install.ps1` (the interactive root installers added in 1.5.7);
  manual `cp -r` kept as alternative with updated file list.
- **README — discovery flowchart** caption «discovery / discovery» typo
  → «discovery / governance».
- **README — skill table** «8 dimensions» → «9 dimensions» (skill-evaluate
  row).
- **AGENTS.md skills table** said skill-evaluate scores «8 quality
  dimensions». Updated to 9 + mention of lexical / writing-quality scans.
  library-audit row updated with security baseline.
- **AGENTS.md Build & Test Commands** comment: «Score one skill across 8
  dimensions» → «across 9 dimensions».
- **.github/copilot-instructions.md** said «no slash commands defined».
  Updated to document `/integration-init`.
- **skill-evaluate SKILL.md** calibration tip mentioned «D1–D8 scoring»
  → «D1–D9 scoring».
- **skill-find SKILL.md** Example 1 output showed «8 dimensions» →
  «9 dimensions, ... safety».
- **library-audit assets/output-template-detailed.md** worked example for
  naming category referenced «skill-audit» as an illustration of naming
  drift. Replaced with «skill-evaluate» (since skill-audit was renamed in
  v1.4.0, the example was confusing).
- **user-guide.ru.md architecture diagram** updated to include install.sh,
  install.ps1, CHANGELOG.md, commands/ subgraph, scripts/init.sh.
- **user-guide.ru.md install section** restructured into 3 variants
  (marketplace / interactive / advanced) matching README's structure.

### Upgrade from 1.5.7
- Documentation-only release. No semantic changes to skills or scripts.

---

## [1.5.7] — 2026-05-24 — Interactive root installers (bash + PowerShell)

### Added
- `./install.sh` at repo root — interactive one-command installer. Asks
  host + scope, auto-detects existing installs and picks the right mode
  (fresh → upgrade → force). Delegates to `scripts/install.sh` under the
  hood. Flags: `--force` (wipe + reinstall), `--yes-default` (non-interactive
  Claude + project for CI).
- `./install.ps1` at repo root — PowerShell equivalent. On Unix delegates
  to `./install.sh`; on Windows has native Copy-Item logic (no rsync
  dependency). Flags: `-Force`, `-YesDefault`.
- README — three install paths now documented:
  - Path A: `claude plugin install` (marketplace)
  - Path B: `./install.sh` interactive (recommended for newcomers)
  - Path C: `./scripts/install.sh` advanced (explicit flags)

### Verified
Smoke-tested: fresh install → re-run auto-detects → upgrade mode →
`--force` overrides to force mode. End-to-end with all 6 skills landing
in `.claude/skills/`.

### Upgrade from 1.5.6
- Existing users can keep calling `./scripts/install.sh` directly with
  flags. The new root installers are an addition, not a replacement.
- For first-time users on a fresh checkout: `./install.sh` is now the
  recommended entry point.

---

## [1.5.6] — 2026-05-24 — Rename /init slash command → /integration-init

### Changed
- 🔴 **BREAKING**: slash command `/init` renamed to `/integration-init`.
  Claude Code reserves `/init` for built-in CLAUDE.md initialization from
  codebase analysis — a fundamentally different operation. Two slash
  commands with the same trigger could collide unpredictably depending on
  load order.
- `commands/init.md` → `commands/integration-init.md` (file + frontmatter
  `name:` updated; 1:1 mapping with the skill it activates).
- Updated references in README, AGENTS.md, user-guide.ru.md, plugin.json
  description, marketplace.json command path, skill body, examples,
  code-reviewer agent comment.

### Unchanged (deliberately)
- `scripts/init.sh` filename stays — it's a bash script path, not a slash
  command. Conventional bash naming, no collision.
- Natural-language triggers for `integration-init` skill («init»,
  «initialize toolkit», «set up integrations») stay. Those are NL hints
  for skill activation, NOT slash commands. They never conflicted.

### Upgrade from 1.5.5
- Anyone with muscle-memory for `/init` (bootstrap integrations) — use
  `/integration-init` instead. Same skill activates.
- `/init` (Claude Code built-in) continues to do its original job
  (initialize CLAUDE.md). No semantic overlap any more.
- Re-install via `./scripts/install.sh --upgrade` or
  `claude plugin install`.

---

## [1.5.5] — 2026-05-24 — Fixes from real library-audit run

### Fixed
- 🔴 **library-audit Pass 1.3 self-flagging.** Added self-exclusion
  meta-rule to `references/handoff-spec.md` (analogous to Phase 5 security
  self-exclusion). `skills/library-audit/**` now exempt from Pass 1.3 — its
  body legitimately documents the detection text + has the Hard-rules forbid
  line, which naive grep was matching against itself.
- 🔴 **skill-evaluate Phase 3.5 spelling dangerous patterns inline.**
  Refactored to reference rule IDs (S1–S10, D1–D9, C1–C9) only;
  literal patterns now live ONLY in `security-spec.md` (self-excluded).
  Removes false-positive 🔴 D1/D8 findings on the skill-evaluate body.
  Reduces duplication and drift between body and canonical catalog.

### Added
- **Asymmetric handoff repairs.**
  - `skill-evaluate` Predecessor — added optional upstream from `skill-find`,
    `skill-build-portable`, `library-audit`.
  - `library-audit` Successor — added recommended follow-ups
    (`skill-evaluate`, `skill-build-portable`) as user-initiated, not
    auto-dispatched.
- **Explicit AskUserQuestion Hard-rules policy lines** in
  `skill-build-portable` (Phase 2 confirmation gate only) and `skill-find`
  (Phase 0 `NEED` elicitation only). Removes 🟡 H1.5 findings.

### Notes
- Token-budget 🟡 B2.2 (always-on 4,173 tokens) accepted as trade-off —
  trimming skill descriptions to drop tokens would hurt discovery routing
  accuracy. Description verbosity is mission-critical per D8 rubric.

### Upgrade from 1.5.4
- No semantic change. Re-install via `./scripts/install.sh --upgrade` or
  `claude plugin install`.

---

## [1.5.4] — 2026-05-24 — Parallelization guidance

### Added
- `library-audit` SKILL.md — new «Parallelization guidance» section before
  the workflow. Explicit instruction: batch independent per-skill tool calls
  in ONE message (Phases 1–5 are embarrassingly parallel within phase).
  Explicit anti-pattern: do NOT use `Task` sub-agent dispatch (breaks
  Gemini compat + fragments cross-skill insights).
- `skill-evaluate` SKILL.md — Parallelization split table per phase.
  Phase 1 (D1–D9) explicitly marked **NOT parallel** — cross-dim insights
  (D3+D4 interaction, D5 vs D9, D9 caps from 3.5, D1 caps from 3.6)
  require single-context reasoning. Phase 3 sub-checks marked **batch in
  one message**.
- `AGENTS.md` — «Parallelization patterns» section: when to batch tool
  calls, when to use Task sub-agent dispatch (only specialized expertise,
  not parallelization).

### Rationale
Existing skills relied on implicit host behavior for parallel work. Now
explicit guidance ensures consistent behavior across runtimes and preserves
cross-skill / cross-dim insights that sub-agent fragmentation would lose.

### Upgrade from 1.5.3
- No semantic change. Re-install via `./scripts/install.sh --upgrade` or
  `claude plugin install`.

---

## [1.5.3] — 2026-05-24 — Upgrade workflow + CHANGELOG

### Added
- `scripts/install.sh --upgrade` flag — rsync-with-delete mode for clean
  in-place upgrades that remove files no longer in the new version. Required
  for handling skill renames (e.g. when v1.3.0 renamed `skill-init` →
  `integration-init`, fresh `install.sh` without `--upgrade` left stale
  `skill-init/` directory behind).
- `scripts/install.sh --force` flag — wipes target dirs entirely before
  install. Most aggressive; use when `--upgrade` leaves unexpected state.
- `CHANGELOG.md` (this file) at toolkit root.
- README + user-guide.ru.md — new «Upgrading» / «Обновление версии»
  sections covering both `claude plugin` path and `install.sh` path.

### Upgrade from 1.5.2
- If installed via `claude plugin install`: standard uninstall + reinstall flow.
- If installed via `install.sh`: re-run with `--upgrade` (or `--force`).
- Neither path requires manual file cleanup.

---

## [1.5.2] — 2026-05-24 — Plugin schema compliance

### Fixed
- `.claude-plugin/marketplace.json` — `"source": "."` → `"source": "./"`
  (Claude Code schema requires trailing slash for relative paths).
- `.claude-plugin/plugin.json` — removed string-valued `skills:`/`agents:`/
  `commands:` fields. Schema expects arrays OR omitted (auto-detect from
  convention dirs `./skills/`, `./agents/`, `./commands/`).

### Upgrade from 1.5.1
- `claude plugin install` should now work out-of-the-box without manual
  manifest patching. Re-add the marketplace + reinstall.

---

## [1.5.1] — 2026-05-24 — Extraction + user guide + writing quality scan

### Added
- `user-guide.ru.md` at toolkit root — Russian-language guide with
  6 mermaid workflow diagrams and 6 use cases.
- `skills/skill-evaluate/assets/output-template-detailed.md` — full
  detailed-mode output template extracted from SKILL.md body (reduces
  body to under overload-risk threshold).
- `skills/library-audit/assets/output-template-detailed.md` — same
  extraction for the audit report.
- `skills/integration-init/references/examples.md` — three worked
  examples extracted from SKILL.md §Examples.
- `skills/skill-evaluate` **Phase 3.6 — Writing quality scan**:
  - Pass 6.1 — Language consistency (Cyrillic / CJK / Arabic detection).
  - Pass 6.2 — Filler phrase density (11 banned phrases).
  - Pass 6.3 — Duplicate paragraph detection.
  - Pass 6.4 — Long prose without list / table / heading breaks.
  - D1 score caps from findings.
- `AGENTS.md` — new «Writing Style» section codifying the rules Phase 3.6
  enforces.

### Changed
- All 6 skill bodies under the 400-line 🟡 candidate threshold (was: skill-evaluate
  at 451 🔴 overload risk).

### Upgrade from 1.5.0
- Frontmatter-only change in skill-evaluate; output format unchanged for
  `standard` and `terse` verbosity modes.

---

## [1.5.0] — 2026-05-24 — Verbose 4-part output format

### Added
- `VERBOSITY` input enum in `skill-evaluate` and `library-audit`:
  `terse` / `standard` / `detailed` (default).
- Per-dim 4-part block in `skill-evaluate` Phase 4: What we check / What
  we found / Why it matters / How to raise the score.
- Per-category 4-part block in `library-audit` Phase 6: same structure.
- Always-explain rule — even 🟢 healthy categories get «What we check / Why
  it matters» so the reader sees the auditor's scope.

### Upgrade from 1.4.1
- Default output mode is now `detailed`. To get the previous v1.4 format,
  pass `VERBOSITY=standard`.

---

## [1.4.1] — 2026-05-24 — Numbering fix + description trim

### Fixed
- `library-audit` Phase 5 passes labeled 6.1 / 6.2 / 6.3 → renumbered to
  5.1 / 5.2 / 5.3 (residual from skill-audit → library-audit rename).
- `library-audit` description 1413 chars → 986 chars (under agentskills.io
  1024-char hard limit).

---

## [1.4.0] — 2026-05-24 — D9 Safety + skill-audit rename

### Added
- **D9 — Safety / Risk Awareness** dimension in `skill-evaluate`. Scores 6
  sub-concerns: blast radius / prompt injection / sensitive data / authz /
  rollback / idempotency.
- **Phase 3.5 — Lexical security scan** in `skill-evaluate`. Per-skill
  scan reusing `library-audit/references/security-spec.md` catalog. D9
  score caps from findings.
- **Safety gate** — D9 ≤ 1 on a mutating skill forces overall verdict to
  🔴 regardless of numeric score.

### Changed
- 🔴 **BREAKING**: `skill-audit` renamed to `library-audit`. Entity now
  reflects scope (operates on the whole library, not one skill).
- Total D-score max: 40 → 45. JSONL schema adds `dims.safety` and
  `lexical_security` and `safety_gate_triggered`.

### Upgrade from 1.3.0
- Update any external invocations of `skill-audit` → `library-audit`.
- Skills with existing `out/scores/index.jsonl` entries have score
  ceilings of 40 — re-score them under v1.4 for the new 45-point ceiling.

---

## [1.3.0] — 2026-05-24 — Security + integration-init rename

### Added
- **Phase 5 — Security validation** in `library-audit` (was `skill-audit`):
  - 5.1 Secret patterns (S1–S10): API keys, private keys, Bearer tokens.
  - 5.2 Dangerous shell patterns (D1–D9): `rm -rf /`, `curl | bash`, etc.
  - 5.3 Credential file path references (C1–C9).
  - Masking of any matched secret in the report.
- Scope expansion: scans both `SKILL.md` files AND `agents/*.md`.

### Changed
- 🔴 **BREAKING**: `skill-init` renamed to `integration-init`. Entity now
  reflects scope (operates on integrations, not skills).
- Marker tokens `<!-- skill-init: ... -->` kept as-is for backward compat
  with existing AGENTS.md installations.

### Upgrade from 1.2.2
- Update any external invocations of `skill-init` → `integration-init`.
- Existing AGENTS.md marker blocks continue to work without rewrite.

---

## [1.2.2] — 2026-05-24 — Targeted fixes

### Fixed
- `init` added to closed-vocab verb list — was missing, would have failed
  self-dogfood on Phase 3 N1.
- Phase 1.3 (handoff-spec) rewritten body-based instead of frontmatter-type
  based — resolves contradiction with skill-evaluate F2 forbidding `type:`.
- `checkpoint.py` run-id microsecond precision — fixes collision under
  fast scripted invocation.
- `skill-find` Phase 1c — added tie-break for duplicate names across sources
  (project > personal > corporate).
- `integration-init` Phase 0 — prereq checks now hard-fail (not just warn)
  when a selected tool's prereq is missing.
- `skill-evaluate` Phase 3.0 — added explicit allowlist of common
  extension fields (`compatibility:`, `license:`, `portability:`).
- `install.sh` — added `rsync` availability check with `cp -R` fallback.

### Added
- Skill-evaluate Phase 4 «Rubric anchor» column — output anchors scoring to
  the exact rubric level matched.
- Skill-audit Phase 5 «Category roll-up» summary table.

---

## [1.2.1] — 2026-05-24 — D4 rubric clarification

### Fixed
- `references/rubrics.md` D4 (Examples) — added «What counts as an example»
  preamble + «D4 trap — templates ≠ examples» calibration tip.

---

## [1.2.0] — 2026-05-24 — Resumable runs + Russian removal

### Added
- `references/checkpointing.md` — canonical resumable-run state pattern.
- `scripts/checkpoint.py` — stdlib-only helper (start / save-phase /
  complete / fail / list-resumable / load).
- `## State persistence` section in 5 multi-phase skills with per-phase
  checkpoint matrix and `RESUME=auto|ask|new` modes.

### Changed
- All Russian phrases removed from SKILL.md files, references, and agents
  (was 11 hits across 7 files). Toolkit is now English-only inside skills.
  Documentation files outside `skills/` may still be multi-lingual.
- `install.sh` now copies `scripts/` and `references/` to all 4 runtimes
  (Claude / Codex / Gemini / Cursor) — earlier versions missed these.

### Upgrade from 1.1.0
- Re-run `install.sh` (no flag changes needed for fresh install in v1.2).

---

## [1.1.0] — 2026-05-23 — Code-reviewer agent + /init command

### Added
- `agents/code-reviewer.md` — TypeScript-focused reviewer with 5 categories
  and severity-tiered findings.
- `commands/init.md` — slash command for `integration-init`.
- 3 optional integrations spec: code-review-graph / repomix / serena.

---

## [1.0.0] — 2026-05-23 — Initial release

### Added
- 6 meta-skills (find / evaluate / compare / audit / build-portable / init).
- Multi-runtime manifests (Claude / Codex / Gemini / Cursor / Copilot).
- `build_index.py` for INDEX.jsonl generation.
- `install.sh` bootstrap installer.
- Universal `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` / `.github/copilot-instructions.md`.
