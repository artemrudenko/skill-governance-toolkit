# Source resolution — full URL construction + auth setup

Detail reference for `skill-find` Phase 1a (Git URL mode). The body of `SKILL.md` keeps only the 1–2 sentence summary; this file holds the full mechanics.

## Source-type detection

- Starts with `https://` or `git@` → **Git URL mode** (this file).
- Filesystem path → **Local mode** (Phase 1b in `SKILL.md`).
- Both repo and local configured → try local first (faster), fall back to Git URL.

## Configuration keys

Read project's `AGENTS.md` (or `CLAUDE.md` / `GEMINI.md`) for these keys:

```yaml
corporate-skills-repo:   https://github.com/{org}/skills-repo   # Git URL (preferred)
corporate-skills-local:  ~/corp-skills-cache                     # local mirror
corporate-skills-branch: main
corporate-skills-token:  ${SKILLS_TOKEN_ENV_VAR}                 # env var NAME, not value
```

Also check `.{tool}/config.yml` and environment variables (`CORPORATE_SKILLS_REPO`, `CORPORATE_SKILLS_DIR`).

If corporate config not found: note it, continue with sources 1–2 only.

## Raw INDEX.jsonl URL construction

```
GitHub:   https://raw.githubusercontent.com/{org}/{repo}/{branch}/INDEX.jsonl
GitLab:   {base_url}/{org}/{repo}/-/raw/{branch}/INDEX.jsonl
Fallback: {repo_url}/raw/{branch}/INDEX.jsonl
```

Default branch: `main`. If config specifies `corporate-skills-branch`, use it. If `corporate-skills-token` is set, read the env var value and add header `Authorization: Bearer {token}`.

## Happy path — INDEX.jsonl found

**If `INDEX.jsonl` is found and non-empty:** parse each line as JSON. Proceed to Phase 2.

## Fallback — INDEX.jsonl missing (slower)

List the skills directory via the Git host's contents API:

```
GET https://api.github.com/repos/{org}/{repo}/contents/skills/
```

For each subdirectory: fetch its `SKILL.md` and extract **frontmatter only** (read until second `---` delimiter; do not load the body).

Note in output: «`INDEX.jsonl` not found — searched individual files (slower). Suggest the repo maintainer run `scripts/build_index.py` to generate an index.»

## Configuration reference (project AGENTS.md)

```yaml
# Corporate skill library configuration
corporate-skills-repo:    https://github.com/{your-org}/skills
corporate-skills-branch:  main
corporate-skills-local:   ~/corp-skills-cache    # optional local mirror
corporate-skills-token:   ${CORP_SKILLS_TOKEN}   # env var name, not the value
```

For self-hosted GitLab:

```yaml
corporate-skills-repo:    https://gitlab.{company}.com/ai-team/skills
```
