# Checkpointing — resumable skill runs

A skill that does meaningful work across multiple phases SHOULD save state after each
phase so the run can resume after a crash, a timeout, or a manual interrupt.

This document defines the canonical pattern. The shipped helper at
`scripts/checkpoint.py` is the reference implementation (Python 3 stdlib only). Skills
invoke it via the host's `Bash` (or equivalent) tool — they never need to import it.

---

## State directory

```
${CWD}/.skill-state/{skill-name}/
```

- **`${CWD}`** — the project being operated on, NOT the toolkit checkout. A single
  toolkit copy may service many projects; each project owns its own state.
- **`{skill-name}`** — the value of the skill's `name:` frontmatter field.
- The directory is created on first write. Listed in `.gitignore`.

---

## File naming

```
run-{YYYY-MM-DDTHH-MM-SS-uuuuuu}Z.json
```

UTC, hyphen-only (no colons) so the name is safe on every filesystem. The
microsecond suffix (`uuuuuu`) prevents collisions when a skill is started
multiple times within the same second (scripted batch runs, automated tests).
One file per invocation. Files are immutable once `complete` runs — never
edited in place.

Atomic write semantics: each save writes `run-{ts}.json.tmp`, then renames over the
target. Survives mid-write process death without leaving half-files for the resumer.

---

## State schema

```json
{
  "run_id": "run-2026-05-24T13-04-22-123456Z",
  "skill": "library-audit",
  "started_at": "2026-05-24T13:04:22Z",
  "last_updated": "2026-05-24T13:05:48Z",
  "inputs": { "MODE": "full", "SKILLS_DIRS": ["skills/"] },
  "completed_phases": ["P0", "P1"],
  "phase_outputs": {
    "P0": { "skills_discovered": 6 },
    "P1": { "handoff_findings": 3 }
  },
  "next_phase": "P2",
  "completed_at": null,
  "error": null
}
```

- `completed_at` is `null` while the run is in flight, set to an ISO timestamp when
  the skill calls `complete`.
- `error` is `null` on success; on an unrecoverable error the skill records a short
  string here and leaves `completed_at` null — that signals "this run is dead, do not
  resume" to the resumer.
- `phase_outputs` is whatever the skill chose to snapshot. Keep it small (< 50 KB
  per file as a soft cap); push large artifacts to disk and reference them by path.

---

## Resume mode (per-skill input `RESUME`)

| Mode | Behavior | Recommended default for |
|---|---|---|
| `auto` | List runs without `completed_at` and without `error`. If exactly one, pick it. If more than one, pick the most recent and log others to stderr. If zero, start fresh. **Never asks.** | **Validator** skills that must stay detect-only (library-audit, skill-evaluate, skill-compare, skill-build-portable). |
| `ask` | If any unfinished run exists, ask the user whether to resume the latest, pick a specific one, or start fresh. Use `AskUserQuestion` only on hosts that provide it; otherwise ask plainly in chat. | **Gateway** skills (integration-init) where the user expects interactive prompts. |
| `new` | Ignore all prior runs unconditionally. Start fresh. | Any time the user explicitly asks to "start over". |

Skills MUST log to stderr which mode was applied and which run-id (if any) is being
resumed — so the user can audit the choice.

---

## Phase contract

For each long-running phase a skill SHOULD:

1. At the **start** of the run (Phase 0): call `checkpoint.py start --skill {name}
   --inputs '{json}'` once. Capture the returned `run_id`.
2. At the **end** of every checkpointable phase: call `checkpoint.py save-phase
   --run-id {id} --phase {label} --output '{json}'`.
3. At the **end** of the run: call `checkpoint.py complete --run-id {id}`. Failure
   to call `complete` leaves the run resumable on next invocation.
4. On a caught **error** that aborts the run: call `checkpoint.py fail --run-id {id}
   --error "{short message}"`. The resumer skips runs with `error != null`.

Skills decide which phases are worth checkpointing — see each skill's "State
persistence" section. Cheap discovery phases (e.g. scanning a frontmatter table)
typically aren't checkpointed; expensive phases (full graph scan, per-tool install,
remote API call) always are.

---

## Helper CLI quick reference

```
checkpoint.py start         --skill NAME --inputs JSON          # → prints run_id
checkpoint.py save-phase    --run-id ID --phase LABEL --output JSON
checkpoint.py complete      --run-id ID
checkpoint.py fail          --run-id ID --error "message"
checkpoint.py list-resumable --skill NAME                       # → JSON array of run_ids
checkpoint.py load          --run-id ID                         # → full state JSON
```

All commands accept `--state-dir` to override the default `${CWD}/.skill-state/`.

---

## What NOT to put in checkpoint files

- **Secrets, tokens, credentials** — these escape `.gitignore` discipline if anyone
  ever commits state by accident.
- **Large blobs** — write blobs to disk and reference them by path.
- **Mutable handles** (open file descriptors, HTTP connections) — resumer cannot
  rehydrate these; record only the data needed to re-open.

---

## Stale-run detection

A process killed before it could call `fail` leaves `completed_at = null AND
error = null` — looks indistinguishable from a legitimately resumable run.
Resumer would pick it up forever.

Skills SHOULD treat `last_updated` older than a freshness window (recommended:
24 hours) as suspect. In `RESUME=auto` mode, ignore stale runs and start
fresh. In `RESUME=ask` mode, surface the staleness to the user and let them
decide. The helper CLI accepts `--max-age-hours N` on `list-resumable` to
filter out stale entries.

## Retention

Skills do not auto-delete state. Operators can prune with:

```
find .skill-state -name 'run-*.json' -mtime +30 -delete
```

A skill that *did* `complete` successfully may safely delete its own state file at
the end if storage matters — but the default is "keep, for audit".
