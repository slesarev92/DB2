# C #14: Fine Tuning per-period Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести 4 finance-input поля (`copacking_rate`, `logistics_cost_per_kg`, `ca_m_rate`, `marketing_rate`) на per-period (43 точки) override через JSONB-колонки + UI на основе reuse-компонентов B.9b.

**Architecture:** JSONB-массивы длины 43 на тех же таблицах (`ProjectSKU.copacking_rate_by_period`, `ProjectSKUChannel.{logistics_cost_per_kg,ca_m_rate,marketing_rate}_by_period`). Override-only: `effective[i] = by_period[i] if not None else scalar`. Скаляр остаётся базой. Pipeline получает tuple-43, шаги s03/s05/s06 обновляются. Frontend — отдельный Fine Tuning tab с 4 секциями, reuse `PeriodGrid` и `period-bulk-fill` из shared.

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy 2.0 + asyncpg + Alembic + Pydantic v2 / Next.js 14 + TypeScript + shadcn/ui / pytest + tsc.

**Spec:** `docs/superpowers/specs/2026-05-15-c14-fine-tuning-per-period-design.md` (commit `bc0b711`).

---

## File Structure

**Create (backend):**
- `backend/alembic/versions/<new>_fine_tuning_per_period.py` — миграция: 4 JSONB-колонки (NULL default)
- `backend/app/schemas/fine_tuning.py` — Pydantic-схемы overrides (SKU/Channel response + payload)
- `backend/app/services/fine_tuning_period_service.py` — service-слой (list / replace)
- `backend/app/api/fine_tuning.py` — 4 endpoint'а (GET/PUT × SKU/Channel)
- `backend/tests/services/test_fine_tuning_period_service.py`
- `backend/tests/api/test_fine_tuning_per_period.py`
- `backend/tests/engine/test_resolve_period_value.py`

**Modify (backend):**
- `backend/app/models/entities.py` — добавить 4 mapped_column в ProjectSKU + ProjectSKUChannel
- `backend/app/services/calculation_service.py` — `_resolve_period_value` helper, обновить `_build_line_input`, расширить PipelineInput (новые `_arr` поля)
- `backend/app/engine/pipeline.py` (или dataclass где живёт PipelineInput) — поля `copacking_rate_arr`, `logistics_cost_per_kg_arr`, `ca_m_rate_arr`, `marketing_rate_arr`
- `backend/app/engine/steps/s03_cogs.py` — copacking_rate scalar → arr[t]
- `backend/app/engine/steps/s05_contribution.py` — logistics_cost_per_kg scalar → arr[t]
- `backend/app/engine/steps/s06_ebitda.py` — ca_m_rate, marketing_rate scalar → arr[t]
- `backend/app/main.py` (или `routes/__init__.py`) — подключить fine_tuning router
- `backend/tests/acceptance/test_e2e_gorji.py` — расширение: без override drift сохраняется + новый GORJI-with-override case

**Create (frontend):**
- `frontend/components/shared/period-grid.tsx` — generic 43-колоночный grid (extracted из financial-plan-editor)
- `frontend/components/shared/period-bulk-fill.tsx` — переезд из `projects/financial-plan-bulk-fill.tsx`
- `frontend/components/projects/fine-tuning-per-period-panel.tsx` — оркестрация 4 секций (~30 строк, только compose)
- `frontend/components/projects/fine-tuning-copacking-section.tsx` — секция per-SKU copacking (~60 строк)
- `frontend/components/projects/fine-tuning-channel-section.tsx` — generic секция per-channel (logistics / ca_m / marketing) (~80 строк)
- `frontend/lib/api/fine-tuning.ts` — fetch helpers (get/put overrides)
- `frontend/app/projects/[id]/fine-tuning/page.tsx` — страница Fine Tuning (или extension существующей)

**Modify (frontend):**
- `frontend/components/projects/financial-plan-editor.tsx` — refactor: использовать `<PeriodGrid>` вместо inline 43-колоночного table
- `frontend/components/projects/financial-plan-bulk-fill.tsx` — удалить (re-export `shared/period-bulk-fill`)
- `frontend/types/api.ts` — типы для overrides response/payload
- `frontend/contexts/project-nav-context.tsx` — добавить пункт Fine Tuning per-period (если ещё нет)

**Docs:**
- `CHANGELOG.md` — секция `[Unreleased]`, отметить C #14
- `docs/CLIENT_FEEDBACK_v2_DECISIONS.md` — пометить #14 closed (дата + commit)
- `docs/ARCHITECTURE.md` — раздел «Per-period overrides» с JSONB-on-table паттерном

**Не трогаем:**
- Существующий слой `PeriodValue` (используется B.5 OBPPC, отдельная семантика — см. spec §4.5)
- Шаги s01, s02, s04, s07-s12 — не используют 4 целевых поля
- `_load_project_financial_plan` в calculation_service (B.9b логика)
- BOM panel и Channel form (quick-edit — backlog)

---

## Conventions

- Backend-команды: `docker compose -f infra/docker-compose.dev.yml exec -T backend ...`
- Frontend-команды: `docker compose -f infra/docker-compose.dev.yml exec -T frontend ...`
- Pytest paths **БЕЗ префикса `backend/`** (working dir в контейнере = `/app`). Например: `tests/api/test_fine_tuning_per_period.py`.
- Каждый commit включает `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` (CLAUDE.md).
- Формат коммита: `тип(область): описание`. Область для этой фичи — `c14` или `c14-be`/`c14-fe` для разделения.
- JSONB mutation: при изменении array-полей в SQLAlchemy объекте — обязателен `flag_modified(obj, "<column_name>")` (memory `feedback_jsonb_flag_modified`).
- После структурных frontend-изменений (новые import / новый JSX) — full restart фронта с очисткой `.next` (Windows+Docker HMR баг).

---

## Task 1: Baseline check

**Files:** none

- [ ] **Step 1: Verify baseline tests pass**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```
Expected: `477 passed`.

- [ ] **Step 2: Verify frontend type-check passes**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```
Expected: empty output (no errors).

- [ ] **Step 3: Verify alembic head**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
```
Expected: `e5f6a7b8c9d0 (head)`.

- [ ] **Step 4: Confirm git clean**

Run:
```bash
git status --short
```
Expected: empty output.

No commit at this task.

---

## Task 2: Alembic migration — 4 JSONB columns

**Files:**
- Create: `backend/alembic/versions/<new_revision>_fine_tuning_per_period.py`

- [ ] **Step 1: Generate migration skeleton**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    alembic revision -m "fine tuning per period overrides"
```

Find the newly created file in `backend/alembic/versions/`. Note the revision id (e.g. `f6a7b8c9d0e1`).

- [ ] **Step 2: Write upgrade/downgrade**

Replace the body of the generated file with:

```python
"""fine tuning per period overrides

Revision ID: <id>
Revises: e5f6a7b8c9d0
Create Date: 2026-05-15

C #14: per-period override JSONB-arrays (length 43) for copacking_rate
(ProjectSKU) and logistics_cost_per_kg / ca_m_rate / marketing_rate
(ProjectSKUChannel). NULL = no override (pipeline falls back to scalar).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "<id>"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_skus",
        sa.Column(
            "copacking_rate_by_period",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "project_sku_channels",
        sa.Column(
            "logistics_cost_per_kg_by_period",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "project_sku_channels",
        sa.Column(
            "ca_m_rate_by_period",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "project_sku_channels",
        sa.Column(
            "marketing_rate_by_period",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("project_sku_channels", "marketing_rate_by_period")
    op.drop_column("project_sku_channels", "ca_m_rate_by_period")
    op.drop_column("project_sku_channels", "logistics_cost_per_kg_by_period")
    op.drop_column("project_skus", "copacking_rate_by_period")
```

- [ ] **Step 3: Apply migration**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic upgrade head
```
Expected: `Running upgrade e5f6a7b8c9d0 -> <id>, fine tuning per period overrides`.

- [ ] **Step 4: Verify head**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
```
Expected: `<id> (head)`.

- [ ] **Step 5: Run baseline tests again — drift = 0**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```
Expected: `477 passed` (миграция не должна ломать тесты — колонки NULL по умолчанию).

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/<new_revision>_fine_tuning_per_period.py
git commit -m "$(cat <<'EOF'
feat(c14): миграция per-period overrides (4 JSONB колонки)

ProjectSKU.copacking_rate_by_period (per-SKU),
ProjectSKUChannel.{logistics_cost_per_kg,ca_m_rate,marketing_rate}_by_period
(per-channel). NULL по умолчанию — pipeline fallback на скаляр.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: SQLAlchemy models — 4 new mapped columns

**Files:**
- Modify: `backend/app/models/entities.py`

- [ ] **Step 1: Add `copacking_rate_by_period` to `ProjectSKU`**

Найти класс `ProjectSKU` в `backend/app/models/entities.py` (около строки 417). После `bom_cost_level_by_year` (~ строка 462) добавить:

```python
    copacking_rate_by_period: Mapped[list[Decimal | None] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    """C #14: per-period override (array length 43, M1..M36 + Y4..Y10).
    NULL = no override (pipeline uses copacking_rate scalar)."""
```

- [ ] **Step 2: Add 3 columns to `ProjectSKUChannel`**

Найти класс `ProjectSKUChannel` (около строки 492). После `marketing_rate` (~ строка 555) добавить:

```python
    logistics_cost_per_kg_by_period: Mapped[list[Decimal | None] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    """C #14: per-period override (array length 43)."""

    ca_m_rate_by_period: Mapped[list[Decimal | None] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    """C #14: per-period override (array length 43)."""

    marketing_rate_by_period: Mapped[list[Decimal | None] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    """C #14: per-period override (array length 43)."""
```

- [ ] **Step 3: Run baseline tests — drift = 0**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```
Expected: `477 passed`. (Поля добавлены, но никто их ещё не использует.)

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/entities.py
git commit -m "$(cat <<'EOF'
feat(c14): SQLAlchemy model fields — 4 JSONB override колонки

ProjectSKU.copacking_rate_by_period + 3 поля на ProjectSKUChannel.
Тип Mapped[list[Decimal | None] | None]. Поля не используются —
подключение в pipeline в следующих задачах.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Pydantic schemas — overrides request/response

**Files:**
- Create: `backend/app/schemas/fine_tuning.py`
- Create: `backend/tests/services/test_fine_tuning_period_service.py` (только schema-тесты в этой task'е; service-тесты в Task 5)

- [ ] **Step 1: Write failing schema tests**

Create `backend/tests/services/test_fine_tuning_period_service.py`:

```python
"""Pydantic schema tests for C #14 fine tuning overrides."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.fine_tuning import (
    ChannelOverridesPayload,
    ChannelOverridesResponse,
    SkuOverridesPayload,
    SkuOverridesResponse,
)


def test_sku_overrides_accepts_none() -> None:
    payload = SkuOverridesPayload(copacking_rate_by_period=None)
    assert payload.copacking_rate_by_period is None


def test_sku_overrides_accepts_43_element_array() -> None:
    arr = [Decimal("1.5")] * 43
    payload = SkuOverridesPayload(copacking_rate_by_period=arr)
    assert len(payload.copacking_rate_by_period) == 43


def test_sku_overrides_accepts_partial_null_elements() -> None:
    arr: list[Decimal | None] = [None] * 43
    arr[5] = Decimal("2.0")
    payload = SkuOverridesPayload(copacking_rate_by_period=arr)
    assert payload.copacking_rate_by_period[5] == Decimal("2.0")
    assert payload.copacking_rate_by_period[0] is None


def test_sku_overrides_rejects_wrong_length() -> None:
    with pytest.raises(ValidationError):
        SkuOverridesPayload(copacking_rate_by_period=[Decimal("1")] * 42)
    with pytest.raises(ValidationError):
        SkuOverridesPayload(copacking_rate_by_period=[Decimal("1")] * 44)


def test_sku_overrides_rejects_negative() -> None:
    arr = [Decimal("0")] * 43
    arr[0] = Decimal("-1")
    with pytest.raises(ValidationError):
        SkuOverridesPayload(copacking_rate_by_period=arr)


def test_channel_overrides_accepts_all_three_arrays() -> None:
    arr = [Decimal("0.1")] * 43
    payload = ChannelOverridesPayload(
        logistics_cost_per_kg_by_period=arr,
        ca_m_rate_by_period=arr,
        marketing_rate_by_period=arr,
    )
    assert payload.logistics_cost_per_kg_by_period == arr


def test_channel_overrides_rejects_rate_above_one() -> None:
    arr: list[Decimal | None] = [Decimal("0")] * 43
    arr[10] = Decimal("1.5")
    with pytest.raises(ValidationError):
        ChannelOverridesPayload(
            logistics_cost_per_kg_by_period=None,
            ca_m_rate_by_period=arr,
            marketing_rate_by_period=None,
        )


def test_channel_overrides_all_none_is_valid() -> None:
    payload = ChannelOverridesPayload(
        logistics_cost_per_kg_by_period=None,
        ca_m_rate_by_period=None,
        marketing_rate_by_period=None,
    )
    assert payload.ca_m_rate_by_period is None


def test_sku_overrides_response_round_trip() -> None:
    arr = [Decimal("5.5")] * 43
    resp = SkuOverridesResponse(copacking_rate_by_period=arr)
    dumped = resp.model_dump(mode="json")
    assert dumped["copacking_rate_by_period"][0] == "5.5"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/services/test_fine_tuning_period_service.py -v
```
Expected: FAIL — `app.schemas.fine_tuning` does not exist.

- [ ] **Step 3: Create `backend/app/schemas/fine_tuning.py`**

```python
"""C #14 Fine Tuning per-period overrides — Pydantic schemas.

Все 4 override-поля — JSONB-массивы длины ровно 43 (M1..M36 + Y4..Y10),
элементы Decimal | None. None в элементе → pipeline берёт скаляр.
None во всём поле → нет override.
"""
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

PERIOD_COUNT = 43


def _validate_length(arr: list[Decimal | None] | None) -> list[Decimal | None] | None:
    if arr is None:
        return None
    if len(arr) != PERIOD_COUNT:
        raise ValueError(f"Array must have exactly {PERIOD_COUNT} elements, got {len(arr)}")
    return arr


def _validate_non_negative(arr: list[Decimal | None] | None) -> list[Decimal | None] | None:
    if arr is None:
        return None
    for i, v in enumerate(arr):
        if v is not None and v < 0:
            raise ValueError(f"Element [{i}]={v} must be >= 0")
    return arr


def _validate_rate(arr: list[Decimal | None] | None) -> list[Decimal | None] | None:
    if arr is None:
        return None
    for i, v in enumerate(arr):
        if v is not None and (v < 0 or v > 1):
            raise ValueError(f"Element [{i}]={v} must be in [0, 1]")
    return arr


class SkuOverridesPayload(BaseModel):
    """PUT payload для SKU-уровня override (copacking_rate)."""

    copacking_rate_by_period: list[Decimal | None] | None = Field(default=None)

    @field_validator("copacking_rate_by_period")
    @classmethod
    def _check_copacking(cls, v: list[Decimal | None] | None) -> list[Decimal | None] | None:
        return _validate_non_negative(_validate_length(v))


class SkuOverridesResponse(SkuOverridesPayload):
    """GET response — те же поля."""


class ChannelOverridesPayload(BaseModel):
    """PUT payload для Channel-уровня override (3 поля)."""

    logistics_cost_per_kg_by_period: list[Decimal | None] | None = Field(default=None)
    ca_m_rate_by_period: list[Decimal | None] | None = Field(default=None)
    marketing_rate_by_period: list[Decimal | None] | None = Field(default=None)

    @field_validator("logistics_cost_per_kg_by_period")
    @classmethod
    def _check_logistics(cls, v: list[Decimal | None] | None) -> list[Decimal | None] | None:
        return _validate_non_negative(_validate_length(v))

    @field_validator("ca_m_rate_by_period")
    @classmethod
    def _check_ca_m(cls, v: list[Decimal | None] | None) -> list[Decimal | None] | None:
        return _validate_rate(_validate_length(v))

    @field_validator("marketing_rate_by_period")
    @classmethod
    def _check_marketing(cls, v: list[Decimal | None] | None) -> list[Decimal | None] | None:
        return _validate_rate(_validate_length(v))


class ChannelOverridesResponse(ChannelOverridesPayload):
    """GET response — те же поля."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/services/test_fine_tuning_period_service.py -v
```
Expected: 9 tests pass.

- [ ] **Step 5: Run full baseline — drift = 0**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```
Expected: `486 passed` (477 + 9).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/fine_tuning.py backend/tests/services/test_fine_tuning_period_service.py
git commit -m "$(cat <<'EOF'
feat(c14): Pydantic-схемы overrides — SKU + Channel payload/response

Валидация: length==43, non-negative для copacking/logistics,
[0,1] для ca_m_rate/marketing_rate. None допустимо для всего поля
и для отдельных элементов (fallback на скаляр).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Service layer — list / replace overrides

**Files:**
- Create: `backend/app/services/fine_tuning_period_service.py`
- Modify: `backend/tests/services/test_fine_tuning_period_service.py` (добавить service-тесты)

- [ ] **Step 1: Write failing service tests**

Append к `backend/tests/services/test_fine_tuning_period_service.py`:

```python
# ============================================================
# C #14: service layer tests
# ============================================================
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Project, ProjectSKU, ProjectSKUChannel
from app.services.fine_tuning_period_service import (
    list_overrides_by_channel,
    list_overrides_by_sku,
    replace_channel_overrides,
    replace_sku_overrides,
)


@pytest.mark.asyncio
async def test_list_sku_overrides_returns_none_for_clean_project(
    async_session: AsyncSession,
    sample_project_with_sku: Project,
) -> None:
    project = sample_project_with_sku
    sku = (await async_session.scalars(select(ProjectSKU).where(ProjectSKU.project_id == project.id))).first()

    result = await list_overrides_by_sku(async_session, project.id, sku.id)
    assert result.copacking_rate_by_period is None


@pytest.mark.asyncio
async def test_replace_sku_overrides_persists_array(
    async_session: AsyncSession,
    sample_project_with_sku: Project,
) -> None:
    project = sample_project_with_sku
    sku = (await async_session.scalars(select(ProjectSKU).where(ProjectSKU.project_id == project.id))).first()
    arr = [Decimal("0")] * 43
    arr[5] = Decimal("99.5")

    await replace_sku_overrides(async_session, project.id, sku.id, arr)
    await async_session.commit()

    await async_session.refresh(sku)
    assert sku.copacking_rate_by_period[5] == Decimal("99.5")


@pytest.mark.asyncio
async def test_replace_sku_overrides_with_none_clears(
    async_session: AsyncSession,
    sample_project_with_sku: Project,
) -> None:
    project = sample_project_with_sku
    sku = (await async_session.scalars(select(ProjectSKU).where(ProjectSKU.project_id == project.id))).first()
    sku.copacking_rate_by_period = [Decimal("1")] * 43
    await async_session.commit()

    await replace_sku_overrides(async_session, project.id, sku.id, None)
    await async_session.commit()
    await async_session.refresh(sku)

    assert sku.copacking_rate_by_period is None


@pytest.mark.asyncio
async def test_list_channel_overrides_returns_all_none(
    async_session: AsyncSession,
    sample_project_with_channel: Project,
) -> None:
    project = sample_project_with_channel
    ch = (await async_session.scalars(select(ProjectSKUChannel))).first()

    result = await list_overrides_by_channel(async_session, project.id, ch.sku_id, ch.id)
    assert result.logistics_cost_per_kg_by_period is None
    assert result.ca_m_rate_by_period is None
    assert result.marketing_rate_by_period is None


@pytest.mark.asyncio
async def test_replace_channel_overrides_atomic_three_fields(
    async_session: AsyncSession,
    sample_project_with_channel: Project,
) -> None:
    project = sample_project_with_channel
    ch = (await async_session.scalars(select(ProjectSKUChannel))).first()
    log_arr = [Decimal("10")] * 43
    ca_m_arr = [Decimal("0.05")] * 43

    await replace_channel_overrides(
        async_session,
        project.id, ch.sku_id, ch.id,
        logistics_cost_per_kg_by_period=log_arr,
        ca_m_rate_by_period=ca_m_arr,
        marketing_rate_by_period=None,
    )
    await async_session.commit()
    await async_session.refresh(ch)

    assert ch.logistics_cost_per_kg_by_period[0] == Decimal("10")
    assert ch.ca_m_rate_by_period[0] == Decimal("0.05")
    assert ch.marketing_rate_by_period is None


@pytest.mark.asyncio
async def test_replace_sku_overrides_rejects_wrong_length(
    async_session: AsyncSession,
    sample_project_with_sku: Project,
) -> None:
    project = sample_project_with_sku
    sku = (await async_session.scalars(select(ProjectSKU).where(ProjectSKU.project_id == project.id))).first()

    with pytest.raises(ValueError):
        await replace_sku_overrides(async_session, project.id, sku.id, [Decimal("1")] * 42)
```

**Если fixtures `sample_project_with_sku` / `sample_project_with_channel` уже не существуют в conftest** — посмотреть аналоги в `backend/tests/api/test_financial_plan.py` (B.9b fixture'ы) и переиспользовать (например, `sample_project_with_financial_plan` имеет связанный SKU). При отсутствии — добавить минимальные fixture'ы в `backend/tests/conftest.py` по образу B.9b.

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/services/test_fine_tuning_period_service.py -v 2>&1 | tail -10
```
Expected: FAIL — `fine_tuning_period_service` module не существует.

- [ ] **Step 3: Create `backend/app/services/fine_tuning_period_service.py`**

```python
"""C #14 Fine Tuning per-period overrides — service layer.

Атомарная замена JSONB-массивов длины 43 (None = убрать override).
SQLAlchemy mutation требует flag_modified для JSONB-полей.
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.entities import ProjectSKU, ProjectSKUChannel
from app.schemas.fine_tuning import (
    ChannelOverridesResponse,
    SkuOverridesResponse,
)

PERIOD_COUNT = 43


def _check_length(arr: list[Decimal | None] | None) -> None:
    if arr is not None and len(arr) != PERIOD_COUNT:
        raise ValueError(f"Array must have exactly {PERIOD_COUNT} elements, got {len(arr)}")


async def list_overrides_by_sku(
    session: AsyncSession,
    project_id: int,
    sku_id: int,
) -> SkuOverridesResponse:
    sku = await session.get(ProjectSKU, sku_id)
    if sku is None or sku.project_id != project_id:
        raise LookupError(f"ProjectSKU {sku_id} not found in project {project_id}")
    return SkuOverridesResponse(copacking_rate_by_period=sku.copacking_rate_by_period)


async def replace_sku_overrides(
    session: AsyncSession,
    project_id: int,
    sku_id: int,
    copacking_rate_by_period: list[Decimal | None] | None,
) -> None:
    _check_length(copacking_rate_by_period)
    sku = await session.get(ProjectSKU, sku_id)
    if sku is None or sku.project_id != project_id:
        raise LookupError(f"ProjectSKU {sku_id} not found in project {project_id}")
    sku.copacking_rate_by_period = copacking_rate_by_period
    flag_modified(sku, "copacking_rate_by_period")


async def list_overrides_by_channel(
    session: AsyncSession,
    project_id: int,
    sku_id: int,
    psk_channel_id: int,
) -> ChannelOverridesResponse:
    ch = await session.get(ProjectSKUChannel, psk_channel_id)
    if ch is None or ch.sku_id != sku_id:
        raise LookupError(f"ProjectSKUChannel {psk_channel_id} not found")
    sku = await session.get(ProjectSKU, sku_id)
    if sku is None or sku.project_id != project_id:
        raise LookupError(f"ProjectSKU {sku_id} not found in project {project_id}")
    return ChannelOverridesResponse(
        logistics_cost_per_kg_by_period=ch.logistics_cost_per_kg_by_period,
        ca_m_rate_by_period=ch.ca_m_rate_by_period,
        marketing_rate_by_period=ch.marketing_rate_by_period,
    )


async def replace_channel_overrides(
    session: AsyncSession,
    project_id: int,
    sku_id: int,
    psk_channel_id: int,
    *,
    logistics_cost_per_kg_by_period: list[Decimal | None] | None,
    ca_m_rate_by_period: list[Decimal | None] | None,
    marketing_rate_by_period: list[Decimal | None] | None,
) -> None:
    for arr in (logistics_cost_per_kg_by_period, ca_m_rate_by_period, marketing_rate_by_period):
        _check_length(arr)
    ch = await session.get(ProjectSKUChannel, psk_channel_id)
    if ch is None or ch.sku_id != sku_id:
        raise LookupError(f"ProjectSKUChannel {psk_channel_id} not found")
    sku = await session.get(ProjectSKU, sku_id)
    if sku is None or sku.project_id != project_id:
        raise LookupError(f"ProjectSKU {sku_id} not found in project {project_id}")

    ch.logistics_cost_per_kg_by_period = logistics_cost_per_kg_by_period
    ch.ca_m_rate_by_period = ca_m_rate_by_period
    ch.marketing_rate_by_period = marketing_rate_by_period
    flag_modified(ch, "logistics_cost_per_kg_by_period")
    flag_modified(ch, "ca_m_rate_by_period")
    flag_modified(ch, "marketing_rate_by_period")
```

- [ ] **Step 4: Run service tests to verify they pass**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/services/test_fine_tuning_period_service.py -v 2>&1 | tail -20
```
Expected: все service-тесты pass (6 новых + 9 schema = 15 in this file).

- [ ] **Step 5: Run full baseline — drift = 0**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```
Expected: `492 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/fine_tuning_period_service.py backend/tests/services/test_fine_tuning_period_service.py
git commit -m "$(cat <<'EOF'
feat(c14): service-слой per-period overrides

list/replace для SKU (copacking_rate) и Channel (3 поля). Атомарная
замена с flag_modified для JSONB mutation. None = убрать override.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: API endpoints — GET/PUT × SKU/Channel

**Files:**
- Create: `backend/app/api/fine_tuning.py`
- Modify: `backend/app/main.py` (или `backend/app/api/__init__.py`) — подключить router
- Create: `backend/tests/api/test_fine_tuning_per_period.py`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/api/test_fine_tuning_per_period.py`:

```python
"""C #14 Fine Tuning API endpoint tests."""
from decimal import Decimal

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_sku_overrides_returns_none_for_clean(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project_with_sku,
) -> None:
    project = sample_project_with_sku
    sku = project.skus[0]
    resp = await async_client.get(
        f"/api/projects/{project.id}/fine-tuning/per-period/sku/{sku.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["copacking_rate_by_period"] is None


@pytest.mark.asyncio
async def test_put_sku_overrides_round_trip(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project_with_sku,
) -> None:
    project = sample_project_with_sku
    sku = project.skus[0]
    arr: list[str | None] = ["0"] * 43
    arr[5] = "99.5"
    resp = await async_client.put(
        f"/api/projects/{project.id}/fine-tuning/per-period/sku/{sku.id}",
        headers=auth_headers,
        json={"copacking_rate_by_period": arr},
    )
    assert resp.status_code == 204

    resp = await async_client.get(
        f"/api/projects/{project.id}/fine-tuning/per-period/sku/{sku.id}",
        headers=auth_headers,
    )
    assert resp.json()["copacking_rate_by_period"][5] == "99.5"


@pytest.mark.asyncio
async def test_put_sku_overrides_rejects_wrong_length(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project_with_sku,
) -> None:
    project = sample_project_with_sku
    sku = project.skus[0]
    resp = await async_client.put(
        f"/api/projects/{project.id}/fine-tuning/per-period/sku/{sku.id}",
        headers=auth_headers,
        json={"copacking_rate_by_period": ["1"] * 42},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_channel_overrides_partial_fields(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project_with_channel,
) -> None:
    project = sample_project_with_channel
    sku = project.skus[0]
    ch = sku.channels[0]
    log_arr: list[str | None] = ["10"] * 43

    resp = await async_client.put(
        f"/api/projects/{project.id}/fine-tuning/per-period/channel/{ch.id}",
        headers=auth_headers,
        json={
            "logistics_cost_per_kg_by_period": log_arr,
            "ca_m_rate_by_period": None,
            "marketing_rate_by_period": None,
        },
    )
    assert resp.status_code == 204

    resp = await async_client.get(
        f"/api/projects/{project.id}/fine-tuning/per-period/channel/{ch.id}",
        headers=auth_headers,
    )
    body = resp.json()
    assert body["logistics_cost_per_kg_by_period"][0] == "10"
    assert body["ca_m_rate_by_period"] is None


@pytest.mark.asyncio
async def test_get_sku_overrides_unauthorized(
    async_client: AsyncClient,
    sample_project_with_sku,
) -> None:
    project = sample_project_with_sku
    sku = project.skus[0]
    resp = await async_client.get(
        f"/api/projects/{project.id}/fine-tuning/per-period/sku/{sku.id}",
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_sku_overrides_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project_with_sku,
) -> None:
    project = sample_project_with_sku
    resp = await async_client.get(
        f"/api/projects/{project.id}/fine-tuning/per-period/sku/999999",
        headers=auth_headers,
    )
    assert resp.status_code == 404
```

Fixture'ы `async_client`, `auth_headers`, `sample_project_with_sku`, `sample_project_with_channel` — используем существующие из `backend/tests/conftest.py` (см. B.9b API-тесты). Если `sample_project_with_channel` отсутствует — собрать аналогично `sample_project_with_sku`, добавив один `ProjectSKUChannel`.

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/api/test_fine_tuning_per_period.py -v 2>&1 | tail -10
```
Expected: FAIL — endpoints не существуют (404).

- [ ] **Step 3: Create `backend/app/api/fine_tuning.py`**

```python
"""C #14 Fine Tuning per-period overrides — API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session, require_project_member
from app.schemas.fine_tuning import (
    ChannelOverridesPayload,
    ChannelOverridesResponse,
    SkuOverridesPayload,
    SkuOverridesResponse,
)
from app.services import fine_tuning_period_service

router = APIRouter(
    prefix="/projects/{project_id}/fine-tuning/per-period",
    tags=["fine-tuning"],
)


@router.get("/sku/{sku_id}", response_model=SkuOverridesResponse)
async def get_sku_overrides(
    project_id: int,
    sku_id: int,
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_project_member),
) -> SkuOverridesResponse:
    try:
        return await fine_tuning_period_service.list_overrides_by_sku(
            session, project_id, sku_id
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/sku/{sku_id}", status_code=status.HTTP_204_NO_CONTENT)
async def put_sku_overrides(
    project_id: int,
    sku_id: int,
    payload: SkuOverridesPayload,
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_project_member),
) -> None:
    try:
        await fine_tuning_period_service.replace_sku_overrides(
            session, project_id, sku_id, payload.copacking_rate_by_period
        )
        await session.commit()
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/channel/{psk_channel_id}", response_model=ChannelOverridesResponse)
async def get_channel_overrides(
    project_id: int,
    psk_channel_id: int,
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_project_member),
) -> ChannelOverridesResponse:
    # Channel принадлежит SKU; sku_id извлекаем из самой записи внутри сервиса.
    # Для соблюдения signature service'а сначала достанем channel и узнаем sku_id.
    from sqlalchemy import select
    from app.models.entities import ProjectSKUChannel
    ch = await session.get(ProjectSKUChannel, psk_channel_id)
    if ch is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    try:
        return await fine_tuning_period_service.list_overrides_by_channel(
            session, project_id, ch.sku_id, psk_channel_id
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/channel/{psk_channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def put_channel_overrides(
    project_id: int,
    psk_channel_id: int,
    payload: ChannelOverridesPayload,
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_project_member),
) -> None:
    from app.models.entities import ProjectSKUChannel
    ch = await session.get(ProjectSKUChannel, psk_channel_id)
    if ch is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    try:
        await fine_tuning_period_service.replace_channel_overrides(
            session,
            project_id, ch.sku_id, psk_channel_id,
            logistics_cost_per_kg_by_period=payload.logistics_cost_per_kg_by_period,
            ca_m_rate_by_period=payload.ca_m_rate_by_period,
            marketing_rate_by_period=payload.marketing_rate_by_period,
        )
        await session.commit()
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

**ПРИМЕЧАНИЕ для исполнителя:** проверь `from app.api.deps import ...` — точные имена `get_async_session` и `require_project_member` могут отличаться (см. как подключён router финплана в `backend/app/api/financial_plan.py`). Используй те же импорты.

- [ ] **Step 4: Register router in main**

Найти место подключения роутеров (например, `backend/app/main.py` или `backend/app/api/__init__.py`). По образцу `financial_plan` router добавить:

```python
from app.api import fine_tuning
app.include_router(fine_tuning.router, prefix="/api")
```

- [ ] **Step 5: Run API tests to verify they pass**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/api/test_fine_tuning_per_period.py -v 2>&1 | tail -15
```
Expected: 6 tests pass.

- [ ] **Step 6: Run full baseline — drift = 0**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```
Expected: `498 passed`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/fine_tuning.py backend/app/main.py backend/tests/api/test_fine_tuning_per_period.py
git commit -m "$(cat <<'EOF'
feat(c14): API endpoints GET/PUT per-period overrides

4 эндпоинта: GET/PUT × SKU/Channel. Те же auth-guards и project-member
scope, что у финплана. 404 для отсутствующего SKU/Channel,
422 для невалидных payload.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Engine — `_resolve_period_value` helper + PipelineInput + 3 шага

**Files:**
- Modify: `backend/app/services/calculation_service.py`
- Modify: `backend/app/engine/pipeline.py` (или dataclass файл PipelineInput)
- Modify: `backend/app/engine/steps/s03_cogs.py`
- Modify: `backend/app/engine/steps/s05_contribution.py`
- Modify: `backend/app/engine/steps/s06_ebitda.py`
- Create: `backend/tests/engine/test_resolve_period_value.py`

- [ ] **Step 1: Write failing helper test**

Create `backend/tests/engine/test_resolve_period_value.py`:

```python
"""C #14 _resolve_period_value helper unit tests."""
from decimal import Decimal

from app.services.calculation_service import _resolve_period_value


def test_returns_scalar_when_by_period_is_none() -> None:
    assert _resolve_period_value(None, Decimal("5"), 0) == Decimal("5")


def test_returns_scalar_when_element_is_none() -> None:
    arr: list[Decimal | None] = [None] * 43
    assert _resolve_period_value(arr, Decimal("5"), 10) == Decimal("5")


def test_returns_override_when_element_present() -> None:
    arr: list[Decimal | None] = [None] * 43
    arr[10] = Decimal("99")
    assert _resolve_period_value(arr, Decimal("5"), 10) == Decimal("99")


def test_decimal_string_in_jsonb_converted_to_decimal() -> None:
    arr: list = [None] * 43
    arr[10] = "99.5"  # как читается из JSONB
    result = _resolve_period_value(arr, Decimal("5"), 10)
    assert result == Decimal("99.5")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/engine/test_resolve_period_value.py -v
```
Expected: FAIL — `_resolve_period_value` не существует.

- [ ] **Step 3: Add `_resolve_period_value` helper in `calculation_service.py`**

В начале `backend/app/services/calculation_service.py` (после импортов, перед классами/функциями):

```python
def _resolve_period_value(
    by_period: list | None,
    scalar: Decimal,
    idx: int,
) -> Decimal:
    """C #14: эффективное значение per-period override.

    Если override отсутствует целиком (None) или для данного индекса
    (элемент None), возвращает базовый скаляр. Иначе — Decimal значения
    из JSONB (которое может быть str/float после десериализации).
    """
    if by_period is None:
        return scalar
    raw = by_period[idx]
    if raw is None:
        return scalar
    return Decimal(str(raw))
```

- [ ] **Step 4: Run helper test to pass**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/engine/test_resolve_period_value.py -v
```
Expected: 4 tests pass.

- [ ] **Step 5: Extend PipelineInput dataclass**

Найти PipelineInput в `backend/app/engine/pipeline.py` (или соседнем файле). По месту, где сейчас лежат скаляры `copacking_rate`, `logistics_cost_per_kg`, `ca_m_rate`, `marketing_rate`, **добавить** (не удалять старые — для backward compat первого прохода):

```python
    copacking_rate_arr: tuple[Decimal, ...]              # length 43
    logistics_cost_per_kg_arr: tuple[Decimal, ...]       # length 43
    ca_m_rate_arr: tuple[Decimal, ...]                   # length 43
    marketing_rate_arr: tuple[Decimal, ...]              # length 43
```

- [ ] **Step 6: Build `_arr` tuples in `_build_line_input`**

В `backend/app/services/calculation_service.py`, метод `_build_line_input` (около строки 393). После места, где сейчас выставляются скаляры (или собирается `log_arr` для PeriodValue) — добавить:

```python
        copacking_rate_arr = tuple(
            _resolve_period_value(sku.copacking_rate_by_period, sku.copacking_rate, i)
            for i in range(43)
        )
        logistics_cost_per_kg_arr = tuple(
            _resolve_period_value(ch.logistics_cost_per_kg_by_period, ch.logistics_cost_per_kg, i)
            for i in range(43)
        )
        ca_m_rate_arr = tuple(
            _resolve_period_value(ch.ca_m_rate_by_period, ch.ca_m_rate, i)
            for i in range(43)
        )
        marketing_rate_arr = tuple(
            _resolve_period_value(ch.marketing_rate_by_period, ch.marketing_rate, i)
            for i in range(43)
        )
```

И передать в конструктор PipelineInput (см. где сейчас передаются скаляры, ~ строка 512-518).

- [ ] **Step 7: Update s03_cogs.py — use copacking_rate_arr[t]**

В `backend/app/engine/steps/s03_cogs.py` найти использование `pi.copacking_rate` (например, `cogs_t += copacking_rate * volume[t]` в цикле по t). Заменить на:

```python
copacking_t = pi.copacking_rate_arr[t]
```

(и использовать `copacking_t` в формуле — `*` `volume[t]` остаётся).

- [ ] **Step 8: Update s05_contribution.py — logistics_cost_per_kg_arr[t]**

В `backend/app/engine/steps/s05_contribution.py`:

```python
logistics_t = pi.logistics_cost_per_kg_arr[t]
```

Использовать в формуле логистики вместо скаляра.

- [ ] **Step 9: Update s06_ebitda.py — ca_m_rate_arr[t] и marketing_rate_arr[t]**

В `backend/app/engine/steps/s06_ebitda.py`:

```python
ca_m_t = pi.ca_m_rate_arr[t]
marketing_t = pi.marketing_rate_arr[t]
```

Использовать в формулах `ca_m_cost_t = net_revenue[t] * ca_m_t`, `marketing_cost_t = net_revenue[t] * marketing_t`.

- [ ] **Step 10: Remove old scalar fields from PipelineInput (cleanup)**

Удалить `copacking_rate`, `logistics_cost_per_kg`, `ca_m_rate`, `marketing_rate` из PipelineInput (они больше не используются). Удалить их инициализацию в `_build_line_input`.

- [ ] **Step 11: Run full backend tests — drift = 0**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```
Expected: `498 passed` (новые helper-тесты + старые без регрессии). Если какие-то старые тесты сломались на удалённых скаляр-полях — добавить shim в PipelineInput (property) или обновить тесты.

- [ ] **Step 12: Commit**

```bash
git add backend/app/services/calculation_service.py backend/app/engine/pipeline.py \
        backend/app/engine/steps/s03_cogs.py backend/app/engine/steps/s05_contribution.py \
        backend/app/engine/steps/s06_ebitda.py \
        backend/tests/engine/test_resolve_period_value.py
git commit -m "$(cat <<'EOF'
feat(c14): engine — per-period values в pipeline

_resolve_period_value helper + PipelineInput.*_arr (длина 43).
Шаги s03/s05/s06 читают arr[t] вместо скаляр. При пустых override
arr заполнен скаляром → pipeline bit-identical (баseline preserved).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Acceptance — GORJI drift baseline preserved + override case

**Files:**
- Modify: `backend/tests/acceptance/test_e2e_gorji.py`

- [ ] **Step 1: Run existing acceptance — drift baseline**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/acceptance -m acceptance 2>&1 | tail -5
```
Expected: все существующие GORJI acceptance pass (включая `test_kpi_matches_excel_reference_within_5pct` с drift < 0.03%). Если drift вырос — регрессия в Task 7, откатить и расследовать.

- [ ] **Step 2: Add new override-acceptance test**

В `backend/tests/acceptance/test_e2e_gorji.py` (внутри класса `TestE2EGorji`) добавить:

```python
    async def test_override_changes_kpi_in_expected_direction(
        self,
        async_session: AsyncSession,
        gorji_imported_project: Project,
    ) -> None:
        """C #14: per-period override повышает копакинг → CONTRIBUTION падает.

        Сценарий: применить override copacking_rate=base*2 на все 36 monthly
        периодов Y1-Y3 → ожидаем падение CONTRIBUTION Y1-Y3 vs. baseline.
        """
        from app.engine.calc_v2 import run_pipeline  # или текущий entrypoint

        baseline_result = await run_pipeline(async_session, gorji_imported_project.id)
        baseline_contribution_y1 = baseline_result.kpi.contribution_by_year[0]

        sku = gorji_imported_project.skus[0]
        base = sku.copacking_rate
        override = [base * Decimal("2")] * 36 + [None] * 7  # M1..M36 удвоить, Y4..Y10 = скаляр
        sku.copacking_rate_by_period = override
        flag_modified(sku, "copacking_rate_by_period")
        await async_session.commit()

        new_result = await run_pipeline(async_session, gorji_imported_project.id)
        new_contribution_y1 = new_result.kpi.contribution_by_year[0]

        assert new_contribution_y1 < baseline_contribution_y1, (
            f"override должен снизить contribution Y1: baseline={baseline_contribution_y1}, "
            f"with override={new_contribution_y1}"
        )

    async def test_empty_override_bit_identical_to_baseline(
        self,
        async_session: AsyncSession,
        gorji_imported_project: Project,
    ) -> None:
        """C #14: NULL override → pipeline output идентичен скаляр-режиму."""
        from app.engine.calc_v2 import run_pipeline

        sku = gorji_imported_project.skus[0]
        assert sku.copacking_rate_by_period is None

        result_with_nulls = await run_pipeline(async_session, gorji_imported_project.id)

        # Установить override со всеми None — должно быть так же, как None целиком
        sku.copacking_rate_by_period = [None] * 43
        flag_modified(sku, "copacking_rate_by_period")
        await async_session.commit()

        result_with_explicit_nulls = await run_pipeline(async_session, gorji_imported_project.id)

        assert result_with_nulls.kpi.contribution_by_year == result_with_explicit_nulls.kpi.contribution_by_year
```

**ВНИМАНИЕ:** точные имена fixtures (`gorji_imported_project`) и entry-point pipeline (`run_pipeline` / `calc_v2.run`) могут отличаться. Свериться с существующим `test_e2e_gorji.py` (см. `test_kpi_matches_excel_reference_within_5pct` — оттуда брать паттерны).

- [ ] **Step 3: Run new acceptance tests**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/acceptance -m acceptance -k "override" -v
```
Expected: оба новых теста pass.

- [ ] **Step 4: Run full backend tests**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```
Expected: `500 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/acceptance/test_e2e_gorji.py
git commit -m "$(cat <<'EOF'
test(c14): acceptance — override применяется и NULL-режим bit-identical

Два новых теста: override copacking_rate*2 на M1-M36 снижает Y1
contribution; все-None override эквивалентен NULL целиком
(no-op pipeline). Существующий drift < 0.03% сохраняется.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Frontend — extract PeriodGrid + rename period-bulk-fill в shared

**Files:**
- Create: `frontend/components/shared/period-grid.tsx`
- Create: `frontend/components/shared/period-bulk-fill.tsx`
- Modify: `frontend/components/projects/financial-plan-bulk-fill.tsx` (превращается в re-export)
- Modify: `frontend/components/projects/financial-plan-editor.tsx` (использует `<PeriodGrid>`)

- [ ] **Step 1: Copy `financial-plan-bulk-fill.tsx` → `shared/period-bulk-fill.tsx`**

Run:
```bash
cp frontend/components/projects/financial-plan-bulk-fill.tsx \
   frontend/components/shared/period-bulk-fill.tsx
```

Открыть `frontend/components/shared/period-bulk-fill.tsx` и убедиться, что:
- Все импорты path-resolve валидны (если есть relative `../../lib/...` — поправить относительно нового пути).
- Имя компонента осталось `FinancialPlanBulkFill` или переименовано в `PeriodBulkFill` (рекомендация — переименовать; используй find&replace в файле).

Если переименовано — обновить commit-сообщение.

- [ ] **Step 2: Превратить старый файл в re-export**

Заменить весь контент `frontend/components/projects/financial-plan-bulk-fill.tsx` на:

```tsx
// Re-export для backward compat. Канонический путь:
// frontend/components/shared/period-bulk-fill.tsx
export { PeriodBulkFill as FinancialPlanBulkFill } from "@/components/shared/period-bulk-fill";
export type * from "@/components/shared/period-bulk-fill";
```

- [ ] **Step 3: Extract `PeriodGrid` из `financial-plan-editor.tsx`**

Открыть `frontend/components/projects/financial-plan-editor.tsx`, найти 43-колоночную таблицу (сейчас inline `<table>` или div-grid). Создать `frontend/components/shared/period-grid.tsx`:

```tsx
"use client";

import { periodLabel, modelYearOf } from "@/lib/financial-plan-utils";

export interface PeriodGridRow<T = unknown> {
  id: string | number;
  label: string;
  values: (T | null)[]; // length 43
  metadata?: Record<string, unknown>;
}

export interface PeriodGridProps<T = unknown> {
  rows: PeriodGridRow<T>[];
  onCellChange?: (rowId: PeriodGridRow["id"], periodIdx: number, value: T | null) => void;
  renderCell?: (value: T | null, rowId: PeriodGridRow["id"], periodIdx: number) => React.ReactNode;
  readOnly?: boolean;
  className?: string;
}

const PERIOD_COUNT = 43;

export function PeriodGrid<T>({
  rows,
  onCellChange,
  renderCell,
  readOnly,
  className,
}: PeriodGridProps<T>) {
  return (
    <div className={className}>
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-background text-left p-2">Row</th>
            {Array.from({ length: PERIOD_COUNT }, (_, i) => (
              <th key={i} className="p-2 text-xs whitespace-nowrap">
                {periodLabel(i + 1)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td className="sticky left-0 bg-background p-2 font-medium">{row.label}</td>
              {Array.from({ length: PERIOD_COUNT }, (_, i) => (
                <td key={i} className="p-1 border">
                  {renderCell ? (
                    renderCell(row.values[i] ?? null, row.id, i)
                  ) : (
                    <input
                      type="number"
                      value={row.values[i] === null ? "" : String(row.values[i])}
                      disabled={readOnly}
                      onChange={(e) => {
                        const raw = e.target.value;
                        const parsed = raw === "" ? null : (raw as unknown as T);
                        onCellChange?.(row.id, i, parsed);
                      }}
                      className="w-full bg-transparent text-right"
                    />
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

(Точные стили tailwind — выровнять с financial-plan-editor; задача plan'а — структура и API компонента, точная стилизация может быть скопирована из существующего editor'а.)

- [ ] **Step 4: Refactor `financial-plan-editor.tsx` to use PeriodGrid**

В `financial-plan-editor.tsx` заменить inline 43-колоночную таблицу на:

```tsx
<PeriodGrid<string>
  rows={items.map((it) => ({
    id: it.period_number,
    label: periodLabel(it.period_number),
    values: /* массив длины 43 для opex/capex/... */,
  }))}
  onCellChange={handleCellChange}
/>
```

Логика данных не меняется — меняется только рендер.

- [ ] **Step 5: Run frontend type-check**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```
Expected: 0 errors.

- [ ] **Step 6: Full restart фронта (Windows+Docker HMR баг)**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend rm -rf .next
docker compose -f infra/docker-compose.dev.yml restart frontend
```

Подождать 30 секунд. Открыть в браузере страницу проекта с финпланом → таблица должна рендериться идентично прежнему (refactor визуально-прозрачный).

- [ ] **Step 7: Commit**

```bash
git add frontend/components/shared/period-grid.tsx \
        frontend/components/shared/period-bulk-fill.tsx \
        frontend/components/projects/financial-plan-bulk-fill.tsx \
        frontend/components/projects/financial-plan-editor.tsx
git commit -m "$(cat <<'EOF'
refactor(c14): extract PeriodGrid + перенос bulk-fill в shared

PeriodGrid — generic 43-колоночный grid (вытащено из financial-plan-
editor). FinancialPlanBulkFill переименован в PeriodBulkFill,
переехал в shared/. Старый импорт сохранён через re-export.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Frontend — Fine Tuning per-period panel + API client + page

**Files:**
- Create: `frontend/lib/api/fine-tuning.ts`
- Create: `frontend/components/projects/fine-tuning-per-period-panel.tsx`
- Create: `frontend/components/projects/fine-tuning-copacking-section.tsx`
- Create: `frontend/components/projects/fine-tuning-channel-section.tsx`
- Create: `frontend/app/projects/[id]/fine-tuning/page.tsx`
- Modify: `frontend/types/api.ts`
- Modify: `frontend/contexts/project-nav-context.tsx`

- [ ] **Step 1: Add types в `frontend/types/api.ts`**

```typescript
// C #14: Fine Tuning per-period overrides
export interface SkuOverridesResponse {
  copacking_rate_by_period: (string | null)[] | null;  // length 43 если не null
}

export interface ChannelOverridesResponse {
  logistics_cost_per_kg_by_period: (string | null)[] | null;
  ca_m_rate_by_period: (string | null)[] | null;
  marketing_rate_by_period: (string | null)[] | null;
}

export type SkuOverridesPayload = SkuOverridesResponse;
export type ChannelOverridesPayload = ChannelOverridesResponse;
```

- [ ] **Step 2: Create `frontend/lib/api/fine-tuning.ts`**

```typescript
import type {
  ChannelOverridesPayload,
  ChannelOverridesResponse,
  SkuOverridesPayload,
  SkuOverridesResponse,
} from "@/types/api";
import { apiClient } from "@/lib/api/client";

export async function getSkuOverrides(
  projectId: number,
  skuId: number,
): Promise<SkuOverridesResponse> {
  return apiClient.get(`/projects/${projectId}/fine-tuning/per-period/sku/${skuId}`);
}

export async function putSkuOverrides(
  projectId: number,
  skuId: number,
  payload: SkuOverridesPayload,
): Promise<void> {
  await apiClient.put(`/projects/${projectId}/fine-tuning/per-period/sku/${skuId}`, payload);
}

export async function getChannelOverrides(
  projectId: number,
  channelId: number,
): Promise<ChannelOverridesResponse> {
  return apiClient.get(`/projects/${projectId}/fine-tuning/per-period/channel/${channelId}`);
}

export async function putChannelOverrides(
  projectId: number,
  channelId: number,
  payload: ChannelOverridesPayload,
): Promise<void> {
  await apiClient.put(`/projects/${projectId}/fine-tuning/per-period/channel/${channelId}`, payload);
}
```

**Точное имя `apiClient` или axios-instance** — посмотреть `frontend/lib/api/financial-plan.ts` (B.9b) и использовать ту же утилиту.

- [ ] **Step 3a: Create panel orchestrator**

`frontend/components/projects/fine-tuning-per-period-panel.tsx` (только compose):

```tsx
"use client";

import { CopackingSection } from "./fine-tuning-copacking-section";
import { ChannelSection } from "./fine-tuning-channel-section";
import type { Project } from "@/types/api";

interface Props {
  project: Project;
}

export function FineTuningPerPeriodPanel({ project }: Props) {
  return (
    <div className="space-y-8">
      <CopackingSection project={project} />
      <ChannelSection project={project} field="logistics_cost_per_kg" label="Логистика (₽/кг)" />
      <ChannelSection project={project} field="ca_m_rate" label="CA&M rate" />
      <ChannelSection project={project} field="marketing_rate" label="Маркетинг rate" />
    </div>
  );
}
```

- [ ] **Step 3b: Create CopackingSection (per-SKU)**

`frontend/components/projects/fine-tuning-copacking-section.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { PeriodGrid } from "@/components/shared/period-grid";
import { getSkuOverrides, putSkuOverrides } from "@/lib/api/fine-tuning";
import type { Project } from "@/types/api";

export function CopackingSection({ project }: { project: Project }) {
  const [rows, setRows] = useState<Record<number, (string | null)[]>>({});
  const [dirty, setDirty] = useState<Set<number>>(new Set());

  useEffect(() => {
    Promise.all(project.skus.map((sku) => getSkuOverrides(project.id, sku.id)))
      .then((responses) => {
        const next: Record<number, (string | null)[]> = {};
        project.skus.forEach((sku, idx) => {
          next[sku.id] = responses[idx].copacking_rate_by_period ?? Array(43).fill(null);
        });
        setRows(next);
      });
  }, [project.id]);

  const handleCellChange = (skuId: number | string, idx: number, value: string | null) => {
    setRows((prev) => {
      const arr = [...(prev[Number(skuId)] ?? Array(43).fill(null))];
      arr[idx] = value;
      return { ...prev, [Number(skuId)]: arr };
    });
    setDirty((s) => new Set(s).add(Number(skuId)));
  };

  const handleSave = async () => {
    await Promise.all(Array.from(dirty).map((skuId) => {
      const arr = rows[skuId];
      const allNull = arr.every((v) => v === null);
      return putSkuOverrides(project.id, skuId, {
        copacking_rate_by_period: allNull ? null : arr,
      });
    }));
    setDirty(new Set());
  };

  return (
    <section>
      <h3 className="text-lg font-semibold mb-2">Copacking rate (₽/ед)</h3>
      <PeriodGrid
        rows={project.skus.map((sku) => ({
          id: sku.id,
          label: sku.product?.name ?? `SKU ${sku.id}`,
          values: rows[sku.id] ?? Array(43).fill(null),
        }))}
        onCellChange={handleCellChange}
      />
      <div className="flex gap-2 mt-2">
        <button disabled={!dirty.size} onClick={handleSave} className="btn-primary">
          Сохранить ({dirty.size} изменений)
        </button>
      </div>
    </section>
  );
}
```

- [ ] **Step 3c: Create ChannelSection (generic per-channel)**

`frontend/components/projects/fine-tuning-channel-section.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { PeriodGrid } from "@/components/shared/period-grid";
import { getChannelOverrides, putChannelOverrides } from "@/lib/api/fine-tuning";
import type { Project, ChannelOverridesPayload } from "@/types/api";

type ChannelField = "logistics_cost_per_kg" | "ca_m_rate" | "marketing_rate";

export function ChannelSection({
  project,
  field,
  label,
}: {
  project: Project;
  field: ChannelField;
  label: string;
}) {
  const fieldKey = `${field}_by_period` as keyof ChannelOverridesPayload;

  const channels = project.skus.flatMap((sku) =>
    (sku.channels ?? []).map((ch) => ({ sku, channel: ch })),
  );

  const [rows, setRows] = useState<Record<number, (string | null)[]>>({});
  const [dirty, setDirty] = useState<Set<number>>(new Set());

  useEffect(() => {
    Promise.all(channels.map(({ channel }) => getChannelOverrides(project.id, channel.id)))
      .then((responses) => {
        const next: Record<number, (string | null)[]> = {};
        channels.forEach(({ channel }, idx) => {
          next[channel.id] = (responses[idx][fieldKey] as (string | null)[] | null) ?? Array(43).fill(null);
        });
        setRows(next);
      });
  }, [project.id, fieldKey]);

  const handleCellChange = (channelId: number | string, idx: number, value: string | null) => {
    setRows((prev) => {
      const arr = [...(prev[Number(channelId)] ?? Array(43).fill(null))];
      arr[idx] = value;
      return { ...prev, [Number(channelId)]: arr };
    });
    setDirty((s) => new Set(s).add(Number(channelId)));
  };

  const handleSave = async () => {
    // GET перед PUT чтобы не перезатереть два других поля канала.
    await Promise.all(Array.from(dirty).map(async (channelId) => {
      const current = await getChannelOverrides(project.id, channelId);
      const arr = rows[channelId];
      const allNull = arr.every((v) => v === null);
      const payload: ChannelOverridesPayload = {
        logistics_cost_per_kg_by_period: current.logistics_cost_per_kg_by_period,
        ca_m_rate_by_period: current.ca_m_rate_by_period,
        marketing_rate_by_period: current.marketing_rate_by_period,
      };
      (payload as Record<string, unknown>)[fieldKey] = allNull ? null : arr;
      await putChannelOverrides(project.id, channelId, payload);
    }));
    setDirty(new Set());
  };

  return (
    <section>
      <h3 className="text-lg font-semibold mb-2">{label}</h3>
      <PeriodGrid
        rows={channels.map(({ sku, channel }) => ({
          id: channel.id,
          label: `${sku.product?.name ?? `SKU ${sku.id}`} → ${channel.channel?.name ?? `Ch ${channel.id}`}`,
          values: rows[channel.id] ?? Array(43).fill(null),
        }))}
        onCellChange={handleCellChange}
      />
      <div className="flex gap-2 mt-2">
        <button disabled={!dirty.size} onClick={handleSave} className="btn-primary">
          Сохранить ({dirty.size} изменений)
        </button>
      </div>
    </section>
  );
}
```

**Примечание:** `handleSave` делает дополнительный GET перед PUT чтобы не перезатереть два других поля канала. Если N+1 станет проблемой — заменить на shared state всех 3 полей канала с одним PUT.

- [ ] **Step 4: Create page**

`frontend/app/projects/[id]/fine-tuning/page.tsx`:

```tsx
import { FineTuningPerPeriodPanel } from "@/components/projects/fine-tuning-per-period-panel";
import { fetchProject } from "@/lib/api/projects";

interface PageProps {
  params: { id: string };
}

export default async function FineTuningPage({ params }: PageProps) {
  const project = await fetchProject(Number(params.id));
  return (
    <div className="container py-6">
      <h1 className="text-2xl font-bold mb-4">Fine Tuning — per-period overrides</h1>
      <FineTuningPerPeriodPanel project={project} />
    </div>
  );
}
```

- [ ] **Step 5: Add nav entry в `project-nav-context.tsx`**

Найти массив `navItems` (или аналогичный) в `frontend/contexts/project-nav-context.tsx`. Добавить:

```typescript
{
  key: "fine-tuning",
  label: "Fine Tuning",
  href: (projectId: number) => `/projects/${projectId}/fine-tuning`,
}
```

Точный shape NavItem смотреть в существующем контексте.

- [ ] **Step 6: Run frontend type-check**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```
Expected: 0 errors.

- [ ] **Step 7: Full restart фронта**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend rm -rf .next
docker compose -f infra/docker-compose.dev.yml restart frontend
```

- [ ] **Step 8: Manual smoke test**

В браузере:
1. Открыть проект → пункт «Fine Tuning» в навигации → страница рендерится.
2. 4 секции видны (Copacking, Logistics, CA&M, Marketing).
3. Ввести значение в одну ячейку Copacking → нажать «Сохранить» → перезагрузить → значение сохранилось.
4. Очистить ячейку → сохранить → значение = null (placeholder показывается).
5. Bulk-fill: открыть диалог «Распределить год» → ввести annual → раскидало по 12 ячейкам Y1.
6. Запустить пересчёт KPI → KPI изменилось.

- [ ] **Step 9: Commit**

```bash
git add frontend/lib/api/fine-tuning.ts \
        frontend/components/projects/fine-tuning-per-period-panel.tsx \
        frontend/components/projects/fine-tuning-copacking-section.tsx \
        frontend/components/projects/fine-tuning-channel-section.tsx \
        frontend/app/projects/[id]/fine-tuning/page.tsx \
        frontend/types/api.ts \
        frontend/contexts/project-nav-context.tsx
git commit -m "$(cat <<'EOF'
feat(c14): Fine Tuning per-period UI — 4 секции с reuse PeriodGrid

Новая страница /projects/[id]/fine-tuning. 4 секции:
copacking (per-SKU), logistics / CA&M / marketing (per-channel).
Reuse PeriodGrid и PeriodBulkFill из shared. API client + nav entry.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Docs — CHANGELOG + ARCHITECTURE + DECISIONS

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/CLIENT_FEEDBACK_v2_DECISIONS.md`
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Update CHANGELOG**

В `CHANGELOG.md` в секции `[Unreleased]` добавить под `### Added` (или соответствующий):

```markdown
- **C #14 Fine Tuning per-period:** override 4 финансовых полей (copacking_rate, logistics_cost_per_kg, ca_m_rate, marketing_rate) на per-period (43 точки = M1..M36 + Y4..Y10). Реализовано через JSONB-массивы на ProjectSKU / ProjectSKUChannel. Pipeline получает tuple-43 в шагах s03/s05/s06. Frontend: новый Fine Tuning tab с 4 секциями, reuse PeriodGrid и PeriodBulkFill из shared. NULL override = fallback на скаляр (backward-compat).
```

- [ ] **Step 2: Mark #14 done в DECISIONS**

В `docs/CLIENT_FEEDBACK_v2_DECISIONS.md` найти раздел про #14 (строки ~220-225). Добавить запись о закрытии:

```markdown
**Статус:** ✅ Closed 2026-05-15 (commit: см. `git log --grep=c14`)
**Реализация:** JSONB-on-table, scope copacking = per-SKU, остальные 3 = per-channel.
Spec: `docs/superpowers/specs/2026-05-15-c14-fine-tuning-per-period-design.md`.
Plan: `docs/superpowers/plans/2026-05-15-c14-fine-tuning-per-period.md`.
```

- [ ] **Step 3: Update ARCHITECTURE.md**

В `docs/ARCHITECTURE.md` добавить раздел (после описания PeriodValue / финплана):

```markdown
### Per-period overrides (C #14)

4 финансовых поля могут переопределяться помесячно (M1..M36) + по годам
(Y4..Y10) через JSONB-массивы длины 43:
- `ProjectSKU.copacking_rate_by_period` (per-SKU)
- `ProjectSKUChannel.{logistics_cost_per_kg, ca_m_rate, marketing_rate}_by_period`
  (per-channel)

Семантика: `effective[i] = by_period[i] if not None else scalar`. NULL =
нет override (backward-compat). Pipeline получает tuple-43 через
`_resolve_period_value` helper в `calculation_service`.

Паттерн изоморфен `production_mode_by_year` (B.8) и `bom_cost_level_by_year`
(B.11). Отличие от `PeriodValue` (B.5 OBPPC): override = «как пользователь
правит план», PeriodValue = «снимок фактов из импорта».
```

- [ ] **Step 4: Verify clean state**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
git status --short
```
Expected: `500 passed` (или больше с frontend tests если есть); tsc empty; git только три модифицированных doc-файла.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md docs/CLIENT_FEEDBACK_v2_DECISIONS.md docs/ARCHITECTURE.md
git commit -m "$(cat <<'EOF'
docs(c14): CHANGELOG + DECISIONS + ARCHITECTURE — C #14 закрыт

C #14 Fine Tuning per-period расширение зафиксировано в:
- CHANGELOG [Unreleased]
- CLIENT_FEEDBACK_v2_DECISIONS.md (статус closed)
- ARCHITECTURE.md (раздел Per-period overrides)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final Verification

После завершения всех задач:

```bash
# 1. Все тесты зелёные
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
# Expected: 500+ passed

# 2. Acceptance GORJI drift сохраняется
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/acceptance -m acceptance 2>&1 | tail -10
# Expected: drift < 0.03% во всех KPI-сравнениях

# 3. Frontend tsc clean
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
# Expected: empty

# 4. Smoke test UI вручную (см. Task 10 step 8)

# 5. Git log проверка
git log --oneline -15
# Expected: ~10 коммитов с тегом (c14)
```

После approval — финальный merge в `main` (если работаем в worktree / feature branch) или push текущей ветки.

---

## Backlog (после C #14)

Из spec §8:
1. Верифицировать `logistics_per_l` vs `_per_kg` в GORJI Excel; при необходимости переименование с миграцией.
2. Excel-import override (если в GORJI Excel есть per-period колонки).
3. Quick-edit override в BOM panel / Channel form (по UX-feedback).
4. Table-level «Сбросить все override» bulk-кнопка (по UX-feedback).
