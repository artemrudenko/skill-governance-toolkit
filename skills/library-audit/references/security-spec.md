# Phase 5 — Security Validation Spec

Loaded by `library-audit` Phase 5 (and reused inline by `skill-evaluate` Phase 3.5 — same regex catalog, different scope: per-skill vs library-wide). Minimum-viable security baseline for skill
libraries — detect hardcoded credentials, dangerous shell patterns, and
references to sensitive credential paths.

**Scope:** runs against **ALL `.md` files under `skills/`** — every
`SKILL.md` plus everything in `references/` and `assets/` — AND **every**
`agents/*.md` file in the library. All of them can leak secrets equally
easily; all are read into agent context when their skill activates.

**Mode:** detect-only (per ADR-008 validator contract). Never auto-redacts.

**Self-exclusion (meta-rule):** files inside `skills/library-audit/` are
**exempt** from Phase 5 scanning of their own bodies. The library-audit skill
is the auditor — it documents the patterns it looks for, so it would
trivially flag itself on every run. Specifically, `security-spec.md`
contains all the regexes as documentation of what to detect. The implementer
MUST exclude `skills/library-audit/**` from the scan corpus. All other skills,
references, and agents remain in scope.

**Documentation exclusion:** markdown table cells whose row contains a
`Pattern` / `What it catches` / `Why dangerous` column header (the
documentation of patterns, not their use) are skipped. This prevents
false positives when a spec elsewhere references the patterns by name.

---

## Pass 5.1 — Secret patterns

Regex catalog for common credential formats. False-positive rate is low
because each pattern matches a vendor-specific shape.

| ID | Pattern | What it catches | Severity |
|---|---|---|---|
| **S1** | `sk-[A-Za-z0-9]{20,}` | OpenAI API keys | 🔴 |
| **S2** | `sk-ant-[a-zA-Z0-9_-]{32,}` | Anthropic API keys | 🔴 |
| **S3** | `xox[baprs]-[A-Za-z0-9-]{10,}` | Slack tokens | 🔴 |
| **S4** | `ghp_[A-Za-z0-9]{36}` | GitHub personal access tokens | 🔴 |
| **S5** | `ghs_[A-Za-z0-9]{36}` | GitHub App tokens | 🔴 |
| **S6** | `AKIA[0-9A-Z]{16}` | AWS access keys | 🔴 |
| **S7** | `AIza[0-9A-Za-z\-_]{35}` | Google API keys | 🔴 |
| **S8** | `(?i)(api[-_]?key\|password\|secret\|token)\s*[:=]\s*["'][^"']{8,}["']` | Generic `key: "value"` patterns with non-trivial values | 🟡 |
| **S9** | `-----BEGIN (RSA \|EC \|DSA \|OPENSSH )?PRIVATE KEY-----` | Inline private keys | 🔴 |
| **S10** | `(?i)bearer\s+[A-Za-z0-9_\-\.]{20,}` | Hardcoded Bearer tokens | 🔴 |

**Allowlist exceptions** (well-known placeholders that look like secrets but
are documentation):

- Pattern `your-token-here`, `<TOKEN>`, `xxx...xxx`, `***`, `REDACTED`
- Patterns inside fenced code blocks tagged `example`, `placeholder`, `mock`
- Patterns inside the `## Examples` section with `<` or `{` around them

When a finding lands inside one of these exceptions → 🟢 informational note,
not a finding.

---

## Pass 5.2 — Dangerous shell patterns

Detect command patterns that, if executed by an agent following the skill,
could destroy data or leak it externally. Apply to fenced code blocks (Bash,
shell) AND inline backticked commands.

> Renamed from D1–D9 in 1.18.1 to avoid colliding with the quality dimensions.

The engine table — `DANGEROUS_PATTERNS` in `scripts/agent_audit.py` — is
**canonical**; this table mirrors its semantics for the skills layer. Never
edit one without the other.

| ID | Pattern | Why dangerous | Severity |
|---|---|---|---|
| **DS1** | `rm` with `-r` AND `-f` flag clusters in **any order, case, or split** (`-rf`, `-fr`, `-Rf`, `-r -f`) targeting bare `/`, a system top-level dir (`/etc` `/usr` `/var` `/home` `/Users` `/boot` `/bin` `/sbin` `/lib` `/lib64` `/opt` `/root` `/srv` `/System`), `~`, or an **unquoted** `$VAR` that could be empty | Catastrophic — wipes filesystem or home | 🔴 |
| **DS2** | `curl\s+[^\|]+\|` piped to any shell sink `sh` / `bash` / `zsh` / `dash` / `ksh` / `fish`, with optional `sudo` before the sink | Pipe-to-shell from network — supply-chain attack vector | 🔴 |
| **DS3** | `wget\s+[^\|]+\|` piped to a shell sink — same sink set and optional `sudo` as DS2 | Same as DS2 | 🔴 |
| **DS4** | `eval\s+\$\(` or `eval\s+"\$\{` | Arbitrary code execution from variable | 🔴 |
| **DS5** | `(?i)dd\s+if=/dev/(random\|urandom\|zero)\s+of=` | Disk wipe pattern | 🔴 |
| **DS6** | `:\(\)\s*\{\s*:\|:\&\s*\}\;:` | Fork bomb | 🔴 |
| **DS7** | `chmod` + `777` or `0777` (optional flags such as `-R` may sit between `chmod` and the mode) on paths outside `/tmp/` | World-writable on non-tmp | 🟡 |
| **DS8** | `sudo\s+rm` (any form) | Privileged delete — needs explicit user consent | 🟡 |
| **DS9** | `>\s*/dev/sda` or similar block device | Raw disk write | 🔴 |
| **DS10** | `git push` followed by `--force` or `-f` anywhere on the command | Rewrites remote history — needs explicit user approval | 🟡 |
| **DS11** | `git reset --hard` | Discards local work irrecoverably — do not normalize | 🟡 |
| **DS12** | `bypass` / `skip` / `circumvent` phrased near `approval(s)` / `sandbox` / `permission(s)` | Instructs agents to defeat safety controls | 🔴 |

**DS1 false-positive budget** (deliberately NOT matched): relative paths,
`/tmp`, and quoted `"$VAR"` cleanup idioms — DS1 is a tripwire, not a
boundary.

**Allowlist:** these patterns are acceptable when they appear as
**anti-pattern examples** under a heading containing `Don't`, `Anti-pattern`,
`Never`, `Avoid`, `Bad example`, or `❌`. Detection skips the immediate
following code block. This lets skills educate about dangers without
self-flagging.

---

## Pass 5.3 — Credential file path references

Skills should never read files at well-known credential paths — those are
the user's secrets, not the skill's concern.

| ID | Path pattern | Why concerning | Severity |
|---|---|---|---|
| **C1** | `~/.aws/credentials`, `~/.aws/config` | AWS CLI credential store | 🔴 |
| **C2** | `~/.ssh/id_rsa`, `~/.ssh/id_ed25519`, `~/.ssh/id_ecdsa` | SSH private keys | 🔴 |
| **C3** | `~/.gnupg/`, `~/.gpg/` | GPG private key store | 🔴 |
| **C4** | `~/.netrc`, `~/.authinfo` | Generic HTTP/IMAP credentials | 🔴 |
| **C5** | `~/.kube/config` | Kubernetes credentials | 🟡 |
| **C6** | `~/.docker/config.json` | Docker registry auth | 🟡 |
| **C7** | `~/.gitconfig` followed by reading `[credential]` section | Git stored credentials | 🟡 |
| **C8** | `.env`, `.env.local`, `.env.production` (when read by a skill) | Project secret stores | 🟡 |
| **C9** | `KEYCHAIN`, `keychain-access` patterns (macOS) | Keychain access | 🟡 |

**Allowlist:** patterns that **document** these paths (telling the user to
configure them) are fine. Patterns that have the skill **read** them are not.
Distinguish by surrounding verbs — «put your key in `~/.aws/credentials`» is
informational; «`cat ~/.aws/credentials`» or «`open ~/.aws/credentials` to
load» is a finding.

---

## Reporting

For each finding, the audit report must include:

- File path (which SKILL.md or agent file)
- Line number of the match
- Phase + rule identifier (S1–S10 / DS1–DS12 / C1–C9)
- Severity emoji (🔴 / 🟡 / 🟢)
- Quoted snippet (truncate to 120 chars, mask middle of any matched secret
  pattern: `sk-...REDACTED...XyZ`)
- Suggested remediation (one line) — e.g. «move secret to environment
  variable referenced as `${OPENAI_API_KEY}`», «replace destructive command
  with safer alternative», «document this credential path but don't read it»

## Hard rules for this phase

- ❌ **Never emit the raw matched secret in the report.** Always mask:
  `sk-...REDACTED...XyZ` showing only first 5 + last 3 characters.
- ❌ Never edit the source file — pure detect.
- ✅ Always run against both `skills/**/SKILL.md` AND `agents/**.md`.
- ✅ Honor allowlists — false-positive control matters more than coverage at
  this baseline level.

## What this phase deliberately does NOT do

- **Static taint analysis** — tracking how secrets flow through a script.
  Out of scope for a regex-based baseline.
- **Network-call detection** — flagging skills that exfiltrate data to
  arbitrary URLs. Useful future addition.
- **Encrypted blob detection** — base64-encoded binaries that could be
  malicious payloads. Heuristic, high false-positive — defer.
- **Plugin / dependency scanning** — `pip install`, `npm install` lines —
  out of scope; that's a build-tool concern, not a SKILL.md concern.

For deeper static + behavioral security analysis, integrate `semgrep` or
similar at the CI layer.
