#!/usr/bin/env bash
# configure_org.sh — replace the REPLACE-ME-ORG / {your-org} sentinels with
# your real GitHub org (or username) across distribution artifacts.
#
# Background: the toolkit ships as a publishable template. Several files
# carry placeholder values that point at a fictional org so the release
# zip is publish-ready after a single, auditable substitution.
#
# Usage:
#   bash scripts/configure_org.sh <org-or-username>
#   bash scripts/configure_org.sh --dry-run <org-or-username>            # show what would change
#   bash scripts/configure_org.sh --host gitlab.example.com <org>        # also rewrite the github.com host
#   bash scripts/configure_org.sh --host https://gitlab.example.com <org> # full base URL accepted; scheme is stripped
#
# --host <base-host>: for orgs hosted outside github.com (e.g. private GitLab),
#   additionally replaces every hardcoded "github.com" host in the same target
#   files so install URLs work out of the box. The value is normalized to a
#   bare host (leading http(s):// and trailing "/" stripped). Without --host,
#   behavior is exactly the historical one: only the org sentinels change.
#
# Files touched (relative to repo root):
#   - .claude-plugin/marketplace.json   (owner.name + owner.url)
#   - README.md                          (any "{your-org}" — install commands)
#
# Idempotent: re-running with the same args is a no-op.

set -euo pipefail

usage() {
  echo "Usage: $0 [--dry-run] [--host <base-host>] <org-or-username>" >&2
  echo "Example: $0 acme-corp" >&2
  echo "Example: $0 --host gitlab.example.com acme-corp" >&2
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

DRY_RUN=false
HOST=""
ORG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true; shift ;;
    --host)
      [[ $# -ge 2 ]] || { echo "--host requires a value" >&2; usage; exit 1; }
      HOST="$2"; HOST_SET=true; shift 2 ;;
    -*)
      echo "Unknown flag: $1" >&2; usage; exit 1 ;;
    *)
      # First positional arg is the org; extras are ignored (historical behavior).
      [[ -n "$ORG" ]] || ORG="$1"
      shift ;;
  esac
done
[[ -n "$ORG" ]] || { echo "Missing org argument" >&2; exit 1; }

# Basic validation — GitHub usernames / orgs are alphanumeric + hyphens, ≤39 chars.
# This also guarantees ORG is safe on the replacement side of sed (no '#', '&', '\').
if ! [[ "$ORG" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,38}$ ]]; then
  echo "Invalid org name: '$ORG'. Must match GitHub username pattern (alphanumeric + hyphens, ≤39 chars)." >&2
  exit 2
fi

if [[ -n "${HOST_SET:-}" ]]; then
  # Normalize a full base URL to a bare host: strip scheme + trailing slash,
  # so "https://github.com/…" prefixes in the files are not doubled.
  HOST="${HOST#https://}"
  HOST="${HOST#http://}"
  HOST="${HOST%/}"
  # Reject anything unsafe for the sed replacement side or for a URL host
  # ('#' is the sed delimiter; quotes would corrupt JSON/markdown; '&' and
  # '\' are sed-replacement metacharacters).
  case "$HOST" in
    ''|*[[:space:]]*|*'#'*|*'"'*|*"'"*|*'&'*|*'\'*)
      echo "Invalid host: '$HOST'. Use a bare host or base URL without spaces, '#', quotes, '&' or '\\'." >&2
      exit 2 ;;
  esac
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Configuring toolkit for org: $ORG"
echo "  repo root: $REPO_ROOT"
$DRY_RUN && echo "  mode: dry-run (no writes)"

# Targets to update — each call is a "file / literal-pattern / replacement"
# triple processed via sed. Use a fixed delimiter that can't appear in the
# values (org + host validation both reject '#').
update_file() {
  local file="$1" pat="$2" repl="$3"
  if [[ ! -f "$file" ]]; then
    echo "  · skipped (missing): $file"
    return 0
  fi
  if ! grep -qF "$pat" "$file"; then
    echo "  · skipped (no $pat found): $(basename "$file")"
    return 0
  fi
  local hits; hits=$(grep -cF "$pat" "$file" || true)
  # sed has no fixed-string mode — escape regex '.' so e.g. "github.com"
  # cannot match "github-com". The other sentinel chars ({}-) are literal in BRE.
  local sed_pat="${pat//./\\.}"
  if $DRY_RUN; then
    echo "  · WOULD replace $hits × '$pat' → '$repl' in $(basename "$file")"
  else
    # Use # as sed delimiter; validation rejects # so this is safe.
    # BSD sed requires a suffix argument to -i (here: .bak, removed after).
    sed -i.bak "s#$sed_pat#$repl#g" "$file" && rm -f "$file.bak"
    echo "  ✓ replaced $hits × '$pat' → '$repl' in $(basename "$file")"
  fi
}

update_file "$REPO_ROOT/.claude-plugin/marketplace.json" "REPLACE-ME-ORG" "$ORG"
update_file "$REPO_ROOT/.claude-plugin/marketplace.json" "{your-org}"     "$ORG"
update_file "$REPO_ROOT/README.md"                       "{your-org}"     "$ORG"

if [[ -n "$HOST" ]]; then
  echo "Rewriting hardcoded github.com host → $HOST"
  update_file "$REPO_ROOT/.claude-plugin/marketplace.json" "github.com" "$HOST"
  update_file "$REPO_ROOT/README.md"                       "github.com" "$HOST"
fi

echo ""
echo "Done. Next steps:"
echo "  · Verify: grep -rn 'REPLACE-ME-ORG\\|{your-org}' . --include='*.json' --include='*.md'"
echo "  · Commit: git add -p && git commit -m 'chore: configure org → $ORG'"
echo "  · Publish: see README § 'Distribution & installation'"
