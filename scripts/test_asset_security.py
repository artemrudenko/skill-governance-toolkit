#!/usr/bin/env python3
"""Behavior tests for the per-asset security pipeline, config, ignore-list, and delta gate."""
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
import agent_audit

class _CacheSafe(unittest.TestCase):
    """load_config()/load_rule_catalog() are @lru_cache'd; clear between tests so
    in-process config changes are observed and tests don't leak state."""
    def setUp(self) -> None:
        agent_audit.load_config.cache_clear()
        agent_audit.load_rule_catalog.cache_clear()
    tearDown = setUp


class ConfigNamespaceTests(_CacheSafe):
    def test_config_exposes_allowlists_with_defaults(self) -> None:
        cfg = agent_audit.load_config()
        for key in ("allow_domains", "allow_unicode_scripts", "allow_mcp_servers",
                    "env_exfil_patterns", "hook_deny", "scripts_manifest"):
            self.assertIn(key, cfg)
        self.assertEqual({"Latin", "Common"} & cfg["allow_unicode_scripts"], {"Latin", "Common"})
        self.assertEqual(cfg["scripts_manifest"], "scripts/runtime-manifest.txt")

    def test_overlay_file_extends_allowlists(self) -> None:
        # Write an overlay next to the real catalog, clear cache, assert it merges.
        import agent_audit as aa
        refs = aa.default_rules_path().parent
        overlay = refs / "audit-config.test-tmp.json"
        overlay.write_text(json.dumps({"allowlists": {"domains": ["example.test"]}}), encoding="utf-8")
        try:
            aa.load_config.cache_clear()
            self.assertIn("example.test", aa.load_config()["allow_domains"])
        finally:
            overlay.unlink(missing_ok=True)
            aa.load_config.cache_clear()


class IgnoreListTests(_CacheSafe):
    def test_central_with_reason_suppresses_any_rule(self):
        doc = {"ignores": [{"rule_id": "SEC011", "path": ".mcp.json", "reason": "test fixture"}]}
        f = [{"rule_id": "SEC011", "file": ".mcp.json", "line": 1, "severity": "high"}]
        self.assertEqual(agent_audit._apply_ignores(f, doc, {}, root="."), [])

    def test_missing_reason_is_failsafe(self):
        doc = {"ignores": [{"rule_id": "SEC011", "path": ".mcp.json"}]}
        f = [{"rule_id": "SEC011", "file": ".mcp.json", "line": 1, "severity": "high"}]
        ids = {x["rule_id"] for x in agent_audit._apply_ignores(f, doc, {}, root=".")}
        self.assertIn("SEC011", ids); self.assertIn("IGNORE002", ids)

    def test_expired_central_does_not_suppress(self):
        doc = {"ignores": [{"rule_id": "SEC003", "path": "x.md", "reason": "old", "expires": "2000-01-01"}]}
        f = [{"rule_id": "SEC003", "file": "x.md", "line": 1, "severity": "medium"}]
        ids = {x["rule_id"] for x in agent_audit._apply_ignores(f, doc, {}, root=".")}
        self.assertIn("SEC003", ids); self.assertIn("IGNORE001", ids)

    def test_inline_suppresses_advisory_but_not_floor(self):
        inline = {(".mcp.json", 1): {"SEC003", "SEC011"}}
        adv = [{"rule_id": "SEC003", "file": ".mcp.json", "line": 1, "severity": "medium"}]
        flo = [{"rule_id": "SEC011", "file": ".mcp.json", "line": 1, "severity": "high"}]
        self.assertEqual(agent_audit._apply_ignores(adv, {"ignores": []}, inline, root="."), [])
        kept = agent_audit._apply_ignores(flo, {"ignores": []}, inline, root=".")
        ids = {x["rule_id"] for x in kept}
        self.assertIn("SEC011", ids)   # floor rule NOT silenced by inline marker
        self.assertIn("IGNORE003", ids)  # the attempt is surfaced

    def test_inline_marker_parsing(self):
        text = "line one\n<!-- sgt-ignore: SEC003 reason=brand name -->\nproblem here\n"
        idx = agent_audit._parse_inline_ignores(text, "x.md")
        # marker covers its own line and the line below
        self.assertIn("SEC003", idx.get(("x.md", 2), set()) | idx.get(("x.md", 3), set()))

    def test_non_dict_entry_is_failsafe_not_crash(self):
        # A malformed (non-object) entry must be skipped, never crash the audit,
        # while valid sibling entries still apply.
        doc = {"ignores": ["evil-string", {"rule_id": "SEC003", "path": "x.md", "reason": "ok"}]}
        f = [{"rule_id": "SEC003", "file": "x.md", "line": 1, "severity": "medium"}]
        self.assertEqual(agent_audit._apply_ignores(f, doc, {}, root="."), [])


class HiddenCharTests(_CacheSafe):
    def _ids(self, text):
        return {x.rule_id for x in agent_audit.scan_hidden_chars(text, Path("x.md"))}
    def test_bidi_override_flagged(self):
        self.assertIn("SEC001", self._ids("a‮b"))
    def test_directional_mark_flagged(self):       # LRM/RLM, previously missed
        self.assertIn("SEC001", self._ids("a‎b"))
    def test_zero_width_flagged(self):
        self.assertIn("SEC002", self._ids("a​b"))
    def test_tag_char_smuggling_flagged(self):     # U+E0000 block
        self.assertIn("SEC002", self._ids("a\U000e0041b"))
    def test_soft_hyphen_flagged(self):            # U+00AD, category Cf
        self.assertIn("SEC002", self._ids("a­b"))
    def test_clean_ascii_no_findings(self):
        self.assertEqual(agent_audit.scan_hidden_chars("clean ascii text", Path("x.md")), [])
    def test_fullwidth_command_normalized_then_caught(self):
        # NFKC turns fullwidth into ASCII so scan_security's dangerous-pattern scan fires.
        text = "ｒｍ －ｒｆ /"   # fullwidth 'rm -rf /'
        f = agent_audit.scan_security(agent_audit.nfkc(text), Path("x.md"),
                                      dangerous_id="SEC010", secret_id="SEC011", prose=False)
        self.assertIn("SEC010", {x.rule_id for x in f})


class HomoglyphTests(_CacheSafe):
    def test_cyrillic_in_latin_word_flagged(self):    # 'pаypal' — 'а' is U+0430
        f = agent_audit.scan_homoglyphs("connect to pаypal", Path("x.md"), allow_scripts={"Latin", "Common"})
        self.assertIn("SEC003", {x.rule_id for x in f})
    def test_pure_nonlatin_word_not_flagged(self):    # legitimate Russian word, mixed into English prose
        self.assertEqual(agent_audit.scan_homoglyphs("deploy to сервер cluster", Path("x.md"),
                          allow_scripts={"Latin", "Common"}), [])
    def test_pure_cjk_not_flagged(self):
        self.assertEqual(agent_audit.scan_homoglyphs("city 北京 here", Path("x.md"),
                          allow_scripts={"Latin", "Common"}), [])
    def test_url_homoglyph_flagged_regardless_of_language(self):
        # An all-Cyrillic-lookalike host is flagged even if the skill declares language: ru.
        f = agent_audit.scan_homoglyphs("see https://pаypal.com/login", Path("x.md"),
                          allow_scripts={"Latin", "Common", "Cyrillic"}, host_aware=True)
        self.assertIn("SEC003", {x.rule_id for x in f})
    def test_plain_ascii_clean(self):
        self.assertEqual(agent_audit.scan_homoglyphs("normal english text and a url https://example.com",
                          Path("x.md"), allow_scripts={"Latin", "Common"}), [])


class DeltaGateTests(_CacheSafe):
    def test_preexisting_finding_not_counted_as_introduced(self):
        base = [{"rule_id": "SEC010", "file": "a.md", "message": "Potentially dangerous instruction detected: rm -rf."}]
        head = [dict(base[0]),
                {"rule_id": "SEC010", "file": "b.md", "message": "Potentially dangerous instruction detected: curl|sh."}]
        introduced = agent_audit.introduced_findings(base, head)
        self.assertEqual([f["file"] for f in introduced], ["b.md"])

    def test_finding_key_ignores_line(self):
        a = {"rule_id": "SEC010", "file": "a.md", "line": 5, "message": "m"}
        b = {"rule_id": "SEC010", "file": "a.md", "line": 99, "message": "m"}
        self.assertEqual(agent_audit.finding_key(a), agent_audit.finding_key(b))


class _SubprocFixture:
    """Helper: write a temp project with a .mcp.json holding an inline OpenAI-style
    token (triggers SEC011 high) and run the CLI via subprocess so lru_cache is fresh."""
    SCRIPT = str(Path(__file__).with_name("agent_audit.py"))

    @staticmethod
    def run(extra_args, env=None):
        import os, subprocess
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".mcp.json").write_text(
                '{"mcpServers":{"x":{"command":"node","env":{"API_KEY":"sk-ABCDEFGHIJKLMNOPQRSTUVWX"}}}}',
                encoding="utf-8",
            )
            run_env = dict(os.environ)
            if env:
                run_env.update(env)
            return subprocess.run(
                ["python3", _SubprocFixture.SCRIPT, "audit-project", d, *extra_args],
                capture_output=True, text=True, env=run_env,
            )


class GithubFormatTests(unittest.TestCase):
    def test_high_finding_emits_error_annotation(self):
        proc = _SubprocFixture.run(["--format", "github"])
        # GitHub workflow command for a high-severity finding, repo-relative path + rule_id title.
        self.assertIn("::error ", proc.stdout)
        self.assertIn("file=.mcp.json", proc.stdout)
        self.assertIn("title=SEC011", proc.stdout)


class FailModeKillSwitchTests(unittest.TestCase):
    def test_advisory_does_not_block_but_reports(self):
        proc = _SubprocFixture.run(["--fail-on", "high"], env={"SGT_FAIL_MODE": "advisory"})
        self.assertEqual(proc.returncode, 0)
        self.assertIn("SEC011", proc.stdout)  # finding still reported

    def test_enforce_default_blocks(self):
        proc = _SubprocFixture.run(["--fail-on", "high"])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("SEC011", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
