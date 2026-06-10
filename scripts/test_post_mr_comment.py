#!/usr/bin/env python3
"""Behavior tests for the GitLab merge-request comment poster."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

import agent_audit
import post_mr_comment


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


@contextmanager
def _env(**overrides: str | None):
    """Temporarily set (value) or unset (None) environment variables."""
    saved = {key: os.environ.get(key) for key in overrides}
    for key, value in overrides.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, prev in saved.items():
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev


@contextmanager
def _report_file(findings: list[dict[str, object]] | None = None):
    """Yield the path of a temporary audit-report JSON for main() CLI tests."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "skill-audit.json"
        path.write_text(json.dumps(_report(findings or [])), encoding="utf-8")
        yield str(path)


def _http_error(code: int, reason: str, body: bytes) -> urllib.error.HTTPError:
    """Build an HTTPError whose .read() returns `body`, like a real GitLab response."""
    return urllib.error.HTTPError(
        "https://gitlab.example/api/v4/projects/1/merge_requests/2/notes",
        code, reason, hdrs=None, fp=io.BytesIO(body),
    )


def _report(findings: list[dict[str, object]]) -> dict[str, object]:
    by_severity = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for item in findings:
        by_severity[str(item["severity"])] += 1
    return {
        "kind": "project-audit",
        "summary": {"total": len(findings), "by_severity": by_severity, "passed": not findings},
        "findings": findings,
    }


class PostMrCommentTests(unittest.TestCase):
    def test_render_includes_marker_and_findings(self) -> None:
        report = _report([
            {"rule_id": "SKILL001", "severity": "high", "file": "skills/x/SKILL.md", "line": 1,
             "message": "Missing frontmatter", "suggestion": "Add name and description."},
        ])

        body = post_mr_comment.render_comment(report)

        self.assertIn(post_mr_comment.MARKER, body)
        self.assertIn("SKILL001", body)
        self.assertIn("skills/x/SKILL.md", body)
        self.assertIn("Missing frontmatter", body)

    def test_render_shows_rule_title_in_rule_column(self) -> None:
        report = _report([
            {"rule_id": "SKILL001", "severity": "high", "file": "skills/x/SKILL.md", "line": 1,
             "message": "Missing frontmatter", "suggestion": "Add name and description.",
             "title": "Missing YAML frontmatter", "rationale": "Frontmatter carries routing metadata."},
        ])

        body = post_mr_comment.render_comment(report)

        self.assertIn("Missing YAML frontmatter", body)
        self.assertIn("SKILL001", body)

    def test_render_clean_report_says_passed(self) -> None:
        body = post_mr_comment.render_comment(_report([]))

        self.assertIn(post_mr_comment.MARKER, body)
        self.assertNotIn("| high |", body.lower())
        self.assertTrue("no governance findings" in body.lower() or "passed" in body.lower())

    def test_render_reports_truncation_without_silent_cap(self) -> None:
        findings = [
            {"rule_id": "SKILL003", "severity": "low", "file": f"skills/s{i}/SKILL.md", "line": 1,
             "message": "Short description", "suggestion": "Expand triggers."}
            for i in range(5)
        ]

        body = post_mr_comment.render_comment(_report(findings), max_findings=2)

        self.assertIn("3 more", body)

    def test_render_escapes_table_breaking_finding_text(self) -> None:
        # Finding text comes from audited file content; a `|` or newline must not
        # break the Markdown table or inject extra rows/markup into the MR note.
        report = _report([
            {"rule_id": "SKILL015", "severity": "high", "file": "skills/z/SKILL.md", "line": 7,
             "message": "secret | injected\n| evil | row |", "suggestion": "Remove the | pipe."},
        ])

        body = post_mr_comment.render_comment(report)

        # The raw pipe from the message must be escaped, and no stray newline may
        # split the single finding row into multiple table rows.
        self.assertIn("secret \\| injected", body)
        self.assertNotIn("\n| evil | row |", body)

    def test_post_or_update_paginates_notes_lookup(self) -> None:
        # The gate note is created early; on a busy MR it drifts past page 1 of
        # the default 20-per-page descending notes window, so find_marker_note
        # misses it and post_or_update POSTs a duplicate — breaking idempotency.
        # The list GET must request a large ascending page so the early note is
        # found deterministically.
        calls: list[tuple[str, str]] = []

        def fake_api(url: str, token: str, method: str = "GET", payload: object = None) -> object:
            calls.append((method, url))
            if url.endswith("/user"):
                return {"id": 99}
            return [] if method == "GET" else None

        original = post_mr_comment._api_request
        post_mr_comment._api_request = fake_api
        try:
            post_mr_comment.post_or_update(
                "https://gitlab.example/api/v4", "1", "2", "tok", "body")
        finally:
            post_mr_comment._api_request = original

        get_url = next(url for method, url in calls if method == "GET" and "/notes" in url)
        self.assertIn("per_page=100", get_url)
        self.assertIn("sort=asc", get_url)

    def test_post_or_update_follows_pagination_past_100_notes(self) -> None:
        # On a long-lived MR with >100 notes created before the gate note, the
        # marker sits on page 2+. The lookup must follow pagination to the end
        # of the list — otherwise it misses the marker and POSTs a duplicate,
        # breaking the idempotency contract.
        calls: list[tuple[str, str, object]] = []
        page1 = [{"id": i, "body": f"review note {i}", "author": {"id": i}} for i in range(100)]
        page2 = [{"id": 200, "body": f"{post_mr_comment.MARKER}\nprevious gate result",
                  "author": {"id": 99}}]

        def fake_api(url: str, token: str, method: str = "GET", payload: object = None) -> object:
            calls.append((method, url, payload))
            if url.endswith("/user"):
                return {"id": 99}
            if method == "GET":
                return page2 if "page=2" in url else page1
            return None

        original = post_mr_comment._api_request
        post_mr_comment._api_request = fake_api
        try:
            action = post_mr_comment.post_or_update(
                "https://gitlab.example/api/v4", "1", "2", "tok", "new body")
        finally:
            post_mr_comment._api_request = original

        self.assertEqual(action, "updated")
        self.assertNotIn("POST", [method for method, _, _ in calls])
        self.assertIn(
            "https://gitlab.example/api/v4/projects/1/merge_requests/2/notes/200",
            [url for method, url, _ in calls if method == "PUT"])

    def test_post_or_update_stops_on_short_page_and_posts(self) -> None:
        # No marker anywhere: a short (<100) page means the list is exhausted —
        # exactly one notes GET, then a POST creating the note (no infinite paging).
        calls: list[tuple[str, str]] = []

        def fake_api(url: str, token: str, method: str = "GET", payload: object = None) -> object:
            calls.append((method, url))
            if url.endswith("/user"):
                return {"id": 99}
            return [{"id": 1, "body": "just a note", "author": {"id": 7}}] if method == "GET" else None

        original = post_mr_comment._api_request
        post_mr_comment._api_request = fake_api
        try:
            action = post_mr_comment.post_or_update(
                "https://gitlab.example/api/v4", "1", "2", "tok", "body")
        finally:
            post_mr_comment._api_request = original

        self.assertEqual(action, "created")
        self.assertEqual(len([m for m, url in calls if m == "GET" and "/notes" in url]), 1)
        self.assertEqual(len([m for m, _ in calls if m == "POST"]), 1)

    def test_find_marker_note_returns_id(self) -> None:
        notes = [
            {"id": 10, "body": "unrelated review note"},
            {"id": 11, "body": f"{post_mr_comment.MARKER}\nprevious gate result"},
        ]

        self.assertEqual(post_mr_comment.find_marker_note(notes, post_mr_comment.MARKER), 11)
        self.assertIsNone(post_mr_comment.find_marker_note(notes[:1], post_mr_comment.MARKER))

    def test_find_marker_note_filters_by_author_id(self) -> None:
        # With an author_id, a marker note from another user must NOT match —
        # any MR commenter can pre-seed the marker to hijack the gate's update.
        notes = [
            {"id": 20, "body": f"{post_mr_comment.MARKER}\nimpostor", "author": {"id": 7}},
            {"id": 21, "body": f"{post_mr_comment.MARKER}\nown note", "author": {"id": 99}},
        ]

        self.assertEqual(post_mr_comment.find_marker_note(notes, post_mr_comment.MARKER, author_id=99), 21)
        self.assertIsNone(post_mr_comment.find_marker_note(notes[:1], post_mr_comment.MARKER, author_id=99))
        # author_id=None keeps the legacy marker-only behavior (graceful degradation).
        self.assertEqual(post_mr_comment.find_marker_note(notes, post_mr_comment.MARKER), 20)

    def test_api_request_sends_non_default_user_agent(self) -> None:
        # Some WAFs / load balancers reset connections whose User-Agent is the
        # default "Python-urllib/x.y". The poster must send an explicit, non-default
        # User-Agent (and an Accept) so the GitLab API call survives those hops.
        captured: dict[str, object] = {}

        @contextmanager
        def fake_urlopen(request: object, timeout: int = 0):  # noqa: ANN001
            captured["request"] = request

            class _Resp:
                def read(self) -> bytes:
                    return b"[]"

            yield _Resp()

        original = post_mr_comment.urllib.request.urlopen
        post_mr_comment.urllib.request.urlopen = fake_urlopen
        try:
            post_mr_comment._api_request("https://gitlab.example/api/v4/x", "tok")
        finally:
            post_mr_comment.urllib.request.urlopen = original

        request = captured["request"]
        user_agent = request.get_header("User-agent")
        self.assertTrue(user_agent, "User-Agent header must be set")
        self.assertNotIn("urllib", user_agent.lower())
        self.assertEqual(request.get_header("Accept"), "application/json")

    def test_introduced_renders_before_preexisting(self) -> None:
        report = {"kind": "project-audit", "summary": {"total": 2, "by_severity": {"high": 2},
                  "passed": False},
                  "findings": [
                    {"rule_id": "SEC010", "severity": "high", "file": "old.md", "line": 1,
                     "message": "old", "suggestion": "x", "introduced": False},
                    {"rule_id": "SEC011", "severity": "high", "file": "new.md", "line": 1,
                     "message": "new", "suggestion": "y", "introduced": True}]}
        body = post_mr_comment.render_comment(report)
        self.assertLess(body.index("new.md"), body.index("old.md"))  # introduced first

    def test_floor_finding_shows_central_suppress_hint_not_inline_marker(self) -> None:
        # SEC011 is a severity-floor rule. The author-facing suppression hint must
        # point at the CODEOWNER-gated central file — an inline marker can NEVER
        # suppress a floor rule (F3 invariant), so it must not appear for SEC011.
        report = _report([
            {"rule_id": "SEC011", "severity": "high", "file": "x.md", "line": 1,
             "message": "inline secret", "suggestion": "Use an env var name."},
        ])
        body = post_mr_comment.render_comment(report)
        self.assertIn("references/audit-ignore.json", body)
        self.assertIn("CODEOWNER", body)
        self.assertNotIn("sgt-ignore: SEC011", body)

    def test_floor_rules_match_engine_source_of_truth(self) -> None:
        # The poster derives its floor set from the engine's SEVERITY_FLOOR. If the
        # two ever diverge (e.g. the engine adds a floor rule the poster doesn't
        # mirror), the poster would hint at an inline marker the engine refuses to
        # honor for that floor rule — a misleading author-facing hint. Fail loudly.
        self.assertEqual(set(post_mr_comment.FLOOR_RULES), set(agent_audit.SEVERITY_FLOOR))

    def test_engine_added_floor_rule_gets_central_hint_not_inline_marker(self) -> None:
        # MCP001/REF002/SCR001/HOOK001 are floor rules the old hardcoded list
        # missed. Their suppression hint must point at the central CODEOWNER-gated
        # file, never the inline `sgt-ignore` marker.
        for rule_id in ("MCP001", "REF002", "SCR001", "HOOK001"):
            report = _report([
                {"rule_id": rule_id, "severity": "high", "file": "x.md", "line": 1,
                 "message": "floor finding", "suggestion": "fix it."},
            ])
            body = post_mr_comment.render_comment(report)
            self.assertIn("references/audit-ignore.json", body)
            self.assertNotIn(f"sgt-ignore: {rule_id}", body)

    def test_advisory_finding_shows_inline_marker(self) -> None:
        report = _report([
            {"rule_id": "SEC003", "severity": "medium", "file": "y.md", "line": 2,
             "message": "homoglyph", "suggestion": "Replace the confusable char."},
        ])
        body = post_mr_comment.render_comment(report)
        self.assertIn("<!-- sgt-ignore: SEC003", body)

    def test_comment_footer_links_author_guide(self) -> None:
        report = _report([
            {"rule_id": "SEC003", "severity": "medium", "file": "y.md", "line": 2,
             "message": "homoglyph", "suggestion": "fix it."},
        ])
        body = post_mr_comment.render_comment(report)
        self.assertIn("docs/gate-for-authors.md", body)

    def test_post_or_update_puts_to_existing_marker_note(self) -> None:
        # Idempotency contract: when the gate's OWN marker note already exists,
        # the poster must PUT the new body to /notes/<id> — never POST a duplicate.
        calls: list[tuple[str, str, object]] = []

        def fake_api(url: str, token: str, method: str = "GET", payload: object = None) -> object:
            calls.append((method, url, payload))
            if url.endswith("/user"):
                return {"id": 99}
            if method == "GET":
                return [
                    {"id": 7, "body": "unrelated review note", "author": {"id": 7}},
                    {"id": 42, "body": f"{post_mr_comment.MARKER}\nprevious gate result",
                     "author": {"id": 99}},
                ]
            return None

        original = post_mr_comment._api_request
        post_mr_comment._api_request = fake_api
        try:
            action = post_mr_comment.post_or_update(
                "https://gitlab.example/api/v4", "1", "2", "tok", "new body")
        finally:
            post_mr_comment._api_request = original

        self.assertEqual(action, "updated")
        self.assertNotIn("POST", [method for method, _, _ in calls])
        put_calls = [(url, payload) for method, url, payload in calls if method == "PUT"]
        self.assertEqual(put_calls, [(
            "https://gitlab.example/api/v4/projects/1/merge_requests/2/notes/42",
            {"body": "new body"},
        )])

    def test_post_or_update_ignores_impostor_marker_note(self) -> None:
        # An MR commenter pre-seeded a note with the gate's marker. It is NOT the
        # token user's note, so the poster must POST a fresh note instead of
        # PUT-updating the impostor's (which would let them displace the report).
        calls: list[tuple[str, str, object]] = []

        def fake_api(url: str, token: str, method: str = "GET", payload: object = None) -> object:
            calls.append((method, url, payload))
            if url.endswith("/user"):
                return {"id": 99}
            if method == "GET":
                return [{"id": 13, "body": f"{post_mr_comment.MARKER}\nfake gate report",
                         "author": {"id": 7}}]
            return None

        original = post_mr_comment._api_request
        post_mr_comment._api_request = fake_api
        try:
            action = post_mr_comment.post_or_update(
                "https://gitlab.example/api/v4", "1", "2", "tok", "real body")
        finally:
            post_mr_comment._api_request = original

        self.assertEqual(action, "created")
        self.assertNotIn("PUT", [method for method, _, _ in calls])
        post_calls = [(url, payload) for method, url, payload in calls if method == "POST"]
        self.assertEqual(post_calls, [(
            "https://gitlab.example/api/v4/projects/1/merge_requests/2/notes",
            {"body": "real body"},
        )])

    def test_post_or_update_user_lookup_failure_falls_back_to_marker_only(self) -> None:
        # /user can fail on older GitLab or a restricted token. The poster must
        # warn once and degrade to legacy marker-only matching — still updating
        # the existing marker note, never crashing the gate over the hardening.
        calls: list[tuple[str, str, object]] = []

        def fake_api(url: str, token: str, method: str = "GET", payload: object = None) -> object:
            calls.append((method, url, payload))
            if url.endswith("/user"):
                raise _http_error(403, "Forbidden", b'{"message":"insufficient_scope"}')
            if method == "GET":
                return [{"id": 42, "body": f"{post_mr_comment.MARKER}\nprevious gate result",
                         "author": {"id": 7}}]
            return None

        original = post_mr_comment._api_request
        post_mr_comment._api_request = fake_api
        stderr = io.StringIO()
        try:
            with redirect_stderr(stderr):
                action = post_mr_comment.post_or_update(
                    "https://gitlab.example/api/v4", "1", "2", "tok", "new body")
        finally:
            post_mr_comment._api_request = original

        self.assertEqual(action, "updated")
        self.assertIn(
            "https://gitlab.example/api/v4/projects/1/merge_requests/2/notes/42",
            [url for method, url, _ in calls if method == "PUT"])
        self.assertIn("marker-only", stderr.getvalue())

    def test_main_http_error_sanitized_and_surfaces_gitlab_body(self) -> None:
        # 401 and 500 from the API must exit non-zero, surface the GitLab response
        # body (the author's only self-diagnosis signal), and never leak the token.
        token_value = "glpat-SUPER-SECRET-VALUE"
        for code, reason, api_body in (
            (401, "Unauthorized", b'{"message":"401 Unauthorized"}'),
            (500, "Internal Server Error", b'{"message":"internal error"}'),
        ):
            with self.subTest(code=code):
                def fake_api(url: str, token: str, method: str = "GET", payload: object = None) -> object:
                    raise _http_error(code, reason, api_body)

                original = post_mr_comment._api_request
                post_mr_comment._api_request = fake_api
                stdout, stderr = io.StringIO(), io.StringIO()
                try:
                    with _report_file() as report, _env(GITLAB_TOKEN=token_value), \
                            redirect_stdout(stdout), redirect_stderr(stderr):
                        rc = post_mr_comment.main([
                            report, "--api-url", "https://gitlab.example/api/v4",
                            "--project-id", "1", "--mr-iid", "2",
                        ])
                finally:
                    post_mr_comment._api_request = original

                self.assertEqual(rc, 1)
                combined = stdout.getvalue() + stderr.getvalue()
                self.assertNotIn(token_value, combined)
                self.assertIn(str(code), stderr.getvalue())
                self.assertIn(api_body.decode("utf-8"), stderr.getvalue())

    def test_main_missing_token_env_exits_2_without_api_call(self) -> None:
        calls: list[str] = []

        def fake_api(url: str, token: str, method: str = "GET", payload: object = None) -> object:
            calls.append(url)
            return []

        original = post_mr_comment._api_request
        post_mr_comment._api_request = fake_api
        stderr = io.StringIO()
        try:
            with _report_file() as report, _env(GITLAB_TOKEN=None), redirect_stderr(stderr):
                rc = post_mr_comment.main([
                    report, "--api-url", "https://gitlab.example/api/v4",
                    "--project-id", "1", "--mr-iid", "2",
                ])
        finally:
            post_mr_comment._api_request = original

        self.assertEqual(rc, 2)
        self.assertEqual(calls, [])
        self.assertIn("GITLAB_TOKEN", stderr.getvalue())
        self.assertIn("missing required config", stderr.getvalue())

    def test_main_proceeds_to_api_call_with_ci_env(self) -> None:
        # The documented CI contract: CI_API_V4_URL / CI_PROJECT_ID /
        # CI_MERGE_REQUEST_IID + token env supply everything — no flags needed.
        calls: list[tuple[str, str]] = []

        def fake_api(url: str, token: str, method: str = "GET", payload: object = None) -> object:
            calls.append((method, url))
            if url.endswith("/user"):
                return {"id": 99}
            return [] if method == "GET" else None

        original = post_mr_comment._api_request
        post_mr_comment._api_request = fake_api
        stdout = io.StringIO()
        try:
            with _report_file() as report, _env(
                CI_API_V4_URL="https://gitlab.example/api/v4",
                CI_PROJECT_ID="123",
                CI_MERGE_REQUEST_IID="9",
                GITLAB_TOKEN="tok",
            ), redirect_stdout(stdout):
                rc = post_mr_comment.main([report])
        finally:
            post_mr_comment._api_request = original

        self.assertEqual(rc, 0)
        urls = [url for _, url in calls]
        self.assertTrue(any("/projects/123/merge_requests/9/notes" in url for url in urls), urls)
        self.assertIn("created", stdout.getvalue())

    def test_main_refuses_http_api_url_with_exit_2(self) -> None:
        # An http:// endpoint would send the PRIVATE-TOKEN header in cleartext.
        # The poster must refuse before any API call, naming the URL and https.
        calls: list[str] = []

        def fake_api(url: str, token: str, method: str = "GET", payload: object = None) -> object:
            calls.append(url)
            return []

        original = post_mr_comment._api_request
        post_mr_comment._api_request = fake_api
        stderr = io.StringIO()
        try:
            with _report_file() as report, _env(GITLAB_TOKEN="tok"), redirect_stderr(stderr):
                rc = post_mr_comment.main([
                    report, "--api-url", "http://gitlab.example/api/v4",
                    "--project-id", "1", "--mr-iid", "2",
                ])
        finally:
            post_mr_comment._api_request = original

        self.assertEqual(rc, 2)
        self.assertEqual(calls, [])
        self.assertIn("https", stderr.getvalue())
        self.assertIn("http://gitlab.example/api/v4", stderr.getvalue())

    def test_main_allow_insecure_http_flag_proceeds(self) -> None:
        # Escape hatch for on-host test instances: --allow-insecure-http lets an
        # http:// endpoint through and the normal post flow runs.
        calls: list[tuple[str, str]] = []

        def fake_api(url: str, token: str, method: str = "GET", payload: object = None) -> object:
            calls.append((method, url))
            if url.endswith("/user"):
                return {"id": 99}
            return [] if method == "GET" else None

        original = post_mr_comment._api_request
        post_mr_comment._api_request = fake_api
        stdout = io.StringIO()
        try:
            with _report_file() as report, _env(GITLAB_TOKEN="tok"), redirect_stdout(stdout):
                rc = post_mr_comment.main([
                    report, "--api-url", "http://gitlab.example/api/v4",
                    "--project-id", "1", "--mr-iid", "2", "--allow-insecure-http",
                ])
        finally:
            post_mr_comment._api_request = original

        self.assertEqual(rc, 0)
        self.assertIn("POST", [method for method, _ in calls])

    def test_cli_dry_run_prints_body_without_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "skill-audit.json"
            audit_path.write_text(json.dumps(_report([
                {"rule_id": "SKILL014", "severity": "high", "file": "skills/y/SKILL.md", "line": 3,
                 "message": "Dangerous command", "suggestion": "Remove destructive shell."},
            ])), encoding="utf-8")

            result = subprocess.run(
                [PYTHON, str(ROOT / "scripts" / "post_mr_comment.py"), str(audit_path), "--dry-run"],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(post_mr_comment.MARKER, result.stdout)
            self.assertIn("SKILL014", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
