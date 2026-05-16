# GO5 — Старт новой сессии DB2

> Создано 2026-05-16 после релиза v2.5.0.
> Фаза B = 5/5 ✅. Фаза C = **7/19 ✅** (закрыто #13, #14, #19, #22, #24, #30, #31).

---

## 0. Минимальный план старта (5 шагов)

1. Прочитать `CLAUDE.md` (роль, стек, правила).
2. Прочитать `docs/CLIENT_FEEDBACK_v2_DECISIONS.md` секция «Фаза C» (строки 219-247) — 12 открытых items.
3. Прочитать `[Unreleased]` в `CHANGELOG.md` — последние релизы C #19, #22, #24, #30, #31.
4. `git log --oneline -15` — увидеть последний `1ffa9a2 feat(c24): Сценарии` + всю цепочку.
5. Поднять dev-стенд:
   ```bash
   docker compose -f infra/docker-compose.dev.yml up -d
   docker compose -f infra/docker-compose.dev.yml exec backend alembic upgrade head
   docker compose -f infra/docker-compose.dev.yml exec backend pytest -q --ignore=tests/integration
   ```
   Ожидаемо: **514 passed**, alembic head `b9986ce73ab2`.

---

## 1. Где остановились (2026-05-16)

### Фаза C — 7/19 ✅

| # | Что | Статус |
|---|---|---|
| 13 | Q4 OBPPC в «Основа» | ✅ 2026-05-16 |
| 14 | Fine Tuning per-period | ✅ 2026-05-15 |
| 19 | SKU.format → enum | ✅ 2026-05-16 |
| 22 | Collapse/expand разделов | ✅ 2026-05-16 |
| 24 | Сценарии: перенос в «Анализ» + name | ✅ 2026-05-16 (интермиттирующая ошибка ⚠️ defer'нута) |
| 30 | nielsen_benchmarks.source_type | ✅ 2026-05-16 |
| 31 | Финальная русификация спот-чек | ✅ 2026-05-16 |

### Backlog Фазы C — 12 items open

**Большие (новые фичи, неделя+):**
- **#15** P&L фильтры + pivot Excel экспорт
- **#16** Каналы: группы (HM/SM/MM/TT/E-COM) + source_type *(prep сделан в #30)*
- **#17** АКБ автоматический расчёт из `nd_target × ОКБ`
- **#18** Waterfall-диаграмма в Unit-экономике
- **#20** Раскраска чувствительности с настраиваемыми порогами
- **#21** Статус проекта dropdown (часть закрыта A.3) + ручная раскраска Gantt

**Средние (полдня-день):**
- **#23** кг/л через слеш, единицы измерения systematically
- **#25** Дублирование SKU между табами устранить
- **#26** BOM сводка справа (Сырьё/Материалы/Прочее/Итого)
- **#27** PDF чекбоксы выбора секций
- **#29** Валидация вводных (отрицательная цена, нулевой объём)

**Требуют декомпозиции / уточнения:**
- **#28** Подсветка BOM документировать — в коде нет такой логики (видимо leftover из Excel-оригинала); до реализации нужна спека «что подсвечиваем и какой порог»

### Deferred (внутри закрытых)

- **C #24 sub-task**: «интермиттирующая ошибка в блоке сценариев» — не локализована; нужна репродукция. См. CHANGELOG запись C #24.

### Рекомендация для следующей сессии

**Лучшие кандидаты по порядку (стратегия GO4 + текущий контекст):**

1. **#16 Каналы: группы + source_type** — самый стратегический. Разблокирует #15, #17, #18. Prep сделан в C #30 (`NielsenBenchmarkItem.source_type`). Размер: medium-large, нужен полный brainstorm → spec → plan → subagent-driven.

2. **#27 PDF чекбоксы** — естественное продолжение C #22 (UI collapse). Спека уже частично есть («экспорт игнорирует collapse, селективный экспорт = #27»). Medium, ~день.

3. **#29 Валидация вводных** — широкая UX-задача (multi-form). Medium, без архитектуры.

4. **#25 Дублирование SKU между табами** — нужна сначала диагностика (что дублируется); потом decision.

Не рекомендуется как первое:
- **#28** — требует уточнения спецификации заказчика
- **#21** — частично закрыто, оставшееся spotty
- **#23** — мелкая, лучше как warmup

---

## 2. Технические напоминания

### Docker / тесты

```bash
# Backend pytest (~85 сек)
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q --ignore=tests/integration
# Ожидаемо: 514 passed

# Frontend tsc
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit

# Acceptance GORJI
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/acceptance -m acceptance
# Ожидаемо: 6 passed, drift < 0.03%
```

**Pytest paths внутри контейнера БЕЗ префикса `backend/`** (working dir = `/app`).

### Порты (стабильно с 2026-05-16)

- DB2 backend: host `8000` → container `8000`
- DB2 frontend: `http://localhost:3000`
- OP_GANSTA на `8001` (не пересекаемся)

См. memory `reference-dev-port-8000`.

### Миграции

Последняя: **`b9986ce73ab2`** (C #24 — scenarios.name).

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
# b9986ce73ab2 (head)
```

Если поднимаешь стенд с нуля — `alembic upgrade head` обязателен.

### Pre-flight для прода (важно перед `alembic upgrade head` на проде!)

C #19 (pack format) добавила migration с fuzzy backfill SKU.format. Перед выкаткой:
```sql
SELECT DISTINCT format FROM skus WHERE format IS NOT NULL;
```
Сверить с MAPPING_RULES в миграции `649d7f6f7144_c19_pack_format_enum.py`. Незнакомые значения будут обнулены — если нужно сохранить, дополнить MAPPING_RULES.

### Полезные точки в коде (после v2.5.0)

| Файл | Что внутри |
|---|---|
| `backend/app/schemas/sku.py` | `PackFormat` Literal — enum упаковки (C #19) |
| `backend/app/schemas/project.py` | `NielsenBenchmarkItem` — type для бенчмарков (C #30) |
| `backend/app/schemas/scenario.py` | `ScenarioRead.name` / `ScenarioUpdate.name` (C #24) |
| `frontend/lib/pack-format.ts` | `PackFormat` + `PACK_FORMAT_OPTIONS` (C #19) |
| `frontend/lib/analysis-sections.ts` | section ID константы (C #22) |
| `frontend/lib/use-collapse-state.ts` | хук collapse-state + localStorage (C #22) |
| `frontend/components/ui/collapsible.tsx` | `<CollapsibleSection>` wrapper (C #22) |
| `frontend/lib/project-nav-context.tsx` | TAB_ORDER + SECTION_GROUPS (где живут sub-tabs) |
| `frontend/components/projects/scenarios-tab.tsx` | UI редактора сценариев (C #24 поле name) |

---

## 3. Правила, которые легко забыть

- **Frontend checklist перед коммитом:** `npx tsc --noEmit` обязателен.
- **При структурных изменениях UI** — full restart frontend контейнера с очисткой `.next` (Windows+Docker HMR баг).
- **JSONB mutation:** `flag_modified(obj, "field")` обязателен.
- **JSONB storage Decimal:** asyncpg не сериализует — `_to_jsonb` в float, читать через `Decimal(str(raw))`.
- **Excel = источник истины** (ADR-CE-01). D-XX финальны.
- **Naming convention в alembic:** `op.drop_constraint("logical_name", ...)` через MetaData expansion — НЕ передавать полное имя `ck_table_logical` иначе двойной prefix `ck_table_ck_table_logical`. См. C #19 fix `92984da`.
- **Деплой:** только локально → GitHub → сервер. По команде пользователя.
- **Subagent-driven workflow** для эпиков ≥5 task (memory `feedback-subagent-driven-workflow`):
  - Brainstorm → Spec → Plan → fresh implementer per task → spec review → code-quality review
  - Sonnet для mechanical, opus для drift-critical integration
  - Controller сам делает micro-fixes (1-5 строк)
- **Branch convention:** `feat/cN-<feature-short>` (как `feat/c24-scenarios`).
- **Merge:** `--ff-only` (fast-forward) для small/medium, `--no-ff` для эпиков (TDD-цепочка). Сейчас в репо: C #13, #14 squash/no-ff, C #19/#22 ff-only.

---

## 4. Финальная проверка готовности к работе

```bash
git status                           # clean
git log --oneline -3                 # 1ffa9a2 feat(c24)... + ранее
git branch                           # * main (feat/* удалены)
git tag | tail -3                    # v2.4.0, v2.5.0 (← последний)
docker compose -f infra/docker-compose.dev.yml ps  # 6 контейнеров healthy

docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
# b9986ce73ab2 (head)

docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q --ignore=tests/integration | tail -3
# 514 passed

docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
# (без output = ок)
```

Всё зелёное — можно стартовать brainstorm для следующего item (рекомендация: #16 каналы группы, или #27 PDF чекбоксы).

---

## 5. Стартовая фраза для новой сессии

> Продолжаем DB2, читай `GO5.md` в корне репозитория. Стартуем
> следующий item Фазы C — рекомендация #16 (каналы группы) или
> #27 (PDF чекбоксы). Если у тебя есть свои предпочтения — скажу.
