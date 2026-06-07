#!/usr/bin/env python3
"""post_mr_comment.py - publish audit-engine findings as a GitLab MR comment.

Reads the JSON produced by `agent_audit.py audit-project ... --format json`
and posts a single, idempotent summary note to a merge request. Re-running
updates the same note (matched by a hidden marker) instead of stacking
duplicates on every pipeline run.

Stdlib-only by project policy: HTTP uses urllib, no third-party SDK.

Security: the API token is read from an environment variable (name, not value).
Never pass a token on the command line.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

# Hidden HTML marker that makes the gate's note findable for idempotent updates.
MARKER = "<!-- skill-governance-gate -->"

SEVERITY_ORDER = ("high", "medium", "low", "info")
SEVERITY_LABEL = {"high": "🔴 High", "medium": "🟠 Medium", "low": "🟡 Low", "info": "🔵 Info"}


def _md_cell(value: Any) -> str:
    """Make an arbitrary finding value safe inside a Markdown table cell.

    Finding text derives from audited file content (e.g. a SKILL.md body), so a
    crafted asset could contain `|`, newlines, or backticks that break the table
    or inject Markdown into the rendered MR note. Neutralise them.
    """
    text = "" if value is None else str(value)
    text = text.replace("\\", "\\\\").replace("|", "\\|")
    text = text.replace("\r", " ").replace("\n", " ")
    return text.strip()


def render_comment(report: dict[str, Any], max_findings: int = 50) -> str:
    """Render a markdown comment body for a project-audit report."""
    findings = report.get("findings") or []
    summary = report.get("summary") or {}
    lines = [MARKER, "## Skill governance gate", ""]

    if not findings:
        lines.append("✅ No governance findings on the changed assets.")
        return "\n".join(lines)

    by_severity = summary.get("by_severity") or {}
    counts = ", ".join(
        f"{SEVERITY_LABEL[sev]}: {by_severity.get(sev, 0)}"
        for sev in SEVERITY_ORDER
        if by_severity.get(sev, 0)
    )
    lines.append(f"Found **{len(findings)}** finding(s) — {counts}.")
    lines.append("")

    shown = findings[:max_findings]
    for sev in SEVERITY_ORDER:
        group = [f for f in shown if f.get("severity") == sev]
        if not group:
            continue
        lines.append(f"### {SEVERITY_LABEL[sev]}")
        lines.append("")
        lines.append("| Rule | Location | Finding | Suggestion |")
        lines.append("|---|---|---|---|")
        for item in group:
            location = f"`{_md_cell(item.get('file'))}:{_md_cell(item.get('line'))}`"
            lines.append(
                f"| {_md_cell(item.get('rule_id'))} | {location} "
                f"| {_md_cell(item.get('message'))} | {_md_cell(item.get('suggestion'))} |"
            )
        lines.append("")

    dropped = len(findings) - len(shown)
    if dropped > 0:
        lines.append(f"_…and {dropped} more finding(s) not shown. See the `skill-audit.json` artifact._")

    return "\n".join(lines).rstrip() + "\n"


def find_marker_note(notes: list[dict[str, Any]], marker: str) -> int | None:
    """Return the id of the first note containing the marker, else None."""
    for note in notes:
        if marker in str(note.get("body", "")):
            return int(note["id"])
    return None


def _api_request(url: str, token: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("PRIVATE-TOKEN", token)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (trusted CI host)
        body = response.read().decode("utf-8")
    return json.loads(body) if body else None


def post_or_update(api_url: str, project_id: str, mr_iid: str, token: str, body: str) -> str:
    """Create the gate note, or update the existing marker note in place."""
    base = f"{api_url.rstrip('/')}/projects/{project_id}/merge_requests/{mr_iid}/notes"
    notes = _api_request(base, token) or []
    existing = find_marker_note(notes, MARKER)
    if existing is not None:
        _api_request(f"{base}/{existing}", token, method="PUT", payload={"body": body})
        return "updated"
    _api_request(base, token, method="POST", payload={"body": body})
    return "created"


def _load_report(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Post audit findings as a GitLab MR comment.")
    parser.add_argument("report", nargs="?", default="skill-audit.json", help="Audit JSON path, or - for stdin.")
    parser.add_argument("--dry-run", action="store_true", help="Print the rendered comment, do not call the API.")
    parser.add_argument("--max-findings", type=int, default=50, help="Cap findings shown in the comment.")
    parser.add_argument("--api-url", default=os.environ.get("CI_API_V4_URL", "https://gitlab.com/api/v4"))
    parser.add_argument("--project-id", default=os.environ.get("CI_PROJECT_ID"))
    parser.add_argument("--mr-iid", default=os.environ.get("CI_MERGE_REQUEST_IID"))
    parser.add_argument("--token-env", default="GITLAB_TOKEN", help="Env var holding the API token.")
    args = parser.parse_args(argv)

    try:
        report = _load_report(args.report)
    except (OSError, ValueError) as exc:
        print(f"post_mr_comment: cannot read report: {exc}", file=sys.stderr)
        return 2

    body = render_comment(report, max_findings=args.max_findings)

    if args.dry_run:
        print(body)
        return 0

    token = os.environ.get(args.token_env)
    missing = [
        name for name, value in (("--project-id", args.project_id), ("--mr-iid", args.mr_iid), (args.token_env, token))
        if not value
    ]
    if missing:
        print(f"post_mr_comment: missing required config: {', '.join(missing)}", file=sys.stderr)
        return 2

    try:
        action = post_or_update(args.api_url, args.project_id, args.mr_iid, token, body)
    except urllib.error.HTTPError as exc:
        # Surface the GitLab response body — it explains WHY (e.g. a token with
        # the wrong scope returns 403 "insufficient_scope"). Without it the author
        # only sees "HTTP Error 403" and cannot self-diagnose.
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace").strip()
        except Exception:  # noqa: BLE001 — diagnostics only, never mask the original error
            detail = ""
        msg = f"post_mr_comment: API call failed: HTTP {exc.code} {exc.reason}"
        if detail:
            msg += f" — {detail}"
        print(msg, file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"post_mr_comment: API call failed: {exc}", file=sys.stderr)
        return 1
    print(f"post_mr_comment: {action} gate note on MR !{args.mr_iid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
