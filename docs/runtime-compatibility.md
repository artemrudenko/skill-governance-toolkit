# Runtime Compatibility Evidence

This page distinguishes documented support from an observed toolkit run.
The matrix records local checks on 2026-10-27.
Host releases and configuration can change these results.

| Host | Local observation | Evidence and limits |
|---|---|---|
| Codex CLI | Installed `skill-find` and ran a bounded discovery request. | Codex `0.164.0-alpha.11.1` read `.codex/skills/skill-find/SKILL.md`. One task succeeded in an isolated temporary project. The run also saw personal skills, so it was not a clean-room test. |
| Claude Code | CLI `2.1.310` discovered and executed `/skill-find` in a synthetic project. | The normal run used read-only tools, project settings, and no MCP servers. A separate `--restricted` run returned `Unknown skill: skill-find` from the Skill tool; its sequential fallback completed the search. |
| GitHub Copilot | CLI `1.0.83` discovered and invoked `skill-find`. | The agent completed one project-only search in a synthetic project. Local discovery also found the skill in a copied project configuration. |
| Gemini CLI | CLI `0.65.0` discovered `skill-find` after the test folder was trusted. | Discovery used a temporary Gemini home and copied project configuration. Execution requires authentication and was not verified. |
| Cursor | CLI `2026.10.22-27dcf5f` was tested without installing it globally. | The installer placed the skill in the documented project path. The CLI requires authentication, so discovery and execution were not verified. |

On 2026-10-27, Copilot, Claude, and Codex each ran one synthetic scenario for
`skill-evaluate`, `skill-compare`, `skill-build-portable`, `library-audit`, and
`integration-init`. The audit covered naming only. The integration scenario used
advice-only mode without installing tools. The other scenarios used read-only
outputs. These checks do not establish all modes or production outcomes.

PowerShell `7.6.9` ran on macOS from a temporary directory.
Its normal Unix path delegates to Bash.
Tests also forced the native PowerShell branch on macOS, covering one skill and all five hosts.
This simulation does not verify Windows-specific filesystem or process behavior.
The repository now defines a Windows runner for the native tests; its remote result is not yet verified.

Gemini may hide project skills until the workspace is trusted.
Trust the intended workspace through the host's normal trust flow; do not disable trust checks globally.

Claude Code can pre-approve tools declared in `allowed-tools`.
Other tools remain subject to permission settings.
See [Claude's documentation](https://code.claude.com/docs/en/skills#pre-approve-tools-for-a-skill).

When a host cannot dispatch a particular agent, use the skill's documented sequential fallback.
