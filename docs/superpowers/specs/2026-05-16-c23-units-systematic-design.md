# C #23 — кг/л через слеш + единицы systematic (design)

> **Brainstorm session:** 2026-05-16 (compressed)
> **Источник:** MEMO 1.2 / CLIENT_FEEDBACK_v2.md:22 — «Везде добавить единицы измерения: шт, л/кг, %, руб (без НДС / с НДС — указывать явно рядом с полем)».
> **Scope category:** Medium UX. Backend получает unit_of_measure на SKU, frontend получает helper'ы для format_volume / format_per_unit и применяет sweep'ом.

---

## §1. Цель

Сделать единицы измерения видимыми во всех числовых полях:
1. Volume — `1.5 л` или `0.25 кг` (в зависимости от типа SKU)
2. Per-unit costs — `руб/л` или `руб/кг` (то же)
3. Существующие `%` и `руб` уже формируются helper'ами — sweep на покрытие
4. `шт` для штучных значений (offtake, ОКБ, package_type quantity)

### §1.1 User story

«Я аналитик, открываю результаты проекта. Цена ex-factory `52.30` — а это рублей за что? За литр или за килограмм? Сейчас догадываюсь из контекста. После #23 везде явно: `52.30 руб/л` или `52.30 руб/кг`».

---

## §2. Out of scope

| Что | Почему |
|---|---|
| Помесячная гранулярность unit_of_measure (одна SKU могла быть л в Y1, кг в Y2) | Нереалистично, YAGNI. |
| Per-channel unit_of_measure | Та же причина — это атрибут SKU, не канала. |
| Conversion между л↔кг (плотность) | Бизнес-сценарий не требует — каждая SKU имеет одну единицу. |
| Display «без НДС / с НДС» суффикс везде (MEMO 1.2 рядом) | Отдельная подзадача — много мест с разной семантикой, выделим как follow-up. Здесь только кг/л. |
| Изменение БД-формата `volume_l` колонки (переименование) | Семантика остаётся: число хранит объём/массу, единица — в новой колонке. Backward-compat. |
| Изменение pipeline-расчётов | Расчёты ведутся в «единицах продукта» (`per_unit`) — для них кг или л неважно. Display-only. |

---

## §3. Текущее состояние

### Backend
- `backend/app/models/entities.py:101-102`:
  ```python
  format: Mapped[str | None] = mapped_column(String(100), nullable=True)  # ПЭТ/Стекло/Банка/...
  volume_l: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
  ```
- Имя `volume_l` подразумевает литры implicitly. Нет колонки `unit_of_measure`.
- `format` (C #19) — enum упаковки. ПЭТ/Стекло/Банка обычно для жидкостей, Сашет/Стик/Пауч — для сухих/гелей.

### Frontend
- `frontend/lib/format.ts` имеет `formatMoney`, `formatPercent`, `formatMoneyPerUnit` (последний без знания единицы — выводит `52.30 ₽`). Нет `formatVolume`.
- Volume отображается raw (например `1.5`) или с подписью «л» в captions.

---

## §4. Дизайн

### §4.1 Backend schema

Добавить `SKU.unit_of_measure` (Literal["л", "кг"], NOT NULL, default "л").

```python
# backend/app/models/entities.py

SkuUnitOfMeasure = Literal["л", "кг"]

class SKU(Base, TimestampMixin):
    # ...existing fields...
    unit_of_measure: Mapped[SkuUnitOfMeasure] = mapped_column(
        String(2),
        nullable=False,
        server_default="л",
    )
```

CHECK constraint в миграции:
```sql
unit_of_measure IN ('л', 'кг')
```

### §4.2 Pydantic schemas

```python
# backend/app/schemas/sku.py

SkuUnitOfMeasure = Literal["л", "кг"]

class SKUBase(BaseModel):
    # ...existing fields...
    unit_of_measure: SkuUnitOfMeasure = "л"

# SKUCreate и SKURead inherit
# SKUUpdate: unit_of_measure: SkuUnitOfMeasure | None = None
```

### §4.3 Миграция

`backend/migrations/versions/<rev>_c23_sku_unit_of_measure.py`:
1. `op.add_column("skus", sa.Column("unit_of_measure", sa.String(2), nullable=True))`
2. `UPDATE skus SET unit_of_measure = 'л' WHERE unit_of_measure IS NULL` (backfill)
3. `op.alter_column("skus", "unit_of_measure", nullable=False, server_default="л")`
4. `op.create_check_constraint("valid_sku_unit_of_measure_value", "skus", "unit_of_measure IN ('л', 'кг')")`

### §4.4 Frontend types

```typescript
// frontend/types/api.ts

export type SkuUnitOfMeasure = "л" | "кг";

export interface SKU {
  // ...existing fields...
  unit_of_measure: SkuUnitOfMeasure;
}

// SKUCreate.unit_of_measure?: SkuUnitOfMeasure (default "л" если опущено — backend проставит)
```

### §4.5 Format helpers

В `frontend/lib/format.ts` добавить:

```typescript
/**
 * C #23: Объём/масса с единицей. Например formatVolume("1.5", "л") → "1,5 л".
 */
export function formatVolume(
  value: string | number | null | undefined,
  unit: "л" | "кг" = "л",
): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${moneyPerUnitFmt.format(num)} ${unit}`;
}

/**
 * C #23: Деньги per-unit с единицей. formatPerUnit("52.30", "л") → "52,30 ₽/л".
 */
export function formatPerUnit(
  value: string | number | null | undefined,
  unit: "л" | "кг" = "л",
): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${moneyPerUnitFmt.format(num)} ₽/${unit}`;
}

/**
 * C #23: Штучные значения. formatPieces(1500) → "1 500 шт".
 */
export function formatPieces(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${numberFmt.format(num)} шт`;
}
```

`formatMoneyPerUnit` (legacy без unit) — оставляем для backward-compat, помечаем deprecated в jsdoc. Постепенно заменяется на `formatPerUnit`.

### §4.6 Sweep по UI

Места где volume_l показывается без единицы → используем `formatVolume(sku.volume_l, sku.unit_of_measure)`:
- `frontend/components/projects/sku-panel.tsx` (список SKU)
- `frontend/components/projects/add-sku-dialog.tsx` (форма создания + edit) — добавить Select unit_of_measure
- `frontend/components/projects/value-chain-tab.tsx` (если есть отображение объёма)
- `frontend/components/projects/results-tab.tsx`
- Любые exports — оставляем как есть (PDF/Excel template'ы — отдельный sweep если попросят)

Места per-unit costs (`formatMoneyPerUnit` → `formatPerUnit` с unit из SKU):
- ChannelsPanel (price columns)
- ResultsTab (cost stack, ex-factory, COGS per unit)
- ValueChain table
- Pricing summary

Места штук (количества точек, ОКБ, offtake target):
- `formatPieces` применяется где число точек/штук
- channels-panel: ОКБ количество
- Sensitivity tables: где количества

### §4.7 Tests

Backend:
- `test_sku_unit_of_measure_default_l` (create без unit → "л")
- `test_sku_unit_of_measure_explicit_kg` (create с "кг" → сохранено)
- `test_sku_unit_of_measure_invalid_422` (передаём "g" → 422)
- `test_c23_migration_backfill` (миграция backfill existing SKUs в "л")

Frontend:
- tsc --noEmit clean
- Smoke: создать SKU с "кг", проверить отображение `0.5 кг` в panel

### §4.8 Docs

- CHANGELOG: запись в Unreleased C #23
- Pre-flight для прода: миграция автоматически backfill'ит existing SKU в "л" — это правильный default для GORJI (напитки).
- GO5.md status table: #23 ✅, count 9 → 10

---

## §5. Plan skeleton (3 задачи)

| # | Задача | Файлы | Модель |
|---|---|---|---|
| T1 | Backend: SKU.unit_of_measure + миграция + schemas + 4 теста | model, schema, migration, sku tests | sonnet |
| T2 | Frontend: TS types + helpers + sweep + AddSkuDialog Select | types, format.ts, sku-panel, add-sku-dialog, results-tab, channels-panel etc | sonnet |
| T3 | Smoke + CHANGELOG + GO5 + merge | docs | sonnet |

Branch: `feat/c23-units-systematic`.

---

## §6. Открытые вопросы

Нет.
