#!/usr/bin/env python3
"""
sgt.py - small CLI facade for common Skill Governance Toolkit tasks.

This is not a packaging layer. It is a stable stdlib-only entry point over the
existing scripts so users can discover and run the common workflows without
remembering every filename.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from doctor import print_text as print_doctor_text
from doctor import run_doctor
from quickstart import print_text as print_quickstart_text
from quickstart import build_quickstart
from marker_block import remove as remove_marker_block

# Install root (where the toolkit's own scripts/references/templates live). Distinct
# from `--root`, which is the user's project being operated on.
SGT_ROOT = Path(__file__).resolve().parents[1]

# Source of truth: docs/skill-authoring-standard.md and AGENTS.md. Kept here so the
# scaffolder fails fast on an invalid name/category without parsing the docs.
ACTION_VERBS = (
    "find", "audit", "evaluate", "compare", "build", "extend",
    "frame", "ingest", "mark", "plan", "query", "init",
)
CATEGORIES = ("code-review", "docs", "testing", "governance", "discovery", "research", "delivery")
TIERS = ("stable", "preview", "experimental", "internal")


def load_index(root: Path) -> list[dict[str, Any]]:
    index_path = root / "skills" / "INDEX.jsonl"
    entries: list[dict[str, Any]] = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def command_doctor(args: argparse.Namespace) -> int:
    report = run_doctor(args.root)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_doctor_text(report)
    return 0 if report["summary"]["passed"] else 1


def command_quickstart(args: argparse.Namespace) -> int:
    report = build_quickstart(args.root)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_quickstart_text(report)
    return 0 if report["doctor_summary"]["fail"] == 0 else 1


def command_skills(args: argparse.Namespace) -> int:
    root = args.root.expanduser().resolve()
    try:
        entries = load_index(root)
    except FileNotFoundError:
        print(f"skills/INDEX.jsonl not found under {root}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps({"root": str(root), "skills": entries}, ensure_ascii=False, indent=2))
        return 0

    print("Skills:")
    for entry in entries:
        metainfo = entry.get("metainfo") or {}
        categories = ",".join(metainfo.get("category") or [])
        tier = metainfo.get("tier", "unknown")
        print(f"  - {entry['name']} [{tier}; {categories}]")
    return 0


def command_audit(args: argparse.Namespace) -> int:
    root = args.root.expanduser().resolve()
    script = root / "scripts" / "audit.sh"
    if not script.exists():
        print(f"scripts/audit.sh not found under {root}", file=sys.stderr)
        return 1
    result = subprocess.run(["bash", str(script)], cwd=root, check=False)
    return result.returncode


def validate_skill_name(name: str) -> str | None:
    """Return an error string if `name` violates the naming convention, else None.

    Convention (AGENTS.md §6): `{entity}-{action}[-{qualifier}]`, kebab-case,
    closed-vocab action verb, ≤ 3 words after the entity (≤ 4 segments total).
    """
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+){1,3}", name):
        return (f"'{name}' is not valid: use kebab-case `entity-action[-qualifier]` "
                f"(lower-case, 2–4 segments, e.g. 'prompt-evaluate').")
    segments = name.split("-")
    action = segments[1]
    if action not in ACTION_VERBS:
        return (f"'{action}' is not an allowed action verb. The second segment must be "
                f"one of: {', '.join(ACTION_VERBS)}.")
    return None


def _scaffold_body(name: str, categories: list[str]) -> str:
    """A governance-clean, detect-only SKILL.md template that passes the engine.

    Detect-only by default: no mutation surface, no user-prompt language, so
    SKILL021 (skill-type), SKILL022 (clarification), and SKILL023 (mutating
    contract) are all satisfied out of the box.
    """
    entity = name.split("-")[0]
    return f"""---
name: {name}
description: |
  TODO one-line purpose of {name}.
  Use when the user TODO describes the trigger situation in their own words.
  Triggers: «TODO phrase one», «TODO phrase two», «TODO phrase three».
compatibility: "Claude Code · GitHub Copilot · Cursor v2.2+ · OpenAI Codex CLI · Google Gemini CLI"
license: MIT
metainfo:
  category: [{', '.join(categories)}]
  tier: preview
  owner: "TODO-your-handle"
---

# {name}

> **Skill type:** Detect-only — reads inputs and reports; never edits any source file.

## When to use

Use when TODO. Skip / Don't use for: TODO the negative triggers.

## Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| `TARGET` | string | — | TODO what this skill operates on. |

## Procedure

1. **Phase 0 — scope check.** Fail fast if `TARGET` is missing or out of scope.
2. **Phase 1 — analyze.** TODO the core read-only work.
3. **Phase 2 — report.** Emit the result; write only to the documented output path.

## Hard rules

- Detect-only: never modify `{entity}` sources. This skill is fully non-interactive.
- Bounded scope: every run must operate on an explicit `TARGET`, never «everything».

## Output

TODO describe the exact output shape (table / JSONL / report path).
"""


def command_new_skill(args: argparse.Namespace) -> int:
    name = args.name
    err = validate_skill_name(name)
    if err:
        print(f"sgt new-skill: {err}", file=sys.stderr)
        return 2
    categories = [c.strip() for c in args.category.split(",") if c.strip()]
    bad = [c for c in categories if c not in CATEGORIES]
    if not categories or bad:
        print(f"sgt new-skill: unknown category {bad or categories}. "
              f"Closed vocab: {', '.join(CATEGORIES)}.", file=sys.stderr)
        return 2

    skill_dir = (args.root.expanduser() / "skills" / name).resolve()
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists() and not args.force:
        print(f"sgt new-skill: {skill_md} already exists. Pass --force to overwrite.", file=sys.stderr)
        return 1

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md.write_text(_scaffold_body(name, categories), encoding="utf-8")
    print(f"✓ scaffolded skills/{name}/SKILL.md ({', '.join(categories)} · tier preview)")
    print("  Next:")
    print(f"    1. Fill the TODOs (description triggers, procedure, output).")
    print(f"    2. Evaluate it:  invoke skill-evaluate on skills/{name}/SKILL.md")
    print(f"    3. Re-index:     python3 {SGT_ROOT}/scripts/build_index.py")
    return 0


def _current_head_sha() -> str | None:
    """The toolkit's own HEAD commit — the immutable ref a consumer should pin."""
    try:
        out = subprocess.run(
            ["git", "-C", str(SGT_ROOT), "rev-parse", "HEAD"],
            text=True, capture_output=True, check=False,
        )
        sha = out.stdout.strip()
        return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None
    except OSError:
        return None


def _origin_url() -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(SGT_ROOT), "remote", "get-url", "origin"],
            text=True, capture_output=True, check=False,
        )
        url = out.stdout.strip()
        return url or None
    except OSError:
        return None


def command_ci_init(args: argparse.Namespace) -> int:
    if bool(args.github) == bool(args.gitlab):
        print("sgt ci-init: pass exactly one of --github or --gitlab.", file=sys.stderr)
        return 2

    platform = "github" if args.github else "gitlab"
    template = SGT_ROOT / "references" / "ci" / ("github-pr.yml" if args.github else "gitlab-ci.yml")
    if not template.exists():
        print(f"sgt ci-init: template not found at {template}", file=sys.stderr)
        return 1

    ref = args.ref or _current_head_sha()
    if not ref:
        print("sgt ci-init: could not resolve the toolkit HEAD SHA; pass --ref <40-char-sha>.",
              file=sys.stderr)
        return 1
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        print(f"sgt ci-init: --ref must be a 40-char commit SHA, got '{ref}'.", file=sys.stderr)
        return 2

    content = template.read_text(encoding="utf-8")
    content = re.sub(r'(SGT_REF:\s*")[^"]*(")', lambda m: m.group(1) + ref + m.group(2), content)
    repo = args.repo or _origin_url()
    if repo:
        content = re.sub(r'(SGT_REPO:\s*")[^"]*(")', lambda m: m.group(1) + repo + m.group(2), content)

    if args.output:
        dest = (args.root.expanduser() / args.output).resolve()
    elif args.github:
        dest = (args.root.expanduser() / ".github" / "workflows" / "skill-gate.yml").resolve()
    else:
        dest = (args.root.expanduser() / ".gitlab-ci.yml").resolve()

    if dest.exists() and not args.force:
        print(f"sgt ci-init: {dest} already exists. Pass --force to overwrite.", file=sys.stderr)
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")

    rel = dest.relative_to(args.root.expanduser().resolve()) if str(dest).startswith(
        str(args.root.expanduser().resolve())) else dest

    # ── Scaffold the rest of the control plane (F3/F4/F5) ──────────────────────
    # A correctly-gated repo also needs the suppression list and a CODEOWNERS
    # stub so the gate can't weaken itself. Scaffold both if absent; never clobber.
    target_root = args.root.expanduser().resolve()
    written: list[str] = [str(rel)]
    notes: list[str] = []

    ignore_path = target_root / "references" / "audit-ignore.json"
    if ignore_path.exists():
        notes.append("references/audit-ignore.json already present — left untouched.")
    else:
        ignore_path.parent.mkdir(parents=True, exist_ok=True)
        ignore_path.write_text(
            json.dumps({"version": "1.0", "ignores": []}, indent=2) + "\n", encoding="utf-8")
        written.append("references/audit-ignore.json")

    codeowners_path = target_root / "CODEOWNERS"
    ci_gate_rel = str(rel).replace("\\", "/")
    if codeowners_path.exists():
        notes.append("CODEOWNERS already present — left untouched; ensure it covers "
                     f"references/audit-ignore.json and {ci_gate_rel}. The rule "
                     "catalog + config overlays live in the SHA-pinned toolkit mirror "
                     "and are governed there, not in this repo.")
    else:
        codeowners_path.write_text(_codeowners_stub(ci_gate_rel), encoding="utf-8")
        written.append("CODEOWNERS")

    # ── Post-init summary ──────────────────────────────────────────────────────
    print(f"✓ wrote {platform} gate to {rel}")
    print(f"  · toolkit pinned to SGT_REF = {ref}")
    if not repo:
        print("  ! SGT_REPO left as a placeholder — set it to your toolkit mirror URL.")
    print("  Files written:")
    for w in written:
        print(f"    · {w}")
    for note in notes:
        print(f"  ! {note}")
    print("  Required setup:")
    print("    1. Replace the @security-group placeholder in CODEOWNERS with your real")
    print("       GitLab/GitHub group so suppression edits need a governance reviewer.")
    if args.gitlab:
        print("    2. Add a MASKED CI/CD variable GITLAB_TOKEN — a project/group access")
        print("       token with `api` scope (enables the idempotent MR comment).")
        print("    3. Enable \"Require approval from Code Owners\" + \"Pipelines must")
        print("       succeed\" on the protected default branch.")
    else:
        print("    2. No secret needed for the gate; GITHUB_TOKEN is read-only on fork PRs")
        print("       (annotations still render). Add a token only if you later post comments.")
        print("    3. Enable branch protection: require this check + \"Require review from")
        print("       Code Owners\" on the default branch.")
    print("    4. Verify the wiring:  sgt gate --check-setup")
    return 0


def _codeowners_stub(ci_gate_rel: str) -> str:
    """A starter CODEOWNERS covering the governance control plane present IN the
    consumer repo: the suppression list (loaded from the consumer root) and the CI
    gate. The rule catalog + config overlays are NOT gated here — they live in the
    SHA-pinned toolkit mirror and are governed there, so an MR in this repo cannot
    weaken its own gate by editing them (the engine never loads them from here).
    """
    return f"""# CODEOWNERS — separation of duties for the governance control plane.
#
# TODO: set your @security-group below. Changes to the suppression list and the
# CI gate must be reviewed by this group — not by the same author who edits a
# skill in the same change. Enforced only when branch protection requires
# code-owner approval.

# --- Suppression list (who can SILENCE a finding) ---
# audit-ignore.json loads from THIS repo's root (the audited tree), so gate it
# here — otherwise an author could self-approve silencing their own finding.
/references/audit-ignore.json        @security-group

# NOTE: the rule catalog (agent-audit-rules.json) + config overlays
# (audit-config.*.json) are NOT gated here. They live in the SHA-pinned toolkit
# mirror ($SGT_REF) and are governed there, not in this repo — the gate runs from
# the pinned toolkit dir and never loads them from the audited tree. Keeping them
# out of the audited tree also means an MR cannot self-weaken its own gate.

# --- CI gate (who can change enforcement) ---
/{ci_gate_rel}                        @security-group
"""


# ── Uninstall — the precise inverse of install, never touching user files ──────
# Host → its per-host install dir (relative to scope base).
HOST_DIRS = {"claude": ".claude", "codex": ".codex", "gemini": ".gemini",
             "cursor": ".cursor", "copilot": ".github"}
# User-owned files the installer manages via a marker block (content preserved).
MARKER_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md")
# Full-file copies the installer places; safe to remove only if byte-identical to
# our source (so a user's edited copy is never deleted). dest-rel → source-rel.
ROOT_OWNED_FILES = {
    ".codex-plugin/plugin.json": ".codex-plugin/plugin.json",
    ".claude-plugin/plugin.json": ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json": ".claude-plugin/marketplace.json",
    "gemini-extension.json": "gemini-extension.json",
}
HOST_OWNED_FILES = {
    "claude": {"CLAUDE.md": "CLAUDE.md", "AGENTS.md": "AGENTS.md"},
    "codex": {"plugin.json": ".codex-plugin/plugin.json"},
    "gemini": {"GEMINI.md": "GEMINI.md", "AGENTS.md": "AGENTS.md",
               "extension.json": "gemini-extension.json"},
    "cursor": {},
    "copilot": {},
}


def _toolkit_skill_names() -> set[str]:
    idx = SGT_ROOT / "skills" / "INDEX.jsonl"
    names: set[str] = set()
    if idx.exists():
        for line in idx.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    names.add(json.loads(line)["name"])
                except (ValueError, KeyError):
                    pass
    return names


def _runtime_script_names() -> list[str]:
    man = SGT_ROOT / "scripts" / "runtime-manifest.txt"
    out: list[str] = []
    if man.exists():
        for raw in man.read_text(encoding="utf-8").splitlines():
            name = raw.split("#", 1)[0].strip()
            if name:
                out.append(name)
    return out


def _owned_entries(d: Path) -> list[str]:
    sidecar = d / ".sgt-owned"
    if sidecar.exists():
        return [ln for ln in sidecar.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return []


def _content_matches_source(dest: Path, src_rel: str) -> bool:
    src = SGT_ROOT / src_rel
    try:
        return src.exists() and dest.read_bytes() == src.read_bytes()
    except OSError:
        return False


def _plan_install_dir(base: Path, skill_names: set[str], script_names: list[str],
                      host: str | None) -> tuple[list[Path], list[Path], list[Path]]:
    """Plan removals inside one canonical install dir (project root or a .{host}/).

    Returns (dirs_to_remove, files_to_remove, sidecars_to_remove). Only
    toolkit-owned paths are listed; anything else is left untouched.
    """
    dirs: list[Path] = []
    files: list[Path] = []
    sidecars: list[Path] = []

    for name in skill_names:
        d = base / "skills" / name
        if d.is_dir():
            dirs.append(d)
    idx = base / "skills" / "INDEX.jsonl"
    if idx.exists():
        files.append(idx)

    for sub in ("agents", "references", "commands"):
        owned = _owned_entries(base / sub)
        for rel in owned:
            p = base / sub / rel
            if p.exists():
                files.append(p)
        if owned:
            sidecars.append(base / sub / ".sgt-owned")

    for name in script_names:
        p = base / "scripts" / name
        if p.exists():
            files.append(p)

    if host is not None:
        for dest_rel, src_rel in HOST_OWNED_FILES.get(host, {}).items():
            p = base / dest_rel
            if p.exists() and _content_matches_source(p, src_rel):
                files.append(p)

    return dirs, files, sidecars


def _prune_empty_dirs(roots: list[Path]) -> list[Path]:
    pruned: list[Path] = []
    for d in roots:
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
            pruned.append(d)
    return pruned


# ── Gate — reproduce the CI block verdict locally ─────────────────────────────
# Where a consuming repo may keep its CODEOWNERS (matches the toolkit's P18 guard
# and the GitHub/GitLab/docs conventions).
CODEOWNERS_LOCATIONS = ("CODEOWNERS", ".gitlab/CODEOWNERS",
                        ".github/CODEOWNERS", "docs/CODEOWNERS")


def _find_codeowners(root: Path) -> Path | None:
    for rel in CODEOWNERS_LOCATIONS:
        p = root / rel
        if p.exists():
            return p
    return None


def _gate_check_setup(root: Path) -> int:
    """Consuming-repo counterpart to the toolkit's P18 self-CI guard.

    Verify the repo is wired so the gate cannot weaken itself: a CODEOWNERS file
    exists and covers references/audit-ignore.json (when that file is present).
    """
    codeowners = _find_codeowners(root)
    if codeowners is None:
        print("✗ gate not wired: no CODEOWNERS found "
              f"(looked in {', '.join(CODEOWNERS_LOCATIONS)}).", file=sys.stderr)
        print("  Add a CODEOWNERS rule covering references/audit-ignore.json so an MR",
              file=sys.stderr)
        print("  author can't self-approve silencing their own finding. Run: sgt ci-init.",
              file=sys.stderr)
        return 1

    ignore_present = (root / "references" / "audit-ignore.json").exists()
    if not ignore_present:
        print(f"✓ CODEOWNERS found at {codeowners.relative_to(root)} — but no "
              "references/audit-ignore.json yet.")
        print("  ! Warning: when you add a suppression list, gate it in CODEOWNERS.")
        return 0

    if "audit-ignore.json" not in _safe_read(codeowners):
        print(f"✗ {codeowners.relative_to(root)} does not cover "
              "references/audit-ignore.json.", file=sys.stderr)
        print("  Add a rule (e.g. `/references/audit-ignore.json  @security-group`) so the",
              file=sys.stderr)
        print("  suppression list needs a governance reviewer.", file=sys.stderr)
        return 1

    print(f"✓ gate wired: {codeowners.relative_to(root)} covers "
          "references/audit-ignore.json.")
    return 0


def command_gate(args: argparse.Namespace) -> int:
    root = args.root.expanduser().resolve()
    if args.check_setup:
        return _gate_check_setup(root)

    engine = SGT_ROOT / "scripts" / "agent_audit.py"
    if not engine.exists():
        print(f"sgt gate: engine not found at {engine}", file=sys.stderr)
        return 1

    # Exactly the CI block job: changed-only delta gate against --base, blocking
    # only on newly INTRODUCED high findings. Propagate the engine's exit code.
    cmd = [sys.executable, str(engine), "audit-project", str(root),
           "--changed-only", "--base", args.base, "--fail-on-new", "high",
           "--format", "text"]
    return subprocess.run(cmd, cwd=root, check=False).returncode


def command_uninstall(args: argparse.Namespace) -> int:
    hosts = list(HOST_DIRS) if args.host == "all" else [args.host]
    skill_names = _toolkit_skill_names()
    script_names = _runtime_script_names()

    all_dirs: list[Path] = []
    all_files: list[Path] = []
    all_sidecars: list[Path] = []
    marker_targets: list[Path] = []

    if args.scope == "project":
        base = Path(args.target_project or args.root).expanduser().resolve()
        d, f, s = _plan_install_dir(base, skill_names, script_names, host=None)
        all_dirs += d; all_files += f; all_sidecars += s
        for mf in MARKER_FILES:
            p = base / mf
            if p.exists() and "skill-governance-toolkit: BEGIN" in _safe_read(p):
                marker_targets.append(p)
        for dest_rel, src_rel in ROOT_OWNED_FILES.items():
            p = base / dest_rel
            if p.exists() and _content_matches_source(p, src_rel):
                all_files.append(p)
        for host in hosts:
            hb = base / HOST_DIRS[host]
            d, f, s = _plan_install_dir(hb, skill_names, script_names, host=host)
            all_dirs += d; all_files += f; all_sidecars += s
    else:  # global
        for host in hosts:
            hb = Path.home() / HOST_DIRS[host]
            d, f, s = _plan_install_dir(hb, skill_names, script_names, host=host)
            all_dirs += d; all_files += f; all_sidecars += s

    total = len(all_dirs) + len(all_files) + len(marker_targets)
    if total == 0:
        print("sgt uninstall: nothing toolkit-owned found at the given scope — nothing to do.")
        return 0

    if args.dry_run:
        print(f"── Uninstall dry-run ({args.scope}) — would remove {total} item(s); nothing written ──")
        for p in marker_targets:
            print(f"  · would remove managed block from {p} (user content preserved)")
        for d in all_dirs:
            print(f"  · would remove skill dir {d}")
        for f in all_files:
            print(f"  · would remove {f}")
        print("  Note: docs/ copies and any user files are left untouched.")
        return 0

    if not args.yes and sys.stdin.isatty():
        resp = input(f"Remove {total} toolkit-owned item(s)? This preserves your own files. [y/N] ")
        if resp.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return 1

    for p in marker_targets:
        remove_marker_block(str(p), "skill-governance-toolkit")
    for d in all_dirs:
        shutil.rmtree(d, ignore_errors=True)
    for f in all_files + all_sidecars:
        try:
            f.unlink()
        except OSError:
            pass
    # Prune now-empty toolkit dirs (skills/agents/references/scripts/commands + host dirs).
    candidate_parents = {f.parent for f in all_files} | {d.parent for d in all_dirs}
    _prune_empty_dirs(sorted(candidate_parents, key=lambda p: len(p.parts), reverse=True))

    print(f"✓ uninstalled {total} toolkit-owned item(s). Your own files were preserved.")
    print("  (docs/ copies, if any, were left in place — remove them manually if unwanted.)")
    return 0


def _safe_read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _detect_hosts() -> list[str]:
    """Which known host CLIs are on PATH — used to suggest a default in init."""
    present = []
    for host, binary in (("claude", "claude"), ("codex", "codex"),
                         ("gemini", "gemini"), ("cursor", "cursor")):
        if shutil.which(binary):
            present.append(host)
    return present


def command_init(args: argparse.Namespace) -> int:
    host, scope = args.host, args.scope
    target = Path(args.target_project or args.root).expanduser().resolve()

    interactive = not args.yes and not args.dry_run and sys.stdin.isatty()
    if interactive:
        detected = _detect_hosts()
        hint = f" (detected on PATH: {', '.join(detected)})" if detected else ""
        print("Skill Governance Toolkit — guided setup")
        default_host = detected[0] if len(detected) == 1 else "claude"
        ans = input(f"  Host [claude/copilot/codex/gemini/cursor/all]{hint} (default {default_host}): ")
        host = ans.strip() or default_host
        ans = input("  Scope [project/global] (default project): ")
        scope = ans.strip() or scope

    if host != "all" and host not in HOST_DIRS:
        print(f"sgt init: unknown host '{host}'. Choose one of {', '.join([*HOST_DIRS, 'all'])}.",
              file=sys.stderr)
        return 2

    installer = SGT_ROOT / "scripts" / "install.sh"
    if not installer.exists():
        print(f"sgt init: installer not found at {installer}", file=sys.stderr)
        return 1

    host_flag = "--all" if host == "all" else f"--{host}"
    cmd = ["bash", str(installer), host_flag, f"--{scope}"]
    if scope == "project":
        cmd.append(f"--target-project={target}")
    for flag, val in (("--category", args.category), ("--tier", args.tier), ("--skill", args.skill)):
        if val:
            cmd += [flag, val]
    if args.dry_run:
        cmd.append("--dry-run")

    print(f"── Installing ({host}, {scope}) ──")
    rc = subprocess.run(cmd, cwd=SGT_ROOT, check=False).returncode
    if rc != 0 or args.dry_run:
        return rc

    # Mandatory "did it work?" final step. We verify what the install actually
    # placed (skills + index) rather than running full `sgt doctor`, which is a
    # toolkit-checkout health check and would false-flag a normal consumer project
    # (no pyproject, not a git repo). `sgt doctor` stays available for deeper checks.
    if scope == "project":
        print("\n── Verifying install ──")
        skills_dir = target / "skills"
        installed = sorted(p.name for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.is_dir() else []
        index_ok = (skills_dir / "INDEX.jsonl").exists()
        if installed and index_ok:
            print(f"  ✓ {len(installed)} skill(s) installed: {', '.join(installed)}")
            print("  ✓ skills/INDEX.jsonl present")
            print("\n✓ Setup complete. Invoke a skill by its trigger phrase, e.g. «is there a skill for…».")
            print("  Deeper health check any time: sgt doctor")
            return 0
        print("  ! Expected skills/ with INDEX.jsonl in the target but did not find them.",
              file=sys.stderr)
        return 1

    print("\n✓ Global install complete. Verify with: sgt doctor")
    print("  Claude: invoke skill-find · Codex: codex plugins list · Gemini: gemini extensions list")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Skill Governance Toolkit command facade.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Project root to operate on.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    doctor = subcommands.add_parser("doctor", help="Run the quick local health check.")
    doctor.add_argument("--format", choices=["text", "json"], default="text")
    doctor.set_defaults(func=command_doctor)

    quickstart = subcommands.add_parser("quickstart", help="Print next steps and the intent-to-skill map.")
    quickstart.add_argument("--format", choices=["text", "json"], default="text")
    quickstart.set_defaults(func=command_quickstart)

    skills = subcommands.add_parser("skills", help="List indexed skills.")
    skills.add_argument("--format", choices=["text", "json"], default="text")
    skills.set_defaults(func=command_skills)

    audit = subcommands.add_parser("audit", help="Run the full self-audit.")
    audit.set_defaults(func=command_audit)

    new_skill = subcommands.add_parser(
        "new-skill", help="Scaffold a governance-clean SKILL.md skeleton.")
    new_skill.add_argument("name", help="Skill name: entity-action[-qualifier] (e.g. prompt-evaluate).")
    new_skill.add_argument(
        "--category", required=True,
        help=f"Comma-separated metainfo categories. Closed vocab: {', '.join(CATEGORIES)}.")
    new_skill.add_argument("--force", action="store_true", help="Overwrite an existing SKILL.md.")
    new_skill.set_defaults(func=command_new_skill)

    ci_init = subcommands.add_parser(
        "ci-init", help="Generate a changed-only PR/MR gate workflow, SHA pre-filled.")
    ci_init.add_argument("--github", action="store_true", help="Emit a GitHub Actions workflow.")
    ci_init.add_argument("--gitlab", action="store_true", help="Emit a GitLab CI pipeline.")
    ci_init.add_argument("--ref", default="", help="Toolkit commit SHA to pin (default: current HEAD).")
    ci_init.add_argument("--repo", default="", help="Toolkit repo URL (default: detected origin).")
    ci_init.add_argument("--output", default="", help="Override the output path (relative to --root).")
    ci_init.add_argument("--force", action="store_true", help="Overwrite an existing file.")
    ci_init.set_defaults(func=command_ci_init)

    gate = subcommands.add_parser(
        "gate", help="Reproduce the CI block verdict locally (changed-only delta gate).")
    gate.add_argument("--base", default="main",
                      help="Git ref to diff against for the delta gate (default: main).")
    gate.add_argument("--check-setup", action="store_true",
                      help="Verify this repo is wired for the gate (CODEOWNERS covers "
                           "the suppression list); audit nothing.")
    gate.set_defaults(func=command_gate)

    uninstall = subcommands.add_parser(
        "uninstall", help="Remove toolkit-owned files; never touches your own content.")
    uninstall.add_argument("--scope", choices=["project", "global"], default="project")
    uninstall.add_argument("--host", choices=[*HOST_DIRS, "all"], default="all")
    uninstall.add_argument("--target-project", default="",
                           help="Project to clean (project scope). Default: --root.")
    uninstall.add_argument("--dry-run", action="store_true", help="Print the plan, remove nothing.")
    uninstall.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    uninstall.set_defaults(func=command_uninstall)

    init = subcommands.add_parser(
        "init", help="Guided one-command install, then verify with doctor.")
    init.add_argument("--host", default="claude",
                      help="claude|copilot|codex|gemini|cursor|all (default claude).")
    init.add_argument("--scope", choices=["project", "global"], default="project")
    init.add_argument("--target-project", default="", help="Project to install into (project scope).")
    init.add_argument("--category", default="", help="Skill category filter (closed vocab).")
    init.add_argument("--tier", default="", help="Skill tier filter (default stable,preview).")
    init.add_argument("--skill", default="", help="Explicit skill names to install.")
    init.add_argument("--yes", action="store_true", help="Non-interactive: accept defaults.")
    init.add_argument("--dry-run", action="store_true", help="Print the install plan, write nothing.")
    init.set_defaults(func=command_init)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
