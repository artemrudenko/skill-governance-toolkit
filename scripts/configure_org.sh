#!/usr/bin/env bash
# configure_org.sh — replace the REPLACE-ME-ORG / {your-org} sentinels with
# your real GitHub org (or username) across distribution artifacts.
#
# Background: the toolkit ships as a publishable template. Several files
# carry placeholder values that point at a fictional org so the release
# zip is publish-ready after a single, auditable substitution.
#
# Usage:
#   bash scripts/configure_org.sh <github-org-or-username>
#   bash scripts/configure_org.sh --dry-run <github-org-or-username>   # show what would change
#
# Files touched (relative to repo root):
#   - .claude-plugin/marketplace.json   (owner.name + owner.url)
#   - README.md                          (any "{your-org}" — install commands)
#
# Idempotent: re-running with the same arg is a no-op.

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 [--dry-run] <github-org-or-username>" >&2
  echo "Example: $0 acme-corp" >&2
  exit 1
fi

DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true; shift
fi
[[ $# -lt 1 ]] && { echo "Missing org argument" >&2; exit 1; }
ORG="$1"

# Basic validation — GitHub usernames / orgs are alphanumeric + hyphens, ≤39 chars.
if ! [[ "$ORG" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,38}$ ]]; then
  echo "Invalid org name: '$ORG'. Must match GitHub username pattern (alphanumeric + hyphens, ≤39 chars)." >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Configuring toolkit for org: $ORG"
echo "  repo root: $REPO_ROOT"
$DRY_RUN && echo "  mode: dry-run (no writes)"

# Targets to update — each entry is a "file:old-pattern" pair processed via sed.
# Use a fixed delimiter that can't appear in the values.
update_file() {
  local file="$1" pat="$2"
  if [[ ! -f "$file" ]]; then
    echo "  · skipped (missing): $file"
    return 0
  fi
  if ! grep -q "$pat" "$file"; then
    echo "  · skipped (no $pat found): $(basename "$file")"
    return 0
  fi
  local hits; hits=$(grep -c "$pat" "$file")
  if $DRY_RUN; then
    echo "  · WOULD replace $hits × '$pat' → '$ORG' in $(basename "$file")"
  else
    # Use # as sed delimiter; ORG validation rejects # so this is safe.
    sed -i.bak "s#$pat#$ORG#g" "$file" && rm -f "$file.bak"
    echo "  ✓ replaced $hits × '$pat' → '$ORG' in $(basename "$file")"
  fi
}

update_file "$REPO_ROOT/.claude-plugin/marketplace.json" "REPLACE-ME-ORG"
update_file "$REPO_ROOT/.claude-plugin/marketplace.json" "{your-org}"
update_file "$REPO_ROOT/README.md"                       "{your-org}"

echo ""
echo "Done. Next steps:"
echo "  · Verify: grep -rn 'REPLACE-ME-ORG\\|{your-org}' . --include='*.json' --include='*.md'"
echo "  · Commit: git add -p && git commit -m 'chore: configure org → $ORG'"
echo "  · Publish: see README § 'Distribution & installation'"
