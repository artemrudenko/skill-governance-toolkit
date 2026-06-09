# Skill Governance Toolkit — руководство пользователя

> **Аудитория:** автор и мейнтейнер скилов · **Тип:** how-to (рабочие процессы) · **Пререквизит:** [QUICKSTART](../QUICKSTART.md)

> **Канонический источник — английский [`user-guide.md`](user-guide.md).** Этот
> перевод зеркалит его раздел в раздел; при расхождении доверяй английской
> версии.

Универсальный набор meta-навыков для команд, принявших стандарты `AGENTS.md`
и `SKILL.md`. Помогает находить, оценивать, сравнивать, аудитить и портировать
agent skills без форка исходников под каждый AI-host.

Этот гайд проводит через восемь ключевых рабочих процессов (Use case 1–8). Он
сознательно не дублирует справочный материал — глубокое содержимое живёт в
канонических документах, на которые ссылается каждый раздел;
[documentation hub](README.md) индексирует их все.

Не знаешь, с чего начать? `python3 scripts/sgt.py quickstart` печатает doctor
summary, следующую рекомендованную команду и компактную карту intent → skill
(`--format json` для автоматизации).

---

## Что внутри toolkit

```mermaid
flowchart TB
    subgraph "Repository root"
        AGENTS["AGENTS.md<br/>single source of truth"]
        ALIASES["CLAUDE.md / GEMINI.md /<br/>.github/copilot-instructions.md<br/>per-host aliases"]
    end

    subgraph "skills/"
        FIND["skill-find"]
        EVAL["skill-evaluate"]
        COMP["skill-compare"]
        AUDIT["library-audit"]
        BUILD["skill-build-portable"]
        INIT["integration-init"]
    end

    subgraph "agents/"
        REVIEWER["code-reviewer"]
    end

    subgraph "scripts/"
        SGT["sgt.py<br/>CLI facade"]
        AUDITCLI["agent_audit.py<br/>deterministic engine"]
        MCP["agent_governance_mcp.py<br/>stdio MCP server"]
    end

    AGENTS --> FIND
    AGENTS --> EVAL
    AGENTS --> COMP
    AGENTS --> AUDIT
    AGENTS --> BUILD
    AGENTS --> INIT
    AUDITCLI --> MCP
```

Над твоими скилами работают два взаимодополняющих слоя:

- **Шесть LLM meta-скилов** (`skills/`) — суждение о качестве, сравнение,
  портирование.
- **Один детерминированный audit engine** (`agent_audit.py`) — воспроизводимые
  проверки безопасности/структуры для CI-гейтов; доступен как CLI, MCP server
  или Docker image (Use case 4).

Плюс `agents/code-reviewer.md` — диспатчабельный read-only TypeScript-ревьюер
(Use case 8).

---

## Карта скилов

```mermaid
flowchart LR
    A[Что-то хочу<br/>сделать со скилом] --> B{Что именно?}

    B -->|«есть ли скил для X?»| FIND[skill-find]
    B -->|«насколько хорош<br/>ЭТОТ скил?»| EVAL[skill-evaluate]
    B -->|«сравнить с<br/>корпоративным»| COMP[skill-compare]
    B -->|«здоровье моей<br/>БИБЛИОТЕКИ скилов»| AUDIT[library-audit]
    B -->|«сделать скил<br/>портабельным»| BUILD[skill-build-portable]
    B -->|«поставить<br/>CRG/repomix/serena»| INIT[integration-init]

    FIND -->|нашёл candidate| EVAL
    EVAL -->|score ниже target| BUILD
    AUDIT -->|findings| BUILD
    AUDIT -->|findings| EVAL
    COMP -->|MERGE recommendation| EVAL
    BUILD -->|post-conversion| EVAL
    BUILD -->|verify| AUDIT
```

| Потребность | Скил |
|---|---|
| Узнать, существует ли уже полезный скил | `skill-find` |
| Оценить один `SKILL.md` по качеству, безопасности и качеству текста | `skill-evaluate` |
| Сравнить локальный скил с корпоративной или upstream-версией | `skill-compare` |
| Проаудитить всю библиотеку скилов | `library-audit` |
| Превратить host-specific скил в портабельный | `skill-build-portable` |
| Поставить опциональные интеграции | `integration-init` |

Правило scope:

| Префикс | Scope |
|---|---|
| `skill-*` | Один скил |
| `library-*` | Вся библиотека |
| `integration-*` | Опциональный внешний тулинг |

---

## Use case 1 — Адаптация (adopt) внешнего скила

Когда коллега или upstream-репозиторий присылает `SKILL.md`, оцени его до
добавления в свою библиотеку.

```mermaid
sequenceDiagram
    actor U as User
    participant E as skill-evaluate
    participant R as references/rubrics.md
    participant J as out/scores/index.jsonl

    U->>E: «evaluate this skill»<br/>SKILL_TARGET=path/to/foreign-skill.md
    E->>R: load D1-D9 rubrics
    E->>E: Phase 0-3: score 9 dimensions
    E->>E: Phase 3.5: lexical security scan (caps D9)
    E->>E: Phase 3.6: writing-quality scan (caps D1)
    E->>E: Phase 3.7: activation coherence (caps D8)
    E->>E: Phase 3.8: info lane (never caps)
    E-->>U: report: summary + per-dim blocks + verdict
    E->>J: append JSONL entry (idempotent)

    Note over U,E: Safety gate форсирует красный вердикт когда (a) D9 ≤ 1<br/>на mutating-скиле OR (b) любой красный lexical security finding
```

```text
evaluate this skill
SKILL_TARGET=path/to/external/SKILL.md
```

Ожидаемый output:

| Секция | Назначение |
|---|---|
| Summary table | Обзор D1–D9 score одной строкой |
| Per-dimension findings | Evidence, риск и конкретное улучшение по каждому dimension |
| Safety gate | Блокирует небезопасные mutating-скилы, даже когда средний score выглядит приемлемо |
| Top 3 improvements | Фиксы с максимальным impact |
| Verdict | Adopt, adopt после фиксов, rewrite или reject |

Решение на основе вердикта:

| Verdict | Действие |
|---|---|
| 🟢 Green (80–100), safety gate чист | Adopt as-is |
| 🟡 Yellow (60–79) | Adopt после top-фиксов |
| 🟠 Orange (40–59) | Предпочесть альтернативу получше или сначала rewrite |
| 🔴 Red (< 40) или safety gate сработал | Не adopt'ить, пока не устранены safety-проблемы (gate срабатывает при D9 ≤ 1 на мутирующем скиле или любом 🔴 lexical security finding) |

---

## Use case 2 — Создание нового скила

Начинай со скаффолдера — `sgt new-skill` генерирует чистый по governance
скелет (portable frontmatter, закрытый словарь `metainfo`, структура фаз), так
что gate и `skill-evaluate` стартуют с проходного baseline — затем заполни его
и прогони оценку.

```bash
python3 scripts/sgt.py new-skill prompt-evaluate --category governance
```

```mermaid
flowchart TD
    A[Идея нового скила] --> B[1. Search существующих]
    B --> C[skill-find NEED='...']
    C --> D{Уже есть?}
    D -->|Да| E[Использовать existing]
    D -->|Нет, но похожий| F[skill-compare с existing]
    D -->|Нет вовсе| G[2. sgt new-skill name --category vocab]

    G --> H[Скаффолд skills/name/SKILL.md<br/>с TODO-заглушками]
    H --> I[Уточнить frontmatter:<br/>trigger-фразы в description, compatibility]
    I --> J[Заполнить body: Purpose / When to use /<br/>Phases / Hard rules]
    J --> K[3. skill-evaluate новый скил]
    K --> L{Score ≥ 80<br/>AND safety gate clear?}
    L -->|Нет| M[Применить top 3 improvements]
    M --> K
    L -->|Да| N[4. library-audit вся библиотека]
    N --> O{Library clean?}
    O -->|Нет: trigger collision<br/>или naming violation| P[Fix collision / rename]
    P --> N
    O -->|Да| Q[5. python3 scripts/build_index.py]
    Q --> R[Готово]
```

Пока заполняешь скаффолдные TODO:

- Держи frontmatter портабельным — не добавляй host-specific полей вроде
  `allowed-tools:`.
- Впиши 2–5 конкретных trigger-фраз в `description` — он управляет активацией.
- Добавь фазы workflow, hard rules, inputs, outputs и verification.
- Итерируйся по findings `skill-evaluate`, пока score и safety gate не
  проходят, затем запусти `library-audit` и пересобери `skills/INDEX.jsonl`.

Форма, которую обязан иметь каждый скил, в миниатюре:

```markdown
---
name: skill-example
description: One specific workflow. Use when "trigger one", "trigger two".
metainfo: { category: governance, tier: preview }  # + compatibility, license
---
> **Skill type:** Detect-only   <!-- required declaration (SKILL021) -->
```

Полный канонический скелет — все обязательные секции, схема `metainfo`, куда
класть запреты и контракт «Skill type» — в
[skill authoring standard](skill-authoring-standard.md). Скаффолдер выдаёт его
за тебя; сверяйся со стандартом при ручном редактировании.

---

## Use case 3 — Аудит библиотеки скилов

Запускай `library-audit` перед релизами и после крупных изменений скилов.

```mermaid
flowchart LR
    U[User] -->|«audit my skills»| LA[library-audit]
    LA --> P0[P0: env + rules setup]
    P0 --> P1[P1: handoff contracts]
    P1 --> P2[P2: token budget]
    P2 --> P3[P3: naming convention]
    P3 --> P4[P4: portability tag]
    P4 --> P45[P4.5: multi-tool compat]
    P45 --> P5[P5: security<br/>secrets / shell / cred paths]
    P5 --> P55[P5.5: metainfo coverage]
    P55 --> P6[P6: aggregate + write report]
    P6 --> OUT["out/library-audit/<br/>library-audit-{date}.md"]
```

```text
audit my skills
```

Что проверяет:

| Категория | Примеры |
|---|---|
| Handoff contracts | Уникальность триггеров, согласованность predecessor/successor |
| Token budget | Always-on стоимость, раздутые тела скилов |
| Naming | Kebab-case, закрытый словарь глаголов, паттерн `{entity}-{action}` |
| Portability | Отсутствующая compatibility-метадата, host-specific поля |
| Multi-tool compat | `allowed-tools:`, per-skill tool mappings, отсутствие sequential fallback для sub-agent путей |
| Security | Секреты, credential paths, опасный shell, риски prompt-injection |
| Metainfo | Обязательные `category` и `tier`, соответствие закрытому словарю |

Отчёт пишется в `out/library-audit/library-audit-{YYYY-MM-DD}.md`.
Большие прогоны чекпойнтятся в `.skill-state/library-audit/` — если прогон
оборвался на середине, повторный запуск скила продолжит с последнего
checkpoint (см. [State persistence](#state-persistence--resumable-runs)).

---

## Use case 4 — Детерминированный audit engine: CLI, MCP, Docker

`library-audit` — это agent skill. Детерминированный audit engine — отдельный
read-only слой для CI, локальных проверок и MCP-клиентов. Он индексирует
артефакты проекта, применяет детерминированные правила и возвращает structured
findings — он не заменяет человеческую или LLM-интерпретацию.

Выбери способ доставки:

- **CLI** — `scripts/agent_audit.py`, для локальных проверок и CI-скриптинга.
- **MCP server** — `scripts/agent_governance_mcp.py`, тот же engine как набор
  tools для агентов Claude / Codex / Cursor / VS Code.
- **Docker** — sandboxed MCP image (`--network none`, read-only mount) для CI
  и zero-install использования.

Setup, конфиги MCP/Docker, tools, профили и поведение путей:
[agent governance engine](agent-governance-engine.md). Полный каталог правил
с обоснованием: [checks reference](checks-reference.md).

### CLI

```bash
# Найти agent-related артефакты
python3 scripts/agent_audit.py discover .

# Полный аудит проекта
python3 scripts/agent_audit.py audit-project . --profile release-ready --format json

# Абсолютный gate: fail, если в дереве есть ХОТЬ ОДИН high-severity finding
python3 scripts/agent_audit.py audit-project . --profile release-ready --fail-on high

# Scope MR/PR-гейта: аудит только изменённых артефактов, блок только INTRODUCED findings
python3 scripts/agent_audit.py audit-project . --changed-only --base origin/main --fail-on-new high

# Аудит одного SKILL.md
python3 scripts/agent_audit.py audit-skill skills/skill-evaluate/SKILL.md

# Каталог правил
python3 scripts/agent_audit.py rules
python3 scripts/agent_audit.py explain-rule SKILL009
```

Каждый JSON-отчёт содержит `engine_version` и `rules_version` — вердикт
прослеживается до версии движка и политики, которые его произвели. Базовые
safety-правила несут **severity floor**, который custom-каталог не может
ослабить — набор floor-правил перечислен в
[checks-reference § Triggering examples and fixes](checks-reference.md#triggering-examples-and-fixes).

### GitHub Actions

`.github/workflows/ci.yml` гоняет baseline-проверки этого репозитория. Чтобы
поставить changed-only gate на consuming GitHub-репо, запусти
`sgt ci-init --github` и следуй
[GitHub onboarding guide](github-onboarding.md).

### GitLab CI — gate на merge request

Готовый шаблон лежит в `references/ci/gitlab-ci.yml` — скопируй его в корень
consuming-репозитория как `.gitlab-ci.yml` (или запусти `sgt ci-init --gitlab`).
Он аудитит только скилы/агенты, изменённые в merge request, по многоуровневой
схеме. **Канонический rollout-гайд** — env vars, запиненный toolkit SHA, auth
клона, переопределение образов для внутренних registry, конфиг постера
MR-комментариев и точные тестовые команды — это
[GitLab onboarding](gitlab-onboarding.md).

```mermaid
flowchart TD
    MR[MR открыт или обновлён] --> NOOP[noop job: всегда зелёная<br/>гарантирует pipeline каждому MR]
    MR --> CH{Изменены<br/>skills/agents/AGENTS.md?}
    CH -- нет --> SKIP[Gate-джобы пропущены]
    CH -- да --> SUP[Гигиена подавлений:<br/>list-suppressions<br/>просроченная запись блокирует]
    SUP --> SCOPE[audit-project --changed-only<br/>--base CI_MERGE_REQUEST_DIFF_BASE_SHA]
    SCOPE --> NEW{--fail-on-new:<br/>INTRODUCED high finding?}
    NEW -- да --> FAIL[skill-gate:block падает<br/>merge заблокирован]
    NEW -- нет --> PASS[skill-gate:block проходит]
    SCOPE --> ADV[skill-gate:advisory<br/>skill-audit.json + идемпотентный коммент в MR]
    FAIL -. SGT_FAIL_MODE=advisory .-> PASS
```

| Job | Команда | Эффект |
|---|---|---|
| `skill-gate:block` | `audit-project . --changed-only --base $CI_MERGE_REQUEST_DIFF_BASE_SHA --fail-on-new high` | Впервые внесённые high-severity findings роняют pipeline и блокируют merge (уже существовавшие high findings на затронутых legacy-ассетах не блокируют) |
| `skill-gate:advisory` | то же с `--fail-on none --format json` + `post_mr_comment.py` | Не блокирует; публикует `skill-audit.json` и идемпотентный коммент в MR |
| `noop` | `echo` на `alpine` | Всегда-зелёная заглушка; с включённым GitLab «Pipelines must succeed» гарантирует pipeline для каждого MR |

Операционные заметки:

- `--changed-only` сравнивает закоммиченный `HEAD` с `--base` (three-dot diff),
  так что автор отвечает только за закоммиченные сущности, которые тронул его
  MR. Локальный запуск гейта через `sgt gate` fail-fast'ится на «грязном»
  дереве — сначала закоммить или сделай stash, либо передай `--allow-dirty`.
  Граничные случаи base-ref (пустой base падает закрыто с exit 2, плохие refs,
  `GIT_DEPTH`) специфицированы в [CLI reference](cli-reference.md).
- Блокирующая джоба также гоняет гигиену подавлений: уже просроченное
  подавление блокирует MR. Процедура и SLA:
  [suppression runbook](security-suppression-runbook.md).
- Kill-switch: CI/CD-переменная `SGT_FAIL_MODE=advisory` переводит gate во
  всём флоте в non-blocking режим — процедура инцидента в
  [security incident runbook](security-incident-runbook.md).

---

## Use case 4.5 — Проверки безопасности артефактов и delta-gate (с 1.12.0)

Помимо структуры скила, движок сканирует **каждый** управляемый артефакт на
проблемы безопасности контента, по этим семействам правил:

- `SEC001`–`SEC003` — скрытые bidi/невидимые символы, homoglyph-тайпсквоттинг.
- `SEC010`–`SEC012` — опасные инструкции, inline-секреты и credential paths
  в не-скил артефактах.
- `REF001`–`REF004` / `SCR001`–`SCR003` — небезопасные ссылки и контент
  referenced-скриптов (exfiltration, опасный shell, секреты).
- `MCP001`/`MCP002` — использование `mcp__server__*` без объявления в
  `metainfo.requires.mcp` (и наоборот).
- `HOOK001`/`HOOK002` — команды хуков, запускающие опасный shell или
  утекающие секреты.

Полный каталог с примерами срабатывания и чистыми фиксами:
[checks reference](checks-reference.md).

### Delta-gate — блокирует только то, что вносит MR

Блокирующая CI-джоба и локальный `sgt gate` используют `--fail-on-new`, а не
абсолютный `--fail-on`. Они блокируют только findings, которые MR **внёс**
относительно базовой ветки; уже существующие остаются advisory. Это позволяет
команде включить набор правил поверх легаси-библиотеки без лавины ошибок — см.
[security rollout guide](security-rollout-guide.md).

```bash
# Воспроизвести точный вердикт блокирующей CI-джобы локально (changed-only delta-gate)
sgt gate --base main

# Эквивалент на сыром движке
python3 scripts/agent_audit.py audit-project . --changed-only --base main --fail-on-new high
```

Каждая подкоманда `agent_audit.py` и `sgt`, флаг, env var и exit code —
включая два слоя scoping (`--changed-only` — scope файлов vs `--fail-on-new` —
scope findings) — задокументированы в [CLI reference](cli-reference.md).

### Подавление findings

| Механизм | Подавляет | Как |
|---|---|---|
| Inline-маркер | только advisory-правила | `<!-- sgt-ignore: RULEID reason=... -->` на строке или над ней |
| Центральный файл | любое правило (gated через CODEOWNERS) | запись в `references/audit-ignore.json` с `reason` + рекомендуемым `expires` |

Сломанное/просроченное/без reason подавление fail-safe — finding остаётся, а
запись `IGNORE001/002/003` всплывает. Полная процедура, SLA и break-glass:
[suppression runbook](security-suppression-runbook.md).

Инструменты оператора — `validate-config`, `explain-finding`,
`list-suppressions`, аннотации `--format github`: см.
[CLI reference](cli-reference.md).

### Два контроля, два момента — качество vs гейт

Детерминированный гейт проверяет **безопасность и структуру**; качество
(D1–D9) скорит LLM-навык `skill-evaluate`, который ты запускаешь локально при
авторинге — он никогда не блокирует merge. Зелёный MR значит «безопасно и
корректно по структуре», **а не** «качественно». Полная картина, включая
side-by-side диаграмму, — в
[the governance gate for authors](gate-for-authors.md).

---

## Use case 5 — Сделать скил портабельным

Используй `skill-build-portable`, когда скил привязан к одному host или
организации.

```mermaid
sequenceDiagram
    actor U as User
    participant B as skill-build-portable
    participant S as Source SKILL.md
    participant T as Target portable file

    U->>B: «universalize this skill»<br/>OUTPUT_MODE=preview
    B->>S: Phase 0: read source
    B->>B: Phase 1: audit (F1-F7 + B1-B7 + S1-S3)
    B->>B: Phase 2: plan transformations
    B-->>U: Phase 3: diff preview<br/>blockers + warnings
    U->>B: Phase 4: confirm<br/>apply with OUTPUT_MODE=new-file
    B->>T: Phase 4: write target
    B->>B: Phase 5: verify portability<br/>(re-audit the output)
    B-->>U: diff report + residual concerns
    Note over U: Ничего не пишется до diff в Phase 3<br/>и подтверждения в Phase 4
```

Типичные проблемы, которые он чинит:

| Проблема | Пример | Ожидаемый фикс |
|---|---|---|
| Host-specific frontmatter | `allowed-tools:` | Удалить из портабельных скилов |
| Claude-only поля | `model`, `effort`, `hooks`, `paths` | Удалить или перенести в host-specific packaging |
| Организационные пути | `_audits/`, внутренние папки | Заменить на портабельные пути `out/...` |
| Per-skill tool mappings | `rules/codex.md` внутри одного скила | Перенести в repo-level `references/{tool}-tools.md` |
| Отсутствующий fallback | `Task` без sequential fallback | Добавить non-subagent fallback с эквивалентным output |

Полный каталог правил F1–F7 / B1–B7 / S1–S3 (что трансформируется
автоматически vs флагается как residual concern для ручного ревью) живёт в
`skills/skill-build-portable/references/audit-rules.md`.

Рекомендованный workflow: начни с `universalize this skill` +
`OUTPUT_MODE=preview`, просмотри diff, затем пиши в новый файл или явный
output path. Не переписывай source-файлы, пока diff не отревьюен.

---

## Use case 6 — Сравнить локальный скил с корпоративным

Используй `skill-compare`, когда локальный скил пересекается с корпоративной
или upstream-версией.

```mermaid
sequenceDiagram
    actor U as User
    participant C as skill-compare
    participant L as Local SKILL.md
    participant CR as Corporate library

    U->>C: «compare with corporate»<br/>LOCAL_SKILL=path · CORPORATE_DIR=path
    C->>L: Phase 0: read local
    C->>CR: Phase 1: find candidates (overlap signals)
    C->>C: Phase 2: deep comparison<br/>SHARED / CORP_ONLY / LOCAL_ONLY / CONFLICT
    C->>C: Phase 3: classify each diff<br/>ADOPT / PROPOSE / KEEP / RULES_FILE
    C->>C: Phase 4: recommendation
    C-->>U: report + optional draft blocks<br/>or OUTPUT_DIR artifacts
```

```text
compare with corporate
LOCAL_SKILL=skills/example/SKILL.md
CORPORATE_DIR=/path/to/corporate/skills
```

Рекомендации:

| Recommendation | Смысл | Критерий Phase 4 |
|---|---|---|
| `USE_CORPORATE` | Корпоративный скил покрывает локальную потребность и как минимум не хуже | `LOCAL_ONLY` ≤ 1 AND corporate quality ≥ local |
| `KEEP_LOCAL` | Локальный скил несёт важное project-specific поведение | `LOCAL_ONLY` > 5 OR local quality clearly exceeds corporate |
| `MERGE` | Обе версии содержат полезный неконфликтующий контент | `CORP_ONLY` ≥ 2 AND `LOCAL_ONLY` ≥ 2 AND no unresolved conflicts |
| `RULES_FILE` | Local-only контенту место в project rules, а не в shared-скиле | 3+ `LOCAL_ONLY` items — project-specific context |

Контракт draft-вывода: без `OUTPUT_DIR` черновики merged-файлов появляются как
fenced blocks внутри отчёта; с ним артефакты пишутся в `OUTPUT_DIR`
(или `out/skill-compare/`).

`skill-compare` не изменяет локальный или корпоративный source-скил. Считай
внешний корпоративный контент untrusted input: не запускай скрипты и команды,
на которые он ссылается.

---

## Use case 7 — Bootstrap опциональных интеграций

Используй `integration-init`, чтобы поставить опциональные тулы и
инжектировать их документацию в маркированные секции `AGENTS.md` и
`agents/code-reviewer.md`.

```text
/integration-init
```

Доступные интеграции:

| Интеграция | Что добавляет |
|---|---|
| code-review-graph | Tree-sitter + SQLite graph для blast-radius запросов |
| repomix | One-shot упаковка репозитория для внешнего ревью |
| serena | LSP-backed поддержка semantic refactoring |

Non-interactive helper: `./scripts/init.sh --all` (также `--with crg,repomix`,
`--use-cli`, `--advise-only`). Если prerequisite отсутствует, скил должен
упасть до частичной установки.

---

## Use case 8 — Code review agent

`agents/code-reviewer.md` — специализированный read-only ревьюер, которого
orchestrator-скил может диспатчить, если host это поддерживает.

Фокус — TypeScript. Что репортит:

| Категория | Примеры |
|---|---|
| Correctness | Runtime-баги, сломанные edge cases |
| Security | Обращение с секретами, unsafe shell, injection-риски |
| Maintainability | Хрупкая структура, дублированная логика |
| Tests | Отсутствующее или слабое покрытие |
| Portability | Host-specific предположения |

Правила:

- Sub-agents не диспатчат другие sub-agents.
- У Gemini нет sub-agent support — любой опциональный sub-agent path требует
  sequential fallback.
- Bash ограничен read-only inspection-командами.

---

## State persistence — resumable runs

Каждый multi-phase скил пишет checkpoint после каждой дорогой фазы. При
crash, timeout или Ctrl-C следующий вызов продолжит с последнего checkpoint.

```mermaid
flowchart LR
    Start([Phase 0]) --> Save0["checkpoint.py start<br/>-> run_id"]
    Save0 --> P1[Phase 1]
    P1 --> Save1["checkpoint.py save-phase<br/>--phase P1 --output {...}"]
    Save1 --> P2[Phase 2]
    P2 --> Save2["save-phase --phase P2"]
    Save2 --> Pn[...]
    Pn --> Done["checkpoint.py complete<br/>-> completed_at set"]

    Save1 -.crash.-> Resume[Next invocation:<br/>list-resumable]
    Resume --> P2
```

State живёт в `${CWD}/.skill-state/{skill-name}/run-{utc-ts}.json` (gitignored).
Схема checkpoint, helper CLI, per-skill дефолты resume-режима
(`auto` / `ask` / `new`) и фильтр stale-прогонов специфицированы в
[references/checkpointing.md](../references/checkpointing.md) — та таблица и
есть single source of truth.

---

## Установка и обновления

Самый быстрый путь:

```bash
git clone https://github.com/{your-org}/skill-governance-toolkit ~/tools/skill-toolkit
cd ~/my-project
python3 ~/tools/skill-toolkit/scripts/sgt.py init    # установка с подсказками + проверка
```

Всё остальное — установка plugin/extension под каждый host, интерактивный и
advanced инсталляторы, выборочная установка по `--category` / `--tier` /
`--skill`, куда ложатся файлы в каждом runtime,
[хостинг на приватном GitLab](installation.md#private-gitlab) и контракт
upgrade / uninstall (что сохраняется, что никогда не трогается) — в
каноническом [installation guide](installation.md). Одностраничная версия:
[QUICKSTART](../QUICKSTART.md). Прочитай `CHANGELOG.md` перед обновлением —
переименования и удаления помечены **🔴 BREAKING**.

---

## Регулярное обслуживание

После добавления, переименования или существенной правки скила:

```bash
python3 scripts/build_index.py
```

Раз в неделю или перед релизом запускай LLM-аудит («audit my skills» →
`library-audit`). Перед push'ем governed-изменения воспроизведи вердикт CI
локально:

```bash
sgt gate --base main
```

Тренд score persistence: `out/scores/index.jsonl` — append-only лог каждого
запуска `skill-evaluate` — отслеживай тренды качества скилов во времени.

---

## Writing Rules — как писать скилы

Держи тела скилов концизными, моноязычными, в active voice и table-driven —
полные правила (banned filler phrases, эвристики краткости, обоснование) — в
[AGENTS.md § Writing Style](../AGENTS.md#writing-style). `skill-evaluate`
Phase 3.6 enforces их лексически и может capнуть D1.

---

## См. также

Всё, что сознательно не покрыто здесь — внутренности движка, полный каталог
проверок, флаги CLI, стандарт авторинга, рубрики скоринга, runbooks и
tool-name mappings — индексировано в [documentation hub](README.md).
Английская (каноническая) версия этого гайда: [user-guide.md](user-guide.md).

---

## License

MIT. См. `LICENSE`.
