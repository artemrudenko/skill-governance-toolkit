# Benchmarks (external — not locally verified)

This file collects performance / token-economy claims about optional
integrations the toolkit ships. **All numbers in this file are external
upstream metrics — the toolkit does NOT include a reproducible eval
artifact for them.** Treat the claims as «reported by the upstream project»
rather than «verified by this toolkit».

If you need verified numbers for your own decision-making, run the
referenced eval methodology yourself on representative repos.

## code-review-graph (CRG)

**Claim:** ~8.2× token reduction across 6 real open-source repos.

**Source:** CRG project upstream — see [code-review-graph repo eval-runner
methodology](https://github.com/code-review-graph) (upstream URL — verify
when adopting).

**Method (per upstream):** Tree-sitter parses the repo into a SQLite call
graph. A code-review agent answers «blast-radius» / «callers of X» queries
by walking the graph instead of reading every file. Token count compared
against the same agent answering from raw file reads.

**Caveats:**
- The 8.2× figure is an average across 6 OSS repos. Real per-repo numbers
  vary by codebase shape (depth, fan-out, language).
- MCP mode has ~12k tokens of MCP schema overhead per session (28 tools).
  CLI mode trades this overhead for per-query startup latency.
- Small repos (< 50 files) often see overhead > savings — CRG is for
  medium / large codebases.
- Caveats and known bugs in the integration are documented in
  [`skills/integration-init/references/integrations.md`](../skills/integration-init/references/integrations.md).

**Status in this toolkit:** documented as «external claim» — not
reproduced locally. We do NOT recommend citing the 8.2× figure as a
guarantee; it is illustrative of «non-trivial reduction is achievable
on real code, when the agent uses graph queries».

## repomix

**Claim:** «one-shot packer (repo → single XML/markdown file) for small
repos or external code review».

This is a UX property, not a measured metric. No benchmark to verify.

## serena

**Claim:** LSP-bridge for semantic refactoring (rename, find-references,
type-aware navigation).

Also a UX property, not a measured metric.

## How to verify any claim here

1. Clone the upstream tool's eval-runner repo (if it has one).
2. Run against your representative codebases.
3. Compare to your existing tooling's baseline.
4. Record the result for your team — DO NOT trust this file as the source
   of truth.

The toolkit could ship a `scripts/eval-runner.py` in a future release if
there's user demand, but currently does not.

## Locally verified properties of the toolkit itself

These ARE measured and reproducible inside this toolkit:

- **All skill bodies ≤ 250 lines** post-v1.7.0 — run
  `bash scripts/audit.sh` to verify the body-budget table.
- **0 hardcoded secrets** in skill / agent / reference files — run
  `bash scripts/audit.sh` (Phase 7 secret-pattern scan).
- **All 4 JSON manifests valid** — run `bash scripts/audit.sh` (Phase 3).
- **Install smoke test passes** (fresh + idempotent re-run) — run
  `bash scripts/audit.sh` (Phase 4).

These are NOT performance benchmarks — they're structural correctness
properties. The toolkit ships self-CI for them via `scripts/audit.sh`.
