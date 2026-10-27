# Documentation Hub

Index of every document the Skill Governance Toolkit ships, classified by [Diátaxis](https://diataxis.fr/) type and audience. Pick your audience below for a numbered reading path; the table answers "which doc covers X".

## All documents

| Document | Type | Audience | Read this when… |
|---|---|---|---|
| [../README.md](../README.md) | explanation | consumer-repo maintainer | you are deciding whether to adopt the toolkit |
| [../QUICKSTART.md](../QUICKSTART.md) | tutorial | skill author · consumer-repo maintainer | you want the first install-to-first-audit run in minutes |
| [../AGENTS.md](../AGENTS.md) | reference | toolkit contributor | you (or your agent) work inside this repo and need its binding rules |
| [installation.md](installation.md) | how-to | consumer-repo maintainer | you install, upgrade, or distribute the toolkit in a repo or org |
| [runtime-compatibility.md](runtime-compatibility.md) | reference | consumer-repo maintainer | you need observed host versions and verification limits |
| [user-guide.md](user-guide.md) | how-to | consumer-repo maintainer · skill author | you run the meta-skill workflows (find / evaluate / compare / audit / port) — Russian version: [user-guide.ru.md](user-guide.ru.md) |
| [skill-authoring-standard.md](skill-authoring-standard.md) | reference | skill author | you write or review a `SKILL.md` and need the canonical skeleton |
| [gate-for-authors.md](gate-for-authors.md) | how-to | skill author | the gate flagged your MR and you need the one-screen overview |
| [checks-reference.md](checks-reference.md) | reference | skill author · consumer-repo maintainer | you need what a rule detects, its severity, and the fix |
| [cli-reference.md](cli-reference.md) | reference | platform-devops | you need exact flags, env vars, exit codes for `agent_audit.py` / `sgt` |
| [agent-governance-engine.md](agent-governance-engine.md) | explanation | platform-devops | you want the CLI / MCP / Docker layering of the audit engine |
| [architecture.md](architecture.md) | explanation | toolkit contributor | you want how the toolkit is structured and why |
| [extending-checks.md](extending-checks.md) | how-to | toolkit contributor | you add, remove, or tune a check or propose an org governance rule |
| [github-onboarding.md](github-onboarding.md) | how-to | platform-devops | you wire the PR gate into a GitHub Actions repo |
| [gitlab-onboarding.md](gitlab-onboarding.md) | how-to | platform-devops | you wire the MR gate into a GitLab CI repo |
| [security-rollout-guide.md](security-rollout-guide.md) | how-to | platform-devops | you enable the security suite over a legacy library without an avalanche |
| [security-incident-runbook.md](security-incident-runbook.md) | how-to | platform-devops | the gate is blocking everything and you have 5 minutes |
| [security-suppression-runbook.md](security-suppression-runbook.md) | how-to | skill author | a finding is a false positive and you need an exception |
| [../references/](../references/) | reference | toolkit contributor | you need the runtime contracts — checkpointing, path resolution, per-host tool mappings |

## Reading paths

### Skill author

1. [../QUICKSTART.md](../QUICKSTART.md)
2. [skill-authoring-standard.md](skill-authoring-standard.md)
3. [gate-for-authors.md](gate-for-authors.md)
4. [security-suppression-runbook.md](security-suppression-runbook.md)
5. [checks-reference.md](checks-reference.md)

### Consumer-repo maintainer

1. [../README.md](../README.md)
2. [installation.md](installation.md)
3. [user-guide.md](user-guide.md)
4. [checks-reference.md](checks-reference.md)
5. [github-onboarding.md](github-onboarding.md) or [gitlab-onboarding.md](gitlab-onboarding.md) — hand off to devops

### Platform-devops

1. [github-onboarding.md](github-onboarding.md) or [gitlab-onboarding.md](gitlab-onboarding.md) — pick your platform
2. [security-rollout-guide.md](security-rollout-guide.md)
3. [cli-reference.md](cli-reference.md)
4. [security-incident-runbook.md](security-incident-runbook.md) — bookmark for the bad day

### Toolkit contributor

1. [architecture.md](architecture.md)
2. [../AGENTS.md](../AGENTS.md)
3. [agent-governance-engine.md](agent-governance-engine.md)
4. [extending-checks.md](extending-checks.md)
5. [../references/](../references/) — runtime contracts
