#!/usr/bin/env python3
"""
generate_subset_agents_md.py — emit a subset-aware copy of AGENTS.md.

Why: when `install.sh` runs with --category / --tier / --skill filters,
the canonical AGENTS.md (which lists all 6 skills) misrepresents what's
actually in the install. This helper takes the source AGENTS.md plus the
list of installed skill names and produces a trimmed copy:

  1. Drops rows in the skill summary table for skills NOT in the install.
  2. Inserts a one-line «scoped install» notice near the top so the
     reader knows this AGENTS.md was tailored, not just outdated.
  3. Leaves every other section verbatim.

Output goes to stdout. Caller pipes / redirects to a temp file, then
passes that path to `marker_block.py upsert --src <tempfile>`.

Usage:
  python3 generate_subset_agents_md.py SOURCE.md skill-a,skill-b,...

Stdlib only. Python 3.8+.
"""
from __future__ import annotations

import re
import sys


CONSUMER_PREAMBLE = """\
# Skill Governance Toolkit — agent rules

> Rules for AI agents working with the skill library in this repository.
> Installed and maintained by the skill-governance-toolkit installer — this
> managed block is replaced on toolkit upgrades; put project-specific rules
> OUTSIDE the managed markers.

---
"""

CONSUMER_OVERVIEW_INTRO = (
    "This project has the **skill-governance toolkit** installed — meta-skills "
    "that govern the skill library in this repository, following the `AGENTS.md` "
    "+ `SKILL.md` open standards (Linux Foundation AAIF · Anthropic Agent Skills). "
    "Installed governance skills (`skills/INDEX.jsonl` is the authoritative list):"
)

CONSUMER_BUILD_BODY = """\
## Build & Test Commands

Validation runs through the installed governance skills and runtime scripts:

```bash
# Audit the skill library — handoff, budget, naming, portability, multi-tool compat
# Trigger: «skill audit» / «check skills»
#
# Output: out/library-audit/library-audit-{date}.md

# Score one skill across 9 dimensions (D1–D9, includes D9 Safety)
# Trigger: «evaluate skill X» / «score skill X»
#
# Output: dimension table + top-3 improvements + (optional) rewrite

# Inspect the installed corpus shape — categories, tiers, orphans
python3 scripts/filter_skills.py --index skills/INDEX.jsonl --list-categories

# Aggregate info-tier evidence across scored skills — promotion view
python3 scripts/filter_skills.py --index out/scores/index.jsonl --info-summary
```

First audit over a pre-existing skill library: run with `STRICTNESS=permissive`
so toolkit-specific conventions (`metainfo:`, `compatibility:`) report as
advisories, not blockers — tighten once the library is annotated.

If `scripts/` directories contain Python helpers, run them with `python3` and stdlib only — **no pip dependencies allowed** (portability requirement).

"""

# Anchors that identify the toolkit's own AGENTS.md. Every transform below is
# guarded by its own anchor — absent anchor → verbatim pass-through.
_TOOLKIT_H1 = "# AGENTS.md — Skill Governance Toolkit"
_OVERVIEW_INTRO_RE = re.compile(
    r"This repository is a \*\*skill-governance toolkit\*\*.*?operate on other skills:",
    re.DOTALL,
)
_SELF_PATTERN_PARA_RE = re.compile(
    r"\n\nThe toolkit itself follows the universal pattern it enforces[^\n]*\n"
)
_STACK_SECTION_RE = re.compile(
    r"\n## Stack & Architecture\n.*?(?=\n## )", re.DOTALL
)
_BUILD_SECTION_RE = re.compile(
    # Replace from the heading up to (not including) the first ### subsection
    # («Script & reference path resolution» — consumer-relevant, kept).
    r"## Build & Test Commands\n.*?(?=### )", re.DOTALL
)
_README_BULLET_RE = re.compile(
    r"\n- `README\.md` — quick start[^\n]*"
)


def consumer_transform(text: str) -> str:
    """Rewrite toolkit-repo-specific sections for a consumer install.

    Anchor-guarded: a source that does not look like the canonical toolkit
    AGENTS.md (e.g. the synthetic fixtures in tests) passes through verbatim.
    """
    if _TOOLKIT_H1 not in text:
        return text

    # Header block: H1 + «single source of truth» blockquote up to the first
    # horizontal rule → consumer preamble.
    head, sep, tail = text.partition("\n---\n")
    if sep and _TOOLKIT_H1 in head:
        text = CONSUMER_PREAMBLE + tail

    text = _OVERVIEW_INTRO_RE.sub(CONSUMER_OVERVIEW_INTRO, text, count=1)
    text = _SELF_PATTERN_PARA_RE.sub("\n", text, count=1)
    text = _STACK_SECTION_RE.sub("\n", text, count=1)
    text = _BUILD_SECTION_RE.sub(CONSUMER_BUILD_BODY, text, count=1)
    text = _README_BULLET_RE.sub("", text, count=1)
    return text


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: generate_subset_agents_md.py SOURCE.md skill-csv", file=sys.stderr)
        return 1

    src_path, skill_csv = sys.argv[1], sys.argv[2]
    installed = {s.strip() for s in skill_csv.split(",") if s.strip()}

    try:
        with open(src_path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"cannot read {src_path}: {e}", file=sys.stderr)
        return 1

    text = consumer_transform(text)

    # Drop skill-summary table rows for skills NOT installed.
    # Match lines whose first table cell is `skill-name` (backtick-quoted).
    # Heuristic: such rows look like  | `name` | description |  with `name`
    # being a kebab-case identifier. We only drop rows whose name is unknown
    # — header/divider rows have no backticked cell and are preserved.
    row_re = re.compile(r"^\|\s*`([a-z0-9][a-z0-9-]*)`\s*\|")
    out_lines: list[str] = []
    dropped: list[str] = []
    for line in text.splitlines():
        m = row_re.match(line)
        if m:
            name = m.group(1)
            # Only filter rows that name a top-level skill (avoid false
            # positives like inline code in a non-skill table). We treat
            # any name not in the full skill set as «pass through», so
            # unknown rows survive. The caller passes the canonical
            # `installed` set; we drop rows whose name LOOKS like a skill
            # (kebab-case + 2+ segments) and is NOT installed.
            looks_like_skill = "-" in name and name.replace("-", "").isalnum()
            if looks_like_skill and name not in installed:
                dropped.append(name)
                continue
        out_lines.append(line)

    new_text = "\n".join(out_lines)

    # Full install (nothing dropped) → consumer copy without a scoped notice.
    if not dropped:
        sys.stdout.write(new_text)
        return 0

    # Insert the scoped-install notice after the first horizontal rule
    # (which separates the header block from the body in AGENTS.md).
    notice = (
        "\n> **Scoped install notice (generated by installer):**\n"
        f"> This `AGENTS.md` was tailored for a subset install — "
        f"{len(installed)} skill(s) actually present. See `skills/INDEX.jsonl` "
        "for the canonical installed list."
    )
    if dropped:
        notice += "\n> Skill rows omitted from the table above: " + ", ".join(f"`{n}`" for n in sorted(dropped)) + "."
    notice += "\n"
    # Insert after first `\n---\n` separator
    if "\n---\n" in new_text:
        head, _, tail = new_text.partition("\n---\n")
        new_text = head + "\n---\n" + notice + tail
    # If no separator found, prepend at top (degenerate AGENTS.md)
    else:
        new_text = notice + "\n" + new_text

    sys.stdout.write(new_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
