#!/usr/bin/env bash
# install-pre-commit-hook.sh — supplementary git pre-commit hook for code-review-graph (CRG).
#
# Why this exists:
#   CRG installs its own post-edit / post-commit hook automatically (via `code-review-graph install`).
#   This script adds a SUPPLEMENTARY pre-commit hook that:
#     - Verifies the graph is in sync with the working tree BEFORE the commit lands.
#     - Blocks commits when the graph is stale (graph must be regenerated first).
#
#   Use this only if you want hard guarantees the graph reflects what's being committed.
#   For most teams, CRG's built-in post-edit hook is enough.
#
# Modes:
#   - Standalone (default):   writes .git/hooks/pre-commit directly
#   - pre-commit framework:   appends a hook entry to .pre-commit-config.yaml (if present)
#
# Usage:
#   ./scripts/install-pre-commit-hook.sh
#   ./scripts/install-pre-commit-hook.sh --uninstall
#   ./scripts/install-pre-commit-hook.sh --check          # show what would happen, don't install

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "✗ Not a git repository (no .git found). Initialize git first: git init"
  exit 1
fi

HOOK_FILE="$REPO_ROOT/.git/hooks/pre-commit"
PCC_FILE="$REPO_ROOT/.pre-commit-config.yaml"
MARKER="# skill-init: CRG freshness check"

MODE="install"
[[ "${1:-}" == "--uninstall" ]] && MODE="uninstall"
[[ "${1:-}" == "--check" ]] && MODE="check"

# ── Detect pre-commit framework ────────────────────────────────────────────────

if [[ -f "$PCC_FILE" ]] && grep -q "^repos:" "$PCC_FILE" 2>/dev/null; then
  FRAMEWORK=true
  echo "ℹ Detected .pre-commit-config.yaml — will use the pre-commit framework integration."
else
  FRAMEWORK=false
  echo "ℹ No .pre-commit-config.yaml — will install a standalone hook at .git/hooks/pre-commit."
fi

# ── Standalone hook payload ────────────────────────────────────────────────────

read -r -d '' STANDALONE_PAYLOAD <<'HOOK_EOF' || true
#!/usr/bin/env bash
# skill-init: CRG freshness check
# This pre-commit hook verifies code-review-graph is in sync with the working tree.
# If graph is stale, the commit is blocked and you must regenerate.

set -e

if ! command -v code-review-graph >/dev/null 2>&1; then
  echo "⚠ code-review-graph not installed — skipping CRG freshness check."
  exit 0
fi

if ! code-review-graph build --check >/dev/null 2>&1; then
  echo "✗ code-review-graph: graph is stale."
  echo "  Regenerate with: code-review-graph build --incremental"
  echo "  Then re-run the commit."
  echo ""
  echo "  To bypass this check once: git commit --no-verify"
  exit 1
fi

echo "✓ code-review-graph: graph in sync."
exit 0
HOOK_EOF

# ── pre-commit framework hook entry ────────────────────────────────────────────

read -r -d '' FRAMEWORK_PAYLOAD <<'PCC_EOF' || true

  - repo: local
    hooks:
      - id: crg-freshness
        name: code-review-graph freshness check
        entry: code-review-graph build --check
        language: system
        always_run: true
        pass_filenames: false
PCC_EOF

# ── Actions ────────────────────────────────────────────────────────────────────

show_check() {
  echo ""
  echo "── Dry-run (no changes will be made) ──"
  if $FRAMEWORK; then
    echo "Would APPEND this entry to $PCC_FILE under the 'repos:' key:"
    echo "$FRAMEWORK_PAYLOAD"
  else
    echo "Would CREATE / OVERWRITE $HOOK_FILE with:"
    echo "$STANDALONE_PAYLOAD"
  fi
  echo "── End dry-run ──"
}

do_install() {
  if $FRAMEWORK; then
    if grep -q "id: crg-freshness" "$PCC_FILE"; then
      echo "  Already installed in $PCC_FILE — no changes."
      return
    fi
    echo "$FRAMEWORK_PAYLOAD" >> "$PCC_FILE"
    echo "✓ Appended CRG hook entry to $PCC_FILE"
    echo "  Run \`pre-commit install\` to activate."
  else
    mkdir -p "$REPO_ROOT/.git/hooks"
    if [[ -f "$HOOK_FILE" ]] && ! grep -q "$MARKER" "$HOOK_FILE" 2>/dev/null; then
      echo "⚠ Existing $HOOK_FILE detected and does not have our marker."
      echo "  Back up and re-run, or merge manually."
      cp "$HOOK_FILE" "$HOOK_FILE.bak.$(date +%s)"
      echo "  Backup saved as $HOOK_FILE.bak.*"
    fi
    echo "$STANDALONE_PAYLOAD" > "$HOOK_FILE"
    chmod +x "$HOOK_FILE"
    echo "✓ Installed CRG freshness check at $HOOK_FILE"
  fi
  echo ""
  echo "Done. Next commit will run: code-review-graph build --check"
}

do_uninstall() {
  if $FRAMEWORK; then
    if grep -q "id: crg-freshness" "$PCC_FILE"; then
      # Remove the framework entry (4 lines after id line — naive but works for our payload)
      python3 - "$PCC_FILE" <<'PYEOF'
import sys, re
path = sys.argv[1]
text = open(path).read()
# Remove the local repo block we added (idempotent for our specific shape)
pattern = re.compile(r'\n\s*- repo: local\s*\n\s*hooks:\s*\n\s*- id: crg-freshness.*?(?=\n\s*- repo:|\Z)', re.DOTALL)
new = pattern.sub('', text)
if new != text:
    open(path, 'w').write(new)
    print(f"  ✓ removed CRG hook entry from {path}")
else:
    print(f"  · CRG hook entry not found in {path}")
PYEOF
    fi
  else
    if [[ -f "$HOOK_FILE" ]] && grep -q "$MARKER" "$HOOK_FILE"; then
      rm "$HOOK_FILE"
      echo "✓ Removed $HOOK_FILE"
    else
      echo "  · $HOOK_FILE not present or not installed by this script."
    fi
  fi
}

case "$MODE" in
  install)    do_install ;;
  uninstall)  do_uninstall ;;
  check)      show_check ;;
esac
