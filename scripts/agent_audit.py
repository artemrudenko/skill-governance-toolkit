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
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from build_index import FRONTMATTER_RE, parse_frontmatter


CLOSED_CATEGORIES = {"code-review", "docs", "testing", "governance", "discovery", "research", "delivery"}
CLOSED_TIERS = {"stable", "preview", "experimental", "internal"}
IGNORED_DIRS = {".git", ".skill-state", "out", "node_modules", "__pycache__"}
SEVERITIES = {"high", "medium", "low", "info"}
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
    ("rm -rf", re.compile(r"\brm\s+-rf\b"), "Avoid destructive deletion examples or require explicit confirmation."),
    ("sudo", re.compile(r"\bsudo\b"), "Avoid privileged command requirements unless scoped and justified."),
    ("chmod 777", re.compile(r"\bchmod\s+777\b"), "Avoid world-writable permission guidance."),
    ("curl pipe shell", re.compile(r"\b(curl|wget)\b[^\n|]{0,120}\|\s*(sh|bash)\b"), "Avoid pipe-to-shell installers."),
    ("eval argv", re.compile(r"\beval\s+[\"']?\$@"), "Avoid eval on user-controlled argv."),
    ("git reset hard", re.compile(r"\bgit\s+reset\s+--hard\b"), "Do not normalize destructive git reset."),
    ("force push", re.compile(r"\bgit\s+push\b[^\n]{0,80}\s--force\b"), "Avoid force push unless user explicitly approves."),
    ("approval bypass", re.compile(r"\b(bypass|skip|circumvent)\b[^\n]{0,80}\b(approval|sandbox|permission)s?\b", re.I), "Do not instruct agents to bypass approvals or sandboxes."),
]

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("OpenAI-style token", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("Anthropic token", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{32,}\b")),
    ("GitHub token", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("credential path", re.compile(r"(\.aws/credentials|\.ssh/id_[a-z0-9_]+|\.config/gh/hosts\.yml)", re.I)),
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
        if len(description) < 80:
            findings.append(
                finding("SKILL003", skill_path, line_for_regex(fm_text, r"^description\s*:", re.M), "Description is under 80 characters.", "Add 2-5 concrete trigger phrases and the main outcome.")
            )
        if len(description) > 1024:
            findings.append(
                finding("SKILL004", skill_path, line_for_regex(fm_text, r"^description\s*:", re.M), "Description exceeds 1024 characters.", "Shorten it without removing critical trigger phrases.")
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
                finding("SKILL007", skill_path, line_for_regex(fm_text, r"^metainfo\s*:", re.M), "Missing `metainfo.category`.", f"Use one or more of: {', '.join(sorted(CLOSED_CATEGORIES))}.")
            )
        else:
            cat_list = categories if isinstance(categories, list) else [categories]
            invalid = [str(cat) for cat in cat_list if str(cat) not in CLOSED_CATEGORIES]
            if invalid:
                findings.append(
                    finding("SKILL008", skill_path, line_for_regex(fm_text, r"category\s*:", re.M), f"Invalid metainfo.category value(s): {', '.join(invalid)}.", f"Use only: {', '.join(sorted(CLOSED_CATEGORIES))}.")
                )
        if not tier:
            findings.append(
                finding("SKILL007", skill_path, line_for_regex(fm_text, r"^metainfo\s*:", re.M), "Missing `metainfo.tier`.", f"Use one of: {', '.join(sorted(CLOSED_TIERS))}.")
            )
        elif str(tier) not in CLOSED_TIERS:
            findings.append(
                finding("SKILL008", skill_path, line_for_regex(fm_text, r"tier\s*:", re.M), f"Invalid metainfo.tier value: {tier}.", f"Use one of: {', '.join(sorted(CLOSED_TIERS))}.")
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
    if len(body_lines) > 600:
        message = f"Skill body has {len(body_lines)} lines, above the critical 600-line threshold."
    elif len(body_lines) > 500:
        message = f"Skill body has {len(body_lines)} lines, above the 500-line portability budget."
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

    for label, pattern, suggestion in DANGEROUS_PATTERNS:
        for match in pattern.finditer(text):
            if is_detection_context(line_text_for_offset(text, match.start())):
                continue
            findings.append(
                finding("SKILL014", skill_path, line_for_offset(text, match.start()), f"Potentially dangerous instruction detected: {label}.", suggestion)
            )

    for label, pattern in SECRET_PATTERNS:
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

    if re.search(r"\bTask\b", body) and not re.search(r"\bGemini\b[^\n]{0,120}\b(fallback|does not support|no sub-agent)", body, re.I):
        findings.append(
            finding("SKILL018", skill_path, line_for_body_regex(text, body, r"\bTask\b"), "`Task` orchestration appears without a Gemini fallback note.", "Document the linear/manual fallback for Gemini CLI users.")
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
        kept = [f for f in findings if f.rule_id in SECURITY_PROFILE_RULE_IDS]
    elif profile == "quality":
        kept = [f for f in findings if f.rule_id not in {"SKILL015"}]
    else:
        kept = findings

    return {
        "kind": "skill-audit",
        "profile": profile,
        "generated_at": utc_now(),
        "target": as_posix(skill_path),
        "summary": summarize_findings(kept),
        "findings": [asdict(f) for f in kept],
    }


def audit_project(root: str | Path = ".", profile: str = "release-ready") -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    discovery = discover_agent_assets(root_path)
    findings: list[Finding] = []
    skill_reports: list[dict[str, Any]] = []

    instruction_assets = [a for a in discovery["assets"] if a["type"] == "instructions"]
    if len(instruction_assets) > 1:
        for asset in instruction_assets:
            findings.append(
                finding("DISC001", Path(asset["path"]), 1, "Additional AGENTS.md instruction root detected.", "Confirm nested instruction scope is intentional and documented.")
            )

    for alias_name in ("CLAUDE.md", "GEMINI.md"):
        alias_path = root_path / alias_name
        if alias_path.exists():
            text = read_text(alias_path)
            if "AGENTS.md" not in text:
                findings.append(
                    finding("DISC002", alias_path, 1, f"{alias_name} does not appear to import AGENTS.md.", "Keep runtime aliases as thin imports of AGENTS.md.")
                )

    copilot_path = root_path / ".github" / "copilot-instructions.md"
    if copilot_path.exists() and "AGENTS.md" not in read_text(copilot_path):
        findings.append(
            finding("DISC002", copilot_path, 1, ".github/copilot-instructions.md does not appear to import AGENTS.md.", "Keep runtime aliases as thin imports of AGENTS.md.")
        )

    for asset in discovery["assets"]:
        if asset["type"] != "skill":
            continue
        report = audit_skill(asset["path"], profile=profile)
        skill_reports.append(report)
        findings.extend(Finding(**f) for f in report["findings"])

    return {
        "kind": "project-audit",
        "profile": profile,
        "generated_at": utc_now(),
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
            report = audit_project(args.root, profile=args.profile)
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
