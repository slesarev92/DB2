# GO5 — Старт новой сессии DB2

> Создано 2026-05-16 после релиза v2.5.0.
> Фаза B = 5/5 ✅. Фаза C = **8/19 ✅** (закрыто #13, #14, #16, #19, #22, #24, #30, #31).

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
   Ожидаемо: **545 passed**, alembic head `eb59341b9034`.

---

## 1. Где остановились (2026-05-16)

### Фаза C — 15/19 ✅

| # | Что | Статус |
|---|---|---|
| 13 | Q4 OBPPC в «Основа» | ✅ 2026-05-16 |
| 14 | Fine Tuning per-period | ✅ 2026-05-15 |
| 16 | Каналы: группы + source_type + bulk endpoint | ✅ 2026-05-16 |
| 19 | SKU.format → enum | ✅ 2026-05-16 |
| 20 | Раскраска чувствительности с настраиваемыми порогами | ✅ 2026-05-16 |
| 21 | Status проекта + Gantt color override | ✅ 2026-05-17 |
| 22 | Collapse/expand разделов | ✅ 2026-05-16 |
| 23 | кг/л + единицы systematic | ✅ 2026-05-16 |
| 24 | Сценарии: перенос в «Анализ» + name | ✅ 2026-05-16 (интермиттирующая ошибка ⚠️ defer'нута) |
| 25 | Дублирование SKU между табами устранено | ✅ 2026-05-16 |
| 26 | BOM сводка справа | ✅ 2026-05-16 |
| 27 | PDF чекбоксы выбора секций | ✅ 2026-05-16 |
| 29 | Валидация вводных (minimum protection) | ✅ 2026-05-16 |
| 30 | nielsen_benchmarks.source_type | ✅ 2026-05-16 |
| 31 | Финальная русификация спот-чек | ✅ 2026-05-16 |

### Backlog Фазы C — 3 items open

**Большие (новые фичи, неделя+):**
- **#15** P&L фильтры + pivot Excel экспорт
- **#17** АКБ автоматический расчёт из `nd_target × ОКБ`
- **#18** Waterfall-диаграмма в Unit-экономике

**Требуют декомпозиции / уточнения:**
- **#28** Подсветка BOM документировать — в коде нет такой логики (видимо leftover из Excel-оригинала); до реализации нужна спека «что подсвечиваем и какой порог»

### Deferred (внутри закрытых)

- **C #24 sub-task**: «интермиттирующая ошибка в блоке сценариев» — не локализована; нужна репродукция. См. CHANGELOG запись C #24.

### Рекомендация для следующей сессии

**Лучшие кандидаты по порядку (стратегия GO4 + текущий контекст):**

1. **#27 PDF чекбоксы** — естественное продолжение C #22 (UI collapse). Спека уже частично есть («экспорт игнорирует collapse, селективный экспорт = #27»). Medium, ~день.

2. **#17 АКБ автоматический расчёт** — разблокирован закрытием #16 (теперь есть channel_group для разрезов). Medium-large, нужен brainstorm.

3. **#15 P&L фильтры + pivot Excel** — разблокирован #16 (group-разрезы теперь доступны в DB). Large, нужна декомпозиция.

4. **#29 Валидация вводных** — широкая UX-задача (multi-form). Medium, без архитектуры.

5. **#25 Дублирование SKU между табами** — нужна сначала диагностика (что дублируется); потом decision.

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
# Ожидаемо: 545 passed

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

Последняя: **`eb59341b9034`** (C #16 — channel_group + source_type).

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
# eb59341b9034 (head)
```

Если поднимаешь стенд с нуля — `alembic upgrade head` обязателен.

### Pre-flight для прода (важно перед `alembic upgrade head` на проде!)

C #19 (pack format) добавила migration с fuzzy backfill SKU.format. Перед выкаткой:
```sql
SELECT DISTINCT format FROM skus WHERE format IS NOT NULL;
```
Сверить с MAPPING_RULES в миграции `649d7f6f7144_c19_pack_format_enum.py`. Незнакомые значения будут обнулены — если нужно сохранить, дополнить MAPPING_RULES.

C #16 (channel groups) добавила миграцию с auto-backfill `channel_group` по паттерну `code`. Перед выкаткой:
```sql
SELECT DISTINCT code FROM channels;
```
Сверить с MAPPING_RULES (`EXACT_RULES` + `PREFIX_RULES`) в миграции `eb59341b9034_c16_channel_group_source_type.py`. Кастомные коды попадут в OTHER (тихо). Если для какого-то канала нужна другая группа — UPDATE до миграции.

### Полезные точки в коде (после v2.5.0)

| Файл | Что внутри |
|---|---|
| `backend/app/schemas/sku.py` | `PackFormat` Literal — enum упаковки (C #19) |
| `backend/app/schemas/project.py` | `NielsenBenchmarkItem` — type для бенчмарков (C #30) |
| `backend/app/schemas/scenario.py` | `ScenarioRead.name` / `ScenarioUpdate.name` (C #24) |
| `backend/app/schemas/channel.py` | `ChannelGroup` + `ChannelSourceType` Literal (C #16) |
| `backend/app/schemas/project_sku_channel.py` | `ProjectSKUChannelDefaults` + `BulkChannelLinkCreate` (C #16) |
| `backend/app/api/project_sku_channels.py` | bulk endpoint `POST /api/project-skus/{psk_id}/channels/bulk` (C #16) |
| `backend/app/services/project_sku_channel_service.py` | `bulk_create_psk_channels` savepoint pattern (C #16) |
| `backend/migrations/versions/eb59341b9034_c16_channel_group_source_type.py` | миграция + MAPPING_RULES (C #16) |
| `frontend/lib/channel-group.ts` | `CHANNEL_GROUP_LABELS`/`_ORDER` + `CHANNEL_SOURCE_TYPE_LABELS` (C #16) |
| `frontend/lib/format.ts` | `pluralizeRu` helper (C #16) |
| `frontend/components/projects/channels-panel.tsx` | точка входа, кнопка «+ Привязать канал» (C #16) |
| `frontend/components/projects/channel-dialogs.tsx` | `AddChannelsDialog` двухфазный + `CreateChannelDialog` + `EditChannelCatalogDialog` (C #16) |
| `frontend/components/ui/checkbox.tsx` | shadcn Checkbox wrapper над @base-ui/react (C #16) |
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
git log --oneline -3                 # последний коммит T5 docs(c16) + ранее
git branch                           # * main (feat/* удалены)
git tag | tail -3                    # v2.4.0, v2.5.0 (← последний)
docker compose -f infra/docker-compose.dev.yml ps  # 6 контейнеров healthy

docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
# eb59341b9034 (head)

docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q --ignore=tests/integration | tail -3
# 545 passed

docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
# (без output = ок)
```

Всё зелёное — можно стартовать brainstorm для следующего item (рекомендация: #27 PDF чекбоксы, или #17 АКБ авторасчёт).

---

## 5. Стартовая фраза для новой сессии

> Продолжаем DB2, читай `GO5.md` в корне репозитория. Стартуем
> следующий item Фазы C — рекомендация #27 (PDF чекбоксы) или
> #17 (АКБ авторасчёт). Если у тебя есть свои предпочтения — скажу.
