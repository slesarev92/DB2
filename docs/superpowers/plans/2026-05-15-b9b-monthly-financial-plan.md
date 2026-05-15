# B.9b: Monthly Financial Plan (Y1-Y3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переключить редактор финплана с 10 годовых ячеек на 43 точки (M1..M36 + Y4..Y10) с bulk-fill UX, без изменения движка расчётов.

**Architecture:** Engine уже работает per-period (43 точки) — не трогаем. Меняем API-контракт `year → period_number`, переписываем service-слой и frontend-редактор. Существующие данные не мигрируем (lazy expand + UI-banner).

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy + Pydantic / Next.js 14 + TypeScript + shadcn/ui / pytest + tsc.

---

## File Structure

**Create:**
- `frontend/lib/financial-plan-utils.ts` — pure helpers (distributeYear, fillRange, isLegacyData, periodLabel)
- `frontend/components/projects/financial-plan-bulk-fill.tsx` — Dialog с режимами "Распределить год" и "Залить диапазон"

**Modify:**
- `backend/app/schemas/financial_plan.py` — `FinancialPlanItem.year` → `period_number` + валидатор уникальности в `FinancialPlanRequest`
- `backend/app/services/financial_plan_service.py` — `list_plan_by_period` (43 элемента) + `replace_plan` по `period_number`
- `backend/app/api/financial_plan.py` — обновить docstring (endpoint логика не меняется)
- `backend/tests/api/test_financial_plan.py` — переписать тесты под `period_number`/43 элемента
- `frontend/types/api.ts` — `FinancialPlanItem.year` → `period_number`
- `frontend/lib/financial-plan.ts` — обновить docstring
- `frontend/components/projects/financial-plan-editor.tsx` — переписать на 43-колоночную таблицу со sticky left column + banner для legacy + интеграция bulk-fill
- `CHANGELOG.md` — секция `[Unreleased]`, отметить B.9b done

**Не трогаем (доказано в spec § 2):** engine (`pipeline.py`, `s01..s12.py`, `aggregator.py`), `_load_project_financial_plan` в calculation_service, экспорт XLSX/PDF/PPTX, миграции БД.

---

## Conventions

- Все backend-команды: `docker compose -f infra/docker-compose.dev.yml exec -T backend ...`
- Все frontend-команды: `docker compose -f infra/docker-compose.dev.yml exec -T frontend ...`
- Sortcut: использовать переменную в сессии — `BE='docker compose -f infra/docker-compose.dev.yml exec -T backend'`, `FE='docker compose -f infra/docker-compose.dev.yml exec -T frontend'`. В шагах ниже команды пишутся полностью.
- В коммите всегда добавлять `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` (CLAUDE.md).
- Формат коммита: `тип(область): описание` (CLAUDE.md). Тип: `feat`/`fix`/`refactor`/`test`/`docs`.

---

## Task 1: Baseline check

**Files:** none

- [ ] **Step 1: Verify baseline tests pass**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```
Expected: `472 passed`.

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

No commit at this task.

---

## Task 2: Backend schema — `year` → `period_number`

**Files:**
- Modify: `backend/app/schemas/financial_plan.py`

- [ ] **Step 1: Write failing test (new schema contract)**

Append to `backend/tests/api/test_financial_plan.py` (at the end, before existing tests are migrated in Task 5):

```python
# ============================================================
# B.9b: schema contract tests for period_number
# ============================================================
import pytest
from pydantic import ValidationError

from app.schemas.financial_plan import FinancialPlanItem, FinancialPlanRequest


def test_financial_plan_item_accepts_period_number() -> None:
    item = FinancialPlanItem(period_number=1, capex="100", opex="0")
    assert item.period_number == 1


def test_financial_plan_item_rejects_period_number_out_of_range() -> None:
    with pytest.raises(ValidationError):
        FinancialPlanItem(period_number=0, capex="0", opex="0")
    with pytest.raises(ValidationError):
        FinancialPlanItem(period_number=44, capex="0", opex="0")


def test_financial_plan_item_no_year_field() -> None:
    # year field is gone; passing it should be ignored (Pydantic v2 default extra="ignore").
    item = FinancialPlanItem(period_number=1, year=1, capex="0", opex="0")
    assert not hasattr(item, "year")


def test_financial_plan_request_rejects_duplicate_period_number() -> None:
    with pytest.raises(ValidationError):
        FinancialPlanRequest(items=[
            FinancialPlanItem(period_number=1, capex="100", opex="0"),
            FinancialPlanItem(period_number=1, capex="200", opex="0"),
        ])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q backend/tests/api/test_financial_plan.py::test_financial_plan_item_accepts_period_number -v
```
Expected: FAIL — `FinancialPlanItem` has no `period_number` field.

- [ ] **Step 3: Update `backend/app/schemas/financial_plan.py`**

Replace the `FinancialPlanItem` and `FinancialPlanRequest` classes:

```python
from pydantic import BaseModel, Field, model_validator


class FinancialPlanItem(BaseModel):
    """Одна строка плана для одного периода (M1..M36 + Y4..Y10).

    B.9b (2026-05-15): per-period вместо per-year. period_number — 1..43,
    маппится на справочник `periods` (1..36 = monthly Y1-Y3, 37..43 = yearly Y4-Y10).

    Логика автосуммирования:
    - opex_items не пустой → opex = sum(opex_items.amount).
    - capex_items не пустой → capex = sum(capex_items.amount).
    """

    period_number: int = Field(..., ge=1, le=43, description="period 1..43")
    capex: Decimal = Field(default=Decimal("0"), ge=0)
    opex: Decimal = Field(default=Decimal("0"), ge=0)
    opex_items: list[OpexItemSchema] = Field(default_factory=list)
    capex_items: list[CapexItemSchema] = Field(default_factory=list)


class FinancialPlanRequest(BaseModel):
    """Тело PUT /api/projects/{id}/financial-plan.

    Полная замена плана: backend удаляет все существующие записи
    `project_financial_plans` для project_id и вставляет новые по
    переданному списку. period_number'ы которых нет в списке → 0/0 в GET.

    Валидация: period_number уникальны в массиве.
    """

    items: list[FinancialPlanItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_period_uniqueness(self) -> "FinancialPlanRequest":
        seen: set[int] = set()
        for item in self.items:
            if item.period_number in seen:
                raise ValueError(
                    f"Duplicate period_number={item.period_number} in items"
                )
            seen.add(item.period_number)
        return self
```

- [ ] **Step 4: Run new tests to verify they pass**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q backend/tests/api/test_financial_plan.py -k "period_number" -v
```
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/financial_plan.py backend/tests/api/test_financial_plan.py
git commit -m "$(cat <<'EOF'
feat(b9b): schema FinancialPlanItem.year → period_number (1..43)

Pydantic-схема перешла с year (1..10) на period_number (1..43) для
покрытия 36 monthly Y1-Y3 + 7 yearly Y4-Y10. FinancialPlanRequest
валидирует уникальность period_number в массиве.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Service — `list_plan_by_period` (43 элемента)

**Files:**
- Modify: `backend/app/services/financial_plan_service.py`

- [ ] **Step 1: Write failing test for `list_plan_by_period`**

Append to `backend/tests/api/test_financial_plan.py`:

```python
# ============================================================
# B.9b: list_plan_by_period returns 43 elements
# ============================================================
from app.services import financial_plan_service


async def test_list_plan_by_period_returns_43_elements(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    plan = await financial_plan_service.list_plan_by_period(
        db_session, project_id
    )
    assert len(plan) == 43
    period_numbers = [item.period_number for item in plan]
    assert period_numbers == list(range(1, 44))
    for item in plan:
        assert item.capex == Decimal("0")
        assert item.opex == Decimal("0")
        assert item.opex_items == []
        assert item.capex_items == []
```

- [ ] **Step 2: Run test, expect fail**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q backend/tests/api/test_financial_plan.py::test_list_plan_by_period_returns_43_elements -v
```
Expected: FAIL — `list_plan_by_period` doesn't exist.

- [ ] **Step 3: Rewrite `financial_plan_service.py`**

Replace the entire file with:

```python
"""Service слой для ProjectFinancialPlan.

B.9b (2026-05-15): per-period вместо per-year. list_plan_by_period
возвращает 43 элемента (1 на каждый период справочника). replace_plan
сохраняет по period_number.

Маппинг period_number → period_id через справочник `periods`:
period_number 1..36 = monthly Y1-Y3 (M1..M36, model_year 1..3),
period_number 37..43 = yearly Y4..Y10 (model_year 4..10).
"""
from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import CapexItem, OpexItem, Period, ProjectFinancialPlan
from app.schemas.financial_plan import (
    CapexItemSchema,
    FinancialPlanItem,
    OpexItemSchema,
)

logger = logging.getLogger(__name__)


async def _get_period_id_by_number(
    session: AsyncSession,
) -> dict[int, int]:
    """Возвращает {period_number → period_id} для всех 43 периодов справочника."""
    rows = (
        await session.scalars(select(Period).order_by(Period.period_number))
    ).all()
    return {p.period_number: p.id for p in rows}


async def list_plan_by_period(
    session: AsyncSession,
    project_id: int,
) -> list[FinancialPlanItem]:
    """Всегда 43 строки (period_number 1..43). Отсутствующие заполняются нулями.

    Загружает все ProjectFinancialPlan записи проекта + Period (для маппинга
    на period_number) + opex_items/capex_items через selectinload.
    """
    rows = (
        await session.execute(
            select(ProjectFinancialPlan, Period)
            .join(Period, Period.id == ProjectFinancialPlan.period_id)
            .where(ProjectFinancialPlan.project_id == project_id)
            .options(
                selectinload(ProjectFinancialPlan.opex_items),
                selectinload(ProjectFinancialPlan.capex_items),
            )
        )
    ).all()

    # Индексируем по period_number
    by_period: dict[int, tuple[ProjectFinancialPlan, Period]] = {
        period.period_number: (plan, period) for plan, period in rows
    }

    result: list[FinancialPlanItem] = []
    for pn in range(1, 44):
        if pn in by_period:
            plan, _ = by_period[pn]
            result.append(
                FinancialPlanItem(
                    period_number=pn,
                    capex=plan.capex,
                    opex=plan.opex,
                    opex_items=[
                        OpexItemSchema(
                            category=item.category,
                            name=item.name,
                            amount=item.amount,
                        )
                        for item in plan.opex_items
                    ],
                    capex_items=[
                        CapexItemSchema(
                            category=item.category,
                            name=item.name,
                            amount=item.amount,
                        )
                        for item in plan.capex_items
                    ],
                )
            )
        else:
            result.append(
                FinancialPlanItem(
                    period_number=pn,
                    capex=Decimal("0"),
                    opex=Decimal("0"),
                    opex_items=[],
                    capex_items=[],
                )
            )
    return result


async def replace_plan(
    session: AsyncSession,
    project_id: int,
    items: list[FinancialPlanItem],
) -> list[FinancialPlanItem]:
    """Полная замена плана проекта.

    1. DELETE все существующие ProjectFinancialPlan для project_id
       (CASCADE удаляет opex_items и capex_items)
    2. INSERT новые записи по period_number → period_id
    3. INSERT OpexItem и CapexItem
    4. Возвращает `list_plan_by_period` (43 элемента)

    period_number'ы которых нет в items → 0/0 в результате.
    """
    logger.info(
        "replace_plan project_id=%s items=%s",
        project_id,
        [
            (
                item.period_number,
                str(item.capex),
                str(item.opex),
                len(item.opex_items or []),
                len(item.capex_items or []),
            )
            for item in items
        ],
    )

    await session.execute(
        sql_delete(ProjectFinancialPlan).where(
            ProjectFinancialPlan.project_id == project_id
        )
    )

    period_map = await _get_period_id_by_number(session)

    for item in items:
        period_id = period_map.get(item.period_number)
        if period_id is None:
            continue  # period_number не в справочнике — игнорируем

        effective_opex = item.opex
        if item.opex_items:
            effective_opex = sum(
                (oi.amount for oi in item.opex_items), Decimal("0")
            )
        effective_capex = item.capex
        if item.capex_items:
            effective_capex = sum(
                (ci.amount for ci in item.capex_items), Decimal("0")
            )

        plan = ProjectFinancialPlan(
            project_id=project_id,
            period_id=period_id,
            capex=effective_capex,
            opex=effective_opex,
        )
        session.add(plan)

        if item.opex_items or item.capex_items:
            await session.flush()
            for oi in item.opex_items:
                session.add(
                    OpexItem(
                        financial_plan_id=plan.id,
                        category=oi.category,
                        name=oi.name,
                        amount=oi.amount,
                    )
                )
            for ci in item.capex_items:
                session.add(
                    CapexItem(
                        financial_plan_id=plan.id,
                        category=ci.category,
                        name=ci.name,
                        amount=ci.amount,
                    )
                )

    await session.flush()
    return await list_plan_by_period(session, project_id)
```

- [ ] **Step 4: Run test, expect pass**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q backend/tests/api/test_financial_plan.py::test_list_plan_by_period_returns_43_elements -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/financial_plan_service.py backend/tests/api/test_financial_plan.py
git commit -m "$(cat <<'EOF'
feat(b9b): service list_plan_by_period (43 элемента) + replace_plan по period_number

financial_plan_service переписан под per-period схему. _get_first_period_by_year
заменён на _get_period_id_by_number возвращающий {period_number → period_id}.
list_plan_by_period возвращает все 43 элемента (отсутствующие нулевые).
replace_plan маппит period_number на period_id через справочник.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Backend tests — переписать under `period_number`

**Files:**
- Modify: `backend/tests/api/test_financial_plan.py`

- [ ] **Step 1: Rewrite `test_financial_plan.py` for new contract**

Replace the entire file with:

```python
"""Тесты GET/PUT /api/projects/{id}/financial-plan.

B.9b (2026-05-15): per-period контракт. 43 элемента (1..43):
period 1..36 = monthly Y1-Y3, period 37..43 = yearly Y4-Y10.
"""
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OpexItem, Period, ProjectFinancialPlan
from app.schemas.financial_plan import FinancialPlanItem, FinancialPlanRequest
from app.services import financial_plan_service


VALID_PROJECT = {
    "name": "Financial plan test",
    "start_date": "2025-01-01",
    "horizon_years": 10,
    "wacc": "0.19",
    "tax_rate": "0.20",
    "wc_rate": "0.12",
    "vat_rate": "0.20",
    "currency": "RUB",
}


async def _create_project(auth_client: AsyncClient) -> int:
    resp = await auth_client.post("/api/projects", json=VALID_PROJECT)
    assert resp.status_code == 201
    return resp.json()["id"]


# ============================================================
# Schema contract
# ============================================================


def test_financial_plan_item_accepts_period_number() -> None:
    item = FinancialPlanItem(period_number=1, capex="100", opex="0")
    assert item.period_number == 1


def test_financial_plan_item_rejects_period_number_out_of_range() -> None:
    with pytest.raises(ValidationError):
        FinancialPlanItem(period_number=0, capex="0", opex="0")
    with pytest.raises(ValidationError):
        FinancialPlanItem(period_number=44, capex="0", opex="0")


def test_financial_plan_request_rejects_duplicate_period_number() -> None:
    with pytest.raises(ValidationError):
        FinancialPlanRequest(items=[
            FinancialPlanItem(period_number=1, capex="100", opex="0"),
            FinancialPlanItem(period_number=1, capex="200", opex="0"),
        ])


# ============================================================
# Service
# ============================================================


async def test_list_plan_by_period_returns_43_elements(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    plan = await financial_plan_service.list_plan_by_period(
        db_session, project_id
    )
    assert len(plan) == 43
    period_numbers = [item.period_number for item in plan]
    assert period_numbers == list(range(1, 44))
    for item in plan:
        assert item.capex == Decimal("0")
        assert item.opex == Decimal("0")


# ============================================================
# GET — empty project returns 43 zeros
# ============================================================


async def test_get_plan_returns_43_periods_zeros_by_default(
    auth_client: AsyncClient,
) -> None:
    project_id = await _create_project(auth_client)
    resp = await auth_client.get(f"/api/projects/{project_id}/financial-plan")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 43
    period_numbers = [item["period_number"] for item in data]
    assert period_numbers == list(range(1, 44))
    for item in data:
        assert Decimal(item["capex"]) == Decimal("0")
        assert Decimal(item["opex"]) == Decimal("0")


async def test_get_plan_unknown_project_404(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/api/projects/999999/financial-plan")
    assert resp.status_code == 404


async def test_get_plan_unauthorized(client: AsyncClient) -> None:
    resp = await client.get("/api/projects/1/financial-plan")
    assert resp.status_code == 401


# ============================================================
# PUT — basic record creation
# ============================================================


async def test_put_plan_creates_records_at_specific_periods(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    body = {
        "items": [
            {"period_number": 3,  "capex": "15000000", "opex": "0"},
            {"period_number": 13, "capex": "5440000",  "opex": "320000"},
            {"period_number": 37, "capex": "0",        "opex": "1500000"},
        ]
    }
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=body
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 43

    p3 = next(i for i in data if i["period_number"] == 3)
    assert Decimal(p3["capex"]) == Decimal("15000000")
    p13 = next(i for i in data if i["period_number"] == 13)
    assert Decimal(p13["capex"]) == Decimal("5440000")
    assert Decimal(p13["opex"]) == Decimal("320000")
    p37 = next(i for i in data if i["period_number"] == 37)
    assert Decimal(p37["opex"]) == Decimal("1500000")

    # Periods не в items → нули
    p1 = next(i for i in data if i["period_number"] == 1)
    assert Decimal(p1["capex"]) == Decimal("0")
    assert Decimal(p1["opex"]) == Decimal("0")

    rows = (
        await db_session.scalars(
            select(ProjectFinancialPlan).where(
                ProjectFinancialPlan.project_id == project_id
            )
        )
    ).all()
    assert len(list(rows)) == 3


async def test_put_plan_replaces_existing(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    first = {"items": [{"period_number": 1, "capex": "1000", "opex": "0"}]}
    await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=first
    )
    second = {"items": [{"period_number": 5, "capex": "2000", "opex": "0"}]}
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=second
    )
    data = resp.json()
    p1 = next(i for i in data if i["period_number"] == 1)
    assert Decimal(p1["capex"]) == Decimal("0")
    p5 = next(i for i in data if i["period_number"] == 5)
    assert Decimal(p5["capex"]) == Decimal("2000")

    rows = (
        await db_session.scalars(
            select(ProjectFinancialPlan).where(
                ProjectFinancialPlan.project_id == project_id
            )
        )
    ).all()
    assert len(list(rows)) == 1


async def test_put_plan_empty_items_clears(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    await auth_client.put(
        f"/api/projects/{project_id}/financial-plan",
        json={"items": [{"period_number": 1, "capex": "1000", "opex": "0"}]},
    )
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json={"items": []}
    )
    assert resp.status_code == 200
    data = resp.json()
    for item in data:
        assert Decimal(item["capex"]) == Decimal("0")
        assert Decimal(item["opex"]) == Decimal("0")

    rows = (
        await db_session.scalars(
            select(ProjectFinancialPlan).where(
                ProjectFinancialPlan.project_id == project_id
            )
        )
    ).all()
    assert len(list(rows)) == 0


async def test_put_plan_mapped_to_correct_period(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    """period_number 1 → M1, period_number 37 → первый yearly (Y4)."""
    project_id = await _create_project(auth_client)
    await auth_client.put(
        f"/api/projects/{project_id}/financial-plan",
        json={
            "items": [
                {"period_number": 1,  "capex": "100", "opex": "0"},
                {"period_number": 37, "capex": "400", "opex": "0"},
            ]
        },
    )
    rows = (
        await db_session.execute(
            select(ProjectFinancialPlan, Period)
            .join(Period, Period.id == ProjectFinancialPlan.period_id)
            .where(ProjectFinancialPlan.project_id == project_id)
        )
    ).all()
    assert len(rows) == 2
    by_pn = {p.period_number: (plan, p) for plan, p in rows}
    assert by_pn[1][1].model_year == 1
    assert by_pn[1][0].capex == Decimal("100")
    assert by_pn[37][1].model_year == 4
    assert by_pn[37][0].capex == Decimal("400")


async def test_put_plan_rejects_duplicate_period_numbers(
    auth_client: AsyncClient,
) -> None:
    project_id = await _create_project(auth_client)
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan",
        json={
            "items": [
                {"period_number": 1, "capex": "100", "opex": "0"},
                {"period_number": 1, "capex": "200", "opex": "0"},
            ]
        },
    )
    assert resp.status_code == 422


async def test_put_plan_unauthorized(client: AsyncClient) -> None:
    resp = await client.put(
        "/api/projects/1/financial-plan", json={"items": []}
    )
    assert resp.status_code == 401


# ============================================================
# OPEX/CAPEX items breakdown
# ============================================================


async def test_get_plan_returns_empty_items_by_default(
    auth_client: AsyncClient,
) -> None:
    project_id = await _create_project(auth_client)
    resp = await auth_client.get(f"/api/projects/{project_id}/financial-plan")
    assert resp.status_code == 200
    for item in resp.json():
        assert item["opex_items"] == []
        assert item["capex_items"] == []


async def test_put_plan_with_opex_items_auto_sums(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    body = {
        "items": [
            {
                "period_number": 1,
                "capex": "100000",
                "opex": "999",
                "opex_items": [
                    {"name": "Аренда", "amount": "200000"},
                    {"name": "ЗП", "amount": "500000"},
                ],
            },
        ]
    }
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=body
    )
    assert resp.status_code == 200
    data = resp.json()
    p1 = next(i for i in data if i["period_number"] == 1)
    assert Decimal(p1["opex"]) == Decimal("700000")
    assert len(p1["opex_items"]) == 2

    opex_rows = (await db_session.scalars(select(OpexItem))).all()
    assert len(list(opex_rows)) == 2


async def test_put_plan_with_capex_items_auto_sums(
    auth_client: AsyncClient,
) -> None:
    project_id = await _create_project(auth_client)
    body = {
        "items": [
            {
                "period_number": 3,
                "capex": "999",
                "opex": "0",
                "capex_items": [
                    {"category": "molds", "name": "Молды партия 1", "amount": "10000000"},
                    {"category": "line",  "name": "Линия розлива",   "amount": "5000000"},
                ],
            },
        ]
    }
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=body
    )
    assert resp.status_code == 200
    p3 = next(i for i in resp.json() if i["period_number"] == 3)
    assert Decimal(p3["capex"]) == Decimal("15000000")
    assert len(p3["capex_items"]) == 2


async def test_put_plan_replace_clears_old_items(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    project_id = await _create_project(auth_client)
    first = {
        "items": [
            {
                "period_number": 1,
                "capex": "0",
                "opex_items": [
                    {"name": "Аренда", "amount": "100000"},
                    {"name": "ЗП", "amount": "200000"},
                ],
            },
        ]
    }
    await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=first
    )
    second = {
        "items": [
            {
                "period_number": 1,
                "capex": "0",
                "opex_items": [
                    {"name": "Новая", "amount": "50000"},
                ],
            },
        ]
    }
    resp = await auth_client.put(
        f"/api/projects/{project_id}/financial-plan", json=second
    )
    p1 = next(i for i in resp.json() if i["period_number"] == 1)
    assert Decimal(p1["opex"]) == Decimal("50000")
    assert len(p1["opex_items"]) == 1

    opex_rows = (await db_session.scalars(select(OpexItem))).all()
    assert len(list(opex_rows)) == 1
```

- [ ] **Step 2: Run all tests, expect pass**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q backend/tests/api/test_financial_plan.py -v
```
Expected: ~14 tests pass.

- [ ] **Step 3: Run full backend test suite to catch regressions**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q --ignore=tests/integration 2>&1 | tail -5
```
Expected: PASS, count ≈ 472 (may differ ±несколько в зависимости от удалённых/добавленных тестов; основное — нет фейлов и acceptance GORJI зелёный).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/api/test_financial_plan.py
git commit -m "$(cat <<'EOF'
test(b9b): переписать API-тесты финплана под period_number / 43 элемента

Удалены тесты под year-based контракт. Добавлены: GET возвращает 43,
PUT принимает period_number, дубли period_number → 422, маппинг
period_number=1 → M1 и =37 → Y4 проверен явно.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: API endpoint — docstring update

**Files:**
- Modify: `backend/app/api/financial_plan.py`

- [ ] **Step 1: Update the file**

Replace the file with:

```python
"""API endpoints для ProjectFinancialPlan — CAPEX/OPEX per-period.

B.9b (2026-05-15): per-period вместо per-year. 43 элемента в массиве
(1..43): period 1..36 — monthly Y1-Y3, period 37..43 — yearly Y4-Y10.

- GET /api/projects/{project_id}/financial-plan
  → всегда 43 строки (нули если записи нет)
- PUT /api/projects/{project_id}/financial-plan
  Body: {items: [{period_number, capex, opex, opex_items?, capex_items?}, ...]}
  → полная замена плана; period_number уникальны в массиве.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.financial_plan import (
    FinancialPlanItem,
    FinancialPlanRequest,
)
from app.services import financial_plan_service, invalidation_service, project_service

router = APIRouter(tags=["financial-plan"])

_project_not_found = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Project not found",
)


@router.get(
    "/api/projects/{project_id}/financial-plan",
    response_model=list[FinancialPlanItem],
)
async def get_project_financial_plan_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[FinancialPlanItem]:
    """Всегда 43 строки (period_number 1..43). Отсутствующие = 0."""
    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _project_not_found
    return await financial_plan_service.list_plan_by_period(session, project_id)


@router.put(
    "/api/projects/{project_id}/financial-plan",
    response_model=list[FinancialPlanItem],
)
async def put_project_financial_plan_endpoint(
    project_id: int,
    body: FinancialPlanRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[FinancialPlanItem]:
    """Полная замена плана проекта. Возвращает обновлённый список из 43 элементов."""
    project = await project_service.get_project(session, project_id, user=current_user)
    if project is None:
        raise _project_not_found
    result = await financial_plan_service.replace_plan(
        session, project_id, body.items
    )
    await invalidation_service.mark_project_stale(session, project_id)
    await session.commit()
    return result
```

- [ ] **Step 2: Run tests, expect pass**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q backend/tests/api/test_financial_plan.py -v
```
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/financial_plan.py
git commit -m "$(cat <<'EOF'
refactor(b9b): API endpoint вызывает list_plan_by_period (43 элемента)

Endpoint логика не меняется — просто вызывает обновлённый service.
Docstring обновлён под per-period контракт.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Frontend types — `year` → `period_number`

**Files:**
- Modify: `frontend/types/api.ts`

- [ ] **Step 1: Update FinancialPlanItem type**

In `frontend/types/api.ts`, find the `FinancialPlanItem` interface (around line 776) and replace:

```typescript
export interface FinancialPlanItem {
  /** B.9b (2026-05-15): период 1..43.
   *  1..36 = monthly Y1-Y3 (M1..M36), 37..43 = yearly Y4-Y10. */
  period_number: number;
  capex: string; // Decimal as string
  opex: string;
  opex_items: OpexItem[];
  /** B.9 / MEMO 2.1: статьи CAPEX. */
  capex_items: CapexItem[];
}
```

- [ ] **Step 2: Run tsc to find all call-sites that need updating**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit 2>&1 | head -40
```
Expected: errors in `financial-plan-editor.tsx` (uses `item.year`). All other usages will be fixed in subsequent tasks; this list is the to-do for Task 9.

- [ ] **Step 3: Update `frontend/lib/financial-plan.ts` docstring**

In `frontend/lib/financial-plan.ts`, replace the header comment:

```typescript
/**
 * API обёртки для ProjectFinancialPlan — CAPEX/OPEX per-period.
 *
 * B.9b (2026-05-15): per-period контракт.
 * Backend endpoints:
 *   GET /api/projects/{id}/financial-plan → всегда 43 строки (period_number 1..43)
 *   PUT /api/projects/{id}/financial-plan — полная замена
 */
```

- [ ] **Step 4: Commit (skip tsc-passes — that comes after editor rewrite)**

```bash
git add frontend/types/api.ts frontend/lib/financial-plan.ts
git commit -m "$(cat <<'EOF'
refactor(b9b): frontend types FinancialPlanItem.year → period_number

Тип FinancialPlanItem перешёл на period_number (1..43). tsc будет красным
до перезаписи financial-plan-editor.tsx в следующих задачах — это
ожидаемо в рамках сессии.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Frontend utils — pure helpers

**Files:**
- Create: `frontend/lib/financial-plan-utils.ts`

- [ ] **Step 1: Write the utils file with implementation + JSDoc tests**

Create `frontend/lib/financial-plan-utils.ts`:

```typescript
/**
 * Pure helpers для редактора финплана (B.9b).
 *
 * Распределение, диапазоны и определение legacy-данных. Никакого state.
 */

import type { FinancialPlanItem } from "@/types/api";

/**
 * period_number → отображаемая метка.
 *   1..36 → "M1".."M36"
 *   37..43 → "Y4".."Y10"
 */
export function periodLabel(periodNumber: number): string {
  if (periodNumber >= 1 && periodNumber <= 36) return `M${periodNumber}`;
  if (periodNumber >= 37 && periodNumber <= 43)
    return `Y${periodNumber - 33}`; // 37→Y4, 43→Y10
  return `?${periodNumber}`;
}

/** period_number → model_year (1..10). */
export function modelYearOf(periodNumber: number): number {
  if (periodNumber >= 1 && periodNumber <= 12) return 1;
  if (periodNumber >= 13 && periodNumber <= 24) return 2;
  if (periodNumber >= 25 && periodNumber <= 36) return 3;
  return periodNumber - 33; // 37→4, 43→10
}

/** Все period_number принадлежащие конкретному model_year. */
export function periodsInYear(modelYear: number): number[] {
  if (modelYear === 1) return Array.from({ length: 12 }, (_, i) => i + 1);
  if (modelYear === 2) return Array.from({ length: 12 }, (_, i) => i + 13);
  if (modelYear === 3) return Array.from({ length: 12 }, (_, i) => i + 25);
  return [modelYear + 33]; // Y4..Y10
}

/**
 * Распределить сумму total на 12 месяцев заданного года.
 * Округление до 2 знаков; невязка идёт в последний месяц.
 * Возвращает [period_number, amount][].
 *
 * Применимо только для year ∈ {1,2,3} — для Y4..Y10 раскидывать нечего.
 */
export function distributeYear(
  modelYear: number,
  total: number,
): Array<[number, string]> {
  if (modelYear < 1 || modelYear > 3) {
    throw new Error(`distributeYear: modelYear must be 1..3, got ${modelYear}`);
  }
  const periods = periodsInYear(modelYear); // 12 элементов
  const per = Math.round((total / 12) * 100) / 100;
  const result: Array<[number, string]> = [];
  let allocated = 0;
  for (let i = 0; i < 11; i++) {
    result.push([periods[i], String(per)]);
    allocated += per;
  }
  // Последний месяц забирает невязку (max 0.11 руб разницы)
  const last = Math.round((total - allocated) * 100) / 100;
  result.push([periods[11], String(last)]);
  return result;
}

/**
 * Заполнить диапазон period_number [from..to] значением value.
 * Возвращает [period_number, value][].
 */
export function fillRange(
  from: number,
  to: number,
  value: string,
): Array<[number, string]> {
  if (from < 1 || to > 43 || from > to) {
    throw new Error(`fillRange: invalid range ${from}..${to}`);
  }
  const result: Array<[number, string]> = [];
  for (let pn = from; pn <= to; pn++) {
    result.push([pn, value]);
  }
  return result;
}

/**
 * Признак "legacy-данных": все ненулевые значения сосредоточены в
 * first-period-of-year (1, 13, 25, 37..43). Используется чтобы показать
 * пользователю banner с подсказкой про "Распределить год".
 */
export function isLegacyData(items: FinancialPlanItem[]): boolean {
  const firstOfYear = new Set([1, 13, 25, 37, 38, 39, 40, 41, 42, 43]);
  let hasAnyNonZero = false;
  for (const item of items) {
    const total = Number(item.capex || 0) + Number(item.opex || 0);
    const itemsTotal =
      item.capex_items.reduce((s, x) => s + Number(x.amount || 0), 0) +
      item.opex_items.reduce((s, x) => s + Number(x.amount || 0), 0);
    if (total > 0 || itemsTotal > 0) {
      hasAnyNonZero = true;
      if (!firstOfYear.has(item.period_number)) return false;
    }
  }
  return hasAnyNonZero;
}
```

- [ ] **Step 2: Run tsc**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit 2>&1 | grep -v "financial-plan-editor" | head -20
```
Expected: новый файл компилируется. Старая ошибка в editor пока остаётся.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/financial-plan-utils.ts
git commit -m "$(cat <<'EOF'
feat(b9b): pure helpers для финплана (periodLabel, distributeYear, fillRange, isLegacyData)

financial-plan-utils.ts содержит чистые функции для расчёта без state.
distributeYear раздаёт сумму на 12 месяцев года с округлением до 2 знаков,
невязка идёт в последний месяц. isLegacyData детектит "старые" проекты
с записями только в first-of-year периодах (для banner с подсказкой).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Bulk-fill Dialog component

**Files:**
- Create: `frontend/components/projects/financial-plan-bulk-fill.tsx`

- [ ] **Step 1: Verify available Dialog primitive**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend ls components/ui/dialog.tsx
```
Expected: file exists. If not, this task creates a simpler popover-based UI (substitute Card+button overlay).

- [ ] **Step 2: Create the component**

Create `frontend/components/projects/financial-plan-bulk-fill.tsx`:

```typescript
"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  distributeYear,
  fillRange,
  periodLabel,
} from "@/lib/financial-plan-utils";

/** Описывает, к какой строке (статье) применить bulk-fill. */
export interface BulkFillTarget {
  rowKey: string; // например "capex.molds.Молды партия 1" или "capex.total"
  label: string; // отображаемое имя для пользователя
}

interface BulkFillProps {
  rows: BulkFillTarget[];
  /** Колбэк применения изменений: список (period_number, value) к выбранной строке. */
  onApply: (rowKey: string, updates: Array<[number, string]>) => void;
  disabled?: boolean;
}

type Mode = "distribute_year" | "fill_range";

export function FinancialPlanBulkFill({
  rows,
  onApply,
  disabled,
}: BulkFillProps) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("distribute_year");
  const [rowKey, setRowKey] = useState<string>(rows[0]?.rowKey ?? "");
  const [year, setYear] = useState<number>(1);
  const [total, setTotal] = useState<string>("0");
  const [rangeFrom, setRangeFrom] = useState<number>(1);
  const [rangeTo, setRangeTo] = useState<number>(12);
  const [value, setValue] = useState<string>("0");

  function handleApply() {
    if (rowKey === "") return;
    if (mode === "distribute_year") {
      const updates = distributeYear(year, Number(total) || 0);
      onApply(rowKey, updates);
    } else {
      const updates = fillRange(rangeFrom, rangeTo, value);
      onApply(rowKey, updates);
    }
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled}>
          Bulk-fill
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Массовое заполнение</DialogTitle>
          <DialogDescription>
            Распределить сумму на год или залить значение на диапазон периодов.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label>Режим</Label>
            <Select value={mode} onValueChange={(v) => setMode(v as Mode)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="distribute_year">Распределить год (Y1-Y3)</SelectItem>
                <SelectItem value="fill_range">Залить диапазон</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label>Строка</Label>
            <Select value={rowKey} onValueChange={setRowKey}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {rows.map((r) => (
                  <SelectItem key={r.rowKey} value={r.rowKey}>
                    {r.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {mode === "distribute_year" && (
            <>
              <div>
                <Label>Год</Label>
                <Select
                  value={String(year)}
                  onValueChange={(v) => setYear(Number(v))}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">Y1 (M1..M12)</SelectItem>
                    <SelectItem value="2">Y2 (M13..M24)</SelectItem>
                    <SelectItem value="3">Y3 (M25..M36)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Сумма за год, ₽</Label>
                <Input
                  type="number"
                  min="0"
                  step="1"
                  value={total}
                  onChange={(e) => setTotal(e.target.value)}
                />
              </div>
            </>
          )}

          {mode === "fill_range" && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label>От (период)</Label>
                  <Select
                    value={String(rangeFrom)}
                    onValueChange={(v) => setRangeFrom(Number(v))}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 43 }, (_, i) => i + 1).map((pn) => (
                        <SelectItem key={pn} value={String(pn)}>
                          {periodLabel(pn)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>До (период)</Label>
                  <Select
                    value={String(rangeTo)}
                    onValueChange={(v) => setRangeTo(Number(v))}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 43 }, (_, i) => i + 1).map((pn) => (
                        <SelectItem key={pn} value={String(pn)}>
                          {periodLabel(pn)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div>
                <Label>Значение в каждый период, ₽</Label>
                <Input
                  type="number"
                  min="0"
                  step="1"
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                />
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Отмена
          </Button>
          <Button onClick={handleApply}>Применить</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 3: tsc check on new file**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit 2>&1 | grep "financial-plan-bulk-fill"
```
Expected: empty (новый файл компилируется). Errors в editor — это ожидаемо.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/projects/financial-plan-bulk-fill.tsx
git commit -m "$(cat <<'EOF'
feat(b9b): диалог bulk-fill (Распределить год / Залить диапазон)

Новый компонент FinancialPlanBulkFill — Dialog с двумя режимами:
1) Распределить сумму X на 12 месяцев года Y1-Y3
2) Залить значение V на диапазон period [from..to]
Применение через onApply колбэк к выбранной строке (rowKey).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Editor rewrite — 43-column table

**Files:**
- Modify: `frontend/components/projects/financial-plan-editor.tsx`

- [ ] **Step 1: Replace the entire file**

Replace `frontend/components/projects/financial-plan-editor.tsx` with:

```typescript
"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import {
  getFinancialPlan,
  putFinancialPlan,
} from "@/lib/financial-plan";
import {
  isLegacyData,
  modelYearOf,
  periodLabel,
} from "@/lib/financial-plan-utils";

import {
  CAPEX_CATEGORIES,
  CAPEX_CATEGORY_LABELS,
  OPEX_CATEGORIES,
  OPEX_CATEGORY_LABELS,
  type CapexItem,
  type FinancialPlanItem,
  type OpexItem,
} from "@/types/api";

import {
  FinancialPlanBulkFill,
  type BulkFillTarget,
} from "./financial-plan-bulk-fill";

interface Props {
  projectId: number;
}

type ItemKind = "capex" | "opex";

/**
 * Редактор финансового плана с per-period гранулярностью (B.9b).
 *
 * Сетка: 43 колонки (M1..M36 + Y4..Y10), sticky left = имена строк.
 * Строки: для CAPEX — итог + N статей; для OPEX — то же. Итог считается
 * на фронте как сумма статей или, если статей нет, как ввод вручную.
 */
export function FinancialPlanEditor({ projectId }: Props) {
  const [items, setItems] = useState<FinancialPlanItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [collapsed, setCollapsed] = useState<{ capex: boolean; opex: boolean }>(
    { capex: false, opex: false },
  );

  useEffect(() => {
    let cancelled = false;
    getFinancialPlan(projectId)
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.detail ?? err.message : "Ошибка");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const showLegacyBanner = useMemo(
    () => (items !== null ? isLegacyData(items) : false),
    [items],
  );

  // Список уникальных статей CAPEX/OPEX, агрегированный по всем периодам.
  // Ключ статьи = `${category}|${name}` — UNIQUE в БД на (financial_plan_id, category, name).
  const capexArticleKeys = useMemo(() => collectArticleKeys(items, "capex"), [items]);
  const opexArticleKeys = useMemo(() => collectArticleKeys(items, "opex"), [items]);

  function updatePeriodTotal(
    periodNumber: number,
    field: "capex" | "opex",
    value: string,
  ) {
    setItems((prev) =>
      prev === null
        ? prev
        : prev.map((p) =>
            p.period_number === periodNumber ? { ...p, [field]: value } : p,
          ),
    );
  }

  function updateArticleAmount(
    periodNumber: number,
    kind: ItemKind,
    category: string,
    name: string,
    amount: string,
  ) {
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((p) => {
        if (p.period_number !== periodNumber) return p;
        const listField = kind === "capex" ? "capex_items" : "opex_items";
        const list = (p as any)[listField] as Array<OpexItem | CapexItem>;
        const idx = list.findIndex(
          (it) => it.category === category && it.name === name,
        );
        let newList: typeof list;
        if (idx === -1) {
          newList = [...list, { category, name, amount }];
        } else {
          newList = list.map((it, i) =>
            i === idx ? { ...it, amount } : it,
          );
        }
        // Удалить статью если стало 0/пусто
        if (amount === "" || Number(amount) === 0) {
          newList = newList.filter(
            (it) => !(it.category === category && it.name === name),
          );
        }
        const totalField = kind === "capex" ? "capex" : "opex";
        const newTotal = newList.reduce(
          (s, it) => s + Number(it.amount || 0),
          0,
        );
        return { ...p, [listField]: newList, [totalField]: String(newTotal) };
      });
    });
  }

  function addArticle(kind: ItemKind, category: string, name: string) {
    // Создаём пустую статью; per-период значения вводятся в ячейках.
    // Простейший подход: добавить статью в первый период с amount=0 — после
    // ввода в любой ячейке через updateArticleAmount она появится там.
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((p) => {
        if (p.period_number !== 1) return p;
        const listField = kind === "capex" ? "capex_items" : "opex_items";
        const list = (p as any)[listField] as Array<OpexItem | CapexItem>;
        if (list.some((it) => it.category === category && it.name === name)) {
          return p; // уже есть
        }
        const next = [...list, { category, name, amount: "0" }];
        return { ...p, [listField]: next };
      });
    });
  }

  function removeArticle(kind: ItemKind, category: string, name: string) {
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((p) => {
        const listField = kind === "capex" ? "capex_items" : "opex_items";
        const list = (p as any)[listField] as Array<OpexItem | CapexItem>;
        const newList = list.filter(
          (it) => !(it.category === category && it.name === name),
        );
        if (newList.length === list.length) return p;
        const totalField = kind === "capex" ? "capex" : "opex";
        const newTotal = newList.reduce(
          (s, it) => s + Number(it.amount || 0),
          0,
        );
        return { ...p, [listField]: newList, [totalField]: String(newTotal) };
      });
    });
  }

  function applyBulkFill(
    rowKey: string,
    updates: Array<[number, string]>,
  ): void {
    // rowKey формат: `${kind}.total` или `${kind}.${category}|${name}`
    const [kind, tail] = rowKey.split(".", 2) as [ItemKind, string];
    if (tail === "total") {
      for (const [pn, val] of updates) {
        updatePeriodTotal(pn, kind, val);
      }
    } else {
      const [category, name] = tail.split("|", 2);
      for (const [pn, val] of updates) {
        updateArticleAmount(pn, kind, category, name, val);
      }
    }
  }

  async function handleSave() {
    if (items === null) return;
    setSaving(true);
    setError(null);
    try {
      const sanitized = items.map((p) => ({
        ...p,
        capex: p.capex === "" ? "0" : p.capex,
        opex: p.opex === "" ? "0" : p.opex,
        opex_items: p.opex_items.map((oi) => ({
          ...oi,
          amount: oi.amount === "" ? "0" : oi.amount,
        })),
        capex_items: p.capex_items.map((ci) => ({
          ...ci,
          amount: ci.amount === "" ? "0" : ci.amount,
        })),
      }));
      const saved = await putFinancialPlan(projectId, { items: sanitized });
      setItems(saved);
      setSavedAt(new Date());
      toast.success("Финансовый план сохранён");
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка сохранения";
      setError(msg);
      toast.error(`Не удалось сохранить: ${msg}`);
    } finally {
      setSaving(false);
    }
  }

  const periods = useMemo(
    () => Array.from({ length: 43 }, (_, i) => i + 1),
    [],
  );

  // Список строк для bulk-fill
  const bulkRows: BulkFillTarget[] = useMemo(() => {
    const rows: BulkFillTarget[] = [
      { rowKey: "capex.total", label: "CAPEX итог (без статей)" },
      ...capexArticleKeys.map((k) => ({
        rowKey: `capex.${k.category}|${k.name}`,
        label: `CAPEX • ${CAPEX_CATEGORY_LABELS[k.category as keyof typeof CAPEX_CATEGORY_LABELS] ?? k.category} • ${k.name}`,
      })),
      { rowKey: "opex.total", label: "OPEX итог (без статей)" },
      ...opexArticleKeys.map((k) => ({
        rowKey: `opex.${k.category}|${k.name}`,
        label: `OPEX • ${OPEX_CATEGORY_LABELS[k.category as keyof typeof OPEX_CATEGORY_LABELS] ?? k.category} • ${k.name}`,
      })),
    ];
    return rows;
  }, [capexArticleKeys, opexArticleKeys]);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="text-base">
              Финансовый план (помесячно Y1-Y3, годами Y4-Y10)
            </CardTitle>
            <CardDescription>
              CAPEX и project OPEX по месяцам первых 3 лет и годам Y4-Y10.
              Используйте кнопку <b>Bulk-fill</b> чтобы распределить годовую
              сумму по месяцам или залить значение на диапазон.
            </CardDescription>
          </div>
          <div className="flex items-center gap-3">
            <FinancialPlanBulkFill
              rows={bulkRows}
              onApply={applyBulkFill}
              disabled={saving || items === null}
            />
            {savedAt !== null && !saving && error === null && (
              <span className="text-xs text-muted-foreground">
                Сохранено {savedAt.toLocaleTimeString("ru-RU")}
              </span>
            )}
            <Button
              size="sm"
              onClick={handleSave}
              disabled={saving || items === null}
            >
              {saving ? "Сохранение..." : "Сохранить"}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {items === null && error === null && (
          <p className="text-sm text-muted-foreground">Загрузка...</p>
        )}
        {error !== null && (
          <p className="mb-3 text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
        {showLegacyBanner && (
          <div className="mb-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            <b>Финплан сохранён годовыми точками.</b> Все значения сейчас
            видны в первом месяце года (M1, M13, M25). Используйте Bulk-fill →
            «Распределить год» чтобы разнести их по месяцам.
          </div>
        )}

        {items !== null && (
          <div className="overflow-x-auto border rounded">
            <table className="min-w-full text-xs border-collapse">
              <thead>
                <tr className="bg-muted">
                  <th
                    className="sticky left-0 bg-muted px-2 py-1 text-left border-r"
                    style={{ minWidth: 220 }}
                  >
                    Статья / Период
                  </th>
                  <th colSpan={12} className="text-center border-r">
                    Y1 (M1-M12)
                  </th>
                  <th colSpan={12} className="text-center border-r">
                    Y2 (M13-M24)
                  </th>
                  <th colSpan={12} className="text-center border-r">
                    Y3 (M25-M36)
                  </th>
                  <th colSpan={7} className="text-center">
                    Y4-Y10
                  </th>
                </tr>
                <tr className="bg-muted/50">
                  <th className="sticky left-0 bg-muted/50 border-r" />
                  {periods.map((pn) => (
                    <th
                      key={pn}
                      className="px-1 py-0.5 text-center border-r font-mono"
                      style={{ minWidth: 70 }}
                    >
                      {periodLabel(pn)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {/* CAPEX header */}
                <tr className="bg-blue-50 font-semibold">
                  <td
                    className="sticky left-0 bg-blue-50 px-2 py-1 border-r cursor-pointer"
                    onClick={() =>
                      setCollapsed((c) => ({ ...c, capex: !c.capex }))
                    }
                  >
                    {collapsed.capex ? "▶" : "▼"} CAPEX итог
                  </td>
                  {periods.map((pn) => {
                    const it = items.find((x) => x.period_number === pn);
                    return (
                      <td key={pn} className="border-r text-center">
                        {it && it.capex_items.length === 0 ? (
                          <Input
                            type="number"
                            min="0"
                            step="1"
                            value={it.capex}
                            onChange={(e) =>
                              updatePeriodTotal(pn, "capex", e.target.value)
                            }
                            disabled={saving}
                            className="h-7 text-right text-xs"
                          />
                        ) : (
                          <span className="text-muted-foreground">
                            {Number(it?.capex || 0).toLocaleString("ru-RU")}
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>

                {/* CAPEX статьи */}
                {!collapsed.capex && capexArticleKeys.map((k) => (
                  <ArticleRow
                    key={`capex-${k.category}-${k.name}`}
                    items={items}
                    kind="capex"
                    category={k.category}
                    name={k.name}
                    saving={saving}
                    onUpdate={(pn, val) =>
                      updateArticleAmount(pn, "capex", k.category, k.name, val)
                    }
                    onRemove={() => removeArticle("capex", k.category, k.name)}
                  />
                ))}
                {!collapsed.capex && (
                  <AddArticleRow
                    kind="capex"
                    onAdd={(cat, name) => addArticle("capex", cat, name)}
                    disabled={saving}
                  />
                )}

                {/* OPEX header */}
                <tr className="bg-green-50 font-semibold">
                  <td
                    className="sticky left-0 bg-green-50 px-2 py-1 border-r cursor-pointer"
                    onClick={() =>
                      setCollapsed((c) => ({ ...c, opex: !c.opex }))
                    }
                  >
                    {collapsed.opex ? "▶" : "▼"} OPEX итог
                  </td>
                  {periods.map((pn) => {
                    const it = items.find((x) => x.period_number === pn);
                    return (
                      <td key={pn} className="border-r text-center">
                        {it && it.opex_items.length === 0 ? (
                          <Input
                            type="number"
                            min="0"
                            step="1"
                            value={it.opex}
                            onChange={(e) =>
                              updatePeriodTotal(pn, "opex", e.target.value)
                            }
                            disabled={saving}
                            className="h-7 text-right text-xs"
                          />
                        ) : (
                          <span className="text-muted-foreground">
                            {Number(it?.opex || 0).toLocaleString("ru-RU")}
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>

                {/* OPEX статьи */}
                {!collapsed.opex && opexArticleKeys.map((k) => (
                  <ArticleRow
                    key={`opex-${k.category}-${k.name}`}
                    items={items}
                    kind="opex"
                    category={k.category}
                    name={k.name}
                    saving={saving}
                    onUpdate={(pn, val) =>
                      updateArticleAmount(pn, "opex", k.category, k.name, val)
                    }
                    onRemove={() => removeArticle("opex", k.category, k.name)}
                  />
                ))}
                {!collapsed.opex && (
                  <AddArticleRow
                    kind="opex"
                    onAdd={(cat, name) => addArticle("opex", cat, name)}
                    disabled={saving}
                  />
                )}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ============================================================
// Helpers
// ============================================================

function collectArticleKeys(
  items: FinancialPlanItem[] | null,
  kind: ItemKind,
): Array<{ category: string; name: string }> {
  if (items === null) return [];
  const seen = new Map<string, { category: string; name: string }>();
  for (const p of items) {
    const list = kind === "capex" ? p.capex_items : p.opex_items;
    for (const it of list) {
      const key = `${it.category}|${it.name}`;
      if (!seen.has(key)) seen.set(key, { category: it.category, name: it.name });
    }
  }
  return Array.from(seen.values());
}

// --- Sub-components ---

interface ArticleRowProps {
  items: FinancialPlanItem[];
  kind: ItemKind;
  category: string;
  name: string;
  saving: boolean;
  onUpdate: (periodNumber: number, value: string) => void;
  onRemove: () => void;
}

function ArticleRow({
  items,
  kind,
  category,
  name,
  saving,
  onUpdate,
  onRemove,
}: ArticleRowProps) {
  const labels =
    kind === "capex" ? CAPEX_CATEGORY_LABELS : OPEX_CATEGORY_LABELS;
  const catLabel = (labels as Record<string, string>)[category] ?? category;
  return (
    <tr>
      <td className="sticky left-0 bg-background px-2 py-1 border-r">
        <div className="flex items-center justify-between gap-2">
          <span>
            <span className="text-muted-foreground">{catLabel}</span> · {name}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={onRemove}
            disabled={saving}
            className="h-5 px-1 text-destructive"
            title="Удалить статью"
          >
            ×
          </Button>
        </div>
      </td>
      {items.map((p) => {
        const article = (kind === "capex" ? p.capex_items : p.opex_items).find(
          (it) => it.category === category && it.name === name,
        );
        return (
          <td key={p.period_number} className="border-r">
            <Input
              type="number"
              min="0"
              step="1"
              value={article?.amount ?? "0"}
              onChange={(e) => onUpdate(p.period_number, e.target.value)}
              disabled={saving}
              className="h-7 text-right text-xs"
            />
          </td>
        );
      })}
    </tr>
  );
}

interface AddArticleRowProps {
  kind: ItemKind;
  onAdd: (category: string, name: string) => void;
  disabled: boolean;
}

function AddArticleRow({ kind, onAdd, disabled }: AddArticleRowProps) {
  const [category, setCategory] = useState<string>("other");
  const [name, setName] = useState<string>("");
  const categories = kind === "capex" ? CAPEX_CATEGORIES : OPEX_CATEGORIES;
  const labels =
    kind === "capex" ? CAPEX_CATEGORY_LABELS : OPEX_CATEGORY_LABELS;

  function handle() {
    if (name.trim() === "") return;
    onAdd(category, name.trim());
    setName("");
  }

  return (
    <tr className="bg-muted/20">
      <td className="sticky left-0 bg-muted/20 px-2 py-1 border-r" colSpan={44}>
        <div className="flex items-center gap-2">
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger className="h-7 w-[180px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {categories.map((c) => (
                <SelectItem key={c} value={c} className="text-xs">
                  {(labels as Record<string, string>)[c] ?? c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            placeholder={`Название статьи ${kind === "capex" ? "CAPEX" : "OPEX"}`}
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={disabled}
            className="h-7 text-xs max-w-xs"
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={handle}
            disabled={disabled || name.trim() === ""}
            className="h-7 text-xs text-primary"
          >
            + Добавить статью
          </Button>
        </div>
      </td>
    </tr>
  );
}
```

- [ ] **Step 2: Run tsc, expect clean**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```
Expected: empty output (no errors).

- [ ] **Step 3: Restart frontend container (Windows+Docker HMR safety, memory `feedback_frontend_structural_restart`)**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml restart frontend
```
Wait ~10 seconds for HMR to come online (Monitor logs or check via curl).

- [ ] **Step 4: Manual smoke check in browser**

Open an existing project's financial-plan tab in browser:
- 43 колонки видны (горизонтальный scroll работает).
- Sticky left column держится при прокрутке.
- На существующих проектах виден amber-banner с подсказкой про "Распределить год".
- Клик на CAPEX итог сворачивает/разворачивает строки статей.
- Bulk-fill открывает диалог с двумя режимами.

Если что-то сломано — НЕ коммитить, фиксить.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/projects/financial-plan-editor.tsx
git commit -m "$(cat <<'EOF'
feat(b9b): редактор финплана — 43-колоночная таблица + bulk-fill

financial-plan-editor.tsx переписан: вместо 10 годовых строк теперь
43 колонки (M1..M36 + Y4..Y10), sticky left, группирующие заголовки
Y1/Y2/Y3 над месяцами. Каждая статья = одна строка с 43 ячейками.
Collapse/expand для CAPEX и OPEX групп. Banner для legacy-данных
(все значения в first-of-year периодах). Интеграция с bulk-fill
через onApply колбэк.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Acceptance check + CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Backend full test suite**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -5
```
Expected: PASS, count ≈ ожидаемое количество (старые 472 минус удалённые year-тесты плюс новые period_number-тесты). Acceptance GORJI зелёный.

- [ ] **Step 2: Frontend type check**

Run:
```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```
Expected: empty output.

- [ ] **Step 3: KPI invariance — Test A (roundtrip)**

Manually in браузере или через DB shell:
1. Открыть существующий проект с финпланом.
2. Запустить расчёт сценария (кнопка "Пересчитать"), записать NPV/IRR.
3. Открыть редактор финплана, ничего не менять, нажать "Сохранить".
4. Запустить расчёт ещё раз. NPV/IRR должны совпасть до 6 знаков.

Если не совпали — diagnostic в `replace_plan` логах + проверить что lazy expand не теряет данные.

- [ ] **Step 4: KPI invariance — Test B (monthly distribution)**

Через UI:
1. Создать тестовый проект с CAPEX = 15000000 ₽ в period_number=3 (через прямое заполнение M3 ячейки CAPEX итог).
2. Сохранить, запустить расчёт. Записать annual_capex[Y1] из таблицы scenario_results (или через API).
3. Создать другой тестовый проект: CAPEX = 15000000 ₽ в period_number=1 (Y1 целиком в M1).
4. Сохранить, запустить расчёт. annual_capex[Y1] должен = 15M (та же сумма).
5. NPV/IRR совпадает в обоих случаях (доказательство аннуализации).

Если не совпадают — баг в engine; вернуться к проверке `_load_project_financial_plan` и `s10_discount`.

- [ ] **Step 5: Update CHANGELOG.md**

In `CHANGELOG.md`, in the `[Unreleased]` → `Changed (Phase B)` section,
add a new entry before B.9:

```markdown
- **B.9b Помесячный финплан Y1-Y3 (MEMO 2.1, финал, 2026-05-15).** Завершает
  B.9: переход с 10 годовых ячеек на **43 точки** = 36 monthly (M1..M36)
  + 7 yearly (Y4..Y10). Каждая статья CAPEX/OPEX = строка таблицы с 43
  ячейками; bulk-fill «Распределить год» (Y/12) и «Залить диапазон»
  (одно значение на period from..to).
  - API: `FinancialPlanItem.year` → `period_number` (1..43). GET всегда
    отдаёт 43 элемента. PUT валидирует уникальность period_number.
  - Service: `_get_first_period_by_year` → `_get_period_id_by_number`;
    `list_plan_by_year` → `list_plan_by_period`.
  - Engine не трогали — `_load_project_financial_plan` (calculation_service)
    уже строил tuple длины 43, `s10_discount` аннуализирует через
    `period_model_year`. Acceptance GORJI стабилен (drift < 0.03%).
  - Существующие проекты: lazy expand, БД не мигрируется. UI-banner
    подсказывает использовать «Распределить год».
  - Тесты: backend pytest зелёный, frontend tsc 0 ошибок, ручная проверка
    KPI invariance (Test A roundtrip + Test B M3 vs Y1 распределение).
```

- [ ] **Step 6: Commit CHANGELOG**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs(b9b): CHANGELOG — закрытие B.9b (помесячный финплан Y1-Y3)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 7: Update CLIENT_FEEDBACK_v2_DECISIONS.md**

Find the B.9b row/section in `docs/CLIENT_FEEDBACK_v2_DECISIONS.md` and
mark it as done (✓ или статус «Закрыто 2026-05-15»). Если нет такого
маркера — добавить в раздел "Фаза B" строку:

```markdown
- B.9b — Помесячная гранулярность Y1-Y3 + UI 43 колонки. **✓ Закрыто 2026-05-15.**
  См. `docs/superpowers/specs/2026-05-15-b9b-monthly-financial-plan-design.md`.
```

Commit:
```bash
git add docs/CLIENT_FEEDBACK_v2_DECISIONS.md
git commit -m "$(cat <<'EOF'
docs(b9b): CLIENT_FEEDBACK_v2_DECISIONS — отметить B.9b закрытым

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

(Run after writing the plan.)

**Spec coverage:**
- § 4.2 (backend service/schema/API) → Tasks 2, 3, 5
- § 4.3 (frontend editor, bulk-fill, banner, collapse) → Tasks 7, 8, 9
- § 4.4 (что НЕ меняется: engine, экспорт, миграции) → не в плане, потому что НЕ трогаем (соответствует решению)
- § 5 (edge cases): E1 banner — Task 9, E2 пустой PUT — Task 4 test_put_plan_empty_items_clears, E3 дубли period_number — Task 4 test_put_plan_rejects_duplicate_period_numbers, E4 валидация диапазона — Task 2 test_financial_plan_item_rejects_period_number_out_of_range, E5 UNIQUE constraint — implicit, E6 округление — Task 7 `distributeYear`, E7 performance — отложено в Out of scope (примечание в spec), E8 тесты — Tasks 2-4
- § 6 acceptance criteria → Task 10
- § 7 out of scope → не реализуем
- § 8 оценка → справочно, не блокирует

**Placeholder scan:** Прошёл по плану — нет "TBD", "TODO", "fill in later". Все шаги содержат конкретный код или конкретную команду.

**Type consistency:** `period_number: int` в Pydantic, `period_number: number` в TS, `period_number=1..43` везде. `FinancialPlanItem` обновлён согласованно. `BulkFillTarget.rowKey` использует формат `${kind}.total` / `${kind}.${category}|${name}` — применяется в Task 8 и Task 9 одинаково. `distributeYear`/`fillRange`/`isLegacyData` сигнатуры идентичны между Task 7 (определение) и Task 8/9 (использование).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-15-b9b-monthly-financial-plan.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch fresh subagent per task, review between tasks, fast iteration.

2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
