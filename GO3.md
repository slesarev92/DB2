# GO3 — Старт новой сессии DB2

> Создано 2026-05-15 после закрытия B.9b. Фаза B (MEMO v2.1) = 5/5 ✅.
> Следующий приоритет — Фаза C #14 (Fine Tuning расширение per-period).

---

## 0. Минимальный план старта (5 шагов)

1. Прочитать `CLAUDE.md` (роль, стек, правила работы).
2. Прочитать `docs/CLIENT_FEEDBACK_v2_DECISIONS.md` — секция «Фаза C»
   (источник истины приоритетов).
3. Прочитать `[Unreleased]` в `CHANGELOG.md` — последний релиз B.9b
   закрыт 2026-05-15.
4. `git log --oneline -15` — увидеть финальные коммиты B.9b на main.
5. Поднять dev-стенд (если ещё не):
   ```
   docker compose -f infra/docker-compose.dev.yml up -d
   docker compose -f infra/docker-compose.dev.yml exec backend alembic upgrade head
   docker compose -f infra/docker-compose.dev.yml exec backend pytest -q --ignore=tests/integration
   ```
   Ожидаемо: **477 passed**.

---

## 1. Где остановились (2026-05-15)

### Фаза B — закрыта целиком (5/5 ✅)

- B.7 CA&M / Marketing → per-channel
- B.8 production_mode по годам
- B.9 статьи CAPEX (часть 1)
- B.9b **помесячный финплан Y1-Y3** ← закрыто в этой сессии
- B.10 НДС dropdown + 22% default
- B.11 BOM 3 уровня + per-year override

### B.9b — итоги (для контекста архитектуры)

- API: `FinancialPlanItem.year (1..10)` → `period_number (1..43)`
- Service: `list_plan_by_period` (43 элемента); engine не трогали
- Frontend: 43-колоночная таблица + bulk-fill Dialog
  ("Распределить год" / "Залить диапазон") + legacy banner
- Pure helpers в `frontend/lib/financial-plan-utils.ts`:
  `periodLabel`, `modelYearOf`, `periodsInYear`, `distributeYear`,
  `fillRange`, `isLegacyData`
- 477 backend tests passed, tsc 0 errors, acceptance GORJI стабилен
- Spec: `docs/superpowers/specs/2026-05-15-b9b-monthly-financial-plan-design.md`
- Plan: `docs/superpowers/plans/2026-05-15-b9b-monthly-financial-plan.md`

---

## 2. Фаза C #14 — Fine Tuning расширение

### Цель (из DECISIONS строка 222-223)

Перенести с per-year/scalar на **per-period (43 точки)** четыре поля:

- `copacking_rate` — стоимость копакинга за единицу
- `logistics_per_l` — логистика за литр
- `ca_m_rate` — commercial activities & marketing rate
- `marketing_rate` — маркетинг rate

Это уже-per-channel поля (закрыто в B.7). Расширяем до per-period —
именно как закрыли финплан в B.9b. **Шаблон один в один.**

### Что уже готово (от B.9b)

- Frontend helpers (`financial-plan-utils.ts`) — переиспользуемые
- Bulk-fill Dialog (`financial-plan-bulk-fill.tsx`) — generic, принимает
  `BulkFillTarget[]` и `onApply` колбэк, можно использовать как есть
- Engine на 43 периода — работает (доказано B.9b acceptance GORJI)
- Pattern: lazy expand + banner для legacy данных

### Что нужно решить в brainstorm (новая сессия)

1. **Где хранить per-period values?** Сейчас 4 поля живут на:
   - `ProjectSKU.copacking_rate` (скаляр)
   - `ProjectSKU.logistics_per_l` (скаляр, нужно проверить)
   - `ProjectSKUChannel.ca_m_rate` (per-channel скаляр, после B.7)
   - `ProjectSKUChannel.marketing_rate` (per-channel скаляр, после B.7)

   Варианты:
   - JSONB override на тех же таблицах (как `bom_cost_level_by_year` в B.11)
   - Новая таблица `psk_channel_period_values` или похожая
   - Использовать существующий `period_values` слой (`PeriodValue`) ─ уже
     three-tier (Predict/Fine-tuned/Actual)

2. **Гранулярность:** monthly Y1-Y3 + yearly Y4-Y10 (43)? Или сразу 43
   monthly (Y1-Y10)? По DECISIONS — 43, как B.9b.

3. **UI расположение:** где редактировать?
   - Внутри Fine Tuning таба
   - В BOM panel (copacking) + Channel form (CA&M/marketing) + отдельная
     панель logistics
   - Единая 43-колоночная таблица "Per-period inputs"

4. **Bulk-fill переиспользование:** интегрировать тот же
   `FinancialPlanBulkFill` (или вынести в общий компонент
   `PeriodBulkFill`)? Скорее всего рефакторинг в `lib/` или
   `components/shared/`.

### Альтернативный быстрый старт

Если #14 кажется крупным — есть быстрый win **#13 Q4: перенос OBPPC**
(чисто навигация в `project-nav-context.tsx`, ~1 ч). Можно закрыть
за половину сессии и потом начать #14 со свежим контекстом.

---

## 3. Технические напоминания

### Docker / тесты (как в GO2.md)

```bash
# Backend без интеграции с Polza API
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q --ignore=tests/integration

# Frontend tsc
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit

# Acceptance GORJI
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/acceptance -m acceptance
```

**ВАЖНО:** в backend-контейнере pytest paths БЕЗ `backend/` префикса
(working dir = `/app`). Используй `tests/api/...`, не
`backend/tests/api/...`. Эта деталь не была в GO2 — добавил после B.9b.

### Миграции

Последняя миграция: `e5f6a7b8c9d0` (B.9 capex_items). B.9b не
требовал миграций — engine уже работал на 43 периода.

### Полезные точки в коде

| Файл | Что внутри |
|---|---|
| `backend/app/services/calculation_service.py:103` | `_load_project_financial_plan` — паттерн "tuple длины 43 из БД" |
| `backend/app/services/financial_plan_service.py` | Service per-period CRUD (B.9b reference) |
| `backend/app/engine/steps/s10_discount.py:85` | Аннуализация per-period → annual через `period_model_year` |
| `frontend/lib/financial-plan-utils.ts` | Pure helpers — переиспользуемые в #14 |
| `frontend/components/projects/financial-plan-bulk-fill.tsx` | Generic Dialog (BulkFillTarget interface) |
| `frontend/components/projects/financial-plan-editor.tsx` | Reference для 43-колоночной таблицы |

---

## 4. Правила, которые легко забыть

(Дублирую из GO2.md, всё ещё актуально)

- **Frontend checklist перед коммитом:** `npx tsc --noEmit` обязателен.
- **При структурных изменениях UI** — full restart frontend контейнера
  с очисткой `.next` (Windows+Docker HMR баг).
- **JSONB mutation:** `flag_modified(obj, "field")` обязателен.
- **Excel = источник истины** (ADR-CE-01). D-XX финальны.
- **Деплой:** только локально → GitHub → сервер. По команде пользователя.
- **Subagent-driven workflow** (новое после B.9b):
  - Brainstorm → Spec → Plan → Subagent per-task → Final review
  - Каждый task: fresh subagent + spec review + code quality review
  - Worktree не используется в DB2; работаем через feature branch
    (как `feat/b9b-monthly-financial-plan`)
- **Pytest paths внутри контейнера БЕЗ префикса `backend/`** (новое).

---

## 5. Финальная проверка готовности

```bash
git status                           # clean
git log --oneline -1                 # 6b9c7ea docs(b9b): CHANGELOG + DECISIONS
git branch                           # * main (без feat/*)
docker compose -f infra/docker-compose.dev.yml ps
# 6 контейнеров healthy

docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
# e5f6a7b8c9d0 (head)

docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q --ignore=tests/integration | tail -3
# 477 passed

docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
# (без output = ок)
```

Если всё зелёное — можно стартовать brainstorm #14.

---

## 6. Стартовая фраза для новой сессии

> Продолжаем DB2, читай `GO3.md` в корне репозитория. Стартуем
> Фазу C #14 (Fine Tuning расширение per-period), если не скажу иначе.
