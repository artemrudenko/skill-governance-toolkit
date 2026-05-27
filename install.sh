#!/usr/bin/env bash
# install.sh — interactive one-command installer.
#
# Asks which AI host and scope, auto-detects existing installs and
# reinstalls in --upgrade mode (cleans renamed/removed files).
#
# Usage:
#   ./install.sh                              # interactive
#   ./install.sh --force                      # interactive, then force-wipe target dirs before copy
#   ./install.sh --yes-default                # non-interactive: Claude + project scope (CI use)
#   ./install.sh --category discovery         # forwarded — selective install (since 1.8.0)
#   ./install.sh --tier stable                # forwarded — tier filter
#   ./install.sh --skill skill-find           # forwarded — explicit skill list
#   ./install.sh --interactive                # forwarded — category-picker menu

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALLER="$REPO_ROOT/scripts/install.sh"

[[ -x "$INSTALLER" ]] || { echo "Error: $INSTALLER not found or not executable" >&2; exit 1; }

FORCE_FLAG=""
NON_INTERACTIVE=0
# Pass-through flags for selective install (since 1.8.0). We don't parse them
# semantically here — just forward to scripts/install.sh so the canonical
# filter logic stays in one place (resolve_skill_subset + filter_skills.py).
PASSTHROUGH=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)         FORCE_FLAG="--force"; shift ;;
    --yes-default)   NON_INTERACTIVE=1; shift ;;
    --category)      PASSTHROUGH+=("--category" "$2"); shift 2 ;;
    --category=*)    PASSTHROUGH+=("$1"); shift ;;
    --tier)          PASSTHROUGH+=("--tier" "$2"); shift 2 ;;
    --tier=*)        PASSTHROUGH+=("$1"); shift ;;
    --skill)         PASSTHROUGH+=("--skill" "$2"); shift 2 ;;
    --skill=*)       PASSTHROUGH+=("$1"); shift ;;
    --interactive)   PASSTHROUGH+=("--interactive"); shift ;;
    -h|--help)
      sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

# ── Menu helpers ───────────────────────────────────────────────────────────────

prompt() {
  local message="$1" default="$2" answer
  read -rp "$message [$default]: " answer
  echo "${answer:-$default}"
}

if [[ $NON_INTERACTIVE -eq 1 ]]; then
  host_choice=1
  scope_choice=2
else
  echo "Skill Governance Toolkit — installer"
  echo
  echo "Which AI host do you want to install for?"
  echo "  1) Claude Code"
  echo "  2) GitHub Copilot"
  echo "  3) OpenAI Codex CLI"
  echo "  4) Google Gemini CLI"
  echo "  5) Cursor"
  echo "  6) All five above"
  host_choice="$(prompt "Choice [1-6]" 1)"

  echo
  echo "Where should it be installed?"
  echo "  1) Global  — ~/.{host}/    (affects all projects)"
  echo "  2) Project — ./.{host}/    (this project only)"
  scope_choice="$(prompt "Choice [1-2]" 2)"
fi

case "$host_choice" in
  1) HOST_FLAG="--claude";  HOST_DIRS=("claude") ;;
  2) HOST_FLAG="--copilot"; HOST_DIRS=("github") ;;
  3) HOST_FLAG="--codex";   HOST_DIRS=("codex") ;;
  4) HOST_FLAG="--gemini";  HOST_DIRS=("gemini") ;;
  5) HOST_FLAG="--cursor";  HOST_DIRS=("cursor") ;;
  6) HOST_FLAG="--all";     HOST_DIRS=("claude" "github" "codex" "gemini" "cursor") ;;
  *) echo "Invalid host choice: $host_choice" >&2; exit 1 ;;
esac

case "$scope_choice" in
  1) SCOPE_FLAG="--global";  SCOPE_PREFIX="$HOME" ;;
  2) SCOPE_FLAG="--project"; SCOPE_PREFIX="$REPO_ROOT" ;;
  *) echo "Invalid scope choice: $scope_choice" >&2; exit 1 ;;
esac

# ── Detect existing install at the resolved target ─────────────────────────────
# An install is considered present if any host dir has a populated `skills/`
# subdir (or, for Copilot, the instructions markdown).

existing=0
for h in "${HOST_DIRS[@]}"; do
  target="$SCOPE_PREFIX/.$h"
  if [[ -d "$target/skills" ]] || [[ -f "$target/copilot-instructions.md" ]]; then
    existing=1
    break
  fi
done

# ── Resolve install mode ───────────────────────────────────────────────────────

if [[ -n "$FORCE_FLAG" ]]; then
  MODE_FLAG="$FORCE_FLAG"
  mode_label="force (wipe + reinstall)"
elif [[ $existing -eq 1 ]]; then
  MODE_FLAG="--upgrade"
  mode_label="upgrade (clean reinstall, removes stale files)"
else
  MODE_FLAG=""
  mode_label="fresh"
fi

echo
echo "Plan:"
echo "  host:  $HOST_FLAG"
echo "  scope: $SCOPE_FLAG  ($SCOPE_PREFIX)"
echo "  mode:  $mode_label"
echo

exec "$INSTALLER" $HOST_FLAG $SCOPE_FLAG $MODE_FLAG "${PASSTHROUGH[@]}"
