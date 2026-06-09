#!/usr/bin/env python3
"""secret-guard-hook.py — opt-in Claude Code PreToolUse hook (DEFENSE-IN-DEPTH).

⚠ THIS IS NOT A SECURITY BOUNDARY. It is a best-effort tripwire that catches the
most obvious secret-read / secret-exfiltration shell commands a misbehaving skill
or agent might run. A determined skill can trivially bypass it — e.g. by reading
the same file from Python, base64-encoding the path, or shelling out indirectly.

Installing this hook does NOT relax any governance rule. The SEC / SCR / HOOK
audit gates (agent_audit.py) remain the authoritative control surface; this hook
is an extra layer, not a replacement. Do not weaken a gate "because the hook will
catch it" — it will not.

Contract (Claude Code PreToolUse):
  · STDIN  — a JSON object describing the tool call. For Bash, the shape is
             {"tool_name": "Bash", "tool_input": {"command": "..."}}. The exact
             shape may vary across versions — this hook reads defensively and
             allows anything it cannot parse.
  · exit 0 — allow the tool call.
  · exit 2 — BLOCK the tool call; the stderr message is surfaced to the user/agent.

Behavior:
  · Inspects Bash command strings only. Non-Bash tools → allow.
  · BLOCKS when a command reads sensitive material (~/.aws/credentials, ~/.ssh/id_*,
    ~/.kube/config, .env files) or dumps secret-looking env vars (printenv/env), and
    ESPECIALLY when any of those is piped into a network tool (curl/wget/nc/...).
  · REDACTS every matched secret-shaped substring before echoing the command to
    stderr — never prints a matched token/path verbatim (leak-guard).
  · Extensible guarded paths via the SGT_GUARD_PATHS env var (colon- OR
    comma-separated). Defaults are sensible when unset.
  · Never crashes on malformed/empty input — fails open (allow).

stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import sys

# ── Default guarded path fragments ───────────────────────────────────────────
# Matched as substrings against the command. `~` and `$HOME` variants both
# resolved so `cat ~/.aws/credentials` and `cat $HOME/.aws/credentials` both hit.
DEFAULT_GUARD_FRAGMENTS: tuple[str, ...] = (
    ".aws/credentials",
    ".aws/config",
    ".ssh/id_",          # id_rsa, id_ed25519, id_dsa, ...
    ".kube/config",
    ".docker/config.json",
    ".netrc",
    ".npmrc",
    ".pgpass",
    "gcloud/credentials",
    ".config/gh/hosts.yml",
)

# .env-family file reads (e.g. `cat .env`, `cat .env.production`). Kept separate
# so we can match the filename token precisely without flagging unrelated text.
DOTENV_RE = re.compile(r"(^|[\s=/'\"`])\.env(\.[\w.-]+)?\b")

# Network/exfil tools — presence alongside a secret read escalates confidence,
# and `printenv | curl` style env-dump-to-network is blocked on its own.
NETWORK_TOOLS_RE = re.compile(
    r"\b(curl|wget|nc|ncat|netcat|telnet|scp|sftp|ftp|httpie|http)\b"
)

# Env-dump commands that expose the whole environment (secrets included).
# `printenv` is distinctive enough to match anywhere; the bare `env` token must
# sit in COMMAND position (start of string, or after ; & | $( `) and not be a
# path component like `env/bin/activate` — hence the `(?!/)` guard.
ENV_DUMP_RE = re.compile(r"\bprintenv\b|(?:^|[;&|]|\$\(|`)\s*env\b(?!/)")

# Secret-looking env var names (best-effort) — `echo $AWS_SECRET_ACCESS_KEY`,
# `printenv GITHUB_TOKEN`, `curl x?d=$my_secret_token`. Case-insensitive: a
# lowercase/mixed-case name is the same secret shape, just spelled small.
SECRET_VAR_RE = re.compile(
    r"\b[A-Z0-9_]*(SECRET|TOKEN|PASSWORD|PASSWD|API[_-]?KEY|PRIVATE[_-]?KEY|"
    r"ACCESS[_-]?KEY|CREDENTIAL)[A-Z0-9_]*\b",
    re.IGNORECASE,
)


def guard_fragments() -> list[str]:
    """Default guarded fragments plus any from SGT_GUARD_PATHS (colon/comma-sep)."""
    fragments = list(DEFAULT_GUARD_FRAGMENTS)
    extra = os.environ.get("SGT_GUARD_PATHS", "").strip()
    if extra:
        # Accept both ':' and ',' as separators; ignore empties/whitespace.
        for token in re.split(r"[:,]", extra):
            token = token.strip()
            if token:
                fragments.append(token)
    return fragments


def redact(command: str, secrets: list[str]) -> str:
    """Mask each matched secret substring in `command` so it never leaks to logs.

    Keeps a short prefix for human recognizability, masks the rest. Longer
    secrets keep at most 4 leading chars; short ones are fully masked.
    """
    masked = command
    # Replace longest-first to avoid partial-overlap artifacts.
    for secret in sorted(set(secrets), key=len, reverse=True):
        if not secret:
            continue
        keep = 4 if len(secret) > 6 else 0
        replacement = secret[:keep] + "***REDACTED***"
        masked = masked.replace(secret, replacement)
    return masked


def detect(command: str) -> tuple[bool, list[str], str]:
    """Inspect a Bash command. Return (blocked, matched_secrets, reason)."""
    matches: list[str] = []
    reasons: list[str] = []

    # 1) Guarded path fragments (credentials, keys, kube/docker config, ...).
    for fragment in guard_fragments():
        if fragment and fragment in command:
            matches.append(fragment)
            reasons.append("reads a guarded credential path")

    # 2) .env-family file reads.
    dotenv = DOTENV_RE.search(command)
    if dotenv:
        matches.append(dotenv.group(0).strip())
        reasons.append("reads a .env secret file")

    has_network = bool(NETWORK_TOOLS_RE.search(command))
    has_env_dump = bool(ENV_DUMP_RE.search(command))
    secret_vars = SECRET_VAR_RE.findall(command)

    # 3) Whole-environment dump piped to the network (printenv | curl ...).
    if has_env_dump and has_network:
        reasons.append("pipes the environment to a network tool")
        # No specific secret token to redact here; flag generically.

    # 4) Secret-looking env var referenced alongside a network tool.
    if secret_vars and has_network:
        # findall on a group-bearing regex returns tuples; recover full matches.
        for m in SECRET_VAR_RE.finditer(command):
            matches.append(m.group(0))
        reasons.append("sends a secret-looking variable to a network tool")

    # Escalation note when an already-flagged secret read is also piped out.
    if matches and has_network:
        reasons.append("and pipes it to a network tool (exfiltration)")

    blocked = bool(reasons)
    reason = "; ".join(dict.fromkeys(reasons))  # de-dupe, preserve order
    return blocked, matches, reason


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0  # nothing to inspect → allow

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return 0  # unparseable → allow, never crash

    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0  # only Bash commands are inspected

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return 0

    blocked, secrets, reason = detect(command)
    if not blocked:
        return 0

    safe_command = redact(command, secrets)
    sys.stderr.write(
        "secret-guard: BLOCKED a Bash command that "
        f"{reason}.\n"
        f"  command (redacted): {safe_command}\n"
        "  This is a defense-in-depth tripwire, not a security boundary.\n"
        "  If this is a legitimate operation, run it outside the agent or "
        "disable the hook in .claude/settings.json.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
