#!/usr/bin/env bash
# audit.sh — self-CI runner for the Skill Governance Toolkit.
#
# Runs the same checks an external reviewer would: syntax, schema, layout,
# budget, secrets. Designed to catch regressions before publishing a release.
#
# Usage:
#   ./scripts/audit.sh            # run all checks, exit non-zero on any failure
#   ./scripts/audit.sh --verbose  # show per-check output
#
# Checks (each is a numbered phase):
#   P1 — bash -n on every shell script
#   P2 — py_compile every Python helper
#   P3 — JSON validity for every manifest
#   P4 — install.sh dry-run smoke test (fresh + re-run)
#   P5 — init.sh argv-passing smoke (verifies "$@" not eval semantics)
#   P6 — per-skill body-length budget (warn at >400, fail at >600)
#   P7 — secret-pattern scan via library-audit/references/security-spec.md
#   P8 — INDEX.jsonl freshness (regen and compare)
#   P9 — metainfo coverage (presence + closed vocab + skills-by-category matrix)
#   P10 — agent governance audit engine behavior
#   P11 — doctor health-check behavior
#   P12 — quickstart behavior
#   P13 — installer behavior
#   P14 — sgt command facade behavior
#   P15 — VERSION metadata synchronization
#
# Exit 0 if all checks pass; non-zero on any failure (so this is CI-friendly).

set -uo pipefail   # NOT -e — we want to run all checks even if one fails

VERBOSE=0
for arg in "$@"; do
  case "$arg" in
    --verbose|-v) VERBOSE=1 ;;
    -h|--help) sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAILED=()
WARNED=()

# ── Helpers ──────────────────────────────────────────────────────────────────

pass()  { echo "  ✓ $1"; }
fail()  { echo "  ✗ FAIL: $1"; FAILED+=("$1"); }
warn()  { echo "  ! WARN: $1"; WARNED+=("$1"); }
phase() { echo ""; echo "── $1 ──"; }

# ── P1: bash -n on shell scripts ─────────────────────────────────────────────

phase "P1 — Shell script syntax (bash -n)"
for f in "$ROOT"/install.sh "$ROOT"/scripts/*.sh; do
  [[ -f "$f" ]] || continue
  if bash -n "$f" 2>/dev/null; then
    pass "$(basename "$f")"
  else
    fail "$(basename "$f"): bash syntax error"
  fi
done

# ── P2: Python compile ───────────────────────────────────────────────────────

phase "P2 — Python helpers compile"
for f in "$ROOT"/scripts/*.py; do
  [[ -f "$f" ]] || continue
  if python3 -m py_compile "$f" 2>/dev/null; then
    pass "$(basename "$f")"
  else
    fail "$(basename "$f"): syntax error"
  fi
done

# ── P3: JSON manifest validity ───────────────────────────────────────────────

phase "P3 — JSON manifest validity"
for f in "$ROOT"/.claude-plugin/plugin.json \
         "$ROOT"/.claude-plugin/marketplace.json \
         "$ROOT"/.codex-plugin/plugin.json \
         "$ROOT"/gemini-extension.json \
         "$ROOT"/references/agent-audit-rules.json \
         "$ROOT"/skills/INDEX.jsonl; do
  [[ -f "$f" ]] || continue
  if python3 -c "
import json, sys
text = open(sys.argv[1]).read()
if sys.argv[1].endswith('.jsonl'):
    for line in text.splitlines():
        if line.strip(): json.loads(line)
else:
    json.loads(text)
" "$f" 2>/dev/null; then
    pass "$(basename "$f")"
  else
    fail "$(basename "$f"): invalid JSON"
  fi
done

if [[ -f "$ROOT/VERSION" ]] && grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.-]+)?$' "$ROOT/VERSION"; then
  pass "VERSION"
else
  fail "VERSION: missing or invalid semantic version"
fi

# ── P4: install.sh smoke test (fresh + re-run) ───────────────────────────────

phase "P4 — install.sh smoke test (fresh + re-run idempotency)"
SMOKE_DIR=$(mktemp -d)
trap "rm -rf $SMOKE_DIR" EXIT
if bash "$ROOT/scripts/install.sh" --claude --project --target-project="$SMOKE_DIR" >/dev/null 2>&1; then
  if [[ -f "$SMOKE_DIR/AGENTS.md" && -f "$SMOKE_DIR/.claude/CLAUDE.md" && -d "$SMOKE_DIR/skills" ]]; then
    pass "fresh install creates root AGENTS.md + .claude/CLAUDE.md + root skills/"
  else
    fail "fresh install missing expected files: AGENTS.md / .claude/CLAUDE.md / skills/"
  fi
  # Re-run — should be idempotent
  RERUN=$(bash "$ROOT/scripts/install.sh" --claude --project --target-project="$SMOKE_DIR" 2>&1)
  if echo "$RERUN" | grep -q "already current"; then
    pass "re-run shows 'already current' (idempotent)"
  else
    warn "re-run did not log 'already current' (idempotency unverified)"
  fi
else
  fail "install.sh --claude --project failed to run"
fi

# ── P5: init.sh argv passing (no eval, no shell-injection vector) ────────────

phase "P5 — init.sh argv hygiene"
if grep -E 'eval\s+"\$@"' "$ROOT/scripts/init.sh" >/dev/null 2>&1; then
  fail "init.sh contains 'eval \"\$@\"' (shell-injection vector)"
else
  pass "init.sh has no 'eval \"\$@\"'"
fi
# Verify run() invocations use separate tokens (not a single quoted string).
# Match lines like:  run "pipx install foo"  — a quoted string with a SPACE inside.
SINGLE_STRING_RUN_CALLS=$(grep -E '^\s*run "[^"]+ [^"]*"' "$ROOT/scripts/init.sh" 2>/dev/null | wc -l | tr -d ' ')
if [[ "${SINGLE_STRING_RUN_CALLS:-0}" -eq 0 ]]; then
  pass "run() invocations use separate tokens"
else
  fail "init.sh has $SINGLE_STRING_RUN_CALLS run() calls passing commands as single strings"
fi

# ── P6: per-skill body-length budget ─────────────────────────────────────────

phase "P6 — Skill body length (≤200 clean, ≤400 warn, ≤600 risk, >600 critical)"
for f in "$ROOT"/skills/*/SKILL.md; do
  name=$(basename "$(dirname "$f")")
  body_lines=$(python3 -c "
import re
text = open('$f').read()
body = re.sub(r'^---\n.*?\n---\n', '', text, count=1, flags=re.DOTALL)
print(len(body.splitlines()))
")
  if   [[ "$body_lines" -le 200 ]]; then pass "$name: $body_lines (clean)"
  elif [[ "$body_lines" -le 400 ]]; then pass "$name: $body_lines (review-recommended, accepted)"
  elif [[ "$body_lines" -le 600 ]]; then warn "$name: $body_lines (overload risk — should extract)"
  else                                   fail "$name: $body_lines (critical — split now)"
  fi
done

# ── P7: secret-pattern scan ──────────────────────────────────────────────────

phase "P7 — Secret-pattern scan (skill bodies + agents)"
# Self-excluded files per security-spec.md
SECRETS=$(python3 -c "
import re, sys
from pathlib import Path
root = Path('$ROOT')
patterns = [
    r'sk-[A-Za-z0-9]{20,}',
    r'sk-ant-[a-zA-Z0-9_-]{32,}',
    r'xox[baprs]-[A-Za-z0-9-]{10,}',
    r'ghp_[A-Za-z0-9]{36}',
    r'AKIA[0-9A-Z]{16}',
    r'AIza[0-9A-Za-z\-_]{35}',
    r'-----BEGIN .* PRIVATE KEY-----',
]
hits = 0
for f in list(root.rglob('skills/**/SKILL.md')) + list(root.rglob('agents/**/*.md')):
    if 'library-audit' in str(f) or 'skill-evaluate' in str(f): continue  # spec self-exclude
    text = f.read_text()
    for pat in patterns:
        for m in re.finditer(pat, text):
            print(f'  ! secret pattern in {f}: {m.group(0)[:8]}...REDACTED')
            hits += 1
print(hits)
" 2>&1)
LAST=$(echo "$SECRETS" | tail -1)
if [[ "$LAST" -eq 0 ]]; then
  pass "no secret patterns detected in skill/agent bodies"
else
  fail "$LAST secret-pattern hit(s) detected"
fi

# ── P8: INDEX.jsonl freshness ────────────────────────────────────────────────

phase "P8 — INDEX.jsonl freshness"
# Since 1.8.0+ the installer's filter (--category/--tier/--skill) reads
# this file. Stale index = wrong subset gets installed silently. Drift is
# now a failure, not a warning. Fix: re-run `python3 scripts/build_index.py`.
TMP_INDEX=$(mktemp)
python3 "$ROOT/scripts/build_index.py" --skills-dir "$ROOT/skills" --output "$TMP_INDEX" >/dev/null 2>&1
if cmp -s "$TMP_INDEX" "$ROOT/skills/INDEX.jsonl"; then
  pass "INDEX.jsonl matches build_index.py output"
else
  fail "INDEX.jsonl drift detected — installer's filter would see wrong skills. Run: python3 scripts/build_index.py"
fi
rm -f "$TMP_INDEX"

# ── P9: metainfo coverage (since 1.8.0) ──────────────────────────────────────
# Mirrors library-audit Phase 5.5 — presence of metainfo.category / .tier,
# closed-vocab compliance, plus a printed skills-by-category matrix so the
# CI log shows the library shape at a glance.

phase "P9 — metainfo coverage (category × tier matrix + drift)"
COVERAGE_OUT=$(python3 - "$ROOT/skills/INDEX.jsonl" <<'PYEOF'
import json, sys
from collections import Counter
from pathlib import Path

CLOSED_CATEGORIES = {"code-review", "docs", "testing", "governance", "discovery", "research", "delivery"}
CLOSED_TIERS = {"stable", "preview", "experimental", "internal"}

index_path = Path(sys.argv[1])
if not index_path.exists():
    print("MISSING_INDEX")
    sys.exit(0)

orphans = []          # skills without any metainfo
missing_category = []
missing_tier = []
unknown_categories = set()
unknown_tiers = set()
deprecated_no_replace = []
cat_counts = Counter()
tier_counts = Counter()

for line in index_path.read_text().splitlines():
    if not line.strip():
        continue
    e = json.loads(line)
    name = e["name"]
    mi = e.get("metainfo") or {}
    if not mi or mi.get("tier") == "unknown":
        orphans.append(name)
        continue
    cats = mi.get("category") or []
    tier = mi.get("tier")
    if not cats:
        missing_category.append(name)
    if not tier:
        missing_tier.append(name)
    for c in cats:
        if c not in CLOSED_CATEGORIES:
            unknown_categories.add(c)
        cat_counts[c] += 1
    if tier and tier not in CLOSED_TIERS:
        unknown_tiers.add(tier)
    if tier:
        tier_counts[tier] += 1
    if mi.get("deprecated") and not mi.get("replaced_by"):
        deprecated_no_replace.append(name)

# Output protocol for the bash wrapper: ORPHANS=, MISSING_CAT=, MISSING_TIER=,
# UNKNOWN_CAT=, UNKNOWN_TIER=, DEPRECATED_NO_REPLACE=, then a printed matrix
# (informational only — bash won't parse the matrix lines, just echo them).
def csv(items):
    return ",".join(sorted(items)) if items else ""

print(f"ORPHANS={csv(orphans)}")
print(f"MISSING_CAT={csv(missing_category)}")
print(f"MISSING_TIER={csv(missing_tier)}")
print(f"UNKNOWN_CAT={csv(unknown_categories)}")
print(f"UNKNOWN_TIER={csv(unknown_tiers)}")
print(f"DEPRECATED_NO_REPLACE={csv(deprecated_no_replace)}")
print("MATRIX_BEGIN")
print(f"  Category coverage: {dict(cat_counts)}")
print(f"  Tier coverage:     {dict(tier_counts)}")
print("MATRIX_END")
PYEOF
)

if [[ "$COVERAGE_OUT" == "MISSING_INDEX" ]]; then
  fail "skills/INDEX.jsonl not found — cannot run P9"
else
  ORPHANS=$(echo "$COVERAGE_OUT" | grep '^ORPHANS=' | cut -d'=' -f2-)
  MISSING_CAT=$(echo "$COVERAGE_OUT" | grep '^MISSING_CAT=' | cut -d'=' -f2-)
  MISSING_TIER=$(echo "$COVERAGE_OUT" | grep '^MISSING_TIER=' | cut -d'=' -f2-)
  UNKNOWN_CAT=$(echo "$COVERAGE_OUT" | grep '^UNKNOWN_CAT=' | cut -d'=' -f2-)
  UNKNOWN_TIER=$(echo "$COVERAGE_OUT" | grep '^UNKNOWN_TIER=' | cut -d'=' -f2-)
  DEPRECATED_NO_REPLACE=$(echo "$COVERAGE_OUT" | grep '^DEPRECATED_NO_REPLACE=' | cut -d'=' -f2-)

  if [[ -n "$ORPHANS" ]]; then
    fail "orphan skills without metainfo: $ORPHANS"
  else
    pass "all skills have metainfo block"
  fi
  if [[ -n "$MISSING_CAT" ]]; then fail "skills with empty category: $MISSING_CAT"; else pass "all skills have non-empty category"; fi
  if [[ -n "$MISSING_TIER" ]]; then fail "skills with missing tier: $MISSING_TIER"; else pass "all skills have tier"; fi
  if [[ -n "$UNKNOWN_CAT" ]]; then warn "category values outside closed vocab: $UNKNOWN_CAT"; else pass "all category values within closed vocab"; fi
  if [[ -n "$UNKNOWN_TIER" ]]; then warn "tier values outside closed vocab: $UNKNOWN_TIER"; else pass "all tier values within enum"; fi
  if [[ -n "$DEPRECATED_NO_REPLACE" ]]; then warn "deprecated without replaced_by: $DEPRECATED_NO_REPLACE"; else pass "no deprecation contract violations"; fi
  echo "$COVERAGE_OUT" | sed -n '/MATRIX_BEGIN/,/MATRIX_END/p' | grep -vE '^(MATRIX_BEGIN|MATRIX_END)$'
fi

# ── P10: agent governance audit engine behavior ──────────────────────────────

phase "P10 — Agent governance audit engine behavior"
if python3 "$ROOT/scripts/test_agent_audit.py" >/dev/null 2>&1; then
  pass "CLI/MCP behavior tests pass"
else
  fail "CLI/MCP behavior tests failed — run: python3 scripts/test_agent_audit.py"
fi

# ── P11: doctor health-check behavior ────────────────────────────────────────

phase "P11 — Doctor health-check behavior"
if python3 "$ROOT/scripts/test_doctor.py" >/dev/null 2>&1; then
  pass "doctor behavior tests pass"
else
  fail "doctor behavior tests failed — run: python3 scripts/test_doctor.py"
fi

# ── P12: quickstart behavior ─────────────────────────────────────────────────

phase "P12 — Quickstart behavior"
if python3 "$ROOT/scripts/test_quickstart.py" >/dev/null 2>&1; then
  pass "quickstart behavior tests pass"
else
  fail "quickstart behavior tests failed — run: python3 scripts/test_quickstart.py"
fi

# ── P13: installer behavior ──────────────────────────────────────────────────

phase "P13 — Installer behavior"
if python3 "$ROOT/scripts/test_install.py" >/dev/null 2>&1; then
  pass "installer behavior tests pass"
else
  fail "installer behavior tests failed — run: python3 scripts/test_install.py"
fi

# ── P14: sgt command facade behavior ─────────────────────────────────────────

phase "P14 — sgt command facade behavior"
if python3 "$ROOT/scripts/test_sgt.py" >/dev/null 2>&1; then
  pass "sgt command facade tests pass"
else
  fail "sgt command facade tests failed — run: python3 scripts/test_sgt.py"
fi

# ── P15: VERSION metadata synchronization ────────────────────────────────────

phase "P15 — VERSION metadata synchronization"
if python3 "$ROOT/scripts/test_sync_version.py" >/dev/null 2>&1; then
  pass "version sync behavior tests pass"
else
  fail "version sync behavior tests failed — run: python3 scripts/test_sync_version.py"
fi
if python3 "$ROOT/scripts/sync_version.py" --check >/dev/null 2>&1; then
  pass "derived version metadata matches VERSION"
else
  fail "derived version metadata drift — run: python3 scripts/sync_version.py"
fi

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "══════════════════════════════════════════════════════════"
echo "Audit summary:"
echo "  ✓ passed:   determined by zero failures"
echo "  ! warned:   ${#WARNED[@]}"
echo "  ✗ failed:   ${#FAILED[@]}"
echo "══════════════════════════════════════════════════════════"

if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo ""
  echo "FAILURES:"
  for f in "${FAILED[@]}"; do echo "  - $f"; done
  exit 1
fi

exit 0
