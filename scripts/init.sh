#!/usr/bin/env bash
# init.sh — bash fallback for integration-init (for runtimes without AskUserQuestion or for headless setup).
#
# Mirrors the integration-init workflow:
#   - Detects environment
#   - Asks (interactively) or accepts CLI flags for tool selection
#   - Runs native installers
#   - Removes per-tool documentation blocks for DESELECTED tools from AGENTS.md and agents/code-reviewer.md
#     (adding blocks for newly installed tools is delegated to the integration-init skill — see Main)
#
# Usage:
#   ./scripts/init.sh                                              # full interactive
#   ./scripts/init.sh --with crg,repomix                           # non-interactive selection
#   ./scripts/init.sh --with crg --use-fork                        # CRG fork variant
#   ./scripts/init.sh --with crg --use-cli --build-mode skip        # CRG in CLI mode, no initial build
#   ./scripts/init.sh --all                                        # install everything (CRG + repomix + serena, defaults)
#   ./scripts/init.sh --advise-only --all                          # print commands, don't execute
#   ./scripts/init.sh --dry-run                                    # full simulation, no side effects

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SELECTED=()
USE_FORK=false
USE_MODE="mcp"             # mcp | cli
BUILD_MODE="full-now"      # full-now | full-later | skip
INSTALL_PRECOMMIT=false
ENRICHMENT=false
SERENA_LANGS="python,typescript"
ADVISE_ONLY=false
DRY_RUN=false

AGENTS_MD="$REPO_ROOT/AGENTS.md"
CODE_REVIEWER_MD="$REPO_ROOT/agents/code-reviewer.md"

# ── Arg parsing ────────────────────────────────────────────────────────────────

usage() {
  cat <<'EOF'
Skill Governance Toolkit — optional integrations installer.

Tool selection:
  --with TOOL[,TOOL]   Non-interactive selection. Tools: crg, repomix, serena
  --all                Install all three with defaults

CRG sub-options:
  --use-fork           Install better-code-review-graph fork instead of upstream main
  --use-mcp            CRG in MCP server mode (default)
  --use-cli            CRG in CLI mode (no MCP server)
  --build-mode MODE    full-now (default) | full-later | skip
  --enrichment         Install with [enrichment] extras (Python Jedi)
  --pre-commit         Install supplementary pre-commit hook

Serena sub-options:
  --serena-langs LANGS Comma-separated languages (default: python,typescript)

Mode:
  --advise-only        Print commands instead of running them
  --dry-run            Simulate without side effects (no install, no doc writes)

Examples:
  ./scripts/init.sh
  ./scripts/init.sh --all
  ./scripts/init.sh --with crg --use-mcp --build-mode full-now --enrichment --pre-commit
  ./scripts/init.sh --advise-only --with crg,repomix
EOF
  exit 0
}

# Validate --build-mode value against the closed set documented in --help.
# Fail-fast with a clear message instead of silently accepting an invalid value
# (which then disappears in the case-statement in install_crg() — see line ~200).
_validate_build_mode() {
  case "$1" in
    full-now|full-later|skip) return 0 ;;
    *) echo "Invalid --build-mode '$1'. Allowed: full-now | full-later | skip" >&2; exit 2 ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with)            IFS=',' read -ra SELECTED <<< "$2"; shift 2 ;;
    --all)             SELECTED=("crg" "repomix" "serena"); shift ;;
    --use-fork)        USE_FORK=true; shift ;;
    --use-mcp)         USE_MODE="mcp"; shift ;;
    --use-cli)         USE_MODE="cli"; shift ;;
    --build-mode)      _validate_build_mode "$2"; BUILD_MODE="$2"; shift 2 ;;
    --enrichment)      ENRICHMENT=true; shift ;;
    --pre-commit)      INSTALL_PRECOMMIT=true; shift ;;
    --serena-langs)    SERENA_LANGS="$2"; shift 2 ;;
    --advise-only)     ADVISE_ONLY=true; shift ;;
    --dry-run)         DRY_RUN=true; shift ;;
    -h|--help)         usage ;;
    *)                 echo "Unknown flag: $1" >&2; usage ;;
  esac
done

# ── Helpers ────────────────────────────────────────────────────────────────────

say() { echo -e "$@"; }
run() {
  # Direct execution — NOT eval. Each arg is preserved as a separate token
  # which prevents shell-injection through user-controlled CLI parameters
  # (e.g. crafted --serena-langs values).
  if $ADVISE_ONLY || $DRY_RUN; then
    say "  [would run] $*"
  else
    say "  [run] $*"
    "$@"
  fi
}

has() { command -v "$1" >/dev/null 2>&1; }

confirm() {
  local prompt="$1"; local default="${2:-y}"
  if [[ ${#SELECTED[@]} -gt 0 ]]; then return 0; fi   # non-interactive: skip confirms
  local hint="[Y/n]"; [[ "$default" == "n" ]] && hint="[y/N]"
  read -p "$prompt $hint " -r ans
  ans="${ans:-$default}"
  [[ "$ans" =~ ^[Yy]$ ]]
}

# ── Interactive mode (when --with not used) ────────────────────────────────────

interactive_select() {
  say "── Select optional integrations to install ──"
  say "1) code-review-graph  (Tree-sitter + SQLite graph, 8.2× token reduction on real PRs)"
  say "2) repomix            (one-shot repo packer for small repos or external review)"
  say "3) serena             (LSP-bridge for semantic refactoring)"
  say ""
  read -p "Selection (comma-separated, e.g. '1,2'; blank to skip): " sel
  [[ -z "$sel" ]] && { say "No selection; exiting."; exit 0; }

  IFS=',' read -ra nums <<< "$sel"
  for n in "${nums[@]}"; do
    n=$(echo "$n" | tr -d ' ')
    case "$n" in
      1) SELECTED+=("crg") ;;
      2) SELECTED+=("repomix") ;;
      3) SELECTED+=("serena") ;;
      *) say "  ignored: '$n'" ;;
    esac
  done
}

interactive_crg_config() {
  say ""
  say "── code-review-graph configuration ──"
  if confirm "Use upstream main? (No = use fork with bug fixes)"; then
    USE_FORK=false
  else
    USE_FORK=true
  fi
  if confirm "Run in MCP server mode? (No = CLI mode)"; then
    USE_MODE="mcp"
  else
    USE_MODE="cli"
  fi
  confirm "Install with [enrichment] extras (Python Jedi)?" "n" && ENRICHMENT=true || ENRICHMENT=false
  read -p "Initial build mode [full-now/full-later/skip] (default full-now): " bm
  BUILD_MODE="${bm:-full-now}"
  _validate_build_mode "$BUILD_MODE"
  confirm "Install supplementary pre-commit hook? (CRG already installs its own post-edit hook)" "n" && INSTALL_PRECOMMIT=true || INSTALL_PRECOMMIT=false
}

# ── Environment detection ──────────────────────────────────────────────────────

detect_env() {
  say "── Environment ──"
  say "  Python:  $(python3 --version 2>&1 || echo 'NOT FOUND')"
  say "  pipx:    $(pipx --version 2>&1 || echo 'NOT FOUND')"
  say "  npm:     $(npm --version 2>&1 || echo 'NOT FOUND')"
  say "  Already installed:"
  has code-review-graph && say "    ✓ code-review-graph $(code-review-graph --version 2>&1 | head -1)" || say "    · code-review-graph: not installed"
  has repomix && say "    ✓ repomix $(repomix --version 2>&1 | head -1)" || say "    · repomix: not installed"
  has serena && say "    ✓ serena $(serena --version 2>&1 | head -1)" || say "    · serena: not installed"
  say ""
}

# ── Per-integration install ─────────────────────────────────────────────────────

install_crg() {
  say ""
  say "── Installing code-review-graph ──"

  # Preflight: CRG is distributed via pipx (Python isolated CLI). Bail early with
  # the same hint Serena's branch gives — avoids a noisy late failure from pipx
  # not being on PATH. (Skipped in --advise-only / --dry-run since `run` won't
  # actually invoke pipx in those modes.)
  if ! $ADVISE_ONLY && ! $DRY_RUN && ! has pipx; then
    say "  ✗ pipx not found — install pipx first (e.g. \`brew install pipx\` or \`python3 -m pip install --user pipx\`), then re-run."
    return 1
  fi

  if $USE_FORK; then
    # Pinned to an immutable commit — a personal fork's mutable default branch
    # is exactly the supply-chain surface the audit gate polices. Bump the pin
    # deliberately (after review) via SGT_CRG_FORK_REF.
    local fork_ref="${SGT_CRG_FORK_REF:-144bd58b5d91ba3e3909ab93985c12b09ce94494}"
    run pipx install "git+https://github.com/n24q02m/better-code-review-graph@${fork_ref}"
  else
    if $ENRICHMENT; then
      run pipx install 'code-review-graph[enrichment]'
    else
      run pipx install code-review-graph
    fi
  fi

  # Native installer detects platform and writes MCP config or rules
  if [[ "$USE_MODE" == "cli" ]]; then
    run code-review-graph install --no-mcp
  else
    run code-review-graph install
  fi

  case "$BUILD_MODE" in
    full-now)
      run code-review-graph build
      ;;
    full-later)
      say "  [info] Skipping initial build. Run \`code-review-graph build\` when ready."
      ;;
    skip)
      say "  [info] No initial build. Graph populates lazily."
      ;;
    *)
      # Defensive default: should be unreachable because _validate_build_mode
      # rejects invalid values at arg-parse time. Kept as a safety net so any
      # future code path that mutates BUILD_MODE post-parse fails loudly instead
      # of silently no-op'ing the build strategy.
      say "  [error] Unknown BUILD_MODE='$BUILD_MODE' (expected full-now | full-later | skip)" >&2
      return 1
      ;;
  esac

  if $INSTALL_PRECOMMIT; then
    run "$REPO_ROOT/scripts/install-pre-commit-hook.sh"  # single token — quoted path is correct here
  fi
}

install_repomix() {
  say ""
  say "── Installing repomix ──"
  # Skip the prereq guard in --advise-only / --dry-run (like install_crg) so the
  # full plan still prints when npm is absent — `run` won't invoke npm in those
  # modes anyway. Without this the integration is silently dropped from the plan.
  if ! $ADVISE_ONLY && ! $DRY_RUN && ! has npm; then
    say "  ✗ npm not found — install Node.js first, then re-run."
    return 1
  fi
  run npm install -g repomix
  if confirm "Initialize repomix.config.json with defaults?" "y"; then
    run repomix --init
  fi
}

install_serena() {
  say ""
  say "── Installing serena ──"
  # Advise/dry-aware prereq guard — see install_repomix.
  if ! $ADVISE_ONLY && ! $DRY_RUN && ! has pipx; then
    say "  ✗ pipx not found — install pipx first (e.g. \`brew install pipx\` or \`python3 -m pip install --user pipx\`), then re-run."
    return 1
  fi
  run pipx install serena-mcp
  run serena init "--languages=$SERENA_LANGS"
}

# ── Marker-block cleanup ───────────────────────────────────────────────────────
# init.sh removes per-tool blocks for DESELECTED integrations. Adding blocks for
# newly installed tools is delegated to the integration-init skill (host runtime,
# needs references/integrations.md template content) — see the note in Main below.
# (There is deliberately no bash inject helper here: it would duplicate marker
# logic and drift from marker_block.py / the skill's injector.)

remove_marker_block() {
  local file="$1"; local marker_id="$2"
  [[ ! -f "$file" ]] && return
  if $DRY_RUN; then
    say "  [dry-run] would remove block '$marker_id' from $file"
    return
  fi
  python3 - "$file" "$marker_id" <<'PYEOF'
import sys, re
path, marker_id = sys.argv[1], sys.argv[2]
text = open(path).read()
# marker_id already carries its family prefix (integration:{tool} / handoff:{tool}).
begin = f"<!-- skill-init: {marker_id} BEGIN -->"
end   = f"<!-- skill-init: {marker_id} END -->"
pattern = re.compile(r'\n*' + re.escape(begin) + r'.*?' + re.escape(end) + r'\n*', re.DOTALL)
new = pattern.sub('\n', text)
if new != text:
    open(path, 'w').write(new)
    print(f"  ✓ removed '{marker_id}' from {path}")
PYEOF
}

# ── Main ───────────────────────────────────────────────────────────────────────

main() {
  detect_env

  if [[ ${#SELECTED[@]} -eq 0 ]]; then
    interactive_select
    if [[ " ${SELECTED[*]} " =~ " crg " ]]; then
      interactive_crg_config
    fi
  fi

  # Fail-fast on an unknown --with value instead of silently no-op'ing it later
  # (the install loop would just print "Unknown tool" and exit 0).
  for tool in "${SELECTED[@]}"; do
    case "$tool" in
      crg|repomix|serena) ;;
      *) say "  ✗ Unknown integration '$tool' (valid: crg, repomix, serena)" >&2; exit 1 ;;
    esac
  done

  say ""
  say "── Plan ──"
  say "  Selected: ${SELECTED[*]}"
  $ADVISE_ONLY && say "  Mode: ADVISE-ONLY (no commands executed)"
  $DRY_RUN     && say "  Mode: DRY-RUN (full simulation, no side effects)"
  say ""

  local installed=()
  for tool in "${SELECTED[@]}"; do
    case "$tool" in
      crg)     install_crg     && installed+=("crg") ;;
      repomix) install_repomix && installed+=("repomix") ;;
      serena)  install_serena  && installed+=("serena") ;;
      *)       say "  Unknown tool: $tool" ;;
    esac
  done

  # ── Documentation injection scope ──────────────────────────────────────────
  # init.sh is a PARTIAL fallback covering: env detection, native installer
  # invocation, and removal of marker blocks for DESELECTED tools.
  #
  # Adding per-integration documentation blocks for newly INSTALLED tools is
  # NOT done by this script — that requires parsing template content from
  # `references/integrations.md` which is host-runtime work. For full
  # behavior including documentation injection, invoke the `integration-init`
  # skill via the host runtime (or `/integration-init` slash command in
  # Claude Code).

  if $ADVISE_ONLY || $DRY_RUN; then
    say ""
    say "── Skipping marker-block cleanup (advise-only / dry-run) ──"
  else
    say ""
    say "── Marker-block cleanup (deselected tools only) ──"
    for tool in crg repomix serena; do
      # `${installed[*]:-}` guards the empty-array case under `set -u` (bash 3.2).
      if [[ ! " ${installed[*]:-} " =~ " $tool " ]]; then
        # AGENTS.md uses the integration:{tool} inner marker; code-reviewer.md
        # uses handoff:{tool} — pass each its own family or removal silently no-ops.
        remove_marker_block "$AGENTS_MD" "integration:$tool"
        remove_marker_block "$CODE_REVIEWER_MD" "handoff:$tool"
      fi
    done
    if [[ ${#installed[@]} -gt 0 ]]; then
      say ""
      say "⚠ init.sh installed ${installed[*]} but did NOT inject per-integration"
      say "  documentation blocks into AGENTS.md / agents/code-reviewer.md."
      say "  Run \`/integration-init\` via your host runtime (or invoke the"
      say "  integration-init skill) to complete the documentation injection."
    fi
  fi

  say ""
  say "── Done ──"
  say "Installed: ${installed[*]:-none}"
  say ""
  if [[ ${#installed[@]} -eq 0 ]]; then
    say "No tools installed (nothing to suggest next-step for)."
    return 0
  fi
  say "Next steps:"
  for tool in "${installed[@]}"; do
    case "$tool" in
      crg)
        say "  · code-review-graph: restart editor; verify with \`code-review-graph status\`"
        ;;
      repomix)
        say "  · repomix: run \`repomix --output context.xml\` from project root for first pack"
        ;;
      serena)
        say "  · serena: restart editor to load LSP servers"
        ;;
    esac
  done
}

main "$@"
