#!/usr/bin/env bash
# install.sh — multi-runtime installer for the Skill Governance Toolkit.
#
# Three distinct directory roles (explicit in v1.6.1+):
#   SOURCE          — where the toolkit code lives (this script's parent dir)
#   TARGET_PROJECT  — where YOUR project lives (cwd by default; --target-project=PATH)
#   RUNTIME_DIR     — per-host install dir ($HOME/.{host}/ for global, $TARGET_PROJECT/.{host}/ for project)
#
# If SOURCE == TARGET_PROJECT (you're running this from inside the toolkit
# repo with --project scope), file copies into the project root would be
# no-ops; the installer detects this and skips identical-file copies with a
# log, instead of erroring out.
#
# Usage:
#   ./scripts/install.sh --claude --global              # ~/.claude/ install
#   ./scripts/install.sh --claude --project             # ./.claude/ install (uses cwd)
#   ./scripts/install.sh --claude --project --target-project=/path/to/proj
#   ./scripts/install.sh --all --global                 # all five runtimes
#   ./scripts/install.sh --claude --project --dry-run   # print plan, write nothing
#
# Install modes:
#   (default)      Fresh — overwrites managed dirs (skills/, agents/, references/, scripts/, commands/).
#                  User-owned root files (AGENTS.md / CLAUDE.md / GEMINI.md /
#                  .github/copilot-instructions.md) are NEVER overwritten — the installer
#                  upserts a single block between BEGIN/END markers; content outside the
#                  markers is preserved verbatim. See scripts/marker_block.py for semantics.
#   --upgrade      Clean upgrade — rsync --delete removes files no longer present in the
#                  source (handles renamed/removed skills). Requires rsync. Marker-block
#                  upsert behavior for user-owned files is unchanged.
#   --force        Wipe managed dirs before copy (does NOT alter the marker-block contract
#                  for user-owned root files — those are still upserted, not overwritten).

set -euo pipefail

# ── Prereq check ───────────────────────────────────────────────────────────────

if command -v rsync >/dev/null 2>&1; then
  COPY_TOOL="rsync"
else
  echo "Note: rsync not found — falling back to cp -R." >&2
  COPY_TOOL="cp"
fi

INSTALL_MODE="fresh"   # fresh | upgrade | force
DRY_RUN=false

_smart_copy() {
  local src="$1" dest="$2"
  if [[ "$COPY_TOOL" == "rsync" ]]; then
    local rsync_flags="-a --exclude=.DS_Store --exclude=__pycache__ --exclude=.skill-state"
    if [[ "$INSTALL_MODE" == "upgrade" ]]; then
      rsync $rsync_flags --delete "$src" "$dest"
    else
      rsync $rsync_flags "$src" "$dest"
    fi
  else
    if [[ "$INSTALL_MODE" == "upgrade" ]]; then
      echo "  ! --upgrade requires rsync; falling back to --force semantics for $dest" >&2
      rm -rf "$dest"
      mkdir -p "$dest"
    fi
    cp -R "$src" "$dest"
    find "$dest" \( -name '.DS_Store' -o -name '__pycache__' -o -name '.skill-state' \) -exec rm -rf {} + 2>/dev/null || true
  fi
}

_pre_install_cleanup() {
  local dest="$1"; shift
  local subdirs=("$@")
  if [[ "$INSTALL_MODE" != "force" ]]; then return 0; fi
  echo "  ⚠ --force: wiping $dest before install"
  for subdir in "${subdirs[@]}"; do
    rm -rf "$dest/$subdir"
  done
}

# _copy_file — copy a single file, but be safe about identical source/dest.
# If src and dest are the same path or have identical content, log and skip.
# If dest exists with different content and --force is NOT set, refuse for
# protected paths (AGENTS.md at project root specifically — see _safe_copy_agents_md).
_copy_file() {
  local src="$1" dest="$2"
  if [[ "$src" -ef "$dest" ]]; then
    echo "  · skipping copy: $dest is already the same file as source"
    return 0
  fi
  if [[ -f "$dest" ]] && cmp -s "$src" "$dest"; then
    echo "  · skipping copy: $dest already matches source content"
    return 0
  fi
  cp "$src" "$dest"
}

# _upsert_marker_block — append or update the toolkit's managed block in a
# USER-OWNED file (AGENTS.md / CLAUDE.md / GEMINI.md / copilot-instructions.md
# at project root). User content OUTSIDE the markers is NEVER modified.
# See scripts/marker_block.py for full semantics.
_upsert_marker_block() {
  local src="$1" dest="$2"
  if [[ "$src" -ef "$dest" ]]; then
    echo "  · skipping $dest (source==destination — same file in toolkit repo)"
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  python3 "$SOURCE/scripts/marker_block.py" upsert --file "$dest" --src "$src"
}

# ── Configuration ──────────────────────────────────────────────────────────────

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_PROJECT="$(pwd)"
TARGETS=()
SCOPE="global"

# Skill subset selection (since 1.8.0). Empty = "no filter active".
# Resolved into SELECTED_SKILLS array later — that's the canonical install list.
CATEGORY_FILTER=""
TIER_FILTER=""           # default "stable,preview" applied if still empty after arg parse
SKILL_FILTER=""
INTERACTIVE=false
SELECTED_SKILLS=()       # populated by resolve_skill_subset() near the start of main

# ── Arg parsing ────────────────────────────────────────────────────────────────

usage() {
  cat <<'EOF'
Skill Governance Toolkit installer (multi-runtime).

Targets (one or more):
  --claude       Install for Claude Code
  --copilot      Install for GitHub Copilot
  --codex        Install for OpenAI Codex CLI
  --gemini       Install for Google Gemini CLI
  --cursor       Install for Cursor v2.2+
  --all          All five above

Scope (one):
  --global       Install per-host files to ~/.{host}/ (project root files skipped)
  --project      Install per-host files to TARGET_PROJECT/.{host}/ AND upsert a
                 managed marker-block into TARGET_PROJECT/AGENTS.md, CLAUDE.md,
                 GEMINI.md, .github/copilot-instructions.md (content outside the
                 markers is preserved verbatim).

Project target (optional, only meaningful with --project):
  --target-project=PATH    Where YOUR project lives. Default: current working directory.

Install mode (optional):
  (default)      Fresh. Managed dirs (skills/, agents/, references/, scripts/, commands/)
                 are overwritten. User-owned root files are upserted via marker block —
                 user content outside the markers is NEVER touched.
  --upgrade      Clean upgrade. rsync --delete removes stale files in managed dirs
                 (handles renamed/removed skills). Marker-block contract unchanged.
  --force        Wipe managed dirs before copy. Marker-block contract for user-owned
                 root files is unchanged (still upsert, not overwrite).
  --dry-run      Resolve filters and target paths, print the install plan, then exit
                 without writing files.

Skill subset (optional — since 1.8.0). Reads skills/INDEX.jsonl, copies only
the matching subset, and writes a filtered INDEX.jsonl to each install dir.
Without any of these flags, all skills with tier ∈ {stable, preview} are
installed (experimental / internal require explicit opt-in).
  --category NAME[,NAME]   Install only skills whose metainfo.category includes ≥1 value.
                           Closed vocab — see docs/skill-authoring-standard.md.
  --tier NAME[,NAME]       Tier filter. Default: stable,preview. Add experimental or
                           internal only with explicit opt-in.
  --skill NAME[,NAME]      Hard list of skill names. Overrides --category and --tier
                           (explicit list ⇒ user knows exactly what they want).
  --interactive            Print a category summary, prompt for selection, then proceed
                           with the chosen --category set. Requires a TTY.

Examples:
  install.sh --claude --global
  install.sh --all --project                            # install into cwd
  install.sh --all --project --target-project=~/myapp   # install into ~/myapp
  install.sh --copilot --codex --global
  install.sh --claude --project --upgrade
  install.sh --claude --project --dry-run
  install.sh --claude --project --category discovery    # only discovery-tagged skills
  install.sh --claude --project --skill skill-find      # just one skill
  install.sh --claude --project --tier stable           # stable only, skip preview
  install.sh --claude --project --interactive           # pick from a menu
EOF
}

# usage_and_exit STATUS — print usage and exit with the given status.
# Use status 0 for --help (success), status 1 for errors (missing/unknown flag).
usage_and_exit() { usage; exit "${1:-1}"; }

[[ $# -eq 0 ]] && usage_and_exit 1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --claude)   TARGETS+=("claude") ;;
    --copilot)  TARGETS+=("copilot") ;;
    --codex)    TARGETS+=("codex") ;;
    --gemini)   TARGETS+=("gemini") ;;
    --cursor)   TARGETS+=("cursor") ;;
    --all)      TARGETS=("claude" "copilot" "codex" "gemini" "cursor") ;;
    --global)   SCOPE="global" ;;
    --project)  SCOPE="project" ;;
    --target-project=*) TARGET_PROJECT="${1#*=}"; TARGET_PROJECT="$(cd "$TARGET_PROJECT" && pwd)" ;;
    --upgrade)  INSTALL_MODE="upgrade" ;;
    --force)    INSTALL_MODE="force" ;;
    --dry-run)  DRY_RUN=true ;;
    --category)      CATEGORY_FILTER="$2"; shift ;;
    --category=*)    CATEGORY_FILTER="${1#*=}" ;;
    --tier)          TIER_FILTER="$2"; shift ;;
    --tier=*)        TIER_FILTER="${1#*=}" ;;
    --skill)         SKILL_FILTER="$2"; shift ;;
    --skill=*)       SKILL_FILTER="${1#*=}" ;;
    --interactive)   INTERACTIVE=true ;;
    -h|--help)  usage_and_exit 0 ;;
    *)          echo "Unknown flag: $1" >&2; usage_and_exit 1 ;;
  esac
  shift
done

[[ ${#TARGETS[@]} -eq 0 ]] && { echo "No target specified." >&2; usage_and_exit 1; }
[[ -z "$TIER_FILTER" ]] && TIER_FILTER="stable,preview"

# ── Resolve per-runtime base dir ──────────────────────────────────────────────

resolve_runtime_dir() {
  local runtime="$1"
  if [[ "$SCOPE" == "global" ]]; then
    echo "$HOME/.$runtime"
  else
    # Map host name to its conventional dotfile dir
    case "$runtime" in
      copilot) echo "$TARGET_PROJECT/.github" ;;
      *)       echo "$TARGET_PROJECT/.$runtime" ;;
    esac
  fi
}

# ── Skill subset resolution (since 1.8.0) ─────────────────────────────────────
# Reads skills/INDEX.jsonl via scripts/filter_skills.py and populates
# SELECTED_SKILLS with the names to install. Honours CATEGORY_FILTER /
# TIER_FILTER / SKILL_FILTER and interactive mode.

_run_interactive_menu() {
  # Show category summary, prompt user, set CATEGORY_FILTER.
  if [[ ! -t 0 ]]; then
    echo "✗ --interactive requires a TTY (stdin is not a terminal)" >&2
    exit 1
  fi
  echo "── Interactive: pick categories ──"
  local lines; lines="$(python3 "$SOURCE/scripts/filter_skills.py" --index "$SOURCE/skills/INDEX.jsonl" --list-categories)"
  # Show category counts, then tier counts as info.
  echo "Available categories (skills count):"
  local cats=()
  local i=1
  while IFS=$'\t' read -r kind name cnt; do
    if [[ "$kind" == "category" ]]; then
      printf "  %d) %-12s (%s skills)\n" "$i" "$name" "$cnt"
      cats+=("$name")
      i=$((i+1))
    fi
  done <<< "$lines"
  echo ""
  echo "Tier distribution:"
  while IFS=$'\t' read -r kind name cnt; do
    if [[ "$kind" == "tier" ]]; then
      printf "  · %-14s %s skills\n" "$name" "$cnt"
    fi
  done <<< "$lines"
  echo ""
  read -p "Select categories (comma-separated numbers, e.g. '1,3' — blank = all stable+preview): " sel
  if [[ -z "$sel" ]]; then
    echo "  → no category filter; installing all stable+preview skills"
    return 0
  fi
  local chosen=()
  IFS=',' read -ra nums <<< "$sel"
  for n in "${nums[@]}"; do
    n=$(echo "$n" | tr -d ' ')
    if [[ "$n" =~ ^[0-9]+$ ]] && (( n >= 1 && n <= ${#cats[@]} )); then
      chosen+=("${cats[$((n-1))]}")
    else
      echo "  · ignored: '$n' (out of range)" >&2
    fi
  done
  if [[ ${#chosen[@]} -gt 0 ]]; then
    CATEGORY_FILTER=$(IFS=,; echo "${chosen[*]}")
    echo "  → CATEGORY_FILTER set to: $CATEGORY_FILTER"
  fi
}

resolve_skill_subset() {
  local index="$SOURCE/skills/INDEX.jsonl"
  if [[ ! -f "$index" ]]; then
    echo "✗ skills/INDEX.jsonl not found. Run scripts/build_index.py first." >&2
    exit 1
  fi
  if $INTERACTIVE; then
    _run_interactive_menu
  fi
  # Build filter args for the helper. Empty strings → flag omitted.
  local fargs=(--index "$index" --tier "$TIER_FILTER")
  [[ -n "$CATEGORY_FILTER" ]] && fargs+=(--category "$CATEGORY_FILTER")
  [[ -n "$SKILL_FILTER" ]]    && fargs+=(--skill "$SKILL_FILTER")
  local names
  names="$(python3 "$SOURCE/scripts/filter_skills.py" "${fargs[@]}")"
  if [[ -z "$names" ]]; then
    echo "✗ No skills match the filter (category=$CATEGORY_FILTER tier=$TIER_FILTER skill=$SKILL_FILTER)." >&2
    echo "  Hint: use --interactive or check 'python3 scripts/filter_skills.py --index skills/INDEX.jsonl --list-categories'." >&2
    exit 1
  fi
  # Read names into the array (bash 4+ readarray would be cleaner but mac default bash is 3.2)
  SELECTED_SKILLS=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && SELECTED_SKILLS+=("$line")
  done <<< "$names"
}

print_dry_run_plan() {
  echo "── Dry-run install plan (no files will be written) ──"
  echo "  source:          $SOURCE"
  echo "  target_project:  $TARGET_PROJECT"
  echo "  scope:           $SCOPE"
  echo "  mode:            $INSTALL_MODE"
  echo "  targets:         ${TARGETS[*]}"
  echo "  skills:          ${SELECTED_SKILLS[*]}"
  echo
  if [[ "$SCOPE" == "project" ]]; then
    if [[ "$SOURCE" -ef "$TARGET_PROJECT" ]]; then
      echo "  project root:    source == target; marker blocks, root dirs, docs, and per-host dirs would be skipped"
    else
      echo "  project root:"
      echo "    · upsert marker blocks in AGENTS.md, CLAUDE.md, GEMINI.md, .github/copilot-instructions.md"
      echo "    · copy filtered skills/ plus agents/, references/, scripts/, commands/"
      echo "    · copy docs/ with conflict-renaming"
      echo "    · place .codex-plugin/, .claude-plugin/, gemini-extension.json manifests"
    fi
  else
    echo "  project root:    skipped for global scope"
  fi
  echo "  runtime dirs:"
  local target dest
  for target in "${TARGETS[@]}"; do
    dest="$(resolve_runtime_dir "$target")"
    echo "    · $target -> $dest"
  done
}

# _copy_filtered_skills DEST — copy only the skills in SELECTED_SKILLS into DEST/,
# then write a filtered INDEX.jsonl listing exactly the installed subset (so
# `skill-find` in the target environment doesn't report skills that aren't there).
_copy_filtered_skills() {
  local dest="$1"
  mkdir -p "$dest"
  local s
  for s in "${SELECTED_SKILLS[@]}"; do
    if [[ -d "$SOURCE/skills/$s" ]]; then
      _smart_copy "$SOURCE/skills/$s/" "$dest/$s/"
    else
      echo "  ! filter selected '$s' but skills/$s/ does not exist on disk — skipped" >&2
    fi
  done
  # Filtered INDEX.jsonl — let the helper re-emit only the selected entries.
  local fargs=(--index "$SOURCE/skills/INDEX.jsonl" --tier "$TIER_FILTER" --filtered-index)
  [[ -n "$CATEGORY_FILTER" ]] && fargs+=(--category "$CATEGORY_FILTER")
  [[ -n "$SKILL_FILTER" ]]    && fargs+=(--skill "$SKILL_FILTER")
  python3 "$SOURCE/scripts/filter_skills.py" "${fargs[@]}" > "$dest/INDEX.jsonl"
}

# _copy_runtime_scripts DEST — copy ONLY whitelisted runtime scripts (see
# scripts/runtime-manifest.txt) into DEST/. Dev/test/release tooling
# (test_*.py, install.sh, sync_version.py, audit.sh, generate_subset_agents_md.py)
# is NEVER shipped. Installer-internal helpers still run from $SOURCE/scripts/.
_copy_runtime_scripts() {
  local dest="$1"
  local manifest="$SOURCE/scripts/runtime-manifest.txt"
  if [[ ! -f "$manifest" ]]; then
    echo "✗ scripts/runtime-manifest.txt not found — cannot resolve runtime script set." >&2
    exit 1
  fi
  mkdir -p "$dest"
  local raw name
  while IFS= read -r raw; do
    name="${raw%%#*}"                 # strip trailing comment
    name="$(echo "$name" | tr -d '[:space:]')"
    [[ -z "$name" ]] && continue
    if [[ -f "$SOURCE/scripts/$name" ]]; then
      cp "$SOURCE/scripts/$name" "$dest/$name"
    else
      echo "  ! manifest lists $name but scripts/$name missing — skipped" >&2
    fi
  done < "$manifest"
}

# _copy_owned_tree SRC DEST — copy a toolkit-owned dir tree into DEST WITHOUT
# ever deleting or clobbering the user's own files. Ownership is tracked in a
# sidecar "$DEST/.sgt-owned" (one relative path per line). On upgrade:
#   · files we ship (in SRC) are overwritten;
#   · files previously owned but now gone from SRC are removed (renamed/removed);
#   · user files (never in .sgt-owned) are left untouched — fixes the rsync
#     --delete data-loss bug;
#   · a user file colliding with one of our names is preserved — OUR copy lands
#     beside it as "<name>.skill-governance-toolkit.<ext>".
# bash 3.2 compatible (no associative arrays — macOS default shell).
_copy_owned_tree() {
  local src="${1%/}" dest="${2%/}"
  [[ -d "$src" ]] || return 0
  mkdir -p "$dest"
  local owned_file="$dest/.sgt-owned"
  local was_owned=""
  [[ -f "$owned_file" ]] && was_owned="$(cat "$owned_file")"
  local now_list="" f rel d base dir renamed prev
  while IFS= read -r f; do
    rel="${f#"$src"/}"
    now_list+="$rel"$'\n'
    d="$dest/$rel"
    mkdir -p "$(dirname "$d")"
    if [[ -e "$d" ]] && ! printf '%s\n' "$was_owned" | grep -qxF "$rel" && ! cmp -s "$f" "$d"; then
      # User file collides with our name and we never owned it → preserve theirs.
      base="${rel##*/}"; dir="${rel%/*}"; [[ "$dir" == "$rel" ]] && dir=""
      renamed="${base%.*}.skill-governance-toolkit.${base##*.}"
      [[ -n "$dir" ]] && renamed="$dir/$renamed"
      cp "$f" "$dest/$renamed"
      echo "  ⚠ conflict: user has $rel — saved ours as $renamed" >&2
    else
      cp "$f" "$d"
    fi
  done < <(find "$src" -type f ! -name '.DS_Store' ! -path '*/__pycache__/*' ! -path '*/.skill-state/*')
  # Remove files we used to own but no longer ship — never user files.
  if [[ -n "$was_owned" ]]; then
    while IFS= read -r prev; do
      [[ -z "$prev" ]] && continue
      if ! printf '%s\n' "$now_list" | grep -qxF "$prev"; then
        [[ -e "$dest/$prev" ]] && rm -f "$dest/$prev"
      fi
    done <<< "$was_owned"
  fi
  printf '%s' "$now_list" | grep -v '^$' | sort > "$owned_file"
}

# ── Ensure project root user-owned files (only for --project scope) ──────────
# These four files are USER-OWNED. The installer NEVER overwrites them — it
# manages a single block between BEGIN/END markers. User edits outside the
# markers are preserved across fresh installs, upgrades, and uninstalls.

ensure_project_root_user_files() {
  if [[ "$SCOPE" != "project" ]]; then return 0; fi
  # Hard guard: never write into the toolkit's own AGENTS.md / CLAUDE.md /
  # GEMINI.md / .github/copilot-instructions.md. If TARGET_PROJECT resolves
  # to SOURCE (e.g. user ran installer from inside the toolkit dir without
  # --target-project), marker_block.py would embed a managed block INTO the
  # canonical source files — every subsequent install then carries that
  # pollution forward. Detected once in pre-release review of 1.8.0; this
  # guard prevents recurrence.
  if [[ "$SOURCE" -ef "$TARGET_PROJECT" ]]; then
    echo "── SOURCE == TARGET_PROJECT (toolkit's own dir) — skipping marker-block upsert of user-owned files ──"
    echo "  · This protects AGENTS.md / CLAUDE.md / GEMINI.md / .github/copilot-instructions.md from self-pollution."
    echo "  · For a real install, pass --target-project=/path/to/external/repo"
    return 0
  fi
  echo "── Ensuring user-owned files at project root (append-with-markers) ──"
  # When a filter is active (--category/--tier/--skill) and the resolved
  # subset is smaller than the full library, the canonical AGENTS.md (which
  # lists all skills) would mislead the agent into routing to skills not
  # actually installed. Generate a subset-aware copy whose skill table only
  # contains installed rows, plus a clear «scoped install» notice.
  local agents_src="$SOURCE/AGENTS.md"
  local full_count; full_count=$(python3 "$SOURCE/scripts/filter_skills.py" --index "$SOURCE/skills/INDEX.jsonl" --tier "stable,preview,experimental,internal,unknown" | wc -l | tr -d ' ')
  if [[ "${#SELECTED_SKILLS[@]}" -lt "$full_count" ]]; then
    local skill_csv; skill_csv=$(IFS=,; echo "${SELECTED_SKILLS[*]}")
    local tmp_agents; tmp_agents=$(mktemp)
    if python3 "$SOURCE/scripts/generate_subset_agents_md.py" "$SOURCE/AGENTS.md" "$skill_csv" > "$tmp_agents"; then
      agents_src="$tmp_agents"
      echo "  · AGENTS.md tailored for subset install (${#SELECTED_SKILLS[@]}/$full_count skills)"
    else
      echo "  ! subset AGENTS.md generation failed — falling back to canonical AGENTS.md" >&2
    fi
  fi
  _upsert_marker_block "$agents_src" "$TARGET_PROJECT/AGENTS.md"
  _upsert_marker_block "$SOURCE/CLAUDE.md" "$TARGET_PROJECT/CLAUDE.md"
  _upsert_marker_block "$SOURCE/GEMINI.md" "$TARGET_PROJECT/GEMINI.md"
  _upsert_marker_block "$SOURCE/.github/copilot-instructions.md" "$TARGET_PROJECT/.github/copilot-instructions.md"
  # Clean up temp file if used. Use `if` (always exits 0) instead of `[[ ]] && rm`
  # (which exits 1 when the [[ test is false → function returns 1 → set -e
  # aborts the whole installer before per-host installs run). Subtle but fatal.
  if [[ -n "${tmp_agents:-}" && -f "${tmp_agents:-/dev/null}" ]]; then
    rm -f "$tmp_agents"
  fi
  return 0
}

# ── Ensure docs/ copied with conflict-renaming (NEVER deletes user docs/) ────
# Per the user contract: we COPY our docs/ files into the target's docs/.
# If a file with the same name already exists with DIFFERENT content, we
# rename OUR file (suffix `.skill-governance-toolkit.md`) — never the user's.
# We NEVER delete the target's docs/ directory or any file in it.

ensure_docs_copied() {
  if [[ "$SCOPE" != "project" ]]; then return 0; fi
  if [[ "$SOURCE" -ef "$TARGET_PROJECT" ]]; then
    echo "── docs/ already at source==target — skip ──"
    return 0
  fi
  echo "── Copying docs/ with conflict-rename (preserves user docs) ──"
  mkdir -p "$TARGET_PROJECT/docs"
  local our_file dest_file base
  for our_file in "$SOURCE"/docs/*.md; do
    [[ -f "$our_file" ]] || continue
    base="$(basename "$our_file")"
    dest_file="$TARGET_PROJECT/docs/$base"
    if [[ ! -f "$dest_file" ]]; then
      cp "$our_file" "$dest_file"
      echo "  · placed docs/$base"
    elif cmp -s "$our_file" "$dest_file"; then
      echo "  · docs/$base unchanged (content matches)"
    else
      # Conflict — rename OUR file, never touch user's
      local renamed="${base%.md}.skill-governance-toolkit.md"
      cp "$our_file" "$TARGET_PROJECT/docs/$renamed"
      echo "  ⚠ conflict: user has differing docs/$base — saved ours as docs/$renamed"
    fi
  done
}

# ── Ensure project root canonical dirs (only for --project scope) ────────────
# Root-first layout — skills/, agents/, references/, scripts/ live at project
# root as the single source of truth. Manifests in .codex-plugin/plugin.json
# reference "./skills/" relative to project root; Copilot / Cursor / Codex
# auto-discover skills from workspace root. Per-host .{host}/ dirs still get
# their own copies for host-specific conventions (Claude reads .claude/skills/).
ensure_project_root_canonical_dirs() {
  if [[ "$SCOPE" != "project" ]]; then return 0; fi
  if [[ "$SOURCE" -ef "$TARGET_PROJECT" ]]; then
    echo "── Source == target: skills/ / agents/ / references/ / scripts/ already at root ──"
    return 0
  fi
  echo "── Placing canonical dirs at project root (root-first layout) ──"
  _pre_install_cleanup "$TARGET_PROJECT" skills agents references scripts commands
  mkdir -p "$TARGET_PROJECT/skills" "$TARGET_PROJECT/agents" \
           "$TARGET_PROJECT/references" "$TARGET_PROJECT/scripts" \
           "$TARGET_PROJECT/commands"
  _copy_filtered_skills "$TARGET_PROJECT/skills"
  _copy_owned_tree "$SOURCE/agents/"     "$TARGET_PROJECT/agents/"
  _copy_owned_tree "$SOURCE/references/" "$TARGET_PROJECT/references/"
  _copy_runtime_scripts "$TARGET_PROJECT/scripts"
  _copy_owned_tree "$SOURCE/commands/"   "$TARGET_PROJECT/commands/"
  # Also place manifests at root (Codex marketplace etc reads ./{...}-plugin/)
  mkdir -p "$TARGET_PROJECT/.codex-plugin" "$TARGET_PROJECT/.claude-plugin"
  _copy_file "$SOURCE/.codex-plugin/plugin.json" "$TARGET_PROJECT/.codex-plugin/plugin.json"
  _copy_file "$SOURCE/.claude-plugin/plugin.json" "$TARGET_PROJECT/.claude-plugin/plugin.json"
  _copy_file "$SOURCE/.claude-plugin/marketplace.json" "$TARGET_PROJECT/.claude-plugin/marketplace.json"
  _copy_file "$SOURCE/gemini-extension.json" "$TARGET_PROJECT/gemini-extension.json"
  echo "  · root layout ready: skills/, agents/, references/, scripts/, commands/, manifests/"
}

# ── Per-host installers ───────────────────────────────────────────────────────

install_claude() {
  local dest; dest="$(resolve_runtime_dir claude)"
  _pre_install_cleanup "$dest" skills agents scripts references commands
  mkdir -p "$dest/skills" "$dest/agents" "$dest/scripts" "$dest/references" "$dest/commands"
  _copy_filtered_skills "$dest/skills"
  _copy_owned_tree "$SOURCE/agents/" "$dest/agents/"
  _copy_runtime_scripts "$dest/scripts"
  _copy_owned_tree "$SOURCE/references/" "$dest/references/"
  _copy_owned_tree "$SOURCE/commands/" "$dest/commands/"
  _copy_file "$SOURCE/CLAUDE.md" "$dest/CLAUDE.md"
  # AGENTS.md INSIDE $dest — CLAUDE.md's `@AGENTS.md` resolves relative to its location
  _copy_file "$SOURCE/AGENTS.md" "$dest/AGENTS.md"
  echo "✓ Claude Code:    $dest/  (${#SELECTED_SKILLS[@]} skills)"
}

install_copilot() {
  local dest; dest="$(resolve_runtime_dir copilot)"
  # For --project scope, copilot-instructions.md is already handled by
  # ensure_project_root_user_files (with append-with-markers semantics).
  # For --global scope, place it in ~/.github/ as a user-wide default.
  if [[ "$SCOPE" == "global" ]]; then
    mkdir -p "$dest"
    _upsert_marker_block "$SOURCE/.github/copilot-instructions.md" "$dest/copilot-instructions.md"
    echo "✓ Copilot (global): $dest/copilot-instructions.md"
  else
    echo "✓ Copilot:        $dest/copilot-instructions.md (managed via marker block; user content preserved)"
  fi
  echo "  → Skills are workspace-auto-discovered (since 2025-12); ensure project has skills/ visible"
  echo "  → AGENTS.md at TARGET_PROJECT root is what Copilot actually reads for rules"
}

install_codex() {
  local dest; dest="$(resolve_runtime_dir codex)"
  _pre_install_cleanup "$dest" skills agents scripts references commands
  mkdir -p "$dest/skills" "$dest/agents" "$dest/scripts" "$dest/references" "$dest/commands"
  _copy_filtered_skills "$dest/skills"
  _copy_owned_tree "$SOURCE/agents/" "$dest/agents/"
  _copy_runtime_scripts "$dest/scripts"
  _copy_owned_tree "$SOURCE/references/" "$dest/references/"
  _copy_owned_tree "$SOURCE/commands/" "$dest/commands/"
  _copy_file "$SOURCE/.codex-plugin/plugin.json" "$dest/plugin.json"
  echo "✓ Codex CLI:      $dest/  (${#SELECTED_SKILLS[@]} skills)"
  echo "  → Codex reads AGENTS.md from TARGET_PROJECT root, not from $dest"
}

install_gemini() {
  local dest; dest="$(resolve_runtime_dir gemini)"
  _pre_install_cleanup "$dest" skills scripts references commands
  mkdir -p "$dest/skills" "$dest/scripts" "$dest/references" "$dest/commands"
  _copy_filtered_skills "$dest/skills"
  _copy_runtime_scripts "$dest/scripts"
  _copy_owned_tree "$SOURCE/references/" "$dest/references/"
  _copy_owned_tree "$SOURCE/commands/" "$dest/commands/"
  _copy_file "$SOURCE/GEMINI.md" "$dest/GEMINI.md"
  # AGENTS.md INSIDE $dest — GEMINI.md uses `@./AGENTS.md` import
  _copy_file "$SOURCE/AGENTS.md" "$dest/AGENTS.md"
  _copy_file "$SOURCE/gemini-extension.json" "$dest/extension.json"
  echo "✓ Gemini CLI:     $dest/  (${#SELECTED_SKILLS[@]} skills)"
  echo "  ! Gemini does NOT support sub-agents — optional Task paths use sequential fallback"
}

install_cursor() {
  local dest; dest="$(resolve_runtime_dir cursor)"
  _pre_install_cleanup "$dest" skills scripts references commands
  mkdir -p "$dest/skills" "$dest/scripts" "$dest/references" "$dest/commands"
  _copy_filtered_skills "$dest/skills"
  _copy_runtime_scripts "$dest/scripts"
  _copy_owned_tree "$SOURCE/references/" "$dest/references/"
  _copy_owned_tree "$SOURCE/commands/" "$dest/commands/"
  echo "✓ Cursor:         $dest/skills/  (${#SELECTED_SKILLS[@]} skills)"
  echo "  → Cursor reads AGENTS.md natively from TARGET_PROJECT root (already ensured above for --project scope)"
}

# ── Main ───────────────────────────────────────────────────────────────────────

echo "Installing Skill Governance Toolkit"
echo "  scope:           $SCOPE"
echo "  mode:            $INSTALL_MODE"
echo "  source:          $SOURCE"
echo "  target_project:  $TARGET_PROJECT"

# Resolve skill subset BEFORE printing the summary so the banner accurately
# reflects what will actually be installed. Bails out fast if filter is empty.
resolve_skill_subset

echo "  skill subset:"
echo "    category filter: ${CATEGORY_FILTER:-<none>}"
echo "    tier filter:     ${TIER_FILTER}"
echo "    skill filter:    ${SKILL_FILTER:-<none>}"
echo "    resolved (${#SELECTED_SKILLS[@]} skills): ${SELECTED_SKILLS[*]}"
echo

if $DRY_RUN; then
  print_dry_run_plan
  echo
  echo "Dry run complete."
  exit 0
fi

# Ensure project root user-owned files ONCE (not per-host) for --project scope.
# Append-with-markers — never overwrites user content.
ensure_project_root_user_files
echo

# Ensure canonical dirs at project root (root-first layout for Copilot/Cursor/Codex
# auto-discovery + manifest "./skills/" resolution).
ensure_project_root_canonical_dirs
echo

# Copy docs/ with conflict-rename — never deletes user's docs/ files.
ensure_docs_copied
echo

# Hard guard #2: per-host installers create .{host}/ subdirs and copy skills/
# agents/refs into them. When SOURCE == TARGET_PROJECT and scope is `project`,
# `resolve_runtime_dir` resolves to `$TARGET_PROJECT/.{host}/` which IS inside
# the toolkit's own dir → we'd pollute the source with a 88-file duplicate
# every run. Bug discovered post-1.8.0 (zip grew from 205K → 368K because
# .claude/ landed in source after self-pollution-guard test). Guard prevents
# recurrence. Real installs use --target-project=external_path → SOURCE ≠ TARGET_PROJECT.
if [[ "$SCOPE" == "project" && "$SOURCE" -ef "$TARGET_PROJECT" ]]; then
  echo "── SOURCE == TARGET_PROJECT — skipping per-host install (would create .{host}/ dupes inside the toolkit dir) ──"
  echo "  · For a real install, pass --target-project=/path/to/external/repo"
else
  for target in "${TARGETS[@]}"; do
    case "$target" in
      claude)   install_claude ;;
      copilot)  install_copilot ;;
      codex)    install_codex ;;
      gemini)   install_gemini ;;
      cursor)   install_cursor ;;
    esac
  done
fi

echo
echo "Done."
echo
echo "Verify install:"
echo "  · Claude Code:    invoke skill-find or any skill by trigger phrase"
echo "  · Copilot:        Open file in TARGET_PROJECT — AGENTS.md is read natively"
echo "  · Codex CLI:      codex plugins list"
echo "  · Gemini CLI:     gemini extensions list"
echo "  · Cursor v2.2+:   AGENTS.md auto-loaded from project root"

if [[ "$INSTALL_MODE" == "fresh" ]]; then
  echo
  echo "Tip: re-run with --upgrade to clean up files removed in this version."
fi
