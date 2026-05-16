# C #19 — Pack format enum (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Преобразовать существующее свободное текстовое поле `SKU.format` (String(100)) в строгий enum из 6 значений + NULL (ПЭТ/Стекло/Банка/Сашет/Стик/Пауч) через Alembic migration (backfill + CHECK constraint), Pydantic Literal type и frontend Select.

**Architecture:** PATTERN-08 varchar+CHECK (прецедент `OBPPCEntry.price_tier`). Существующие данные мигрируются fuzzy mapping'ом (Пэт/PET → ПЭТ, Glass → Стекло, etc), несовпадающие → NULL. Расчёты не тронуты — `format` только для display/AI. UI Select добавляется в `add-sku-dialog.tsx`.

**Tech Stack:** Backend: Python 3.12, FastAPI, Pydantic v2 (`Literal` type), SQLAlchemy 2.0, Alembic, pytest. Frontend: Next.js 14, TypeScript, `@base-ui/react` Select.

**Spec reference:** `docs/superpowers/specs/2026-05-16-c19-pack-format-enum-design.md` (закоммичена `0c1da7b`).

**Branch:** `feat/c19-pack-format-enum` (уже создана от main; spec там же).

---

## Контекст для исполнителя

### Текущий alembic head
`d4c87e14d126` (C #14 fine_tuning_per_period_overrides). Новая миграция должна `down_revision = "d4c87e14d126"`.

### Точные file paths
- `backend/app/models/entities.py:101` — `SKU.format` declaration
- `backend/app/schemas/sku.py` — Pydantic schemas (4 классa: `SKUBase`/`SKUCreate`/`SKUUpdate`/`SKURead`)
- `backend/tests/api/test_skus.py` — существующие SKU API тесты (16+ тестов, fixture `SKU_BODY` на строке 26-33 использует `"format": "PET"`)
- `backend/migrations/versions/` — здесь живут migration файлы
- `frontend/types/api.ts:222` — TS interface SKU
- `frontend/components/projects/add-sku-dialog.tsx` — диалог создания SKU (нет input для format сейчас; уже использует Select из `@/components/ui/select` для SKU-выбора — паттерн на строках 170-188)
- `frontend/components/projects/sku-panel.tsx:141` — display SKU.format
- `frontend/lib/` — здесь живут lib-helpers (новый файл `pack-format.ts` будет здесь)
- `CHANGELOG.md` — секция `## Phase C` → `### Added`
- `docs/CLIENT_FEEDBACK_v2_STATUS.md` — Блок 3 (статус #19 строки)

### Тестовый стек (frontend без unit-runner)
- Backend pytest:
  ```bash
  docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration
  ```
  Ожидаемо до старта: **508 passed** (после Tasks 1-2 ожидается **+3-4 passed** для новых тестов; после Tasks 3 — может вырасти если добавлены constraint tests).
  
- Backend pytest конкретный файл:
  ```bash
  docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/api/test_skus.py -v
  ```

- Frontend type-check:
  ```bash
  docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
  ```

- Alembic команды (изнутри backend контейнера):
  ```bash
  docker compose -f infra/docker-compose.dev.yml exec -T backend alembic upgrade head
  docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
  docker compose -f infra/docker-compose.dev.yml exec -T backend alembic downgrade -1
  ```

### Frontend structural restart (после edit `add-sku-dialog.tsx`)
По правилу `feedback-frontend-structural-restart` (Windows+Docker HMR баг):
```bash
docker compose -f infra/docker-compose.dev.yml stop frontend
docker compose -f infra/docker-compose.dev.yml run --rm frontend sh -c "rm -rf .next/* .next/.[!.]* 2>/dev/null"
docker compose -f infra/docker-compose.dev.yml up -d frontend
```

---

## Task 1: Pydantic Literal enum + обновление test fixture + validation тесты

**Files:**
- Modify: `backend/app/schemas/sku.py` (4 классa: `SKUBase`/`SKUCreate`/`SKUUpdate`/`SKURead`)
- Modify: `backend/tests/api/test_skus.py` (fixture + new tests)

**Контекст:** Существующий fixture `SKU_BODY` использует `"format": "PET"` — после введения `Literal[6 значений]` Pydantic будет отвергать "PET" (422). Нужно обновить fixture до `"ПЭТ"` СНАЧАЛА, иначе после schema change 16+ тестов сразу красные. После — добавить 3 новых теста на enum валидацию.

- [ ] **Step 1: Обновить SKU_BODY fixture (зелёный сейчас, остаётся зелёным после)**

В `backend/tests/api/test_skus.py:26-33` заменить:
```python
SKU_BODY = {
    "brand": "Gorji",
    "name": "Gorji Citrus 0.5L PET",
    "format": "PET",
    "volume_l": "0.5",
    "package_type": "Bottle",
    "segment": "CSD",
}
```

на:
```python
SKU_BODY = {
    "brand": "Gorji",
    "name": "Gorji Citrus 0.5L PET",
    "format": "ПЭТ",
    "volume_l": "0.5",
    "package_type": "Bottle",
    "segment": "CSD",
}
```

(Меняется только значение `format` — `"PET"` → `"ПЭТ"`. Всё остальное — без изменений. `package_type: "Bottle"` остаётся свободным String, это другое поле — out of scope C #19.)

- [ ] **Step 2: Прогнать существующие тесты — должны быть зелёные**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/api/test_skus.py -v 2>&1 | tail -10
```

Expected: все существующие тесты passed (16+). До schema change "ПЭТ" — просто другая строка для String(100), Pydantic пропускает.

Если падает — НЕ продолжать. Скорее всего другое место в test_skus.py содержит hardcoded "PET". Найти grep'ом:
```bash
grep -nE "PET\"|format.*PET" backend/tests/api/test_skus.py
```

- [ ] **Step 3: Добавить failing тест на enum валидацию**

В конец `backend/tests/api/test_skus.py` (после последнего теста) добавить:
```python
# ============================================================
# C #19: format enum validation (Literal type)
# ============================================================


async def test_create_sku_invalid_format_returns_422(
    auth_client: AsyncClient,
) -> None:
    """C #19: format='random' → 422 (Pydantic Literal rejects)."""
    body = {**SKU_BODY, "format": "random-package-type"}
    resp = await auth_client.post("/api/skus", json=body)
    assert resp.status_code == 422
    detail = resp.json().get("detail", [])
    assert any("format" in str(err).lower() for err in detail), (
        f"Expected 'format' in 422 detail; got: {detail}"
    )


async def test_create_sku_null_format_ok(
    auth_client: AsyncClient,
) -> None:
    """C #19: format=null → 201."""
    body = {**SKU_BODY, "format": None}
    resp = await auth_client.post("/api/skus", json=body)
    assert resp.status_code == 201
    data = resp.json()
    assert data["format"] is None


async def test_create_sku_all_enum_values_ok(
    auth_client: AsyncClient,
) -> None:
    """C #19: все 6 enum значений принимаются."""
    for fmt in ["ПЭТ", "Стекло", "Банка", "Сашет", "Стик", "Пауч"]:
        body = {**SKU_BODY, "format": fmt, "name": f"SKU {fmt}"}
        resp = await auth_client.post("/api/skus", json=body)
        assert resp.status_code == 201, (
            f"Format '{fmt}' rejected: {resp.json()}"
        )
        assert resp.json()["format"] == fmt
```

- [ ] **Step 4: Запустить новые тесты — должны быть КРАСНЫЕ (Literal ещё не введён)**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/api/test_skus.py::test_create_sku_invalid_format_returns_422 -v 2>&1 | tail -10
```

Expected: **FAIL** — без Literal, "random-package-type" принимается → 201, тест ожидает 422.

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/api/test_skus.py::test_create_sku_all_enum_values_ok -v 2>&1 | tail -10
```

Expected: PASS (без Literal Pydantic принимает любую строку).

`test_create_sku_null_format_ok` тоже PASS — null уже валиден в текущей схеме.

- [ ] **Step 5: Реализация — Pydantic Literal**

Заменить `backend/app/schemas/sku.py` целиком на:
```python
"""Pydantic-схемы справочника SKU (не привязан к проекту)."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# C #19: enum типа упаковки. См. spec docs/superpowers/specs/
# 2026-05-16-c19-pack-format-enum-design.md §4.1.
PackFormat = Literal[
    "ПЭТ",
    "Стекло",
    "Банка",
    "Сашет",
    "Стик",
    "Пауч",
]


class SKUBase(BaseModel):
    brand: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=500)
    format: PackFormat | None = Field(default=None)
    volume_l: Decimal | None = Field(default=None, ge=0)
    package_type: str | None = Field(default=None, max_length=100)
    segment: str | None = Field(default=None, max_length=100)


class SKUCreate(SKUBase):
    """Тело POST /api/skus."""


class SKUUpdate(BaseModel):
    """Тело PATCH /api/skus/{id}. Все поля Optional."""

    brand: str | None = Field(default=None, min_length=1, max_length=255)
    name: str | None = Field(default=None, min_length=1, max_length=500)
    format: PackFormat | None = Field(default=None)
    volume_l: Decimal | None = Field(default=None, ge=0)
    package_type: str | None = Field(default=None, max_length=100)
    segment: str | None = Field(default=None, max_length=100)


class SKURead(SKUBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
```

Изменения:
- Импорт `Literal` из `typing`
- Новый type alias `PackFormat = Literal[...]` с 6 значениями
- `SKUBase.format`: `str | None, max_length=100` → `PackFormat | None`
- `SKUUpdate.format`: тоже самое
- `SKURead` наследует от `SKUBase`, не меняется явно

- [ ] **Step 6: Запустить все sku тесты — должны быть зелёные**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/api/test_skus.py -v 2>&1 | tail -15
```

Expected: все тесты passed (existing 16+ + 3 new = 19+).

- [ ] **Step 7: Прогнать полный backend test suite (страховка — не сломали ничего где-то ещё)**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```

Expected: `511 passed` (было 508, +3 новых тестов).

Если упало — скорее всего где-то ещё в тестах используется `format="PET"` или другое non-enum значение. Найти grep'ом по всему `tests/`:
```bash
grep -rnE "format.*PET\"|format.*Bottle\"|format.*Glass\"" backend/tests/ 2>&1 | head -10
```

И исправить найденные на `"ПЭТ"`.

- [ ] **Step 8: Закоммитить**

```bash
git add backend/app/schemas/sku.py backend/tests/api/test_skus.py
git commit -m "$(cat <<'EOF'
feat(c19): Pydantic Literal enum для SKU.format + tests

C #19: SKU.format становится Literal["ПЭТ", "Стекло", "Банка", "Сашет",
"Стик", "Пауч"] | None. Pydantic отвергает любое другое значение с 422.

Изменения:
- backend/app/schemas/sku.py: новый PackFormat Literal type alias,
  использован в SKUBase.format и SKUUpdate.format (max_length убран —
  Literal уже validates).
- backend/tests/api/test_skus.py: SKU_BODY fixture "PET" → "ПЭТ"
  (Literal требует exact match). Добавлены 3 теста:
  * invalid format → 422 + 'format' in detail
  * null format → 201 + null in response
  * все 6 enum значений → 201

CHECK constraint для DB-уровня — отдельной задачей (Task 2 migration).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Alembic migration — backfill + CHECK constraint

**Files:**
- Create: `backend/migrations/versions/<auto>_c19_pack_format_enum.py`
- Modify: `backend/tests/api/test_skus.py` (опциональный DB constraint test)

**Контекст:** После Task 1 Pydantic блокирует на API-level, но БД всё ещё содержит legacy данные ("Пэт", "0.5L PET") и принимает любой String через прямой SQL bypass. Migration делает 2 шага: (1) fuzzy backfill existing → enum values, NULL для нераспознанных; (2) ADD CHECK constraint.

- [ ] **Step 1: Создать migration файл**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic revision -m "c19 pack format enum"
```

Это сгенерирует файл `backend/migrations/versions/<id>_c19_pack_format_enum.py` (id — auto-gen 12-hex). Найти его:

```bash
ls -t backend/migrations/versions/ | head -3
```

Имя файла будет вида `XXXXXXXXXXXX_c19_pack_format_enum.py`.

- [ ] **Step 2: Заменить содержимое migration файла**

Открыть только что созданный файл. Заменить полностью на:

```python
"""c19 pack format enum

Revision ID: <auto-id>
Revises: d4c87e14d126
Create Date: 2026-05-16 ...

C #19: SKU.format → enum (ПЭТ/Стекло/Банка/Сашет/Стик/Пауч + NULL).

Шаг 1: backfill existing значений через fuzzy mapping
(case-insensitive substring match). Несовпадающие → NULL с логом.
Шаг 2: ADD CHECK constraint.

Spec: docs/superpowers/specs/2026-05-16-c19-pack-format-enum-design.md
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "<auto-id>"  # ← НЕ ТРОГАТЬ, alembic сгенерил
down_revision: Union[str, None] = "d4c87e14d126"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# C #19 enum values (Cyrillic). Должны совпадать с PackFormat Literal
# в backend/app/schemas/sku.py.
VALID_FORMATS = ("ПЭТ", "Стекло", "Банка", "Сашет", "Стик", "Пауч")

# Fuzzy mapping: case-insensitive substring patterns → target enum value.
# Первый match wins (порядок важен; более специфичные паттерны раньше).
MAPPING_RULES = [
    ("ПЭТ", ["пэт", "pet", "p.e.t"]),
    ("Стекло", ["стекл", "glass"]),
    ("Банка", ["банк", "can", "tin"]),
    ("Сашет", ["саше", "sachet"]),
    ("Стик", ["стик", "stick"]),
    ("Пауч", ["пауч", "pouch"]),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Step 1: backfill fuzzy matches.
    for target, patterns in MAPPING_RULES:
        like_clauses = " OR ".join(
            [f"LOWER(format) LIKE '%{p}%'" for p in patterns]
        )
        conn.execute(sa.text(
            f"UPDATE skus SET format = :tgt "
            f"WHERE format IS NOT NULL AND ({like_clauses})"
        ), {"tgt": target})

    # Step 2: log + null out non-matching.
    in_list = ", ".join([f"'{v}'" for v in VALID_FORMATS])
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

    # Step 3: ADD CHECK constraint.
    op.create_check_constraint(
        "ck_skus_format",
        "skus",
        f"format IS NULL OR format IN ({in_list})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_skus_format", "skus", type_="check")
```

**Важно:** `revision` строка (5-я строка с `revision: str = "<auto-id>"`) — НЕ менять, оставить то, что alembic сгенерил. `down_revision` должен быть `"d4c87e14d126"` (текущий head).

- [ ] **Step 3: Применить migration к dev БД**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic upgrade head 2>&1 | tail -10
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade d4c87e14d126 -> <new-id>, c19 pack format enum
[C #19] Setting to NULL non-mappable formats:
  '...': N rows  ← если есть non-mappable
```

(Если в dev БД был только "Пэт" и "0.5L PET" — оба mappable, лог "Setting to NULL" не появится. Все 163 строки получат "ПЭТ".)

- [ ] **Step 4: Проверить state БД после migration**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T postgres psql -U dbuser -d dbpassport -c "SELECT format, COUNT(*) FROM skus GROUP BY format ORDER BY 2 DESC;"
```

Expected: только значения из enum + NULL. Пример:
```
 format | count
--------+-------
 ПЭТ    |   163
 NULL   |   ...
```

- [ ] **Step 5: Проверить CHECK constraint работает**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T postgres psql -U dbuser -d dbpassport -c "UPDATE skus SET format = 'invalid' WHERE id = (SELECT id FROM skus LIMIT 1);"
```

Expected: `ERROR: new row for relation "skus" violates check constraint "ck_skus_format"`.

(Никаких прав мы не теряем — UPDATE rolled back автоматически на error.)

- [ ] **Step 6: Прогнать backend test suite после migration**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```

Expected: **511 passed** (то же количество, что и после Task 1; migration не ломает тесты т.к. test DB пересоздаётся с включением миграции).

- [ ] **Step 7: Опционально — добавить DB constraint integration test**

В `backend/tests/api/test_skus.py` после Task 1 тестов добавить:
```python
async def test_db_check_constraint_blocks_invalid_format(
    auth_client: AsyncClient,
) -> None:
    """C #19: DB CHECK constraint блокирует invalid value даже при bypass Pydantic.

    Симулируем bypass: создаём SKU через API (валидный ПЭТ), затем через
    raw SQL пытаемся UPDATE с invalid — должен бросить IntegrityError.
    """
    from sqlalchemy import text

    from app.db import session_factory  # type: ignore

    sku_id = await _create_sku(auth_client)

    async with session_factory() as session:
        with pytest.raises(Exception) as exc_info:  # IntegrityError or DBAPIError
            await session.execute(
                text("UPDATE skus SET format = 'invalid' WHERE id = :id"),
                {"id": sku_id},
            )
            await session.commit()
        # Подтверждаем что это именно CHECK constraint
        assert "ck_skus_format" in str(exc_info.value).lower() or \
               "check constraint" in str(exc_info.value).lower()
```

**Это опционально** — если возникают трудности с import path (`app.db.session_factory`) или fixture для raw session, пропустить и положиться на тест из Step 5 (manual). Если файл не запускается без рефакторинга — отказаться, основное покрытие даёт Pydantic тесты из Task 1.

Если добавляешь — прогнать:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/api/test_skus.py::test_db_check_constraint_blocks_invalid_format -v
```

Expected: PASS.

- [ ] **Step 8: Закоммитить migration (+ опциональный тест, если добавил)**

```bash
git add backend/migrations/versions/*_c19_pack_format_enum.py
# Если добавил DB constraint test:
git add backend/tests/api/test_skus.py
git commit -m "$(cat <<'EOF'
feat(c19): migration — pack format enum (backfill + CHECK)

Two-step migration:
1. Fuzzy backfill existing значений format → enum (Пэт/PET → ПЭТ, etc).
   Несовпадающие → NULL с логом в alembic output.
2. ADD CHECK constraint ck_skus_format — гарантирует, что format
   принимает только 6 enum значений или NULL даже при bypass Pydantic.

down_revision = d4c87e14d126 (C #14 fine_tuning_per_period).
downgrade — только DROP CONSTRAINT, данные не возвращаются.

Pre-flight для прода: SELECT distinct(format) перед `alembic upgrade head`,
дополнить MAPPING_RULES если найдены незнакомые значения.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Frontend — типы + Select в add-sku-dialog

**Files:**
- Create: `frontend/lib/pack-format.ts`
- Modify: `frontend/types/api.ts:222` (interface SKU.format)
- Modify: `frontend/components/projects/add-sku-dialog.tsx`

**Контекст:** Frontend не имеет unit-test runner — verification = `tsc --noEmit` + manual browser smoke. Структурный рестарт frontend после правки add-sku-dialog обязателен (Windows+Docker HMR).

- [ ] **Step 1: Создать `frontend/lib/pack-format.ts`**

```ts
/**
 * C #19: Тип упаковки SKU — справочник enum.
 *
 * Должен совпадать с PackFormat Literal в backend/app/schemas/sku.py
 * и с CHECK constraint ck_skus_format в БД.
 *
 * См. spec docs/superpowers/specs/2026-05-16-c19-pack-format-enum-design.md §4.
 */

export type PackFormat =
  | "ПЭТ"
  | "Стекло"
  | "Банка"
  | "Сашет"
  | "Стик"
  | "Пауч";

export const PACK_FORMAT_OPTIONS: readonly PackFormat[] = [
  "ПЭТ",
  "Стекло",
  "Банка",
  "Сашет",
  "Стик",
  "Пауч",
] as const;
```

- [ ] **Step 2: Обновить `frontend/types/api.ts` SKU interface**

Найти строку (~222):
```ts
  format: string | null;
```

в interface SKU. Заменить на:
```ts
  format: PackFormat | null;
```

И добавить import на верх файла (в существующий блок импортов, по алфавиту относительно других `@/lib/*`):
```ts
import type { PackFormat } from "@/lib/pack-format";
```

**Важно:** если в `types/api.ts` ещё не было импортов из `@/lib/*` — добавить новый import-блок. Стиль file подсказывает; следуй существующему форматированию.

- [ ] **Step 3: tsc — verify types compile**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit 2>&1 | tail -10
```

Expected: 0 errors.

Если ошибка типа `Type 'string' is not assignable to type 'PackFormat | null'` — где-то в codebase есть assignment SKU.format = "random_string". Найти и зафиксить (вероятно тест или mock-данные).

- [ ] **Step 4: Изменить `frontend/components/projects/add-sku-dialog.tsx`**

Добавить импорты в начало файла (в существующий import блок, после `Select`-импортов):
```tsx
import { PACK_FORMAT_OPTIONS, type PackFormat } from "@/lib/pack-format";
```

Найти state-объявления (около `const [packageType, setPackageType]`). Добавить рядом:
```tsx
  const [format, setFormat] = useState<PackFormat | "">("");
```

(Тип `PackFormat | ""` потому что Select API проекта работает со строками и пустая строка = «не выбрано».)

Найти где формируется body для POST (около `package_type: packageType || null`):
```tsx
          package_type: packageType || null,
```

Добавить рядом (или перед — по логическому порядку полей):
```tsx
          format: format === "" ? null : format,
```

- [ ] **Step 5: Добавить Select UI в форму**

Найти секцию с `volume_l` input (около `<Label htmlFor="volume_l">`). После закрывающего `</div>` этой пары (volume_l + package_type находятся в одном grid-row), внести изменение.

Внимательно прочитать секцию строк примерно 225-252 (volume_l + package_type), чтобы понять текущую структуру. Затем заменить пару `[volume_l] [package_type]` на тройку `[volume_l] [format Select]` на одной строке, и `[package_type]` на отдельной строке ниже.

Точнее: найти существующий блок (примерно строки 225-252):
```tsx
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="volume_l">Объём (л)</Label>
                  <Input
                    id="volume_l"
                    type="number"
                    step="0.01"
                    min="0"
                    value={volumeL}
                    onChange={(e) => setVolumeL(e.target.value)}
                    disabled={submitting}
                    placeholder="0.5"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="package_type">Вложение в кейс</Label>
                <Input
                  id="package_type"
                  value={packageType}
                  onChange={(e) => setPackageType(e.target.value)}
                  disabled={submitting}
                  placeholder="6 / 12 / 24 шт"
                />
              </div>
```

Заменить на:
```tsx
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="volume_l">Объём (л)</Label>
                  <Input
                    id="volume_l"
                    type="number"
                    step="0.01"
                    min="0"
                    value={volumeL}
                    onChange={(e) => setVolumeL(e.target.value)}
                    disabled={submitting}
                    placeholder="0.5"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="format">Тип упаковки</Label>
                  <Select
                    value={format}
                    onValueChange={(v) =>
                      setFormat((v ?? "") as PackFormat | "")
                    }
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
                        <SelectItem key={opt} value={opt}>
                          {opt}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="package_type">Вложение в кейс</Label>
                <Input
                  id="package_type"
                  value={packageType}
                  onChange={(e) => setPackageType(e.target.value)}
                  disabled={submitting}
                  placeholder="6 / 12 / 24 шт"
                />
              </div>
```

Изменения:
- Внутри `grid-cols-2` теперь 2 элемента: `[volume_l] [format]`.
- `[package_type]` переехал отдельно ниже.

`Select`, `SelectTrigger`, `SelectValue`, `SelectContent`, `SelectItem` уже импортированы в файле (используются для SKU-каталога). Не нужно добавлять imports.

- [ ] **Step 6: tsc — verify implementation compiles**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit 2>&1 | tail -5
```

Expected: 0 errors.

- [ ] **Step 7: Frontend structural restart**

```bash
docker compose -f infra/docker-compose.dev.yml stop frontend
docker compose -f infra/docker-compose.dev.yml run --rm frontend sh -c "rm -rf .next/* .next/.[!.]* 2>/dev/null"
docker compose -f infra/docker-compose.dev.yml up -d frontend
```

Wait ~10 sec. Verify:
```bash
docker compose -f infra/docker-compose.dev.yml logs --tail=20 frontend 2>&1 | tail -15
```

Expect `✓ Ready in <time>` and no compile errors.

- [ ] **Step 8: Manual smoke в браузере**

1. Открыть `http://localhost:3000/projects/<id>` → таб «SKU и BOM» → нажать «Добавить SKU из каталога» или «Создать новый».
2. Если открылся диалог «Создать новый SKU» (не «из каталога») — увидеть поле «Тип упаковки» рядом с «Объём (л)».
3. Кликнуть Select — увидеть 6 опций: ПЭТ / Стекло / Банка / Сашет / Стик / Пауч.
4. Выбрать «ПЭТ» → заполнить остальные поля → нажать «Добавить» → SKU создаётся с format="ПЭТ".
5. Создать ещё один SKU БЕЗ выбора Type → format=null в БД. Проверить через `psql`:
   ```bash
   docker compose -f infra/docker-compose.dev.yml exec -T postgres psql -U dbuser -d dbpassport -c "SELECT id, name, format FROM skus ORDER BY id DESC LIMIT 3;"
   ```
6. В `sku-panel` отображается тип упаковки рядом с volume_l (как раньше работало с free-text).

Если smoke ок — Step 8 готов.

- [ ] **Step 9: Закоммитить**

```bash
git add frontend/lib/pack-format.ts frontend/types/api.ts frontend/components/projects/add-sku-dialog.tsx
git commit -m "$(cat <<'EOF'
feat(c19): frontend Select для типа упаковки + типизированный PackFormat

- frontend/lib/pack-format.ts (NEW): PackFormat union type + PACK_FORMAT_OPTIONS
  const array. Источник истины для UI.
- frontend/types/api.ts: SKU.format string | null → PackFormat | null.
- frontend/components/projects/add-sku-dialog.tsx: добавлен Select
  «Тип упаковки» в grid рядом с volume_l. «Вложение в кейс»
  (package_type, не enum) переехал в отдельную строку ниже.

Поля выбираются опционально — пустой Select оставляет format=null.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: STATUS + CHANGELOG

**Files:**
- Modify: `docs/CLIENT_FEEDBACK_v2_STATUS.md` (строка про #19 в Блоке 3)
- Modify: `CHANGELOG.md` (Phase C → Added)

- [ ] **Step 1: Найти строку статуса #19**

```bash
grep -nE "Тип упаковки|#19|enum.*ПЭТ" docs/CLIENT_FEEDBACK_v2_STATUS.md | head -5
```

Это покажет точную строку. Она вероятно содержит `❌` или `❓` и текст вроде «Тип упаковки → справочник».

- [ ] **Step 2: Обновить статус**

Заменить найденную строку (`❌`/`❓` → `✅`) и поставить ссылку. Пример (адаптировать к фактическому тексту):
```
| Тип упаковки → справочник enum | ✅ | Закрыто C #19 (2026-05-16). SKU.format → Literal['ПЭТ', 'Стекло', 'Банка', 'Сашет', 'Стик', 'Пауч'] на уровне Pydantic, CHECK constraint ck_skus_format на уровне БД. Migration с fuzzy backfill existing значений. Frontend Select в add-sku-dialog. См. spec `docs/superpowers/specs/2026-05-16-c19-pack-format-enum-design.md`. |
```

- [ ] **Step 3: Обновить CHANGELOG.md**

Открыть `CHANGELOG.md`, найти `## Phase C` → `### Added`. После последней записи (вероятно C #22) добавить:

```markdown
- **C #19 Тип упаковки → enum (MEMO 1.3 / Блок 3, 2026-05-16).**
  Свободное поле `SKU.format` (String(100)) преобразовано в строгий
  enum из 6 значений + NULL: ПЭТ / Стекло / Банка / Сашет / Стик / Пауч.
  Реализовано через PATTERN-08 (varchar + CHECK constraint) — прецедент
  `OBPPCEntry.price_tier`. Pydantic Literal type на API уровне (422 на
  невалидные значения), CHECK на DB уровне (защита от SQL bypass).
  Migration с fuzzy backfill existing values (Пэт/PET → ПЭТ, Glass →
  Стекло, etc); несовпадающие → NULL с логом. Расчёты не тронуты —
  format только для display/AI. Frontend: Select в add-sku-dialog.
  - Spec: `docs/superpowers/specs/2026-05-16-c19-pack-format-enum-design.md`
  - Plan: `docs/superpowers/plans/2026-05-16-c19-pack-format-enum.md`
  - Verification: backend pytest 511 passed (+3 new); tsc 0 errors;
    manual smoke в add-sku-dialog ok.
```

- [ ] **Step 4: Закоммитить**

```bash
git add docs/CLIENT_FEEDBACK_v2_STATUS.md CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs(c19): close MEMO 1.3 — тип упаковки → enum (STATUS + CHANGELOG)

- docs/CLIENT_FEEDBACK_v2_STATUS.md: статус #19 ❌ → ✅
  со ссылкой на spec.
- CHANGELOG.md: запись C #19 в Phase C ### Added.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Финальная проверка + merge

**Files:** (verification + merge)

- [ ] **Step 1: Проверить ветку**

```bash
git status
git log --oneline main..HEAD
```

Expected (5 коммитов на ветке + spec-коммит):
```
<hash> docs(c19): close MEMO 1.3 — тип упаковки → enum (STATUS + CHANGELOG)
<hash> feat(c19): frontend Select для типа упаковки + типизированный PackFormat
<hash> feat(c19): migration — pack format enum (backfill + CHECK)
<hash> feat(c19): Pydantic Literal enum для SKU.format + tests
0c1da7b docs(c19): spec — pack format enum ...
```

`git status` clean.

- [ ] **Step 2: Финальный backend pytest**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```

Expected: `511 passed` (508 baseline + 3 новых C #19 теста).

- [ ] **Step 3: Финальный tsc**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

Expected: 0 errors (no output).

- [ ] **Step 4: Acceptance GORJI (страховка — расчёты не должны сдвинуться)**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/acceptance -m acceptance 2>&1 | tail -5
```

Expected: 6 passed, drift < 0.03%. (format не участвует в pipeline → числа не меняются.)

- [ ] **Step 5: Final manual smoke**

1. Создать SKU в новом проекте через add-sku-dialog → выбрать «ПЭТ» → SKU создан, в sku-panel отображается «ПЭТ» в строке.
2. Создать SKU без выбора format → NULL → в sku-panel «—» или пусто.
3. Открыть существующий проект → SKU отображаются с миграционными значениями («ПЭТ»).
4. Проверить PDF/PPT экспорт (если время) — format-колонка показывает enum-значения.

- [ ] **Step 6: Спросить пользователя о merge стратегии**

Подобно C #13 / C #22:
- **fast-forward** (`--ff-only`) — 5 коммитов в линейной истории main. Default.
- **--no-ff** — merge commit, сохраняет atomic-цепочку.
- **squash** — 1 коммит, теряем гранулярность.

Рекомендация: **fast-forward** (как C #13 / C #22).

**НЕ мержить без подтверждения пользователя.**

- [ ] **Step 7: После approval — merge**

```bash
git checkout main
git merge feat/c19-pack-format-enum --ff-only
git log --oneline -8
```

- [ ] **Step 8: Удалить feature-ветку**

```bash
git branch -d feat/c19-pack-format-enum
git branch
```

Expected: `* main`, без `feat/c19-*`.

- [ ] **Step 9: Краткий отчёт пользователю**

- C #19 закрыт; ветка смержена в main, удалена.
- Изменены 4 файла backend (schemas/sku.py, test_skus.py + migration NEW), 3 файла frontend (lib/pack-format.ts NEW, types/api.ts, add-sku-dialog.tsx), 2 docs (STATUS + CHANGELOG).
- Tests: 511 backend passed (+3 new), tsc 0 errors, acceptance GORJI drift <0.03%, manual smoke ok.
- Phase C: 4/18 ✅ (#14 + #13 + #22 + #19).
- **Pre-flight для прода**: перед `alembic upgrade head` на проде — проверить `SELECT distinct(format) FROM skus`, дополнить MAPPING_RULES если найдены незнакомые значения. См. spec §5.4.

---

## Self-review checklist

- ✅ **Spec coverage:**
  - §1 Цель → Tasks 1-3 реализуют (Pydantic + DB + frontend)
  - §2 Out of scope → план НЕ трогает package_type / OBPPCEntry.pack_format / 7-е значение / PostgreSQL ENUM type. ✓
  - §3 Текущее состояние → Tasks обращаются к точным указанным файлам/строкам. ✓
  - §4 Дизайн enum'а → Task 1 (Pydantic), Task 2 (CHECK), Task 3 (TS type). ✓
  - §5 Миграция → Task 2 целиком; §5.4 «Production rollout» упомянут в Task 5 Step 9 отчёт. ✓
  - §6 Backend изменения → Tasks 1, 2. ✓
  - §7 Frontend → Task 3. ✓
  - §8 Тестирование → Task 1 (Pydantic тесты), Task 2 Step 7 (опц. DB constraint), Task 3 Step 8 (manual smoke), Task 5 Step 4 (acceptance GORJI). ✓
  - §9 Edge cases → план не реализует тесты на каждый case explicitly, но Pydantic Literal + DB CHECK + fuzzy mapping покрывают их по дизайну. ✓
  - §10 Non-goals → плэн не реализует. ✓
  - §11 File map → совпадает с Tasks. ✓
  - §12 Branch/commits → 5 коммитов на ветке + spec, fast-forward merge. ✓

- ✅ **Placeholders:** Нет TBD / TODO / «implement later». Все code blocks конкретные. Единственный шаблон `<auto-id>` в migration — комментирован «НЕ ТРОГАТЬ, alembic сгенерил».

- ✅ **Type consistency:**
  - `PackFormat` Literal — 6 значений совпадают между Task 1 (Python Literal), Task 2 (VALID_FORMATS tuple в migration), Task 3 (TS PackFormat union + PACK_FORMAT_OPTIONS array). ✓
  - `ck_skus_format` constraint name — одинаков в migration upgrade/downgrade + в опциональном тесте Step 7. ✓
  - `MAPPING_RULES` в migration — 6 target значений совпадают с enum. ✓
  - `format` имя поля одно во всех слоях (model / schema / TS interface / migration / test). ✓

- ✅ **Scope:** Plan focused. Не лезет в OBPPCEntry.pack_format, не переименовывает package_type, не расширяет enum. ✓

- ✅ **Decomposition:** 5 атомарных task'ов. Tasks 1-2 backend (DB-зависимы — Task 2 после Task 1, но Task 1 может быть применён без Task 2). Task 3 frontend (можно параллельно с Task 2). Task 4 docs (после 1-3). Task 5 merge.
