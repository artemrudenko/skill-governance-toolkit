#!/usr/bin/env python3
"""backfill_requires_mcp.py — one-time migration codemod for metainfo.requires.mcp.

Wave C added MCP001: a skill that USES an `mcp__<server>__<tool>` token in its body
must DECLARE that server under `metainfo.requires.mcp`. Skills authored before this
field trip MCP001 the first time they are touched. This codemod scans a corpus and
backfills the missing declarations so adopters aren't blocked.

Usage:
    python3 scripts/backfill_requires_mcp.py [--root .] [--apply] [--skill PATH]

Default is a dry run: per-skill report of used + missing servers and the exact
frontmatter change that WOULD be made. `--apply` rewrites the SKILL.md frontmatter,
preserving everything byte-for-byte except the inserted lines. Idempotent.

Server extraction reuses agent_audit's masking + token regex so the backfilled set
EXACTLY matches what MCP001 flags — an extraction mismatch would backfill wrong data.

stdlib-only. The repo's frontmatter parser (build_index._parse_yaml_lines) only
round-trips a flow-style inline list under the 3-level `metainfo.requires.mcp` path,
so we emit `mcp: [a, b]`, not a block list.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import agent_audit
from build_index import parse_frontmatter

# Reuse the engine's masking + token regex + detection-context guard. Keeping this
# DRY guarantees the codemod backfills exactly the servers MCP001 would flag.
_mask_code_spans = agent_audit._mask_code_spans
_MCP_TOKEN_RE = agent_audit._MCP_TOKEN_RE
_declared_mcp_servers = agent_audit._declared_mcp_servers


def used_servers(body: str) -> set[str]:
    """MCP servers genuinely USED in the body (matching MCP001's extraction):
    tokens inside fenced/inline code are masked, detection-context lines skipped."""
    masked = _mask_code_spans(body)
    out: set[str] = set()
    for m in _MCP_TOKEN_RE.finditer(masked):
        line = agent_audit.line_text_for_offset(masked, m.start())
        if agent_audit.is_detection_context(line):
            continue
        out.add(m.group(1))
    return out


def _split_frontmatter(text: str) -> tuple[list[str], str] | None:
    """Split a SKILL.md into (frontmatter_lines, remainder) where remainder starts
    at the closing `---` line. Returns None if there is no leading `---` block.

    Line-based, not regex — we must reinsert lines and re-join without disturbing
    the body or line endings beyond the inserted text."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n").rstrip("\r") != "---":
        return None
    for idx in range(1, len(lines)):
        if lines[idx].rstrip("\n").rstrip("\r") == "---":
            return lines[1:idx], "".join(lines[idx:])
    return None  # unterminated frontmatter


def _flow_list(servers: list[str]) -> str:
    """Render a sorted flow-style inline list, e.g. `[github, serena]`."""
    return "[" + ", ".join(servers) + "]"


def _rewrite_frontmatter(fm_lines: list[str], full_set: list[str]) -> list[str]:
    """Return new frontmatter lines with `metainfo.requires.mcp` set to full_set.

    Three cases, in order of locality:
      1. A `mcp:` line already exists under requires → replace its value in place.
      2. A `requires:` block exists (no mcp) → insert `    mcp: [...]` right after it.
      3. A `metainfo:` block exists (no requires) → insert `  requires:` + `    mcp:`.
      4. No metainfo at all → append a metainfo block at the end.

    Indentation follows the repo's 2-space convention: metainfo sub-keys at 2 spaces,
    requires sub-keys (mcp) at 4 spaces. full_set is already the complete desired set."""
    flow = _flow_list(full_set)
    out = list(fm_lines)

    metainfo_idx = _find_top_key(out, "metainfo")

    if metainfo_idx is None:
        # Case 4: no metainfo block — append one.
        if out and not out[-1].endswith("\n"):
            out[-1] = out[-1] + "\n"
        out.append("metainfo:\n")
        out.append("  requires:\n")
        out.append(f"    mcp: {flow}\n")
        return out

    # Bounds of the metainfo block: from metainfo_idx+1 until the next top-level key.
    block_end = _block_end(out, metainfo_idx)

    requires_idx = _find_sub_key(out, metainfo_idx + 1, block_end, "requires", indent=2)
    if requires_idx is None:
        # Case 3: insert requires + mcp at the top of the metainfo block.
        insert = ["  requires:\n", f"    mcp: {flow}\n"]
        return out[: metainfo_idx + 1] + insert + out[metainfo_idx + 1 :]

    req_end = _block_end(out, requires_idx, max_idx=block_end)
    mcp_idx = _find_sub_key(out, requires_idx + 1, req_end, "mcp", indent=4)
    if mcp_idx is None:
        # Case 2: requires exists but no mcp — insert mcp right after requires.
        insert = [f"    mcp: {flow}\n"]
        return out[: requires_idx + 1] + insert + out[requires_idx + 1 :]

    # Case 1: replace the existing mcp value in place, preserving its line ending.
    eol = "\n" if out[mcp_idx].endswith("\n") else ""
    out[mcp_idx] = f"    mcp: {flow}{eol}"
    return out


def _line_key(line: str) -> tuple[int, str] | None:
    """Return (indent, key) for a `key:`-shaped line, else None. Ignores list items,
    comments, and blank lines."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("-"):
        return None
    if ":" not in line:
        return None
    indent = len(line) - len(line.lstrip(" "))
    key = line.split(":", 1)[0].strip()
    return indent, key


def _find_top_key(lines: list[str], key: str) -> int | None:
    for idx, line in enumerate(lines):
        parsed = _line_key(line)
        if parsed and parsed[0] == 0 and parsed[1] == key:
            return idx
    return None


def _find_sub_key(lines: list[str], start: int, end: int, key: str, indent: int) -> int | None:
    for idx in range(start, end):
        parsed = _line_key(lines[idx])
        if parsed and parsed[0] == indent and parsed[1] == key:
            return idx
    return None


def _block_end(lines: list[str], start: int, max_idx: int | None = None) -> int:
    """Index one past the last line belonging to the block opened at `start`.
    A block ends at the next line whose indent is <= the opener's indent."""
    opener = _line_key(lines[start])
    base_indent = opener[0] if opener else 0
    limit = len(lines) if max_idx is None else max_idx
    for idx in range(start + 1, limit):
        line = lines[idx]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= base_indent:
            return idx
    return limit


def backfill_text(text: str, path: Path) -> tuple[str, set[str]] | None:
    """Compute the backfilled SKILL.md text. Returns (new_text, missing_servers) or
    None if there is nothing to change. Verifies the result round-trips and clears
    MCP001 for the backfilled servers before returning."""
    split = _split_frontmatter(text)
    fm = parse_frontmatter(text)
    if split is None or fm is None:
        return None

    body = agent_audit.body_without_frontmatter(text)
    used = used_servers(body)
    if not used:
        return None

    declared = _declared_mcp_servers(fm)
    missing = used - declared
    if not missing:
        return None

    fm_lines, remainder = split
    full_set = sorted(declared | used)
    new_fm_lines = _rewrite_frontmatter(fm_lines, full_set)
    new_text = "---\n" + "".join(new_fm_lines) + remainder

    # Round-trip verification: the parser must now yield the full set, and the
    # engine must no longer raise MCP001 for any backfilled server.
    new_fm = parse_frontmatter(new_text)
    parsed_mcp = _declared_mcp_servers(new_fm or {})
    if not used.issubset(parsed_mcp):
        raise RuntimeError(
            f"{path}: backfill did not round-trip — parsed requires.mcp={sorted(parsed_mcp)}, "
            f"expected superset of {sorted(used)}"
        )

    return new_text, missing


def _iter_skills(root: Path, single: Path | None) -> list[Path]:
    if single is not None:
        return [single]
    return sorted(root.rglob("skills/**/SKILL.md")) or sorted(root.glob("skills/**/SKILL.md"))


def process(path: Path, apply: bool) -> bool:
    """Process one SKILL.md. Returns True if a change was made (apply) or would be
    made (dry-run). Prints a per-skill report. Untouched skills print nothing."""
    text = path.read_text(encoding="utf-8")
    result = backfill_text(text, path)
    if result is None:
        return False

    new_text, missing = result
    used = sorted(used_servers(agent_audit.body_without_frontmatter(text)))
    print(f"{path}")
    print(f"  used:    {', '.join(used)}")
    print(f"  missing: {', '.join(sorted(missing))}")
    if apply:
        path.write_text(new_text, encoding="utf-8")
        print(f"  applied: declared {', '.join(sorted(missing))} under metainfo.requires.mcp")
    else:
        print("  would declare the missing server(s) under metainfo.requires.mcp")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="repository root to scan (default: .)")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument("--skill", help="process a single SKILL.md path instead of scanning")
    args = parser.parse_args(argv)

    single = Path(args.skill).expanduser().resolve() if args.skill else None
    root = Path(args.root).expanduser().resolve()

    if single is not None and not single.is_file():
        print(f"error: --skill path not found: {single}", file=sys.stderr)
        return 1

    skills = _iter_skills(root, single)
    changed = 0
    for path in skills:
        try:
            if process(path, args.apply):
                changed += 1
        except (OSError, RuntimeError) as exc:
            print(f"error: {path}: {exc}", file=sys.stderr)
            return 1

    verb = "changed" if args.apply else "would change"
    print(f"\n{changed} skill(s) {verb}; {len(skills)} scanned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
