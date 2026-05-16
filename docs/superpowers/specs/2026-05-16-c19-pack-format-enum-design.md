# C #19 — Тип упаковки → enum (design)

> **Brainstorm session:** 2026-05-16
> **Источник:** MEMO 1.3 / Блок 3 / BL-#19 («Тип упаковки → справочник enum (ПЭТ/Стекло/Банка/Сашет/Стик/Пауч)»).
> **Scope category:** Data model + validation + UI. Чисто продуктовая фича, не навигация.

---

## §1. Цель

Преобразовать существующее свободное текстовое поле `SKU.format` (`String(100)`) в строгий enum с фиксированным списком из 6 значений: **ПЭТ, Стекло, Банка, Сашет, Стик, Пауч**. NULL остаётся допустимым (= «не указано»).

### §1.1 User stories

- **US-1.** Как продакт, при создании SKU я выбираю тип упаковки из выпадающего списка — не путаюсь в «Пэт / пэт / PET / 0.5L PET».
- **US-2.** Как аналитик, в отчёте я вижу 6 чётких категорий упаковки, могу группировать SKU по типу.
- **US-3.** Как разработчик AI-промптов, я получаю на вход `format` ровно одно из 6 нормализованных значений (или null), а не «случайную строку».

---

## §2. Out of scope

| Что | Почему |
|---|---|
| `SKU.package_type` (String(100), используется как «Вложение в кейс») | Другая семантика — количество штук в кейсе («6 / 12 / 24 шт»). Будет отдельно почищен в #29 (валидация вводных) или отдельной задачей рефакторинга нейминга. |
| `OBPPCEntry.pack_format` (String(100), default `"bottle"`) | Это поле в OBPPC-матрице описывает форм-фактор позиции (bottle/can/...) в стратегическом плане, не материал контейнера SKU. Расширение OBPPC на enum — отдельная задача если потребуется. |
| Расширение enum-списка / поддержка «Прочее» | Решено в брейнсторме: 6 значений + NULL. Если когда-то появится 7-й вид — `ALTER TABLE ... DROP CONSTRAINT ... + ADD CONSTRAINT ...` тривиальна (прецедент: `capex_categories` в B.9). |
| PostgreSQL `CREATE TYPE ... AS ENUM` | Нарушает PATTERN-08 (varchar + CHECK constraint). Не используется в проекте. |
| Изменения движка расчётов | `format` — описательное поле, не участвует в pipeline. Подтверждено grep'ом (только AI/exports). |
| Локализация enum-значений на другие языки | Проект Русский-only. |

---

## §3. Текущее состояние

### §3.1 Backend

- `backend/app/models/entities.py:101` — `SKU.format: Mapped[str | None] = mapped_column(String(100), nullable=True)`
- `backend/app/schemas/sku.py:11, 26` — Pydantic `format: str | None = Field(default=None, max_length=100)` (в `SKUBase` и `SKUUpdate`)
- `backend/app/api/skus.py:54` — PATCH `/api/skus/{id}` endpoint работает (через `update_sku` service)
- Использование `format` (без расчётов, только display/AI):
  - `backend/app/api/ai.py:1422, 1469` — AI промпты (executive summary, image generation)
  - `backend/app/services/ai_context_builder.py:618` — AI context dictionary
  - `backend/app/export/pdf_exporter.py:156` — PDF SKU-row
  - `backend/app/export/ppt_exporter.py:569` — PPT SKU-row
  - `backend/app/export/templates/project_passport.html:440` — HTML template
  - `backend/app/services/pricing_service.py:102, 208` — sku_format в PricingSummary/ValueChain (display-only)

### §3.2 Frontend

- `frontend/types/api.ts:222` — `format: string | null` в SKU interface
- `frontend/components/projects/sku-panel.tsx:141` — display `p.sku.format ?? "—"`
- `frontend/components/projects/add-sku-dialog.tsx` — **нет** input для `format` (UI редактирует только brand/name/volume_l/package_type)
- `frontend/components/projects/fine-tuning-copacking-section.tsx:273` — display `sku.format ? ` · ${sku.format}` : ""`

### §3.3 Production DB (срез 2026-05-16)

В dev-БД (предположительно похожа на прод):
- `format = 'Пэт'` — 162 строки
- `format = '0.5L PET'` — 1 строка

Реальные значения на проде будут проверены при выкатке. Migration script будет логировать все non-mapped значения (см. §6.2).

---

## §4. Дизайн enum'а

### §4.1 Значения

Ровно 6 значений + NULL. **Cyrillic, точно как в MEMO**:

| Значение | Описание | Английский эквивалент (для fuzzy) |
|---|---|---|
| `ПЭТ` | Пластиковая ПЭТ-бутылка | PET, polyethylene terephthalate |
| `Стекло` | Стеклянная бутылка | Glass |
| `Банка` | Металлическая банка | Can, aluminium can |
| `Сашет` | Пакетик-саше | Sachet |
| `Стик` | Стик-пакет | Stick, stick-pack |
| `Пауч` | Гибкий пакет / pouch | Pouch |

NULL = «не указано / неизвестно».

### §4.2 SQL-уровень

```sql
-- Текущий: format String(100) NULL
-- Новый:   format VARCHAR(50) NULL + CHECK

ALTER TABLE skus
    ADD CONSTRAINT ck_skus_format
    CHECK (format IS NULL OR format IN ('ПЭТ', 'Стекло', 'Банка', 'Сашет', 'Стик', 'Пауч'));
```

Возможно `ALTER COLUMN format TYPE VARCHAR(50)` — но не обязательно, String(100) и так держит длиннейшее значение (Стекло = 12 байт UTF-8). Уменьшение длины делаем только если хочется явной сигнализации. **Решение:** оставить `String(100)` (минимальное изменение), но CHECK гарантирует корректность.

### §4.3 Pydantic-уровень

```python
# backend/app/schemas/sku.py

from typing import Literal

PackFormat = Literal["ПЭТ", "Стекло", "Банка", "Сашет", "Стик", "Пауч"]

class SKUBase(BaseModel):
    ...
    format: PackFormat | None = Field(default=None)
    # max_length=100 убираем — Literal уже валидирует
```

В `SKUUpdate` — то же самое.

### §4.4 TypeScript-уровень

```typescript
// frontend/types/api.ts

export type PackFormat = "ПЭТ" | "Стекло" | "Банка" | "Сашет" | "Стик" | "Пауч";

interface SKU {
  ...
  format: PackFormat | null;
}
```

```typescript
// frontend/lib/pack-format.ts (новый файл)

export const PACK_FORMAT_OPTIONS: readonly PackFormat[] = [
  "ПЭТ",
  "Стекло",
  "Банка",
  "Сашет",
  "Стик",
  "Пауч",
] as const;
```

---

## §5. Миграция данных

Alembic migration с двумя шагами:

### §5.1 Шаг 1: Backfill existing values (fuzzy mapping)

```python
# В migration's upgrade()

mapping_rules = [
    # (pattern, target_value); первый match wins; pattern — substring case-insensitive
    (("пэт", "pet", "p.e.t"), "ПЭТ"),
    (("стекл", "glass"), "Стекло"),
    (("банк", "can", "tin"), "Банка"),  # "Банка" + EN can/tin
    (("саше", "sachet"), "Сашет"),
    (("стик", "stick"), "Стик"),
    (("пауч", "pouch"), "Пауч"),
]

# Применяем case-insensitive substring match:
# UPDATE skus SET format = 'ПЭТ' WHERE LOWER(format) ~ 'пэт|pet|p\.e\.t';
# и так далее. Несовпадающие — обнуляем (NULL):
# UPDATE skus SET format = NULL WHERE format NOT IN ('ПЭТ', 'Стекло', 'Банка', 'Сашет', 'Стик', 'Пауч') AND format IS NOT NULL;
```

Для каждой mapping rule — один `UPDATE` оператор. Перед обнулением — `SELECT format, COUNT(*)` чтобы залогировать что обнуляется (видимо в alembic output).

### §5.2 Шаг 2: Add CHECK constraint

```python
op.create_check_constraint(
    "ck_skus_format",
    "skus",
    "format IS NULL OR format IN ('ПЭТ', 'Стекло', 'Банка', 'Сашет', 'Стик', 'Пауч')",
)
```

Если §5.1 не покрыл все строки (получили exception при ADD CHECK) — migration aborts, и devops видит что обнуление не сработало. Безопасный rollback.

### §5.3 Downgrade

```python
# downgrade(): DROP CONSTRAINT only.
# Существующие значения остаются как есть (уже валидные); freetext снова разрешён.
op.drop_constraint("ck_skus_format", "skus", type_="check")
```

Никакого обратного маппинга — это нормально, downgrade редок и destructive-fixup в нём не нужен.

### §5.4 Production rollout

Перед `alembic upgrade head` на проде:
1. SSH в прод → `SELECT format, COUNT(*) FROM skus GROUP BY format`.
2. Сверить с §5.1 mapping rules.
3. Если есть значения, которых mapping не покрывает (например «бутылка», «can-light», «mixed»), — обсудить с пользователем и дополнить rules в migration ПЕРЕД выкаткой.
4. Запустить migration.
5. После — `SELECT format, COUNT(*) FROM skus GROUP BY format` → должно быть ровно 6 значений + NULL.

Этот pre-flight check обязателен; внести в `docs/DEPLOYMENT.md` или CHANGELOG.

---

## §6. Backend изменения

### §6.1 Файлы

| Файл | Тип | Изменение |
|---|---|---|
| `backend/alembic/versions/XXXX_pack_format_enum.py` | NEW | Migration: backfill + CHECK constraint |
| `backend/app/models/entities.py` | EDIT | Добавить inline-комментарий про CHECK (модельно `format: Mapped[str \| None]` не меняем) |
| `backend/app/schemas/sku.py` | EDIT | Поменять `format: str \| None` → `format: PackFormat \| None`; убрать `max_length=100` |
| `backend/app/schemas/sku.py` | EDIT | Добавить `PackFormat = Literal[...]` type alias на верх файла |

Backend сервис `sku_service.update_sku` — без изменений (Pydantic schema validates на вход). Если фронт пошлёт невалидное значение → 422 от FastAPI.

### §6.2 Migration script: точный sketch

```python
"""C #19 — pack format enum

Revision ID: <auto-generated>
Revises: <head>
"""
from alembic import op
import sqlalchemy as sa


revision = "..."
down_revision = "<head>"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Step 1: Backfill via fuzzy mapping (case-insensitive substring match).
    mapping = [
        ("ПЭТ", ["пэт", "pet", "p.e.t"]),
        ("Стекло", ["стекл", "glass"]),
        ("Банка", ["банк", "can", "tin"]),
        ("Сашет", ["саше", "sachet"]),
        ("Стик", ["стик", "stick"]),
        ("Пауч", ["пауч", "pouch"]),
    ]
    for target, patterns in mapping:
        like_clauses = " OR ".join([f"LOWER(format) LIKE '%{p}%'" for p in patterns])
        conn.execute(sa.text(
            f"UPDATE skus SET format = :tgt WHERE ({like_clauses})",
        ), {"tgt": target})

    # Step 2: Log + null out non-matching.
    valid = ("ПЭТ", "Стекло", "Банка", "Сашет", "Стик", "Пауч")
    in_list = ",".join([f"'{v}'" for v in valid])
    # Log to alembic output для post-mortem
    rows = conn.execute(sa.text(
        f"SELECT format, COUNT(*) FROM skus "
        f"WHERE format IS NOT NULL AND format NOT IN ({in_list}) "
        f"GROUP BY format"
    )).fetchall()
    if rows:
        print(f"[C #19] Setting to NULL non-mappable formats:")
        for fmt, cnt in rows:
            print(f"  '{fmt}': {cnt} rows")
    conn.execute(sa.text(
        f"UPDATE skus SET format = NULL "
        f"WHERE format IS NOT NULL AND format NOT IN ({in_list})"
    ))

    # Step 3: Add CHECK constraint.
    op.create_check_constraint(
        "ck_skus_format",
        "skus",
        f"format IS NULL OR format IN ({in_list})",
    )


def downgrade():
    op.drop_constraint("ck_skus_format", "skus", type_="check")
```

(Использование f-string + LIKE — не SQL-injection risk: значения literal в коде; pattern'ы тоже literal. Но если уже-параноидально — можно вынести в `text(...).bindparams(...)`. Не обязательно.)

### §6.3 Тесты

| Тест | Где | Что проверяет |
|---|---|---|
| Pydantic validation: ПЭТ → ok | `tests/api/test_skus_api.py` | POST /api/skus с format="ПЭТ" → 201 |
| Pydantic validation: free text → 422 | `tests/api/test_skus_api.py` | POST с format="random" → 422 + сообщение про Literal |
| Pydantic validation: NULL → ok | `tests/api/test_skus_api.py` | POST без format / format=null → 201 |
| DB CHECK: bypass Pydantic | `tests/db/test_sku_constraints.py` (NEW или к существующему) | Direct INSERT с format='random' через session → IntegrityError |
| Migration backfill: fuzzy mapping | Manual (run migration on staging copy of prod) | dev DB → запустить, проверить распределение |

Backend test suite сейчас 508 passed. Добавим 2-3 теста на API + 1 на DB constraint.

---

## §7. Frontend изменения

### §7.1 Файлы

| Файл | Тип | Изменение |
|---|---|---|
| `frontend/lib/pack-format.ts` | NEW | `PACK_FORMAT_OPTIONS` const array (Single Source of Truth для UI) |
| `frontend/types/api.ts` | EDIT | Тип `PackFormat = Literal union`; `SKU.format: PackFormat \| null` |
| `frontend/components/projects/add-sku-dialog.tsx` | EDIT | Добавить `<Select>` для format поля, state, передачу в POST body |
| `frontend/components/projects/sku-panel.tsx` | NO CHANGE | Display строка `p.sku.format ?? "—"` работает с enum как с любой строкой |
| `frontend/components/projects/fine-tuning-copacking-section.tsx` | NO CHANGE | Display `sku.format ? ` · ${sku.format}` : ""` тоже работает как есть |

### §7.2 UI в add-sku-dialog

Currently (без format input):
```
[Brand] [Name]
[Volume L] [Вложение в кейс (package_type)]
```

After:
```
[Brand] [Name]
[Volume L] [Тип упаковки (Select)]
[Вложение в кейс (package_type)]
```

Точное расположение — на одном grid-row с volume_l (логически связано — оба про физическую упаковку), package_type («Вложение в кейс») спускается на новую строку.

### §7.3 Select component

Используем `Select` из `frontend/components/ui/select.tsx` (обёртка над `@base-ui/react`). Прецедент API уже есть в этом же файле на строках 170-188 (SKU выбор из каталога). Следуем тому же стилю: `items` prop + `SelectContent`/`SelectItem` children.

```tsx
<div className="space-y-2">
  <Label htmlFor="format">Тип упаковки</Label>
  <Select
    value={format ?? ""}
    onValueChange={(v) => setFormat(!v ? null : (v as PackFormat))}
    disabled={submitting}
    items={Object.fromEntries(
      PACK_FORMAT_OPTIONS.map((opt) => [opt, opt]),
    )}
  >
    <SelectTrigger id="format">
      <SelectValue placeholder="Не указано" />
    </SelectTrigger>
    <SelectContent>
      {PACK_FORMAT_OPTIONS.map((opt) => (
        <SelectItem key={opt} value={opt}>{opt}</SelectItem>
      ))}
    </SelectContent>
  </Select>
</div>
```

«Не указано» = пустое значение Select (placeholder показывает текст когда не выбрано). Сброс на null — через UI-кнопку «Очистить» рядом с Select, либо просто переключение проекта.

**Альтернатива** для UX: добавить «— Не указано —» как первый SelectItem с value=`""`. Менее идиоматично, но даёт явный «выбрать пусто» без отдельной кнопки. Решение оставляем плану.

---

## §8. Тестирование

### §8.1 Unit / integration

- Backend pytest добавит 3-4 теста (см. §6.3).
- Frontend без unit runner — `npx tsc --noEmit` + manual smoke.

### §8.2 Manual smoke

1. Создать SKU через add-sku-dialog: выбрать «ПЭТ» → POST → SKU создан.
2. Создать SKU без format → POST → SKU создан с format=null.
3. SKU отображается в sku-panel с типом упаковки в строке после volume_l.
4. PDF/PPT экспорт — `format` колонка показывает «ПЭТ» (а не пустоту/null).
5. AI комментарий получает format в context.

### §8.3 Migration smoke

- Локально на dev БД: `alembic upgrade head` → проверить, что 162 строки с «Пэт» → стало «ПЭТ»; 1 строка с «0.5L PET» → стало «ПЭТ» (через "pet" pattern); 0 строк обнулилось.
- `alembic downgrade -1` → CHECK уходит, данные не возвращаются (ожидаемо).

---

## §9. Edge cases

| Случай | Поведение |
|---|---|
| Backend получает legacy format='Пэт' через миграцию | UPDATE в migration переводит в 'ПЭТ'; CHECK затем validates ok |
| Pre-existing «Glass»/«Pouch» (EN) | Mapping переводит → «Стекло»/«Пауч» |
| Полностью неузнаваемое значение типа «mixed-pack» | Обнуляется в NULL; лог печатается в alembic output |
| User вводит через legacy API (без enum) | FastAPI Pydantic возвращает 422 (Literal validation) |
| Direct SQL bypass Pydantic | DB CHECK constraint бросает IntegrityError на UPDATE/INSERT |
| Frontend получает SKU.format = «Сашет» с prod (где migration уже была) | TypeScript тип = PackFormat, отображается «Сашет» в UI normaly |
| Существующий SKU без format (NULL) | Все display'ы показывают «—» или пустоту, как и раньше |

---

## §10. Non-goals / Future

- **OBPPC pack_format** enum — отдельная задача если потребуется.
- **`package_type` (вложение в кейс)** — переименовать поле / валидировать как int — отдельная задача в Phase D-валидации.
- **Material → sub-material** (тонкий ПЭТ / преформный / re-PET и т.д.) — overengineering.
- **i18n** перевод enum значений — Russian-only проект.

---

## §11. File map (для writing-plans)

| Файл | Тип | Кратко |
|---|---|---|
| `backend/alembic/versions/<id>_c19_pack_format_enum.py` | NEW | Migration: backfill + CHECK |
| `backend/app/schemas/sku.py` | EDIT | `PackFormat` Literal + use в `SKUBase`/`SKUUpdate` |
| `backend/tests/api/test_skus_api.py` | EDIT | 3 теста: valid enum → 201, invalid → 422, NULL → 201 |
| `backend/tests/db/test_sku_constraints.py` | NEW (или edit existing) | DB CHECK bypass test |
| `frontend/lib/pack-format.ts` | NEW | `PACK_FORMAT_OPTIONS` array |
| `frontend/types/api.ts` | EDIT | `PackFormat` type + `SKU.format: PackFormat \| null` |
| `frontend/components/projects/add-sku-dialog.tsx` | EDIT | Add `<Select>` для format |
| `docs/CLIENT_FEEDBACK_v2_STATUS.md` | EDIT | Строка про #19 ❌ → ✅ |
| `CHANGELOG.md` | EDIT | Phase C ### Added — запись C #19 |

---

## §12. Branch / commit hygiene

- **Branch**: `feat/c19-pack-format-enum` (уже создана, spec этим коммитом).
- **Коммиты ожидаемо ~5-6**:
  1. `docs(c19): spec — pack format enum`
  2. `docs(c19): plan — pack format enum`
  3. `feat(c19): migration + Pydantic Literal для SKU.format`
  4. `feat(c19): frontend Select для типа упаковки в add-sku-dialog`
  5. `test(c19): API + DB constraint coverage`
  6. `docs(c19): close MEMO 1.3 — pack format enum (STATUS + CHANGELOG)`
- **Merge**: fast-forward на main (как C #13, C #22).
