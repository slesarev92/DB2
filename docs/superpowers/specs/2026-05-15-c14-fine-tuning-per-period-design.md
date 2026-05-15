# Фаза C #14 — Fine Tuning расширение per-period (design)

**Дата:** 2026-05-15
**Автор:** SashaS (через brainstorm с LLM-агентом, шаблон-референс — B.9b)
**Статус:** Design — ожидает user review перед writing-plans
**Связанные документы:**
- `GO3.md` §2 — постановка задачи и открытые вопросы
- `docs/CLIENT_FEEDBACK_v2_DECISIONS.md:222-223` — фиксация гранулярности
- `docs/CLIENT_FEEDBACK_v2.md:148-157` — MEMO §5.1 Fine Tuning
- `docs/superpowers/specs/2026-05-15-b9b-monthly-financial-plan-design.md` — референс архитектуры
- ADR-CE-01 (Excel = источник истины)

---

## 1. Цель

Перенести 4 finance-input поля с per-year-скаляров на **per-period (43 точки = M1..M36 + Y4..Y10)** override:

| Поле | Текущая dimension | Целевая dimension |
|---|---|---|
| `ProjectSKU.copacking_rate` | per-SKU, скаляр | per-SKU, 43 override + fallback на скаляр |
| `ProjectSKUChannel.logistics_cost_per_kg` | per-channel, скаляр | per-channel, 43 override + fallback на скаляр |
| `ProjectSKUChannel.ca_m_rate` | per-channel, скаляр (after B.7) | per-channel, 43 override + fallback на скаляр |
| `ProjectSKUChannel.marketing_rate` | per-channel, скаляр (after B.7) | per-channel, 43 override + fallback на скаляр |

**Бизнес-сценарий (MEMO §5.1):** «повышенный тариф копакинга для марта–июня Y2», сезонное удорожание логистики, перераспределение бюджета маркетинга внутри года.

**Acceptance:** при пустых override pipeline даёт **идентичный** результат → GORJI drift сохраняется < 0.03%.

---

## 2. Решения по архитектурным вопросам (зафиксировано)

### 2.1 Scope `copacking_rate` — **per-SKU**

Копакинг = тариф завода-партнёра, не зависит от канала продаж. Семантически парный с `production_mode_by_year` (Q1 DECISIONS — per-SKU per-year). Асимметрия с 3 другими полями оправдана.

### 2.2 Storage — **JSONB-массив длины 43 на тех же таблицах**

Изоморфно `production_mode_by_year` (B.8) и `bom_cost_level_by_year` (B.11). Один паттерн для всех 4 полей.

**Семантика:** `effective[i] = by_period[i] if by_period and by_period[i] is not None else scalar`.

Скаляр (`copacking_rate` и т.д.) остаётся базой; override — опциональный «слой сверху».

**Почему не PeriodValue:**
- PeriodValue привязан к `psk_channel_id` → не подходит для per-SKU `copacking_rate`.
- Three-tier (Predict/FineTuned/Actual) + версионирование избыточны для override-сценария.
- Смешение паттернов в одной фиче — антипаттерн.

**Почему не отдельная таблица:**
- 4 поля, JSONB достаточно.
- B.8 / B.11 успешно используют JSONB-on-table.
- Меньше миграций и join'ов в pipeline.

### 2.3 Гранулярность — **43 периода (M1..M36 + Y4..Y10)**

Фиксировано DECISIONS:222-223. Совпадает с B.9b.

### 2.4 UI placement — **отдельный Fine Tuning tab, 4 секции**

Все per-period override в одном месте. Не захламляет BOM panel и Channel form. Скаляр-fallback виден как placeholder в каждой ячейке. Quick-edit в существующих формах — backlog (YAGNI).

### 2.5 Bulk-fill — **reuse `FinancialPlanBulkFill` через generic `BulkFillTarget[]`**

Вынести компонент в `frontend/components/shared/period-bulk-fill.tsx`. Helpers из `financial-plan-utils.ts` — переиспользуем как есть.

---

## 3. Архитектура данных

### 3.1 Alembic-миграция (revision after `e5f6a7b8c9d0`)

```sql
ALTER TABLE project_skus
  ADD COLUMN copacking_rate_by_period JSONB DEFAULT NULL;

ALTER TABLE project_sku_channels
  ADD COLUMN logistics_cost_per_kg_by_period JSONB DEFAULT NULL,
  ADD COLUMN ca_m_rate_by_period             JSONB DEFAULT NULL,
  ADD COLUMN marketing_rate_by_period        JSONB DEFAULT NULL;
```

`NULL` по умолчанию = «нет override» = pipeline берёт скаляр. Data-миграция не требуется.

### 3.2 SQLAlchemy model changes

```python
# ProjectSKU (backend/app/models/entities.py)
copacking_rate_by_period: Mapped[list[Decimal | None] | None] = mapped_column(
    JSONB, nullable=True, default=None
)

# ProjectSKUChannel
logistics_cost_per_kg_by_period: Mapped[list[Decimal | None] | None] = mapped_column(
    JSONB, nullable=True, default=None
)
ca_m_rate_by_period:      Mapped[list[Decimal | None] | None] = mapped_column(JSONB, nullable=True, default=None)
marketing_rate_by_period: Mapped[list[Decimal | None] | None] = mapped_column(JSONB, nullable=True, default=None)
```

**Mutation:** при изменении JSONB-полей обязателен `flag_modified(obj, "<column>")` (см. memory `feedback_jsonb_flag_modified`).

### 3.3 Constraints / validation

- Если `by_period is not None` → `len(by_period) == 43`.
- Каждый элемент: `Decimal | None`.
- Диапазон элементов = диапазон скаляра:
  - `copacking_rate` — `>= 0` (стоимость, ₽).
  - `logistics_cost_per_kg` — `>= 0` (₽/кг).
  - `ca_m_rate`, `marketing_rate` — `[0, 1]` (доля).
- Pydantic-валидация на API-границе + service-level assert перед save.

---

## 4. Backend

### 4.1 Service layer

Новый модуль `backend/app/services/fine_tuning_period_service.py`:

```python
def list_overrides_by_sku(session, project_id, sku_id) -> SkuOverrides:
    """Возврат 43-элементного массива copacking_rate (с null = нет override)."""

def list_overrides_by_channel(session, project_id, sku_id, psk_channel_id) -> ChannelOverrides:
    """Возврат dict {logistics_cost_per_kg: [43], ca_m_rate: [43], marketing_rate: [43]}."""

def replace_sku_overrides(session, project_id, sku_id, copacking_rate_by_period) -> None:
    """Атомарная замена (None = убрать override, иначе массив длиной 43)."""

def replace_channel_overrides(session, project_id, sku_id, psk_channel_id, payload) -> None:
    """Атомарная замена 3 массивов на канале."""
```

Паттерн повторяет `financial_plan_service.list_plan_by_period` / `replace_plan` (B.9b).

### 4.2 API endpoints (FastAPI)

```
GET    /api/v1/projects/{project_id}/fine-tuning/per-period/sku/{sku_id}
PUT    /api/v1/projects/{project_id}/fine-tuning/per-period/sku/{sku_id}
GET    /api/v1/projects/{project_id}/fine-tuning/per-period/channel/{psk_channel_id}
PUT    /api/v1/projects/{project_id}/fine-tuning/per-period/channel/{psk_channel_id}
```

Pydantic-схемы (`backend/app/schemas/fine_tuning.py`):
- `SkuOverridesResponse(copacking_rate_by_period: list[Decimal | None] | None)`
- `ChannelOverridesResponse(logistics_cost_per_kg_by_period, ca_m_rate_by_period, marketing_rate_by_period: list[Decimal | None] | None)`
- `SkuOverridesPayload` / `ChannelOverridesPayload` — те же поля, with field-level validators (`length == 43`, value-range).

Авторизация: те же scope-проверки, что в B.9b (project-member, recalc capability).

### 4.3 Engine integration

В `calculation_service._build_line_input`:

```python
def _resolve_period_value(by_period, scalar, idx):
    if by_period is not None and by_period[idx] is not None:
        return Decimal(by_period[idx])
    return scalar

copacking_arr = tuple(
    _resolve_period_value(sku.copacking_rate_by_period, sku.copacking_rate, i)
    for i in range(43)
)
logistics_arr = tuple(
    _resolve_period_value(ch.logistics_cost_per_kg_by_period, ch.logistics_cost_per_kg, i)
    for i in range(43)
)
ca_m_arr = tuple(
    _resolve_period_value(ch.ca_m_rate_by_period, ch.ca_m_rate, i)
    for i in range(43)
)
marketing_arr = tuple(
    _resolve_period_value(ch.marketing_rate_by_period, ch.marketing_rate, i)
    for i in range(43)
)
```

`PipelineInput` обновляется: 4 скаляр-поля заменяются на tuple-43 (или сохраняем скаляр + добавляем `_arr` параллельно — выбор в plan'е, влияет на минимальность diff в шагах).

**Шаги, требующие правок:**

| Шаг | Поле | Текущий доступ | Новый доступ |
|---|---|---|---|
| s03 (COGS) | `copacking_rate` | `pi.copacking_rate` | `pi.copacking_rate_arr[t]` |
| s05 (Contribution) | `logistics_cost_per_kg` | `pi.logistics_cost_per_kg` | `pi.logistics_cost_per_kg_arr[t]` |
| s06 (EBITDA) | `ca_m_rate`, `marketing_rate` | скаляр | `pi.ca_m_rate_arr[t]`, `pi.marketing_rate_arr[t]` |

Шаги s01, s02, s04, s07-s12 не затронуты.

### 4.4 Backward compat / legacy

- Все 4 JSONB-поля по умолчанию `NULL` → `_resolve_period_value` возвращает скаляр → bit-identical вывод pipeline.
- Acceptance GORJI без override-данных = drift < 0.03% (текущий baseline).

### 4.5 Взаимодействие с существующим `PeriodValue`

`PeriodValue.values["logistic_per_kg"]` сейчас используется в B.5 (импорт actual-данных, three-tier). После #14:
- Источник истины для **эффективной ставки в pipeline** = `logistics_cost_per_kg_by_period` (override) → `logistics_cost_per_kg` (скаляр).
- `PeriodValue.values["logistic_per_kg"]` остаётся как fact-data из импорта (B.5 OBPPC). Если пользователь импортировал GORJI с фактической логистикой — это уезжает в PeriodValue actual-слой, не в наш override.
- **Чёткое разделение:** override = «как пользователь хочет править план», PeriodValue = «снимок фактов из импорта».

Это разные слои данных — не дублирование, не конфликт. Документируется в комментарии к engine.

---

## 5. Frontend

### 5.1 Структура UI

Новый таб **Fine Tuning → Per-period overrides** в навигации проекта.

Внутри — 4 collapsible-секции:

1. **Copacking rate (₽/ед)** — таблица:
   - Строки: SKU проекта.
   - Колонки: M1, M2, ..., M36, Y4, Y5, ..., Y10 (43 колонки).
   - Cell: input number. Placeholder = текущий скаляр-fallback. Empty input = убрать override.
2. **Logistics (₽/кг)** — строки `SKU × Channel`, колонки 43.
3. **CA&M rate (%)** — строки `SKU × Channel`, колонки 43.
4. **Marketing rate (%)** — строки `SKU × Channel`, колонки 43.

**Override indicator:** ячейка с заданным override — outlined / accent-color. Ячейка с fallback — placeholder с прозрачностью.

**Banner:** если все 4 поля для SKU/Channel = NULL — «Per-period override не настроены, используются базовые ставки (см. BOM panel / Channel form)».

### 5.2 Reuse существующих компонентов

| Источник | Назначение |
|---|---|
| `frontend/lib/financial-plan-utils.ts` | `periodLabel`, `modelYearOf`, `periodsInYear`, `distributeYear`, `fillRange`, `isLegacyData` — используем как есть. |
| `frontend/components/projects/financial-plan-bulk-fill.tsx` | Переезжает в `frontend/components/shared/period-bulk-fill.tsx`. Generic `BulkFillTarget[]` интерфейс уже подходит — миграция = path rename + import update. |
| `frontend/components/projects/financial-plan-editor.tsx` | Извлечь общий 43-колоночный grid в `frontend/components/shared/period-grid.tsx` (с slots для rows/cells/edit-callbacks). |
| `frontend/components/projects/financial-plan-editor.tsx` | Остаётся для B.9b финплана; внутри использует новый `<PeriodGrid>`. |

Новый компонент: `frontend/components/projects/fine-tuning-per-period-panel.tsx` — оркестрация 4 секций.

### 5.3 Bulk-fill действия

- **«Распределить год»** — выбрать model_year (1..10), ввести annual value → раскидать по периодам этого года (M-периоды для Y1..Y3 = annual/12, Y-периоды для Y4..Y10 = annual).
- **«Залить диапазон»** — выбрать period_number range → задать value во все.
- **«Сбросить override»** (новое для #14) — в строке/выделенном диапазоне → выставить `null` (вернуться к скаляру).

### 5.4 Quick-edit в существующих формах — backlog

В первой итерации **не делаем**. BOM panel и Channel form редактируют только скаляр (baseline). После UX-feedback — решаем нужен ли quick-edit. (YAGNI.)

---

## 6. Testing

| Слой | Файлы | Сценарии |
|---|---|---|
| Unit (service) | `tests/services/test_fine_tuning_period_service.py` | round-trip get/set; partial null elements; length≠43 → reject; out-of-range → reject; per-SKU vs per-channel разделение |
| Unit (engine) | `tests/engine/test_resolve_period_value.py` | fallback на скаляр при `None`; override применяется; legacy NULL ≡ no-op pipeline |
| Integration (API) | `tests/api/test_fine_tuning_per_period.py` | GET/PUT round-trip; auth; project-member scope; idempotency; rejection bad payloads |
| Acceptance | `tests/acceptance/test_e2e_gorji.py` | (расширение существующих) без override → drift < 0.03%; новый case с override → drift в ожидаемую сторону |
| Frontend | `npx tsc --noEmit` 0 errors; manual smoke: 4 секции рендерятся, bulk-fill работает, override сохраняется и применяется (полный refresh — пересчёт KPI) |

**Цель:** baseline 477 + новые ~25-30 = **~500-510 passed**.

---

## 7. Migration / rollout

1. Создать миграцию `fine_tuning_per_period.py` — 4 JSONB-колонки `NULL`-default.
2. SQLAlchemy-модели обновить.
3. Service + API + Pydantic-схемы.
4. Engine `_resolve_period_value` + 3 шага (s03, s05, s06).
5. Acceptance GORJI — drift baseline сохраняется.
6. Frontend: refactor financial-plan-bulk-fill → shared, extract PeriodGrid, новый panel.
7. CHANGELOG + DECISIONS update.

Подход TDD: тесты до кода (как в B.9b).

---

## 8. Открытые backlog-вопросы (не блокируют дизайн)

1. **`logistics_per_l` vs `_per_kg`:** в DECISIONS «руб/л», в коде/БД `logistics_cost_per_kg`. Перед имплементацией верифицировать в GORJI Excel — какая единица в формуле и нужно ли переименовывать поле/конвертировать через density. На `ProjectSKU` есть поле `volume_l` (литры/ед) — потенциально логистика рассчитывается через `volume_l × шт × density × tariff_per_kg`, тогда `_per_kg` корректно и UI просто маркирует единицу как «₽/кг». Финализируем перед эпиком.
2. **Excel-import override:** есть ли в GORJI-Excel колонки с per-period для этих 4 полей? Если есть — расширяем парсер импорта. Если нет — backlog.
3. **Bulk-reset:** в §5.3 есть per-row / per-range «Сбросить override» (выставить null). Отдельный вопрос — нужна ли *table-level* кнопка «сбросить ВСЮ таблицу для секции» (например, очистить весь copacking-override всех SKU одним кликом). Решим по UX-feedback.

---

## 9. Out of scope

- PeriodValue refactor — оставляем как есть (используется для B.5 OBPPC).
- Quick-edit в BOM panel / Channel form — backlog после UX-feedback.
- Импорт override из Excel — backlog (зависит от #8.2).
- Версионирование override (audit log) — backlog. Текущая схема — last-write-wins.
- Per-channel copacking_rate — решено остаться per-SKU (см. §2.1).

---

## 10. Файлы, затрагиваемые имплементацией

**Backend:**
- `backend/alembic/versions/<new>_fine_tuning_per_period.py` (new)
- `backend/app/models/entities.py` (ProjectSKU, ProjectSKUChannel)
- `backend/app/services/fine_tuning_period_service.py` (new)
- `backend/app/schemas/fine_tuning.py` (new)
- `backend/app/api/routes/fine_tuning.py` (new или расширение)
- `backend/app/services/calculation_service.py` (`_build_line_input`, PipelineInput)
- `backend/app/engine/steps/s03_cogs.py`
- `backend/app/engine/steps/s05_contribution.py`
- `backend/app/engine/steps/s06_ebitda.py`
- `tests/services/test_fine_tuning_period_service.py` (new)
- `tests/engine/test_resolve_period_value.py` (new)
- `tests/api/test_fine_tuning_per_period.py` (new)
- `tests/acceptance/test_e2e_gorji.py` (расширение)

**Frontend:**
- `frontend/components/shared/period-grid.tsx` (new — extract из financial-plan-editor)
- `frontend/components/shared/period-bulk-fill.tsx` (rename из financial-plan-bulk-fill)
- `frontend/components/projects/financial-plan-editor.tsx` (refactor: использовать PeriodGrid)
- `frontend/components/projects/financial-plan-bulk-fill.tsx` (удалить, re-export из shared)
- `frontend/components/projects/fine-tuning-per-period-panel.tsx` (new)
- `frontend/app/projects/[id]/fine-tuning/page.tsx` (new tab или extension)
- `frontend/contexts/project-nav-context.tsx` (добавить навигацию)
- `frontend/lib/api/fine-tuning.ts` (new — fetch helpers)

**Docs:**
- `CHANGELOG.md` — секция `[Unreleased] feat(c14)`
- `docs/CLIENT_FEEDBACK_v2_DECISIONS.md` — отметить #14 closed
- `docs/ARCHITECTURE.md` — добавить §«Per-period overrides» с указанием паттерна

---

**Готовность дизайна:** ✅. Ожидает user review перед `writing-plans`.
