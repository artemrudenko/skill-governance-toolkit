#!/usr/bin/env python3
"""
sgt.py - small CLI facade for common Skill Governance Toolkit tasks.

This is not a packaging layer. It is a stable stdlib-only entry point over the
existing scripts so users can discover and run the common workflows without
remembering every filename.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import os
from pathlib import Path
from typing import Any

from doctor import print_text as print_doctor_text
from doctor import run_doctor
from quickstart import print_text as print_quickstart_text
from quickstart import build_quickstart
from marker_block import remove as remove_marker_block
from managed_skills import INDEX_MARKER, owned_and_unchanged, owned_index_unchanged
from managed_docs import MARKER as DOCS_MARKER, load_hashes, managed_unchanged

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


def check_sarif(report: dict[str, Any]) -> dict[str, Any]:
    """Export toolkit findings; retain external check statuses as run metadata."""
    policy = report["policy"]
    levels = {"high": "error", "medium": "warning", "low": "note", "info": "note"}
    results = []
    for finding in policy["findings"]:
        results.append({
            "ruleId": finding["rule_id"],
            "level": levels.get(finding["severity"], "warning"),
            "message": {"text": finding["message"]},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": Path(finding["file"]).resolve().as_uri()},
                "region": {"startLine": max(1, int(finding.get("line") or 1))},
            }}],
            "properties": {"suggestion": finding.get("suggestion", "")},
        })
    return {"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [{"tool": {"driver": {"name": "Skill Governance Toolkit",
                                          "version": policy.get("engine_version", "unknown")}},
                      "results": results,
                      "properties": {"sha256": report["sha256"],
                                     "standard_status": report["standard"]["status"],
                                     "cisco_status": report.get("cisco", {}).get("status", "not_requested")}}]}


def command_check(args: argparse.Namespace) -> int:
    """Check a skill without installing the toolkit into the target project."""
    from agent_audit import audit_skill, should_fail

    supplied = Path(args.path).expanduser().resolve()
    skill_path = supplied / "SKILL.md" if supplied.is_dir() else supplied
    if skill_path.name != "SKILL.md" or not skill_path.is_file():
        print("sgt check: provide a skill directory or an existing SKILL.md", file=sys.stderr)
        return 2
    try:
        content = skill_path.read_bytes()
        policy = audit_skill(skill_path)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"sgt check: {exc}", file=sys.stderr)
        return 2

    executable = shutil.which("skills-ref")
    standard: dict[str, Any] = {"status": "not_checked", "reason": "skills-ref is not on PATH"}
    if executable:
        try:
            result = subprocess.run([executable, "validate", str(skill_path.parent)],
                                    capture_output=True, text=True, timeout=30, check=False)
            status = "passed" if result.returncode == 0 else "failed" if result.returncode == 1 else "error"
            standard = {"status": status,
                        "validator": "skills-ref", "exit_code": result.returncode,
                        "output": (result.stdout + result.stderr).strip()}
        except (OSError, subprocess.TimeoutExpired) as exc:
            standard = {"status": "error", "reason": str(exc)}
    report = {"target": str(skill_path), "sha256": hashlib.sha256(content).hexdigest(),
              "standard": standard, "policy": policy}
    if args.cisco:
        scanner = shutil.which("skill-scanner")
        if not scanner:
            report["cisco"] = {"status": "error", "reason": "skill-scanner is not on PATH"}
        else:
            try:
                version = subprocess.run([scanner, "--version"], capture_output=True, text=True,
                                         timeout=30, check=False)
                if version.returncode != 0 or version.stdout.strip() != "skill-scanner 2.3.2":
                    raise ValueError("unsupported Cisco scanner version; expected skill-scanner 2.3.2")
                scan = subprocess.run([scanner, "scan", str(skill_path.parent), "--format", "json"],
                                      capture_output=True, text=True, timeout=120, check=False)
                data = json.loads(scan.stdout) if scan.returncode == 0 else None
                if (not isinstance(data, dict) or not isinstance(data.get("findings"), list)
                        or data.get("findings_count") != len(data["findings"])
                        or not isinstance(data.get("analyzers_used"), list) or not data["analyzers_used"]):
                    raise ValueError("scanner returned an invalid report")
                metadata = data.get("scan_metadata") or {}
                if (metadata.get("rule_contract", {}).get("status") != "passed"
                        or metadata.get("cel", {}).get("projection_incomplete") != 0
                        or metadata.get("cel", {}).get("errors") != []):
                    raise ValueError("scanner reported an incomplete or invalid analysis")
                report["cisco"] = {"status": "completed", "version": version.stdout.strip(), "report": data}
            except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
                report["cisco"] = {"status": "error", "reason": str(exc)}
    try:
        if hashlib.sha256(skill_path.read_bytes()).hexdigest() != report["sha256"]:
            print("sgt check: target changed during inspection; rerun the check", file=sys.stderr)
            return 2
    except OSError as exc:
        print(f"sgt check: target became unavailable: {exc}", file=sys.stderr)
        return 2
    if args.format in ("json", "sarif"):
        print(json.dumps(check_sarif(report) if args.format == "sarif" else report,
                         ensure_ascii=False, indent=2))
    else:
        print(f"Standard: {standard['status']}")
        if standard.get("reason"):
            print(f"  {standard['reason']}")
        if standard.get("output"):
            print(f"  {standard['output']}")
        print(f"Toolkit policy: {policy['summary']['total']} finding(s)")
        for item in policy["findings"]:
            print(f"  {item['severity']} {item['rule_id']}: {item['message']}")
        if args.cisco:
            cisco = report["cisco"]
            print(f"Cisco scanner: {cisco['status']}")
            if cisco.get("reason"):
                print(f"  {cisco['reason']}")
            if cisco.get("report"):
                print(f"  {len(cisco['report']['findings'])} finding(s); use --format json for details")
        print(f"SHA-256: {report['sha256']}")
    if (standard["status"] == "error" or (args.require_standard and standard["status"] == "not_checked")
            or (args.cisco and report["cisco"]["status"] == "error")):
        return 2
    if standard["status"] == "failed" or should_fail(policy, args.fail_on):
        return 1
    return 0


def command_migrate_metadata(args: argparse.Namespace) -> int:
    """Preview or migrate the supported legacy frontmatter without data loss."""
    from build_index import FRONTMATTER_RE, governance_metadata, parse_frontmatter

    supplied = Path(args.path).expanduser().absolute()
    skill_path = supplied / "SKILL.md" if supplied.is_dir() else supplied
    if skill_path.is_symlink() or skill_path.name != "SKILL.md" or not skill_path.is_file():
        print("sgt migrate-metadata: provide a non-symlink SKILL.md or skill directory", file=sys.stderr)
        return 2
    try:
        original = skill_path.read_bytes().decode("utf-8")
        if "\r" in original:
            raise ValueError("CRLF input requires manual migration to preserve line endings")
        fm = parse_frontmatter(original)
        match = FRONTMATTER_RE.match(original)
        if not fm or not match or not isinstance(fm.get("metainfo"), dict):
            raise ValueError("a legacy metainfo mapping is required")
        if "metadata" in fm:
            raise ValueError("metadata already exists; merge it manually to preserve its fields")
        legacy = fm["metainfo"]
        known = {"category", "tier", "owner", "added", "deprecated", "replaced_by", "language", "requires"}
        if set(legacy) - known:
            raise ValueError("legacy metainfo has unsupported keys; migrate them manually")
        requires = legacy.get("requires")
        if requires is not None and (not isinstance(requires, dict) or set(requires) - {"mcp"}):
            raise ValueError("legacy requires has unsupported fields; migrate them manually")
        block = re.search(r"(?m)^metainfo:[ \t]*\n(?:(?:[ \t]+[^\n]*|[ \t]*)\n)*", match.group(1) + "\n")
        if block is None or "#" in block.group(0):
            raise ValueError("cannot safely migrate this metainfo block or its comments")
        for line in block.group(0).splitlines()[1:]:
            if not line.strip():
                continue
            if not (re.match(r"^  (category|tier|owner|added|deprecated|replaced_by|language|requires):", line)
                    or re.match(r"^    mcp:", line) or re.match(r"^      - ", line)):
                raise ValueError("legacy block contains unsupported syntax; migrate it manually")
        normalized = governance_metadata(fm)
        lines = ["metadata:"]
        for key in ("category", "tier", "owner", "added", "deprecated", "replaced_by", "language"):
            if key not in normalized:
                continue
            value = normalized[key]
            if key == "category":
                value = value if isinstance(value, list) else [value]
                if not all(isinstance(item, str) and "," not in item for item in value):
                    raise ValueError("unsupported category format")
                value = ", ".join(value)
            if not isinstance(value, str):
                raise ValueError(f"{key} must be a string")
            lines.append(f"  sgt-{key.replace('_', '-')}: {json.dumps(value, ensure_ascii=False)}")
        if requires and "mcp" in requires:
            servers = requires["mcp"]
            servers = servers if isinstance(servers, list) else [servers]
            if not all(isinstance(item, str) and "," not in item for item in servers):
                raise ValueError("unsupported MCP server list")
            lines.append(f'  sgt-requires-mcp: {json.dumps(", ".join(servers), ensure_ascii=False)}')
        fm_text = match.group(1) + "\n"
        updated_fm = fm_text[:block.start()] + "\n".join(lines) + "\n" + fm_text[block.end():]
        updated = "---\n" + updated_fm.rstrip("\n") + "\n---\n" + original[match.end():]
        parsed = parse_frontmatter(updated)
        expected = dict(normalized)
        if isinstance(expected.get("category"), str):
            expected["category"] = [expected["category"]]
        if requires and isinstance(requires.get("mcp"), str):
            expected["requires"] = {**requires, "mcp": [requires["mcp"]]}
        if parsed is None or "metainfo" in parsed or governance_metadata(parsed) != expected:
            raise ValueError("migration did not round-trip the original governance data")
        print("".join(difflib.unified_diff(original.splitlines(keepends=True), updated.splitlines(keepends=True),
                                          fromfile=str(skill_path), tofile=str(skill_path) + " (proposed)")), end="")
        if args.apply:
            backup = skill_path.with_name("SKILL.md.sgt-backup")
            with backup.open("x", encoding="utf-8") as stream:
                stream.write(original)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=skill_path.parent, delete=False) as stream:
                temp_path = Path(stream.name)
                stream.write(updated)
            try:
                os.chmod(temp_path, skill_path.stat().st_mode)
                os.replace(temp_path, skill_path)
            finally:
                temp_path.unlink(missing_ok=True)
            print(f"Backup: {backup}")
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"sgt migrate-metadata: {exc}", file=sys.stderr)
        return 2
    return 0


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
metadata:
  sgt-category: "{', '.join(categories)}"
  sgt-tier: "preview"
  sgt-owner: "TODO-your-handle"
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


# Dev-only files that exist ONLY in the toolkit's own source tree, never in a
# consumer install (per runtime-manifest.txt). Their presence is how we know
# SGT_ROOT is the toolkit checkout and not the user's project. Mirrors
# doctor.CHECKOUT_MARKERS.
_TOOLKIT_CHECKOUT_MARKERS = ("scripts/audit.sh", "pyproject.toml")


def _sgt_root_is_toolkit_checkout() -> bool:
    """True only when SGT_ROOT is the toolkit's own source tree. In a consumer
    install SGT_ROOT is the install dir inside the USER's project, whose git HEAD
    and origin belong to the user — pinning those into a generated gate makes every
    PR clone a SHA absent from the toolkit mirror, so the gate fails on every PR."""
    return all((SGT_ROOT / marker).exists() for marker in _TOOLKIT_CHECKOUT_MARKERS)


def _current_head_sha() -> str | None:
    """The toolkit's own HEAD commit — the immutable ref a consumer should pin.
    Returns None outside a toolkit checkout so we never pin the consumer's HEAD."""
    if not _sgt_root_is_toolkit_checkout():
        return None
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
    """The toolkit's origin — only trusted inside a checkout, for the same reason
    as _current_head_sha (a consumer's origin is the user's repo, not the toolkit)."""
    if not _sgt_root_is_toolkit_checkout():
        return None
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
        print(
            "sgt ci-init: cannot auto-resolve the toolkit's pinned SHA from a consumer\n"
            "  install (only the toolkit's own checkout exposes it — pinning this project's\n"
            "  HEAD would make every PR clone a SHA absent from the toolkit mirror).\n"
            "  Pass --ref <40-char-sha> of the toolkit release you want every PR to pin.",
            file=sys.stderr,
        )
        return 1
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        print(f"sgt ci-init: --ref must be a 40-char commit SHA, got '{ref}'.", file=sys.stderr)
        return 2

    content = template.read_text(encoding="utf-8")
    content = re.sub(r'(SGT_REF:\s*")[^"]*(")', lambda m: m.group(1) + ref + m.group(2), content)
    repo = args.repo or _origin_url()
    if repo:
        if platform == "gitlab" and repo.startswith("https://") and "@" not in repo:
            # The GitLab template clones with the per-job CI_JOB_TOKEN so a
            # private toolkit mirror needs no PAT; re-inject the auth prefix a
            # plain https origin/--repo URL would otherwise drop. URLs that
            # already carry userinfo (or use ssh) pass through untouched.
            repo = "https://gitlab-ci-token:${CI_JOB_TOKEN}@" + repo[len("https://"):]
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
        if owned_and_unchanged(d):
            dirs.append(d)
    idx = base / "skills" / "INDEX.jsonl"
    if owned_index_unchanged(base / "skills"):
        files.append(idx)
        sidecars.append(base / "skills" / INDEX_MARKER)

    # docs/ included: the installer copies toolkit docs into the project and
    # records them in docs/.sgt-owned, so uninstall removes exactly our docs and
    # never the user's — honoring "removes ONLY toolkit-owned files".
    for sub in ("agents", "references", "commands", "docs"):
        owned = _owned_entries(base / sub)
        doc_hashes = load_hashes(base / sub) if sub == "docs" else {}
        for rel in owned:
            p = base / sub / rel
            if p.exists() and (sub != "docs" or managed_unchanged(base / sub, rel, doc_hashes)):
                files.append(p)
        if owned:
            sidecars.append(base / sub / ".sgt-owned")
        if sub == "docs" and (base / sub / DOCS_MARKER).exists():
            sidecars.append(base / sub / DOCS_MARKER)

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


def _working_tree_dirty(root: Path) -> bool:
    """True if the git working tree at `root` has uncommitted changes (staged,
    unstaged, or untracked — gitignored paths excluded by porcelain). Returns
    False when `root` is not a git repo, so non-git callers are never blocked."""
    proc = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        return False
    return bool(proc.stdout.strip())


def _detect_default_base(root: Path) -> str:
    """The repo's default branch (e.g. main/master), so `sgt gate` works on a
    non-`main` repo without forcing `--base`. Falls back to 'main' if origin/HEAD
    is unset (no remote, fresh clone)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "origin/HEAD"],
            text=True, capture_output=True, check=False,
        )
        ref = out.stdout.strip()  # e.g. "origin/master"
        if out.returncode == 0 and "/" in ref:
            return ref.split("/", 1)[1]
    except OSError:
        pass
    return "main"


def command_gate(args: argparse.Namespace) -> int:
    root = args.root.expanduser().resolve()
    if args.check_setup:
        return _gate_check_setup(root)

    base = args.base or _detect_default_base(root)

    engine = SGT_ROOT / "scripts" / "agent_audit.py"
    if not engine.exists():
        print(f"sgt gate: engine not found at {engine}", file=sys.stderr)
        return 1

    # The gate audits committed HEAD only (the engine diffs `base...HEAD`), so an
    # uncommitted change is invisible. Fail-fast on a dirty tree rather than print
    # a false green the user reads as "safe to push". `--allow-dirty` opts out.
    if not args.allow_dirty and _working_tree_dirty(root):
        print(
            "sgt gate: working tree has uncommitted changes.\n"
            "  The gate audits committed HEAD only (base...HEAD diff), so these\n"
            "  changes would NOT be checked — a pass here would be misleading.\n"
            "  Commit or stash first, or pass --allow-dirty to audit HEAD anyway.",
            file=sys.stderr,
        )
        return 1

    # Exactly the CI block job: changed-only delta gate against --base, blocking
    # only on newly INTRODUCED high findings. Propagate the engine's exit code.
    cmd = [sys.executable, str(engine), "audit-project", str(root),
           "--changed-only", "--base", base, "--fail-on-new", "high",
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
            hb = Path.home() / (".copilot" if host == "copilot" else HOST_DIRS[host])
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
        print("  Note: toolkit-owned docs/ (tracked in docs/.sgt-owned) are removed; your own files are untouched.")
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
    print("  (toolkit-owned docs/ tracked in docs/.sgt-owned were removed; user docs left in place.)")
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

    check = subcommands.add_parser("check", help="Check one skill without installing into its project.")
    check.add_argument("path", help="Skill directory or SKILL.md to inspect.")
    check.add_argument("--format", choices=["text", "json", "sarif"], default="text")
    check.add_argument("--fail-on", choices=["none", "any", "low", "medium", "high"], default="none")
    check.add_argument("--require-standard", action="store_true", help="Fail if skills-ref is unavailable.")
    check.add_argument("--cisco", action="store_true", help="Also run the installed Cisco skill-scanner locally.")
    check.set_defaults(func=command_check)

    migrate = subcommands.add_parser("migrate-metadata", help="Preview migration of legacy metainfo for one skill.")
    migrate.add_argument("path", help="Skill directory or SKILL.md to migrate.")
    migrate.add_argument("--apply", action="store_true", help="Write the migration after creating a backup.")
    migrate.set_defaults(func=command_migrate_metadata)

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
    gate.add_argument("--base", default=None,
                      help="Git ref to diff against for the delta gate "
                           "(default: auto-detected default branch via origin/HEAD, else main).")
    gate.add_argument("--allow-dirty", action="store_true",
                      help="Audit committed HEAD even with uncommitted changes "
                           "(default: fail-fast on a dirty tree).")
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
