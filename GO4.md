# GO4 — Старт новой сессии DB2

> Создано 2026-05-16 после merge C #14 в main.
> Фаза B = 5/5 ✅. Фаза C = 1/18 ✅ (закрыт #14 Fine Tuning per-period).

---

## 0. Минимальный план старта (5 шагов)

1. Прочитать `CLAUDE.md` (роль, стек, правила работы).
2. Прочитать `docs/CLIENT_FEEDBACK_v2_DECISIONS.md` — секция «Фаза C» (строки 219-247). 17 открытых items.
3. Прочитать `[Unreleased]` в `CHANGELOG.md` — последний эпик C #14 закрыт 2026-05-16.
4. `git log --oneline -10` — увидеть финальный merge `1d7eb26` и chain.
5. Поднять dev-стенд:
   ```
   docker compose -f infra/docker-compose.dev.yml up -d
   docker compose -f infra/docker-compose.dev.yml exec backend alembic upgrade head
   docker compose -f infra/docker-compose.dev.yml exec backend pytest -q --ignore=tests/integration
   ```
   Ожидаемо: **508 passed**, alembic head `d4c87e14d126`.

---

## 1. Где остановились (2026-05-16)

### Фаза B — закрыта целиком (5/5 ✅)

- B.7 CA&M / Marketing → per-channel
- B.8 production_mode по годам
- B.9 статьи CAPEX (часть 1)
- B.9b помесячный финплан Y1-Y3 (43 периода)
- B.10 НДС dropdown + 22% default
- B.11 BOM 3 уровня + per-year override

### Фаза C — 1/18 ✅

- **#14 ✅** Fine Tuning per-period расширение (4 поля × 43 точки через JSONB-on-table)
  - Merge commit `1d7eb26` (merge --no-ff, 17 атомарных коммитов в графе).
  - Backend 508 passed (was 477 = +31). Acceptance GORJI drift < 0.03% preserved.
  - Spec: `docs/superpowers/specs/2026-05-15-c14-fine-tuning-per-period-design.md`
  - Plan: `docs/superpowers/plans/2026-05-15-c14-fine-tuning-per-period.md`
  - Реализация: spec/plan/CHANGELOG/DECISIONS/ARCHITECTURE.md (новый файл)

---

## 2. Открытый backlog Фазы C (17 items)

См. `docs/CLIENT_FEEDBACK_v2_DECISIONS.md` строки 221-247.

### Быстрые wins (1-3 часа, навигация / UX)

- **#13 Q4** — перенос OBPPC таб в "Содержание". Чисто navigation в `project-nav-context.tsx` (~1ч).
- **#22** — collapse/expand разделов отчёта.
- **#24** — Сценарии → Анализ/Результаты + переименование.
- **#25** — устранить дублирование SKU между табами.
- **#27** — PDF чекбоксы выбора секций.
- **#31** — финальная русификация спот-чек.

### Средние (валидация / единицы / справочники, полдня-день)

- **#19** — Тип упаковки → справочник enum (ПЭТ/Стекло/Банка/Сашет/Стик/Пауч).
- **#23** — единицы измерения systematically (кг/л через слеш).
- **#29** — валидация вводных (отрицательная цена, нулевой объём).
- **#30** — `nielsen_benchmarks.source_type` (заранее, до #16).
- **#26** — BOM сводка справа (Сырьё/Материалы/Прочее/Итого).
- **#28** — BOM пороги документировать.

### Большие (новые фичи, неделя+)

- **#15** — P&L фильтры + pivot Excel экспорт.
- **#16** — каналы: группы (HM/SM/MM/TT/E-COM) + source_type.
- **#17** — АКБ автоматический расчёт из `nd_target × ОКБ`.
- **#18** — waterfall-диаграмма в Unit-экономике.
- **#20** — раскраска чувствительности с настраиваемыми порогами.
- **#21** — статус проекта dropdown (часть закрыта A.3) + Gantt раскраска.

### Рекомендация для следующей сессии

Быстрый старт **#13 Q4** (~1ч) — закрыть half-session. Дальше brainstorm для **#16** (каналы группы / source_type) или **#17** (АКБ) — это infrastructure, на которых стоят #15, #18.

---

## 3. Backlog от закрытого C #14 (8 items)

Отложенный tech debt и UX, документирован в `docs/ARCHITECTURE.md` → раздел «Per-period overrides» → Backlog. Не блокирует Фазу C; решать когда удобно.

1. **Banner «все NULL»** в UI (spec §5.1) — hint для пустых override таблиц.
2. **PeriodBulkFill Y4-Y10** — сейчас «Распределить год» только Y1-Y3.
3. **`financial-plan-editor.tsx` refactor** под PeriodGrid (нужен data-model adapter; B.9b редактор оставлен как есть, regression risk).
4. **JSONB style standardization** для будущих миграций (`postgresql.JSONB(astext_type=Text())` vs bare `JSONB`).
5. **PipelineInput legacy-scalar cleanup** (Step 12 C #14 plan) — 32 occurrences в aggregator + 5 test files.
6. **ChannelSection batching** — единый PATCH per channel вместо GET+PUT × 3 секции.
7. **TOCTOU защита** для параллельных channel-section saves.
8. **Logistics placeholder в UI** — учесть PeriodValue actual layer (сейчас показывает только scalar).

---

## 4. Технические напоминания

### Docker / тесты

```bash
# Backend без интеграции с Polza API
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q --ignore=tests/integration
# Ожидаемо: 508 passed

# Frontend tsc
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit

# Acceptance GORJI
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/acceptance -m acceptance
# Ожидаемо: 6 passed, drift < 0.03%
```

**Pytest paths внутри контейнера БЕЗ префикса `backend/`** (working dir = `/app`).

### Порты (новое после C #14)

DB2 backend: **host `8001` → container `8000`** (см. memory `reference-dev-port-8001`). На host port 8000 локально живёт `OP_GANSTA` с hot-reload zombie sockets.

- `NEXT_PUBLIC_API_URL=http://localhost:8001`
- Backend openapi: `http://localhost:8001/openapi.json`
- Frontend: `http://localhost:3000` (без изменений)

### Миграции

Последняя: `d4c87e14d126` (C #14 — 4 JSONB override колонки). Если поднимаешь стенд с нуля — `alembic upgrade head` обязателен.

### Полезные точки в коде (после C #14)

| Файл | Что внутри |
|---|---|
| `backend/app/services/calculation_service.py:90` | `_resolve_period_value` — паттерн для per-period override fallback |
| `backend/app/services/calculation_service.py:472` | Option B порядок для logistics: override ДО `delta_logistics` |
| `backend/app/services/fine_tuning_period_service.py` | Service per-period CRUD (C #14 reference) |
| `backend/app/api/fine_tuning.py:35` | `_resolve_owned_channel` — IDOR-safe pattern для cross-project access |
| `backend/app/engine/context.py:71` | PipelineInput с scalar + _arr parallel (cleanup deferred) |
| `frontend/components/shared/period-grid.tsx` | Generic 43-column grid (reusable) |
| `frontend/components/shared/period-bulk-fill.tsx` | Bulk-fill dialog (распределить год / залить диапазон) |
| `frontend/lib/fine-tuning-utils.ts` | Helpers `sameOverride` / `normalizeInput` / `cellClasses` |

---

## 5. Правила, которые легко забыть

- **Frontend checklist перед коммитом:** `npx tsc --noEmit` обязателен.
- **При структурных изменениях UI** — full restart frontend контейнера с очисткой `.next` (Windows+Docker HMR баг).
- **JSONB mutation:** `flag_modified(obj, "field")` обязателен.
- **JSONB storage Decimal:** asyncpg не сериализует — конвертировать в float (`_to_jsonb`), читать через `Decimal(str(raw))` (memory `project-c14-option-b`).
- **Excel = источник истины** (ADR-CE-01). D-XX финальны.
- **Деплой:** только локально → GitHub → сервер. По команде пользователя.
- **Subagent-driven workflow** для эпиков ≥5 task (memory `feedback-subagent-driven-workflow`):
  - Brainstorm → Spec → Plan → fresh implementer per task → spec review → code-quality review
  - Sonnet для mechanical, opus для drift-critical integration.
  - Controller сам делает micro-fixes (1-5 строк), subagent overkill для cosmetic.
- **Branch convention:** `feat/cN-<feature-short>` (как `feat/c14-fine-tuning-per-period`).
- **Merge:** `--no-ff` для эпиков (сохраняет TDD-цепочку), squash для single-commit fixes.

---

## 6. Финальная проверка готовности

```bash
git status                           # clean
git log --oneline -1                 # 1d7eb26 Merge branch 'feat/c14-...'
git branch                           # * main (feat/* удалены)
docker compose -f infra/docker-compose.dev.yml ps
# 6 контейнеров healthy

docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
# d4c87e14d126 (head)

docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q --ignore=tests/integration | tail -3
# 508 passed

docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
# (без output = ок)
```

Если всё зелёное — можно стартовать brainstorm для следующего item (рекомендация: #13 Q4 как warmup, потом #16 / #17).

---

## 7. Стартовая фраза для новой сессии

> Продолжаем DB2, читай `GO4.md` в корне репозитория. Стартуем
> следующий item Фазы C, если не скажу иначе.
