# Phase 0 — Environment detection

Loaded by `integration-init` Phase 0. Detection logic, prereq matrix, and hard-fail gating rules.

---

## 1. Detect runtime

Check for the host AI runtime — first match wins, order matters (most specific first):

| Runtime | Detection signal |
|---|---|
| Claude Code | `which claude` succeeds, OR `~/.claude/` directory exists, OR `$CLAUDE_CODE_*` env vars set |
| OpenAI Codex CLI | `which codex` succeeds |
| Google Gemini CLI | `which gemini` succeeds |
| GitHub Copilot | `gh copilot --version` succeeds |
| Cursor | `$CURSOR_*` env vars set, OR Cursor config dir present |
| Unknown | none of the above |

The detected runtime is recorded for Phase 3 (`code-review-graph install --platform {runtime}`) and Phase 6 (final report).

---

## 2. Detect package managers

Probe each one and record version. Used for prereq gating in Phase 0 and install dispatch in Phase 3.

```bash
python3 --version       # must be ≥ 3.10 for CRG, serena
pipx --version          # preferred installer for Python tools
pip --version           # fallback for Python tools
node --version
npm --version           # required for repomix
```

---

## 3. Detect currently-installed integrations

Each probe is authoritative (used by Phase 4 verify-before-inject):

```bash
which code-review-graph || pipx list | grep code-review-graph
which repomix
which serena
```

Results determine:
- Phase 1 default selection (pre-check tools already installed)
- Idempotent re-run behavior (deselected tool → remove its marker block; re-selected installed tool → no-op install, refresh doc block)

---

## 4. Detect repo context

| Check | Purpose |
|---|---|
| `AGENTS.md` at project root | Phase 5 inject target — required to exist for marker writes |
| `agents/code-reviewer.md` | Phase 5 inject target — required to exist for handoff writes |
| `.git/` present | Phase 2a CRG pre-commit hook (`Q-CRG-5`) gated on this |

If `AGENTS.md` or `agents/code-reviewer.md` is missing → warn the user. Phase 5 can be skipped (still install binaries), but the integration won't be documented.

---

## 5. Prereq gating (hard-fail, not just warn)

Hard-fail only when a prereq is needed for an **active selection**. Warnings are acceptable when a tool is not selected.

| Selection | Prereq | Fail action |
|---|---|---|
| CRG | `python3 ≥ 3.10` | Stop Phase 0. Print: «code-review-graph requires Python ≥ 3.10; upgrade or deselect CRG.» Do NOT advance to Phase 3 (install would crash mid-run). |
| CRG | `pipx` available | Stop. Print platform-specific pipx install instructions. |
| serena | `pipx` available | Stop (same reason as CRG). |
| serena | `python3 ≥ 3.10` | Stop. Same message as CRG. |
| repomix | `npm` available | Stop. Print Node install instructions. |

Hard-fail means: exit cleanly, persist the partial state, allow the user to re-run after fixing prereqs.

---

## 6. State snapshot written at end of Phase 0

Stored at `${CWD}/.skill-state/integration-init/run-{utc-timestamp}.json`:

```json
{
  "phase": 0,
  "runtime": "claude-code",
  "package_managers": { "python3": "3.11.5", "pipx": "1.4.3", "npm": "10.2.0" },
  "currently_installed": { "code-review-graph": null, "repomix": null, "serena": null },
  "repo_context": { "agents_md": true, "code_reviewer_md": true, "git": true }
}
```
