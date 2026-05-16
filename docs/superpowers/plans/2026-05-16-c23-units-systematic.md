# C #23 — кг/л через слеш + единицы systematic (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. 3-task compact эпик.

**Goal:** Добавить `SKU.unit_of_measure` (Literal "л"/"кг" NOT NULL default "л"), миграция backfill, frontend helpers `formatVolume`/`formatPerUnit`/`formatPieces`, sweep по местам отображения volume + per-unit + штуки.

**Spec:** `docs/superpowers/specs/2026-05-16-c23-units-systematic-design.md`.
**Branch:** `feat/c23-units-systematic`.
**Baseline:** main `3bad0c9` (после C #27), 549 passed, alembic head `eb59341b9034`, tsc clean.

---

## Контекст

- `backend/app/models/entities.py:101-102` — SKU.format + volume_l (без unit_of_measure)
- `backend/app/schemas/sku.py` — SKUBase/Create/Update/Read
- `backend/scripts/seed_reference_data.py` — нет SKU seed (SKU создаются юзером)
- `frontend/lib/format.ts` — формат-хелперы (нет formatVolume/formatPerUnit с unit)
- `frontend/types/api.ts` — interface SKU
- `frontend/components/projects/add-sku-dialog.tsx` — форма создания/edit SKU
- `frontend/components/projects/sku-panel.tsx` — список SKU
- Места per-unit cost (нужен sweep): channels-panel, results-tab, value-chain, pricing displays

---

## Task 1: Backend schema + migration + tests

**Files:**
- Modify: `backend/app/models/entities.py` (SKU + SkuUnitOfMeasure Literal)
- Modify: `backend/app/schemas/sku.py` (3 классa + Literal)
- Create: `backend/migrations/versions/<rev>_c23_sku_unit_of_measure.py`
- Modify: `backend/tests/api/test_skus.py` (3-4 тестов)

### Шаги

- [ ] **Step 1: Создать миграцию через alembic revision**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic revision -m "c23_sku_unit_of_measure"
```
Получить generated revision id (например `abc123def456`).

- [ ] **Step 2: Написать тело миграции**

В `backend/migrations/versions/<rev>_c23_sku_unit_of_measure.py`:
```python
"""c23_sku_unit_of_measure

C #23: добавление SKU.unit_of_measure (Literal "л"/"кг", NOT NULL,
default "л"). Backfill existing SKU в "л" — текущее implicit поведение
(volume_l хранил литры).

Revision ID: <rev>
Revises: eb59341b9034
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "<rev>"  # alembic-сгенерированный
down_revision: Union[str, None] = "eb59341b9034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VALID_UNITS = ("л", "кг")


def upgrade() -> None:
    # 1. Add column nullable
    op.add_column(
        "skus",
        sa.Column("unit_of_measure", sa.String(2), nullable=True),
    )
    # 2. Backfill existing → "л" (текущее implicit поведение)
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE skus SET unit_of_measure = 'л' WHERE unit_of_measure IS NULL"))
    # 3. Set NOT NULL + server_default + CHECK
    op.alter_column("skus", "unit_of_measure", nullable=False, server_default="л")
    units_sql = ",".join(f"'{u}'" for u in VALID_UNITS)
    op.create_check_constraint(
        "valid_sku_unit_of_measure_value",
        "skus",
        f"unit_of_measure IN ({units_sql})",
    )


def downgrade() -> None:
    op.drop_constraint("valid_sku_unit_of_measure_value", "skus", type_="check")
    op.drop_column("skus", "unit_of_measure")
```

- [ ] **Step 3: Обновить SQLAlchemy модель SKU**

В `backend/app/models/entities.py:96+` (class SKU):
```python
SkuUnitOfMeasure = Literal["л", "кг"]

class SKU(Base, TimestampMixin):
    # ...existing fields...
    volume_l: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    package_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_of_measure: Mapped[SkuUnitOfMeasure] = mapped_column(
        String(2),
        nullable=False,
        server_default="л",
    )
```

Type alias `SkuUnitOfMeasure` — рядом с другими (после `ChannelGroup`/`ChannelSourceType` если есть в файле, иначе в начале).

- [ ] **Step 4: Обновить Pydantic schemas**

В `backend/app/schemas/sku.py`:
```python
from typing import Literal

SkuUnitOfMeasure = Literal["л", "кг"]


class SKUBase(BaseModel):
    # ...existing fields...
    unit_of_measure: SkuUnitOfMeasure = "л"


class SKUCreate(SKUBase):
    pass


class SKURead(SKUBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime | None = None


class SKUUpdate(BaseModel):
    # ...existing optional fields...
    unit_of_measure: SkuUnitOfMeasure | None = None
```

⚠ Проверить точную текущую структуру SKUBase — backend имеет паттерны Pydantic v2 + `ConfigDict(from_attributes=True)` в Read, и Update обычно полностью optional. Сохранить эти паттерны.

- [ ] **Step 5: Применить миграцию**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic upgrade head
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
# Expected: <rev> (head)
```

- [ ] **Step 6: Добавить 3-4 теста в `backend/tests/api/test_skus.py`**

```python
async def test_sku_create_default_unit_l(auth_client: AsyncClient):
    """C #23: POST /api/skus без unit_of_measure → 'л' default."""
    resp = await auth_client.post("/api/skus", json={
        "brand": "Test", "name": "Test SKU",
    })
    assert resp.status_code == 201
    assert resp.json()["unit_of_measure"] == "л"


async def test_sku_create_with_unit_kg(auth_client: AsyncClient):
    """C #23: POST /api/skus с unit_of_measure='кг' → сохранено."""
    resp = await auth_client.post("/api/skus", json={
        "brand": "Test", "name": "Test Powder",
        "unit_of_measure": "кг",
    })
    assert resp.status_code == 201
    assert resp.json()["unit_of_measure"] == "кг"


async def test_sku_create_invalid_unit_422(auth_client: AsyncClient):
    """C #23: Pydantic отвергает unit вне "л"/"кг"."""
    resp = await auth_client.post("/api/skus", json={
        "brand": "Test", "name": "Test", "unit_of_measure": "g",
    })
    assert resp.status_code == 422


async def test_sku_patch_unit_of_measure(auth_client: AsyncClient, _create_sku_helper):
    """C #23: PATCH unit_of_measure меняет значение."""
    sku = await _create_sku_helper()
    resp = await auth_client.patch(f"/api/skus/{sku.id}", json={"unit_of_measure": "кг"})
    assert resp.status_code == 200
    assert resp.json()["unit_of_measure"] == "кг"
```

Если `_create_sku_helper` отсутствует — использовать другой паттерн из existing тестов в этом файле.

- [ ] **Step 7: Run tests**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/api/test_skus.py -v
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration | tail -3
```
Expected: всё зелёное, 553+ passed (549 + 4 new).

- [ ] **Step 8: Verify alembic round-trip**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic downgrade -1
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic upgrade head
```
Expected: оба clean.

- [ ] **Step 9: Commit T1**

```bash
git add backend/app/models/entities.py \
        backend/app/schemas/sku.py \
        backend/migrations/versions/*c23_sku_unit_of_measure.py \
        backend/tests/api/test_skus.py
git commit -m "$(cat <<'EOF'
feat(c23-t1): SKU.unit_of_measure (Literal "л"/"кг", default "л")

- Колонка unit_of_measure NOT NULL default "л" + CHECK constraint
- Миграция backfill всех existing SKU в "л" (current implicit поведение)
- Pydantic schemas: Literal type + default "л"
- 3 теста: create default, create kg, invalid 422
- 1 тест на PATCH
EOF
)"
```

---

## Task 2: Frontend — types + helpers + sweep + AddSkuDialog Select

**Files:**
- Modify: `frontend/types/api.ts` (SkuUnitOfMeasure, SKU interface)
- Modify: `frontend/lib/format.ts` (новые helpers formatVolume / formatPerUnit / formatPieces)
- Modify: `frontend/components/projects/add-sku-dialog.tsx` (Select unit_of_measure)
- Modify: `frontend/components/projects/sku-panel.tsx` (display)
- Modify: `frontend/components/projects/results-tab.tsx`, `value-chain-tab.tsx`, `channels-panel.tsx`, `pricing-*.tsx` если есть (sweep — найти все consumer'ы `volume_l`)

### Шаги

- [ ] **Step 1: Найти consumer'ы `volume_l` и per-unit displays**

```bash
grep -rn "volume_l\|formatMoneyPerUnit\|per_unit\|/л\|/кг" frontend/ --include="*.tsx" --include="*.ts" | head -50
```

Запомнить файлы.

- [ ] **Step 2: Обновить TS типы**

В `frontend/types/api.ts`:
```typescript
export type SkuUnitOfMeasure = "л" | "кг";

export interface SKU {
  // ...existing fields...
  unit_of_measure: SkuUnitOfMeasure;
}

// SKUCreate / SKUUpdate: unit_of_measure?: SkuUnitOfMeasure
```

- [ ] **Step 3: Добавить format helpers**

В `frontend/lib/format.ts` (после существующих) добавить:
```typescript
const volumeFmt = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 4,
});

/** C #23: Объём/масса с единицей. formatVolume("1.5", "л") → "1,5 л". */
export function formatVolume(
  value: string | number | null | undefined,
  unit: "л" | "кг" = "л",
): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${volumeFmt.format(num)} ${unit}`;
}

/** C #23: Деньги per-unit с единицей. formatPerUnit("52.30", "л") → "52,30 ₽/л". */
export function formatPerUnit(
  value: string | number | null | undefined,
  unit: "л" | "кг" = "л",
): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${moneyPerUnitFmt.format(num)} ₽/${unit}`;
}

/** C #23: Штуки. formatPieces(1500) → "1 500 шт". */
export function formatPieces(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${numberFmt.format(num)} шт`;
}
```

- [ ] **Step 4: AddSkuDialog — добавить Select unit_of_measure**

В `frontend/components/projects/add-sku-dialog.tsx` (или эквиваленте):
- Добавить state field `unit_of_measure: "л" | "кг"`, default "л"
- Рядом с volume input — Select из двух опций:
  ```tsx
  <Select value={form.unit_of_measure} onValueChange={(v) => setForm({...form, unit_of_measure: v as "л" | "кг"})}>
    <SelectTrigger><SelectValue/></SelectTrigger>
    <SelectContent>
      <SelectItem value="л">л (литры)</SelectItem>
      <SelectItem value="кг">кг (килограммы)</SelectItem>
    </SelectContent>
  </Select>
  ```
- Передавать в payload при создании/обновлении
- Pre-fill при edit из существующего SKU

⚠ Прочитать существующий AddSkuDialog файл сначала, чтобы понять паттерн form state.

- [ ] **Step 5: Sweep — заменить отображения volume на formatVolume**

Везде где `sku.volume_l` рендерится без единицы:
```tsx
// Было: {sku.volume_l}
// Стало: {formatVolume(sku.volume_l, sku.unit_of_measure)}
```

Sweep файлы из Step 1.

- [ ] **Step 6: Sweep — per-unit cost с unit**

Везде где `formatMoneyPerUnit(value)` показывает ₽ без знаменателя → заменить на `formatPerUnit(value, sku.unit_of_measure)`.

⚠ Контекст имеет значение: per-unit cost для конкретной SKU — берём SKU.unit_of_measure. Если контекст не имеет привязки к SKU (агрегированный) — оставляем `formatMoneyPerUnit` (legacy).

- [ ] **Step 7: Frontend restart + tsc**

```bash
docker compose -f infra/docker-compose.dev.yml stop frontend
docker compose -f infra/docker-compose.dev.yml run --rm frontend sh -c "rm -rf .next/* .next/.[!.]* 2>/dev/null"
docker compose -f infra/docker-compose.dev.yml up -d frontend
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```
Expected: EXIT=0.

- [ ] **Step 8: Commit T2**

```bash
git add frontend/types/api.ts \
        frontend/lib/format.ts \
        frontend/components/projects/add-sku-dialog.tsx \
        <sweep files>
git commit -m "$(cat <<'EOF'
feat(c23-t2): unit_of_measure в UI + formatVolume/PerUnit/Pieces helpers

- types/api.ts: SKU.unit_of_measure ("л" | "кг")
- lib/format.ts: formatVolume(value, unit), formatPerUnit(value, unit),
  formatPieces(value)
- AddSkuDialog: Select unit_of_measure рядом с volume input
- Sweep: volume_l → formatVolume в N мест, formatPerUnit с unit где
  контекст привязан к SKU
EOF
)"
```

---

## Task 3: Smoke + CHANGELOG + GO5 + merge

- [ ] **Step 1: Final verification**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration | tail -3
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/acceptance -m acceptance | tail -3
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```
Expected: 553+ passed, 6 acceptance, tsc EXIT=0.

- [ ] **Step 2: CHANGELOG**

```markdown
### Added (Phase C — C #23)

- **C #23**: SKU получил поле `unit_of_measure` (Literal "л" / "кг", default "л"). Везде в UI volume теперь отображается с единицей (`1.5 л` / `0.5 кг`). Per-unit costs показывают `руб/л` / `руб/кг` в контексте SKU. `formatPieces` для штучных значений. (MEMO 1.2)

### Migrations (Phase C — C #23)

- `<rev>_c23_sku_unit_of_measure` — добавлена `skus.unit_of_measure` (NOT NULL, default "л", CHECK 2 значения). Auto-backfill existing SKU в "л" (current implicit поведение).
```

- [ ] **Step 3: GO5 status**

Заголовок «### Фаза C — 9/19 ✅» → «### Фаза C — 10/19 ✅».
Добавить строку: `| 23 | кг/л через слеш + единицы systematic | ✅ 2026-05-16 |`.
Убрать #23 из backlog «Средние».

- [ ] **Step 4: Commit T3**

```bash
git add CHANGELOG.md GO5.md
git commit -m "docs(c23): CHANGELOG + GO5 — C #23 units systematic closed"
```

- [ ] **Step 5: Merge --no-ff**

```bash
git checkout main
git merge --no-ff feat/c23-units-systematic -m "Merge C #23 — кг/л + единицы systematic

3-task small эпик:
- T1 backend: SKU.unit_of_measure Literal л/кг + миграция + 4 теста
- T2 frontend: TS типы + formatVolume/PerUnit/Pieces helpers + AddSkuDialog Select + sweep
- T3 docs + smoke

Backward-compat: existing SKU auto-backfill в \"л\". CHECK constraint в DB.
Closes Phase C #23."
git tag v2.6.2 -m "v2.6.2 — C #23 units systematic"
git branch -d feat/c23-units-systematic
```

DO NOT push.
