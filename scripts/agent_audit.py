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
    "SEC010": "high",
    "SEC011": "high",
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
    "SKILL012",
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
    "SEC010",
    "SEC011",
    "SEC012",
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
    ("rm -rf", re.compile(r"\brm\s+-rf\s+(?:/(?:\s|$)|\$[A-Za-z_][A-Za-z0-9_]*\b)"), "Avoid destructive deletion examples or require explicit confirmation."),
    ("sudo rm", re.compile(r"\bsudo\s+rm\b"), "Avoid privileged delete commands unless scoped and explicitly approved."),
    ("chmod 777", re.compile(r"\bchmod\s+777\s+(?!/tmp\b)"), "Avoid world-writable permission guidance outside /tmp."),
    ("curl pipe shell", re.compile(r"\b(curl|wget)\b[^\n|]{0,120}\|\s*(sh|bash)\b"), "Avoid pipe-to-shell installers."),
    ("eval argv", re.compile(r"\beval\s+(?:[\"']?\$@|\$\(|\"\$\{)"), "Avoid eval on user-controlled input."),
    ("disk wipe", re.compile(r"\bdd\s+if=/dev/(?:random|urandom|zero)\s+of=", re.I), "Avoid disk-wipe command patterns."),
    ("fork bomb", re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;?\s*:"), "Do not include executable fork-bomb patterns."),
    ("block device write", re.compile(r">\s*/dev/(?:sd[a-z]|nvme\d+n\d+|disk\d+)"), "Avoid raw block-device writes."),
    ("git reset hard", re.compile(r"\bgit\s+reset\s+--hard\b"), "Do not normalize destructive git reset."),
    ("force push", re.compile(r"\bgit\s+push\b[^\n]{0,80}\s--force\b"), "Avoid force push unless user explicitly approves."),
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


def as_posix(path: Path) -> str:
    return str(path).replace("\\", "/")


def rel_to(path: Path, root: Path) -> str:
    try:
        return as_posix(path.relative_to(root))
    except ValueError:
        return as_posix(path)


def should_skip(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


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
    return None


def discover_agent_assets(root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    assets: list[AgentAsset] = []
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
    }


def body_without_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1)


def frontmatter_text(text: str) -> str:
    match = FRONTMATTER_RE.match(text)
    return match.group(1) if match else ""


def audit_skill(path: str | Path, profile: str = "release-ready") -> dict[str, Any]:
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

    if not re.search(r"^##\s+When to use\b", body, re.I | re.M):
        findings.append(
            finding("SKILL012", skill_path, 1, "Missing canonical `## When to use` section.", "Add activation, high-impact, skip, and don't-skip criteria.")
        )

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

    if re.search(r"\bTask\b", body) and not re.search(r"\b(fallback|linear|sequential|inline)\b", body, re.I):
        findings.append(
            finding("SKILL018", skill_path, line_for_body_regex(text, body, r"\bTask\b"), "`Task` or sub-agent dispatch appears without a sequential fallback.", "Document the linear/manual fallback and ensure sub-agent dispatch is optional, not required for correctness.")
        )

    overbroad_pattern = r"\b(do anything|handle everything|all tasks|be an? universal agent|always handle|handle any request)\b"
    if re.search(overbroad_pattern, body, re.I):
        findings.append(
            finding("SKILL019", skill_path, line_for_body_regex(text, body, overbroad_pattern, re.I), "Overbroad scope language detected.", "Narrow the workflow and define skip criteria.")
        )

    if "## Predecessor" not in body and "## Successor" not in body:
        findings.append(
            finding("SKILL020", skill_path, 1, "No predecessor/successor workflow contract detected.", "Consider documenting adjacent skills or handoff points.")
        )

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
        "findings": [asdict(f) for f in kept],
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


def scan_hidden_chars(text: str, path: Path) -> list[Finding]:
    """Stub filled in by a later task (A1). Returns no findings for now."""
    return []


def scan_security(text: str, path: Path, *, dangerous_id: str, secret_id: str, prose: bool = True) -> list[Finding]:
    """Reusable secret + dangerous scan for any asset body. For non-prose assets
    (mcp/plugin/hook/script) the is_detection_context exemption is disabled."""
    cfg = load_config()
    out: list[Finding] = []
    for label, pattern, suggestion in cfg["dangerous_patterns"]:
        for m in pattern.finditer(text):
            if prose and is_detection_context(line_text_for_offset(text, m.start())):
                continue
            out.append(finding(dangerous_id, path, line_for_offset(text, m.start()),
                               f"Potentially dangerous instruction detected: {label}.", suggestion))
    for label, pattern in cfg["secret_patterns"]:
        for m in pattern.finditer(text):
            if prose and is_detection_context(line_text_for_offset(text, m.start())):
                continue
            # Split credential-PATH matches (medium SEC012) from inline-secret values (high SEC011).
            rid = "SEC012" if (secret_id == "SEC011" and _is_credential_path_label(label)) else secret_id
            sugg = ("Reference credential files by documented config, not inline."
                    if rid == "SEC012" else
                    "Remove inline secrets and refer to environment variable names only.")
            out.append(finding(rid, path, line_for_offset(text, m.start()),
                               f"Potential secret or credential reference detected: {label}.", sugg))
    return out


def checks_for(asset_type_name: str):
    """Return [(text, path)->[Finding]] callables for an asset type. scan_hidden_chars
    runs on EVERY non-skill type; the security scan runs on config/agent/hook/script."""
    default = [lambda text, path: scan_hidden_chars(text, path)]
    security_types = {"mcp-config", "plugin-config", "agent", "runtime-config", "command", "prompt"}
    if asset_type_name in security_types:
        return default + [lambda text, path: scan_security(text, path, dangerous_id="SEC010",
                                                           secret_id="SEC011", prose=False)]
    return default


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
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _in_scope(relative_path: str, changed_paths: set[str] | None) -> bool:
    """Whole-repo audit when changed_paths is None; otherwise scope to the set."""
    return changed_paths is None or relative_path in changed_paths


def audit_project(
    root: str | Path = ".",
    profile: str = "release-ready",
    changed_paths: set[str] | None = None,
) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    discovery = discover_agent_assets(root_path)
    findings: list[Finding] = []
    skill_reports: list[dict[str, Any]] = []

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
        report = audit_skill(asset["path"], profile=profile)
        skill_reports.append(report)
        findings.extend(Finding(**f) for f in report["findings"])

    for asset in discovery["assets"]:
        if asset["type"] == "skill":
            continue
        if not _in_scope(asset["relative_path"], changed_paths):
            continue
        text = safe_read_asset(Path(asset["path"]), root_path)
        if text is None:
            continue
        for check in checks_for(asset["type"]):
            findings.extend(check(text, Path(asset["path"])))

    return {
        "kind": "project-audit",
        "profile": profile,
        "generated_at": utc_now(),
        "engine_version": engine_version(),
        "rules_version": load_rule_catalog()["version"],
        "root": as_posix(root_path),
        "discovery": discovery,
        "summary": summarize_findings(findings),
        "findings": [asdict(f) for f in findings],
        "skill_reports": skill_reports,
    }


def summarize_findings(findings: list[Finding]) -> dict[str, Any]:
    counts = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for item in findings:
        counts[item.severity] = counts.get(item.severity, 0) + 1
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


def rule_catalog() -> dict[str, Any]:
    catalog = load_rule_catalog()
    load_config()  # surface a malformed `config` block here, not only on the audit path
    return {
        "generated_at": utc_now(),
        "version": catalog["version"],
        "source": "references/agent-audit-rules.json",
        "rules": catalog["rules"],
    }


def print_text_report(report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    print(f"{report.get('kind', 'audit')} ({report.get('profile', 'default')})")
    print(f"Target: {report.get('target') or report.get('root')}")
    print(f"Findings: {summary.get('total', 0)}")
    for severity, count in (summary.get("by_severity") or {}).items():
        if count:
            print(f"  {severity}: {count}")
    for item in report.get("findings", []):
        print("")
        print(f"[{item['severity'].upper()}] {item['rule_id']} {item['file']}:{item['line']}")
        print(f"  {item['message']}")
        print(f"  Suggestion: {item['suggestion']}")


def emit(data: dict[str, Any], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if data.get("kind") in {"project-audit", "skill-audit"}:
            print_text_report(data)
        elif "assets" in data:
            print(f"Discovered {len(data['assets'])} agent asset(s) under {data['root']}")
            for asset in data["assets"]:
                print(f"{asset['type']}\t{asset['relative_path']}")
        elif "rules" in data:
            for rule in data["rules"]:
                print(f"{rule['rule_id']}\t{rule['severity']}\t{rule['title']}")
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover and audit agent-governance assets.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    sub = parser.add_subparsers(dest="command", required=True)

    p_discover = sub.add_parser("discover", help="Discover agent assets in a project.")
    p_discover.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)
    p_discover.add_argument("root", nargs="?", default=".")

    p_project = sub.add_parser("audit-project", help="Audit all discovered skills and instruction aliases.")
    p_project.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)
    p_project.add_argument("root", nargs="?", default=".")
    p_project.add_argument("--profile", choices=["security", "quality", "maintainability", "release-ready"], default="release-ready")
    p_project.add_argument("--fail-on", choices=["none", "high", "medium", "low", "info", "any"], default="none", help="Exit 1 when findings meet or exceed this severity.")
    p_project.add_argument("--changed-only", action="store_true", help="Audit only assets changed against --base (merge request scope).")
    p_project.add_argument("--base", default="origin/main", help="Git ref to diff against when --changed-only is set.")

    p_skill = sub.add_parser("audit-skill", help="Audit one SKILL.md file.")
    p_skill.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)
    p_skill.add_argument("path")
    p_skill.add_argument("--profile", choices=["security", "quality", "maintainability", "release-ready"], default="release-ready")
    p_skill.add_argument("--fail-on", choices=["none", "high", "medium", "low", "info", "any"], default="none", help="Exit 1 when findings meet or exceed this severity.")

    p_rule = sub.add_parser("explain-rule", help="Explain one rule.")
    p_rule.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)
    p_rule.add_argument("rule_id")

    p_rules = sub.add_parser("rules", help="List rule catalog.")
    p_rules.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)

    args = parser.parse_args(argv)

    try:
        if args.command == "discover":
            emit(discover_agent_assets(args.root), args.format)
        elif args.command == "audit-project":
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
            report = audit_project(args.root, profile=args.profile, changed_paths=changed_paths)
            emit(report, args.format)
            if should_fail(report, args.fail_on):
                return 1
        elif args.command == "audit-skill":
            report = audit_skill(args.path, profile=args.profile)
            emit(report, args.format)
            if should_fail(report, args.fail_on):
                return 1
        elif args.command == "explain-rule":
            emit(explain_rule(args.rule_id), args.format)
        elif args.command == "rules":
            emit(rule_catalog(), args.format)
        else:
            parser.error(f"unknown command: {args.command}")
    except (FileNotFoundError, KeyError, OSError, UnicodeError, ValueError) as exc:
        print(f"agent_audit: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
