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


if __name__ == "__main__":
    unittest.main(verbosity=2)
