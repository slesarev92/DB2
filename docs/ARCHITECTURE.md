# Архитектура DB2

Системная архитектура корпоративного FMCG-инструмента «Цифровой паспорт проекта».

Актуально для версии `v2.4.0+` (2026-04-15). Паттерны реализации — в
[`PATTERNS.md`](PATTERNS.md). Архитектурные решения — в [`ADR.md`](ADR.md).

---

## Стек

| Слой | Технология |
|------|-----------|
| Backend | Python 3.12 + FastAPI + SQLAlchemy (asyncpg) + Alembic |
| Async tasks | Celery + Redis |
| БД | PostgreSQL 16 |
| Frontend | Next.js 14 App Router + TypeScript + Tailwind + shadcn/ui |
| Таблицы | AG Grid Community (MIT) |
| Экспорт | python-pptx + openpyxl + WeasyPrint |
| AI | Polza AI (OpenAI-совместимый) — Claude 4.6 |
| Auth | JWT (MVP) |
| Инфра | Docker Compose (dev + prod), nginx + Let's Encrypt |

---

## Расчётное ядро

### Pipeline (12 шагов)

Все финансовые вычисления выполняются **только на бэкенде**.
Фронтенд только отображает и принимает правки пользователя.

```
s01 → s02 → s03 → s04 → s05 → s06 → s07 → s08 → s09 → s10 → s11 → s12
params  pricing  cogs  volume  contrib  below_gp  opex  capex  ocf  disc  kpi  summary
```

Шаги — чистые функции без побочных эффектов. Порядок строгий.
Файлы: `backend/app/engine/steps/s01..s12.py`.

### Три слоя данных (приоритет: Actual > Fine-tuned > Predict)

- **Predict** — автоматически рассчитанные значения из справочников
- **Fine-tuned** — значения изменённые пользователем вручную
- **Actual** — фактические данные из импорта Excel

### Временная ось

43 периода: M1..M36 (помесячно, Y1-Y3) + Y4..Y10 (годами) = 43 точки.

---

## Слои данных — Fine Tuning

### PeriodValue (B.5 OBPPC)

OBPPC (Price Pack Architecture) хранится в отдельной таблице `period_values`
как снимок фактов из импорта. Назначение: «что было на полке в этом периоде».

### Финплан (B.9b)

`FinancialPlanItem.period_number` (1..43). GET всегда отдаёт 43 элемента.
Bulk-fill «Распределить год» (Y/12) и «Залить диапазон» (one value → range).
Подробнее — в `docs/superpowers/specs/2026-05-15-b9b-monthly-financial-plan-design.md`.

### Per-period overrides (C #14)

4 финансовых поля могут переопределяться помесячно (M1..M36) + по годам
(Y4..Y10) через JSONB-массивы длины 43:
- `ProjectSKU.copacking_rate_by_period` (per-SKU)
- `ProjectSKUChannel.{logistics_cost_per_kg, ca_m_rate, marketing_rate}_by_period`
  (per-channel)

Семантика: `effective[i] = by_period[i] if not None else scalar`. NULL =
нет override (backward-compat). Pipeline получает tuple-43 через
`_resolve_period_value` helper в `calculation_service`.

**Storage:** asyncpg не сериализует Decimal в JSONB → service `_to_jsonb`
конвертирует в float. Engine при чтении использует `Decimal(str(raw))`
для controlled конверсии (precision-safe для domain values ≤ 6 знаков).

**Scenario delta + override (Option B):** для logistics override
применяется ДО `delta_logistics` multiplier — scenario stress работает
поверх override (override = новый base, stress поверх). Иначе stress
становится неинформативным в override-периодах. Для других 3 полей
(copacking/CA&M/marketing) scenario delta multipliers отсутствуют.

Паттерн изоморфен `production_mode_by_year` (B.8) и `bom_cost_level_by_year`
(B.11). Отличие от `PeriodValue` (B.5 OBPPC): override = «как пользователь
правит план», PeriodValue = «снимок фактов из импорта».

**Backlog:**
- «Banner all NULL» в UI (spec §5.1) — отложено.
- PeriodBulkFill «Распределить год» — только Y1-Y3 (preexisting limitation).
- financial-plan-editor.tsx refactor под PeriodGrid — отложено (data model adapter нужен).
- JSONB style standardization (`postgresql.JSONB(astext_type=Text())` vs `JSONB`) — для будущих миграций.

---

## Изоляция расширений

Все модули расширений — в `backend/app/` (сервисы, схемы, роутеры).
Расчётное ядро — в `backend/app/engine/`. Чистое разделение: ядро не
импортирует сервисы, сервисы вызывают ядро через `calculation_service`.

---

## Принципы безопасности

- IDOR-защита: все запросы проверяют `project.user_id == current_user.id`
- prod credentials — только в `.env`, не в репо
- CORS настроен в nginx (не в FastAPI)
- Rate limiting на API (см. `SECURITY_AUDIT_2026-04-14.md`)
