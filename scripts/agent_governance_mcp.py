#!/usr/bin/env python3
"""
agent_governance_mcp.py - stdio MCP server for agent-governance audits.

The server is read-only. It exposes deterministic discovery/audit tools and
returns structured JSON as text content so any MCP client can hand the report
to an LLM for interpretation or patch planning.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from agent_audit import audit_project, audit_skill, discover_agent_assets, explain_rule, rule_catalog


PROTOCOL_VERSION = "2024-11-05"


class InvalidParams(ValueError):
    """Raised when an MCP tool call has invalid or out-of-scope arguments."""


TOOLS: list[dict[str, Any]] = [
    {
        "name": "discover_agent_assets",
        "description": "Find AGENTS.md, SKILL.md, prompts, agent configs, runtime aliases, MCP configs, and plugin manifests in a repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string", "default": ".", "description": "Project root to scan."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "audit_skill",
        "description": "Audit one SKILL.md file for structure, metadata, portability, safety, and verification issues.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to a SKILL.md file."},
                "profile": {
                    "type": "string",
                    "enum": ["security", "quality", "maintainability", "release-ready"],
                    "default": "release-ready",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "audit_project",
        "description": "Audit all discovered skills and instruction aliases in a project. Returns structured findings with severity, file, line, rule_id, message, and suggestion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string", "default": ".", "description": "Project root to audit."},
                "profile": {
                    "type": "string",
                    "enum": ["security", "quality", "maintainability", "release-ready"],
                    "default": "release-ready",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "explain_rule",
        "description": "Explain a deterministic audit rule by rule_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "string", "description": "Rule id such as SKILL009."},
            },
            "required": ["rule_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_rule_catalog",
        "description": "Return the full deterministic audit rule catalog.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


def write_message(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def result_content(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ]
    }


def error_response(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def debug_enabled() -> bool:
    return os.environ.get("AGENT_GOVERNANCE_DEBUG") == "1"


def allowed_root() -> Path:
    raw = os.environ.get("AGENT_GOVERNANCE_ROOT") or os.getcwd()
    return Path(raw).expanduser().resolve()


def resolve_within_root(value: str | None, default: str = ".") -> str:
    root = allowed_root()
    raw = value or default
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise InvalidParams(f"Path is outside allowed root: {raw}") from exc
    return str(resolved)


def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "discover_agent_assets":
        root = resolve_within_root(arguments.get("root"), ".")
        return result_content(discover_agent_assets(root))
    if name == "audit_skill":
        if "path" not in arguments:
            raise InvalidParams("Missing required argument: path")
        path = resolve_within_root(arguments["path"])
        return result_content(audit_skill(path, profile=arguments.get("profile", "release-ready")))
    if name == "audit_project":
        root = resolve_within_root(arguments.get("root"), ".")
        return result_content(audit_project(root, profile=arguments.get("profile", "release-ready")))
    if name == "explain_rule":
        if "rule_id" not in arguments:
            raise InvalidParams("Missing required argument: rule_id")
        return result_content(explain_rule(arguments["rule_id"]))
    if name == "get_rule_catalog":
        return result_content(rule_catalog())
    raise KeyError(f"Unknown tool: {name}")


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if request_id is None and str(method).startswith("notifications/"):
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agent-governance-audit", "version": "0.1.0"},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            result = handle_tool_call(name, arguments)
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except InvalidParams as exc:
            data = traceback.format_exc(limit=4) if debug_enabled() else None
            return error_response(request_id, -32602, str(exc), data)
        except Exception as exc:  # MCP clients expect errors as JSON-RPC responses.
            data = traceback.format_exc(limit=4) if debug_enabled() else None
            return error_response(request_id, -32000, f"{exc.__class__.__name__}: {exc}", data)
    if method in {"ping", "resources/list", "prompts/list"}:
        key = "resources" if method == "resources/list" else "prompts" if method == "prompts/list" else None
        result = {key: []} if key else {}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    return error_response(request_id, -32601, f"Method not found: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            write_message(error_response(None, -32700, f"Parse error: {exc}"))
            continue

        if isinstance(request, list):
            responses = [handle_request(item) for item in request if isinstance(item, dict)]
            responses = [response for response in responses if response is not None]
            if responses:
                write_message(responses)
            continue

        if not isinstance(request, dict):
            write_message(error_response(None, -32600, "Invalid Request"))
            continue

        response = handle_request(request)
        if response is not None:
            write_message(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
