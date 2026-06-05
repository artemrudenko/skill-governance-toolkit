# Output Template — Diff Report + Residual Concerns

Always-rendered output produced by Phase 3 (preview) and Phase 4 (write). The same
template is used in all three `OUTPUT_MODE`s; only the «file written to …» footer differs.

---

## Diff report skeleton

```
# Portable Skill Build — {SKILL_TARGET}

Source:     {path}     ({lines} lines, {audit findings} violations)
Target:     {output path}   (preview / new-file / in-place)
Runtimes:   {TARGET_RUNTIMES}

## Transformations applied ({N})

🔴 BLOCKERS (must apply to be portable):
  1. {rule_id} · {location} · {description}
  ...

🟡 PORTABILITY WARNINGS (recommended):
  N. {rule_id} · {location} · {description}
  ...

## Diff (unified, abridged)

```diff
- allowed-tools:
-   - Read
-   - Grep
+ # (removed — non-portable; tool restrictions documented in body)
- type: skill
- status: active
+ compatibility: "Claude Code · GitHub Copilot · Cursor v2.2+ · OpenAI Codex CLI · Google Gemini CLI"
+ license: MIT

  description: |
    [unchanged]

  ...

- Apply 3 atomic passes per `references/handoff-spec.md` (ADR-008 §3 compliance).
+ Apply 3 atomic passes per `references/handoff-spec.md`.
- Output → `_audits/legacy-audit/legacy-audit-{date}.md`
+ Output → `out/legacy-audit/legacy-audit-{date}.md`
```

## Residual concerns (user must review)

🟡 The source `description` is 1247 chars — exceeds agentskills.io 1024-char limit. Manual rewrite required; this skill did not auto-truncate to preserve semantics.

🟡 `rules/claude.md` exists with content that should merge into repo-level `references/claude-tools.md` — review and merge manually.

🟡 Line 132 references `Task` / sub-agent dispatch; sequential fallback note added but verify the fallback path produces the same output schema.

## Post-transform checklist verification

✓ No `allowed-tools:` in frontmatter
✓ No Claude-only frontmatter fields (paths/hooks/model/effort/context/disable-model-invocation)
✓ `compatibility:` field present
✓ Tool names canonical (Read, Grep, Bash, Edit, Write — not aliases)
✓ Sequential fallback note present where `Task` is used
✓ No org-specific paths (`/_audits/`, `/outputs/`, `materials/raw/`, etc.)
```

---

## Footer per `OUTPUT_MODE`

- **preview** — `(no file written — preview mode)`
- **new-file** — `Written to: {source_dir}/SKILL.portable.md`
- **in-place** — `Overwrote: {source_path}  (backup: {source_path}.bak)`

---

## Residual concerns — common patterns

The skill cannot auto-fix the following; always surface them:

1. **Over-length description** (>1024 chars) — semantics matter, machine truncation is unsafe.
2. **`rules/{tool}.md` content** — needs human judgment for repo-level merge target.
3. **`Task` calls** — added fallback note, but real end-to-end verification without sub-agent dispatch is required.
4. **ADR / internal doc references stripped** — make sure the *concept* still reads correctly without the link.
5. **Org-specific names not in `PROJECT_STYLE`** — anything the skill couldn't auto-detect.
