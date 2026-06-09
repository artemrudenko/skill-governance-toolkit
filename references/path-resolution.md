# Script & Reference Path Resolution

How a skill locates a toolkit script (`scripts/*.py|sh`) or a shared reference
(`references/*.md`) across every install shape. Skills shell out with bare paths
like `scripts/checkpoint.py`; the rule below tells the agent what to prefix.

## Why this exists

The toolkit installs into three different shapes, and the working directory at
runtime is the user's project — NOT the install dir. A bare relative path like
`scripts/checkpoint.py` only resolves when the user's CWD happens to be the
install root. Under a plugin install it never does. Resolve a root first.

## SGT_ROOT — resolution order (first match wins)

This table mirrors the copy-paste resolver below exactly — same order, same fallbacks.

| Order | Source | When it applies |
|---|---|---|
| 1 | `$CLAUDE_PLUGIN_ROOT` | Claude Code plugin install (set by the host) |
| 2 | `$SGT_ROOT` | explicit override the user may export |
| 3 | CWD walk-up for a `scripts/`+`skills/` pair (the active `AGENTS.md` dir) | script-install, project or per-host scope |
| 4 | `$CODEX_HOME` (default `~/.codex`) | Codex CLI — no plugin-root var exists; last-resort anchor when set |
| 5 | `$PWD` | final fallback |

Then the toolkit assets are at `$SGT_ROOT/scripts/…` and `$SGT_ROOT/references/…`.

> Codex note: Codex exposes no `CODEX_PLUGIN_ROOT`. The documented Codex pattern
> anchors on `$CODEX_HOME` (e.g. `export TOOL="$CODEX_HOME/skills/.../scripts/<tool>.py"`).
> The toolkit's Codex install lands under `$CODEX_HOME/.codex`-style dirs, so the
> CWD walk-up rule (3) covers it; `$CODEX_HOME` (4) is the explicit anchor when known.

## Copy-paste resolver (bash)

Skills that execute a script should resolve the root once:

```bash
# Resolve the toolkit root, then run a script portably.
sgt_root() {
  if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then echo "$CLAUDE_PLUGIN_ROOT"; return; fi
  if [[ -n "${SGT_ROOT:-}" ]]; then echo "$SGT_ROOT"; return; fi
  # Walk up from CWD looking for a scripts/ + skills/ pair (the install root).
  local d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -d "$d/scripts" && -d "$d/skills" ]] && { echo "$d"; return; }
    d="$(dirname "$d")"
  done
  echo "${CODEX_HOME:-$PWD}"
}
ROOT="$(sgt_root)"
python3 "$ROOT/scripts/checkpoint.py" --help
```

## Authoring rule

- A skill MAY write `scripts/<name>` for brevity, but MUST link here so the agent
  resolves `$SGT_ROOT` first in non-trivial (plugin / global) installs.
- Never assume CWD is the install root.
- Shared references are resolved the same way: `$SGT_ROOT/references/<name>`.
- A skill's OWN bundled assets (`skills/<name>/references/…`, `skills/<name>/scripts/…`)
  travel inside the skill and need no resolution — reference them relative to the skill.
