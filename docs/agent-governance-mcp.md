# Agent Governance CLI, MCP, and Docker

This repository includes a deterministic read-only audit engine for agent
assets. It is intentionally split into three layers:

| Layer | Entrypoint | Purpose |
|---|---|---|
| Core + CLI | `scripts/agent_audit.py` | Local and CI discovery/audit commands |
| MCP stdio server | `scripts/agent_governance_mcp.py` | Tool calls from Codex, Claude Desktop, Cursor, VS Code agents, or other MCP clients |
| Docker runner | `Dockerfile` | Reproducible local/CI execution with a read-only project mount |
| Rule catalog | `references/agent-audit-rules.json` | Shared rule metadata returned by CLI/MCP |

## CLI

```bash
python3 scripts/agent_audit.py discover .
python3 scripts/agent_audit.py audit-skill skills/skill-evaluate/SKILL.md --format json
python3 scripts/agent_audit.py audit-project . --profile release-ready --format json
python3 scripts/agent_audit.py audit-project . --profile release-ready --fail-on high
python3 scripts/agent_audit.py rules
python3 scripts/agent_audit.py explain-rule SKILL009
```

Profiles:

| Profile | Use |
|---|---|
| `security` | Focus on tool safety, destructive commands, secrets, external trust, hardcoded paths |
| `quality` | Skill structure and usability checks |
| `maintainability` | Full rule set, same current behavior as release-ready |
| `release-ready` | Full rule set for pre-release audits |

The JSON report contains:

```json
{
  "summary": {"total": 1, "by_severity": {"high": 1}},
  "findings": [
    {
      "severity": "high",
      "rule_id": "SKILL009",
      "file": "/repo/skills/example/SKILL.md",
      "line": 4,
      "message": "allowed-tools appears in frontmatter.",
      "suggestion": "Remove it and document tool restrictions in the body as guidance."
    }
  ]
}
```

## MCP server

The MCP server exposes these read-only tools:

| Tool | Purpose |
|---|---|
| `discover_agent_assets` | Find `AGENTS.md`, `SKILL.md`, prompts, agent configs, runtime aliases, MCP configs, and plugin manifests |
| `audit_skill` | Audit one `SKILL.md` |
| `audit_project` | Audit all discovered skills and instruction aliases |
| `explain_rule` | Explain one rule by `rule_id` |
| `get_rule_catalog` | Return the full rule catalog |

Example MCP client config:

```json
{
  "mcpServers": {
    "agent-governance": {
      "command": "python3",
      "args": ["/path/to/skill-governance-toolkit/scripts/agent_governance_mcp.py"],
      "env": {
        "AGENT_GOVERNANCE_ROOT": "/path/to/project"
      }
    }
  }
}
```

By default, the MCP server accepts only paths under its process working
directory. Set `AGENT_GOVERNANCE_ROOT` to make that boundary explicit.
Set `AGENT_GOVERNANCE_DEBUG=1` only while debugging; otherwise MCP errors are
sanitized and do not include tracebacks.

The public rule metadata is loaded from
`references/agent-audit-rules.json`. Set `AGENT_GOVERNANCE_RULES_PATH` to test
or ship a different catalog without editing Python code. Override catalogs must
define every `rule_id` used by the engine; missing IDs fail startup instead of
silently weakening audits.

## Docker

Build the image:

```bash
docker build -t agent-governance-mcp:local .
```

Run as a stdio MCP server against the current project:

```bash
docker run --rm -i \
  --network none \
  -v "$PWD:/workspace:ro" \
  agent-governance-mcp:local
```

The image runs as a non-root user. If your CI checkout uses restrictive file
permissions, run with the host UID/GID:

```bash
docker run --rm -i \
  --network none \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace:ro" \
  agent-governance-mcp:local
```

Example MCP client config using Docker:

```json
{
  "mcpServers": {
    "agent-governance": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "-v",
        "/path/to/repo:/workspace:ro",
        "agent-governance-mcp:local"
      ]
    }
  }
}
```

Inside Docker, pass `root` as `/workspace`.

## GitHub Actions

The repository includes `.github/workflows/ci.yml` with two baseline jobs:

| Job | Checks |
|---|---|
| `audit` | `scripts/audit.sh`, audit-engine behavior tests, and `release-ready` CLI gate |
| `docker` | Docker build, MCP `tools/list`, and Docker `audit_project /workspace` |

For local reproduction, run the commands in `docs/user-guide.md` or
`docs/user-guide.ru.md` under the component status section.

## Design constraints

- Read-only by default.
- No network required.
- No pip dependencies.
- No automatic patch application.
- LLM agents interpret findings and decide whether to propose edits.
- Rule metadata lives in `references/agent-audit-rules.json`; detector logic
  stays in stdlib Python.
