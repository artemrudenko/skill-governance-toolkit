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
import urllib.parse
import urllib.request
from typing import Any

# Hidden HTML marker that makes the gate's note findable for idempotent updates.
MARKER = "<!-- skill-governance-gate -->"

SEVERITY_ORDER = ("high", "medium", "low", "info")
SEVERITY_LABEL = {"high": "🔴 High", "medium": "🟠 Medium", "low": "🟡 Low", "info": "🔵 Info"}

# Author guide referenced from the comment footer. Created by a later docs task;
# the path is stable so we link it now.
AUTHOR_GUIDE = "docs/gate-for-authors.md"

# Severity-floor rule ids — these can ONLY be suppressed via the CODEOWNER-gated
# references/audit-ignore.json (the F3 invariant: an inline marker must never
# suppress a floor rule). The engine's SEVERITY_FLOOR (agent_audit.py) is the
# source of truth; derive from it so the two can never silently diverge (a stale
# copy would hint at an inline marker the engine refuses to honor for a floor rule).
# Fall back to a hardcoded mirror only if the engine is unimportable (poster run in
# isolation, no sibling on sys.path) — the gate must still publish.
try:
    from agent_audit import SEVERITY_FLOOR

    FLOOR_RULES = frozenset(SEVERITY_FLOOR)
except Exception:  # noqa: BLE001 — degrade gracefully when run standalone
    FLOOR_RULES = frozenset(
        {
            "SEC001", "SEC002", "SEC010", "SEC011",
            "SKILL001", "SKILL002", "SKILL009", "SKILL014", "SKILL015",
            "REF002", "SCR001", "SCR002", "SCR003",
            "MCP001", "HOOK001", "HOOK002",
        }
    )


def _suppress_hint(rule_id: Any) -> str:
    """Return the CORRECT suppression hint for a finding's rule.

    Floor rule → central CODEOWNER-gated file only (inline cannot suppress it).
    Advisory rule → inline marker at the finding site.
    """
    rid = "" if rule_id is None else str(rule_id)
    if rid in FLOOR_RULES:
        return "add to references/audit-ignore.json (needs CODEOWNER approval)"
    return f"<!-- sgt-ignore: {rid} reason=... -->"


def _suggestion_cell(item: dict[str, Any]) -> str:
    """Compose the table's Suggestion cell: the finding's own suggestion plus a
    copy-paste suppression hint, both markdown-cell-safe."""
    suggestion = _md_cell(item.get("suggestion"))
    suppress = _md_cell(_suppress_hint(item.get("rule_id")))
    if suggestion:
        return f"{suggestion} · Suppress: {suppress}"
    return f"Suppress: {suppress}"


def _rule_cell(item: dict[str, Any]) -> str:
    """Compose the table's Rule cell: the rule id in code font plus the rule's
    human-readable title on a second line, so a reviewer sees WHAT the rule is.
    Both halves are markdown-cell-safe (title derives from the catalog, but stay
    consistent with the rest of the table's escaping)."""
    rid = _md_cell(item.get("rule_id"))
    title = _md_cell(item.get("title"))
    if title:
        return f"`{rid}`<br/>{title}"
    return f"`{rid}`"


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


# Per-severity visible cap inside a delta-mode group; the rest collapse to a
# "+N more — see artifact" line so a noisy severity can't blow up the note.
PER_SEVERITY_CAP = 20


def _severity_tables(findings: list[dict[str, Any]], lines: list[str]) -> None:
    """Append per-severity Markdown tables for `findings` to `lines`, capping each
    severity group at PER_SEVERITY_CAP rows with a "+N more" overflow line."""
    for sev in SEVERITY_ORDER:
        group = [f for f in findings if f.get("severity") == sev]
        if not group:
            continue
        visible = group[:PER_SEVERITY_CAP]
        lines.append(f"### {SEVERITY_LABEL[sev]}")
        lines.append("")
        lines.append("| Rule | Location | Finding | Suggestion |")
        lines.append("|---|---|---|---|")
        for item in visible:
            location = f"`{_md_cell(item.get('file'))}:{_md_cell(item.get('line'))}`"
            lines.append(
                f"| {_rule_cell(item)} | {location} "
                f"| {_md_cell(item.get('message'))} | {_suggestion_cell(item)} |"
            )
        overflow = len(group) - len(visible)
        if overflow > 0:
            lines.append("")
            lines.append(f"_…and {overflow} more {sev} finding(s) — see the `skill-audit.json` artifact._")
        lines.append("")


def render_comment(report: dict[str, Any], max_findings: int = 50) -> str:
    """Render a markdown comment body for a project-audit report.

    Delta mode (any finding carries an `introduced` flag): INTRODUCED findings —
    the ones that block — render first in full; pre-existing findings collapse
    into a <details> block. Non-delta mode keeps the flat per-severity layout.
    """
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

    delta_mode = any("introduced" in f for f in findings)
    if delta_mode:
        introduced = [f for f in findings if f.get("introduced")]
        preexisting = [f for f in findings if not f.get("introduced")]

        if introduced:
            lines.append(f"### 🚩 {len(introduced)} introduced by this MR (blocking)")
            lines.append("")
            _severity_tables(introduced, lines)
        else:
            lines.append("✅ No newly introduced findings — nothing blocks this MR.")
            lines.append("")

        if preexisting:
            lines.append("<details>")
            lines.append(f"<summary>{len(preexisting)} pre-existing (not introduced by this MR)</summary>")
            lines.append("")
            _severity_tables(preexisting, lines)
            lines.append("</details>")

        _append_footer(lines)
        return "\n".join(lines).rstrip() + "\n"

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
                f"| {_rule_cell(item)} | {location} "
                f"| {_md_cell(item.get('message'))} | {_suggestion_cell(item)} |"
            )
        lines.append("")

    dropped = len(findings) - len(shown)
    if dropped > 0:
        lines.append(f"_…and {dropped} more finding(s) not shown. See the `skill-audit.json` artifact._")

    _append_footer(lines)
    return "\n".join(lines).rstrip() + "\n"


def _append_footer(lines: list[str]) -> None:
    """Append the shared footer: how the Suggestion column's suppress hint works
    and a link to the full author guide."""
    lines.append("")
    lines.append(
        "_The Suggestion column carries a copy-paste suppression hint. "
        "Floor rules suppress only via the CODEOWNER-gated `references/audit-ignore.json`; "
        "advisory rules accept the inline `sgt-ignore` marker._"
    )
    lines.append(f"_Full guide: {AUTHOR_GUIDE}_")


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
    # Some WAFs / load balancers reset connections whose User-Agent is the
    # default "Python-urllib/x.y" (RemoteDisconnected: "Remote end closed
    # connection without response"), while letting curl through. Send an
    # explicit, non-default User-Agent and Accept so the API call survives.
    request.add_header("User-Agent", "skill-governance-gate")
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (trusted CI host)
        body = response.read().decode("utf-8")
    return json.loads(body) if body else None


def post_or_update(api_url: str, project_id: str, mr_iid: str, token: str, body: str) -> str:
    """Create the gate note, or update the existing marker note in place."""
    base = f"{api_url.rstrip('/')}/projects/{project_id}/merge_requests/{mr_iid}/notes"
    # The gate note is created early in the MR's life. List notes oldest-first
    # and follow pagination to the end of the list — a fixed single page (even a
    # large one) misses the marker on an MR with 100+ earlier notes, and we'd
    # POST a duplicate, breaking the idempotency contract this module promises.
    existing = None
    page = 1
    while True:
        list_url = f"{base}?per_page=100&page={page}&order_by=created_at&sort=asc"
        notes = _api_request(list_url, token) or []
        existing = find_marker_note(notes, MARKER)
        if existing is not None or len(notes) < 100:
            break
        page += 1
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
    parser.add_argument(
        "--allow-insecure-http", action="store_true",
        help="Permit a non-https --api-url (on-host test instances only). "
             "Without it the poster refuses: the PRIVATE-TOKEN header would travel in cleartext.",
    )
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

    # Refuse cleartext token transport: a non-https api-url would send the
    # PRIVATE-TOKEN header unencrypted. --allow-insecure-http is the explicit
    # escape hatch for on-host test instances.
    scheme = urllib.parse.urlsplit(args.api_url).scheme.lower()
    if scheme != "https" and not args.allow_insecure_http:
        print(
            f"post_mr_comment: refusing non-https api-url {args.api_url!r} — "
            "the PRIVATE-TOKEN header would travel in cleartext. "
            "Use an https endpoint or pass --allow-insecure-http.",
            file=sys.stderr,
        )
        return 2

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
