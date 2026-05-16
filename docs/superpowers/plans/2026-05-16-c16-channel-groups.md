# C #16 — Каналы: группы + source_type (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить `Channel.channel_group` (8 значений) и `Channel.source_type` (5 значений nullable), переписать UI добавления каналов на двухфазный bulk-flow (выбор чекбоксами по группам → одна форма метрик → atomic POST), сделать inline-редактирование каталога каналов (create custom / edit existing).

**Architecture:** PATTERN-08 varchar+CHECK (как `SKU.format` в C #19, `NielsenBenchmarkSourceType` в C #30). Auto-backfill 25 GORJI seed-кодов через MAPPING_RULES в миграции. Bulk endpoint reuse'ит существующий `create_psk_channel` (savepoint + predict-layer уже там) в loop'е. Frontend — двухфазный диалог с reuse `<ChannelForm>` (новый prop `channelHidden`).

**Tech Stack:** Backend: Python 3.12, FastAPI, Pydantic v2 (`Literal`), SQLAlchemy 2.0, Alembic, pytest. Frontend: Next.js 14, TypeScript, `@base-ui/react`, shadcn/ui Checkbox + CollapsibleSection.

**Spec reference:** `docs/superpowers/specs/2026-05-16-c16-channel-groups-design.md` (закоммичена `e4e547e`).

**Branch:** `feat/c16-channel-groups` (создать от main; spec уже там).

---

## Контекст для исполнителя

### Текущий alembic head
`b9986ce73ab2` (C #24 scenarios.name). Новая миграция должна `down_revision = "b9986ce73ab2"`. ID миграции получить через `alembic revision -m "c16_channel_group_source_type"` (генерируется автоматически).

### Точные file paths

**Backend:**
- `backend/app/models/entities.py:107-122` — `Channel` SQLAlchemy model
- `backend/app/schemas/channel.py` — 3 Pydantic классa (`ChannelRead`, `ChannelCreate`, `ChannelUpdate`)
- `backend/app/schemas/project_sku_channel.py` — schemas для PSC
- `backend/app/api/channels.py` — CRUD endpoints `/api/channels`
- `backend/app/api/project_sku_channels.py:87-117` — single-channel POST (паттерн для bulk)
- `backend/app/services/project_sku_channel_service.py:51-96` — `create_psk_channel` (reuse в bulk)
- `backend/migrations/versions/` — здесь живут миграции
- `backend/scripts/seed_reference_data.py:37-63` — `CHANNELS_DATA` (25 строк)
- `backend/tests/api/test_channels.py` — существующие channel CRUD тесты
- `backend/tests/api/test_psk_channels.py` — существующие PSC тесты (паттерн для bulk-тестов)

**Frontend:**
- `frontend/types/api.ts` — TS interfaces
- `frontend/lib/channels.ts` — API обёртки
- `frontend/components/projects/channel-form.tsx` — общий `<ChannelForm>` (нужен prop `channelHidden`)
- `frontend/components/projects/channel-dialogs.tsx` — `AddChannelDialog` + `EditChannelDialog` (диалог метрик PSC, оставляем; первый переписываем)
- `frontend/components/projects/channels-panel.tsx` — список PSC (использует `AddChannelDialog`, обновим импорт)
- `frontend/components/ui/collapsible.tsx` — `<CollapsibleSection>` (C #22, использовать для групп)
- `frontend/components/ui/checkbox.tsx` — shadcn/ui Checkbox (если отсутствует — добавить)

**Docs:**
- `CHANGELOG.md` — секция `## [Unreleased]` → `### Added` + `### Migrations`
- `docs/CLIENT_FEEDBACK_v2_STATUS.md` — обновить статусы строк 117-121
- `GO5.md` — § «Pre-flight для прода» — добавить запись про C #16

### Тестовый стек

```bash
# Backend pytest (~85 сек, после T1-T2 ожидаем +9-10 passed):
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration
# До старта: 514 passed; после T1+T2: ~523-524 passed.

# Конкретный файл:
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q backend/tests/api/test_channels.py -v
# (ВНИМАНИЕ: внутри контейнера префикс backend/ убираем — working dir /app)
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/api/test_channels.py -v

# Frontend type-check:
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit

# Alembic команды:
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic upgrade head
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic downgrade -1

# Acceptance (T5):
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/acceptance -m acceptance
# Ожидаемо: 6 passed, drift < 0.03%.

# Seed re-run (T1, идемпотентно):
docker compose -f infra/docker-compose.dev.yml exec -T backend python -m scripts.seed_reference_data
```

### Frontend structural restart (после edit'ов JSX-структуры в T3, T4)

По правилу `feedback-frontend-structural-restart` (Windows+Docker HMR баг):
```bash
docker compose -f infra/docker-compose.dev.yml stop frontend
docker compose -f infra/docker-compose.dev.yml run --rm frontend sh -c "rm -rf .next/* .next/.[!.]* 2>/dev/null"
docker compose -f infra/docker-compose.dev.yml up -d frontend
```

### Setup перед T1

```bash
git checkout main
git pull origin main          # Должны быть на e4e547e (spec commit) или новее
git checkout -b feat/c16-channel-groups
```

---

## Task 1: Schema + миграция + auto-backfill + seed update

**Goal:** Добавить `channel_group` и `source_type` колонки в `channels`, написать миграцию с автоматическим backfill'ом по паттерну `code`, обновить Pydantic schemas, обновить seed.

**Files:**
- Modify: `backend/app/models/entities.py:107-122` (Channel model)
- Modify: `backend/app/schemas/channel.py` (3 классa)
- Create: `backend/migrations/versions/<rev>_c16_channel_group_source_type.py`
- Modify: `backend/scripts/seed_reference_data.py:37-63` (add channel_group to 25 строк)
- Modify: `backend/tests/api/test_channels.py` (обновить fixture + добавить 4 теста)
- Create: `backend/tests/migrations/test_c16_backfill.py` (3 unit-теста на _resolve_group)

**Контекст:** Существующая `Channel` фабрика в `tests/conftest.py` создаёт каналы без `channel_group` — после введения NOT NULL колонки тесты упадут. Решение: server_default="OTHER" в БД сохранит fixture-каналы, плюс фабрика обновится использовать default channel_group="OTHER".

### Шаги

- [ ] **Step 1: Создать ветку и убедиться в чистом state**

```bash
git status                                                        # должно быть clean
git checkout -b feat/c16-channel-groups                           # если не на ней уже
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
# Ожидаемо: b9986ce73ab2 (head)
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration | tail -3
# Ожидаемо: 514 passed
```

- [ ] **Step 2: Написать unit-тесты для helper `_resolve_group` (пока миграции нет)**

Создать `backend/tests/migrations/test_c16_backfill.py`:
```python
"""Unit-тесты для backfill-helper _resolve_group из миграции C #16.

Импорт по абсолютному пути к файлу миграции через importlib —
revision-id не статичный. Можно адаптировать под точное имя файла
после `alembic revision` (см. Step 5).
"""
import importlib.util
from pathlib import Path

import pytest

MIGRATION_FILE = next(
    Path("migrations/versions").glob("*_c16_channel_group_source_type.py")
)
spec = importlib.util.spec_from_file_location("c16_migration", MIGRATION_FILE)
mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(mod)  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "code, expected",
    [
        ("HM", "HM"),
        ("SM", "SM"),
        ("MM", "MM"),
        ("TT", "TT"),
        ("Vkusno I tochka", "QSR"),
        ("Burger king", "QSR"),
        ("Rostics", "QSR"),
        ("Do-Do_pizza", "QSR"),
    ],
)
def test_resolve_group_exact_match(code: str, expected: str) -> None:
    assert mod._resolve_group(code) == expected


@pytest.mark.parametrize(
    "code, expected",
    [
        ("E-COM_OZ", "E_COM"),
        ("E-COM_WB", "E_COM"),
        ("E_COM_E-grocery", "E_COM"),
        ("E-COM_OZ_Fresh", "E_COM"),
        ("HORECA_АЗС", "HORECA"),
        ("HORECA_HOTEL", "HORECA"),
    ],
)
def test_resolve_group_prefix(code: str, expected: str) -> None:
    assert mod._resolve_group(code) == expected


@pytest.mark.parametrize(
    "code",
    ["Beauty", "Beauty-NS", "DS_Pyaterochka", "HDS", "ALCO", "VEND_machine", "UnknownCustomCode"],
)
def test_resolve_group_fallback_other(code: str) -> None:
    assert mod._resolve_group(code) == "OTHER"
```

- [ ] **Step 3: Запустить — тесты падают (нет миграции)**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/migrations/test_c16_backfill.py -v
```
Expected: collection error / StopIteration (миграционный файл не существует).

- [ ] **Step 4: Сгенерировать пустой revision и сразу же переименовать**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic revision -m "c16_channel_group_source_type"
# Создаст migrations/versions/<random>_c16_channel_group_source_type.py
```
Скопировать сгенерированный `revision` id (строка вверху файла) в `down_revision` следующей миграции после неё (на момент написания плана — нет следующей; просто `down_revision = "b9986ce73ab2"`).

- [ ] **Step 5: Написать содержимое миграции**

Заменить содержимое `migrations/versions/<rev>_c16_channel_group_source_type.py` на:
```python
"""c16_channel_group_source_type

C #16: добавление channel_group (8 значений) и source_type (5 значений
nullable) на таблицу channels. Backfill существующих 25 GORJI каналов
через MAPPING_RULES (см. _resolve_group).

Pre-flight для прода: SELECT DISTINCT code FROM channels — кастомные
коды (не из 25 known) попадут в OTHER. Если юзер хочет другое — UPDATE
до миграции.

Revision ID: <rev>
Revises: b9986ce73ab2
Create Date: 2026-05-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "<rev>"  # ← оставить сгенерированный alembic'ом
down_revision: Union[str, None] = "b9986ce73ab2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ============================================================
# Backfill rules — единый источник истины для миграции и seed.
# ============================================================

EXACT_RULES: dict[str, str] = {
    "HM": "HM",
    "SM": "SM",
    "MM": "MM",
    "TT": "TT",
    "Vkusno I tochka": "QSR",
    "Burger king": "QSR",
    "Rostics": "QSR",
    "Do-Do_pizza": "QSR",
}
PREFIX_RULES: list[tuple[str, str]] = [
    ("E-COM_", "E_COM"),
    ("E_COM_", "E_COM"),
    ("HORECA_", "HORECA"),
]

VALID_GROUPS = ("HM", "SM", "MM", "TT", "E_COM", "HORECA", "QSR", "OTHER")
VALID_SOURCES = ("nielsen", "tsrpt", "gis2", "infoline", "custom")


def _resolve_group(code: str) -> str:
    """Маппит channel.code → channel_group. Неизвестные коды → 'OTHER'."""
    if code in EXACT_RULES:
        return EXACT_RULES[code]
    for prefix, group in PREFIX_RULES:
        if code.startswith(prefix):
            return group
    return "OTHER"


def upgrade() -> None:
    # 1. Добавляем колонки nullable — чтобы существующие rows не упали на NOT NULL.
    op.add_column(
        "channels",
        sa.Column("channel_group", sa.String(20), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column("source_type", sa.String(20), nullable=True),
    )

    # 2. Backfill channel_group по коду.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, code FROM channels")).fetchall()
    for row_id, code in rows:
        group = _resolve_group(code)
        conn.execute(
            sa.text("UPDATE channels SET channel_group = :g WHERE id = :id"),
            {"g": group, "id": row_id},
        )
    # source_type оставляем NULL — юзер укажет вручную через UI.

    # 3. Set NOT NULL + server_default + CHECK constraints.
    op.alter_column(
        "channels",
        "channel_group",
        nullable=False,
        server_default="OTHER",
    )
    op.create_check_constraint(
        "valid_channel_group_value",
        "channels",
        "channel_group IN ('HM','SM','MM','TT','E_COM','HORECA','QSR','OTHER')",
    )
    op.create_check_constraint(
        "valid_channel_source_type_value",
        "channels",
        "source_type IS NULL OR source_type IN "
        "('nielsen','tsrpt','gis2','infoline','custom')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "valid_channel_source_type_value", "channels", type_="check"
    )
    op.drop_constraint(
        "valid_channel_group_value", "channels", type_="check"
    )
    op.drop_column("channels", "source_type")
    op.drop_column("channels", "channel_group")
```

- [ ] **Step 6: Запустить unit-тесты helper'а — должны пройти**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/migrations/test_c16_backfill.py -v
```
Expected: 13 passed (4+6+3 параметризованных).

- [ ] **Step 7: Применить миграцию**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic upgrade head
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
# Ожидаемо: <rev> (head)
```

- [ ] **Step 8: Проверить SQL — все channel_group заполнены, source_type NULL**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T postgres psql -U db2_user -d db2 -c \
  "SELECT channel_group, COUNT(*) FROM channels GROUP BY channel_group ORDER BY channel_group;"
```
Expected (если seed уже прогнан):
```
HM | 1
SM | 1
MM | 1
TT | 1
E_COM | 6
HORECA | 4
QSR | 4
OTHER | 7
```

Если на dev'е нет 25 каналов (свежая БД без seed) — это нормально, увидим только канал(ы) из тестов. Сразу запустим seed в Step 14.

- [ ] **Step 9: Обновить SQLAlchemy модель `Channel`**

В `backend/app/models/entities.py:107-122` после `universe_outlets` добавить:
```python
from typing import Literal  # уже импортирован выше для других моделей
from app.db.varchar_enum import varchar_enum  # тоже уже импортирован

# в начале файла рядом с другими type-aliases:
ChannelGroup = Literal["HM", "SM", "MM", "TT", "E_COM", "HORECA", "QSR", "OTHER"]
ChannelSourceType = Literal["nielsen", "tsrpt", "gis2", "infoline", "custom"]

# внутри class Channel:
class Channel(Base, TimestampMixin):
    """Справочник каналов сбыта.

    C #16: добавлены channel_group (8 значений, NOT NULL, default OTHER)
    и source_type (5 значений, nullable, NULL = не указан).
    """
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    universe_outlets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_group: Mapped[ChannelGroup] = mapped_column(
        varchar_enum(ChannelGroup, "channel_group_value"),
        nullable=False,
        server_default="OTHER",
    )
    source_type: Mapped[ChannelSourceType | None] = mapped_column(
        varchar_enum(ChannelSourceType, "channel_source_type_value"),
        nullable=True,
    )
```

Если `varchar_enum` не в импортах — добавить `from app.db.varchar_enum import varchar_enum` в верх файла.

- [ ] **Step 10: Обновить Pydantic schemas**

В `backend/app/schemas/channel.py`:
```python
"""Pydantic-схемы справочника каналов сбыта.

B-05: добавлен region для региональной детализации + CRUD endpoints.
C #16: добавлены channel_group (enum 8 значений) и source_type
(enum 5 значений, nullable).
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ChannelGroup = Literal["HM", "SM", "MM", "TT", "E_COM", "HORECA", "QSR", "OTHER"]
ChannelSourceType = Literal["nielsen", "tsrpt", "gis2", "infoline", "custom"]


class ChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    channel_group: ChannelGroup
    source_type: ChannelSourceType | None = None
    region: str | None = None
    universe_outlets: int | None = None
    created_at: datetime


class ChannelCreate(BaseModel):
    """POST /api/channels."""

    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    channel_group: ChannelGroup
    source_type: ChannelSourceType | None = None
    region: str | None = Field(default=None, max_length=100)
    universe_outlets: int | None = Field(default=None, ge=0)


class ChannelUpdate(BaseModel):
    """PATCH /api/channels/{id}."""

    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    channel_group: ChannelGroup | None = None
    source_type: ChannelSourceType | None = None
    region: str | None = Field(default=None, max_length=100)
    universe_outlets: int | None = Field(default=None, ge=0)
```

- [ ] **Step 11: Найти и обновить fixtures каналов в тестах**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend grep -rn "Channel(" tests/ --include="*.py" | head -20
# Найти fabric'и которые создают Channel напрямую без channel_group.
```

В `backend/tests/conftest.py` (если там фабрика канала) — где создаётся `Channel(code=..., name=...)` без `channel_group`, добавить `channel_group="OTHER"` (server_default подстрахует, но явное явное лучше).

Аналогично в любых fixtures в `tests/api/test_channels.py` и `tests/api/test_psk_channels.py` — channel_group="OTHER" в дефолтных body.

- [ ] **Step 12: Добавить 4 теста на новые поля в `test_channels.py`**

В `backend/tests/api/test_channels.py` дописать (используя существующий стиль fixtures):
```python
async def test_create_channel_with_group_and_source(
    authenticated_client: AsyncClient,
):
    """C #16: POST /api/channels принимает channel_group и source_type."""
    resp = await authenticated_client.post(
        "/api/channels",
        json={
            "code": "TEST_HM",
            "name": "Test Hypermarket",
            "channel_group": "HM",
            "source_type": "nielsen",
            "universe_outlets": 100,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["channel_group"] == "HM"
    assert body["source_type"] == "nielsen"


async def test_patch_channel_group(
    authenticated_client: AsyncClient,
    seed_other_channel,  # фабрика "OTHER" канала — добавить в conftest при необходимости
):
    """C #16: PATCH channel_group переводит канал в другую группу."""
    resp = await authenticated_client.patch(
        f"/api/channels/{seed_other_channel.id}",
        json={"channel_group": "HM"},
    )
    assert resp.status_code == 200
    assert resp.json()["channel_group"] == "HM"


async def test_create_channel_invalid_group_422(
    authenticated_client: AsyncClient,
):
    """C #16: Pydantic отвергает channel_group вне 8 значений."""
    resp = await authenticated_client.post(
        "/api/channels",
        json={
            "code": "X",
            "name": "X",
            "channel_group": "INVALID_GROUP",
        },
    )
    assert resp.status_code == 422


async def test_create_channel_invalid_source_type_422(
    authenticated_client: AsyncClient,
):
    """C #16: Pydantic отвергает source_type вне 5 значений."""
    resp = await authenticated_client.post(
        "/api/channels",
        json={
            "code": "X",
            "name": "X",
            "channel_group": "OTHER",
            "source_type": "other_source",
        },
    )
    assert resp.status_code == 422
```

- [ ] **Step 13: Запустить тесты — должны пройти**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/api/test_channels.py tests/migrations/test_c16_backfill.py -v
```
Expected: existing tests still pass + 4 new + 13 migration = passing.

- [ ] **Step 14: Обновить seed_reference_data.py**

В `backend/scripts/seed_reference_data.py:37-63` обновить `CHANNELS_DATA` — добавить `"channel_group"` к каждой из 25 записей. Источник истины = `_resolve_group` из миграции:
```python
CHANNELS_DATA: list[dict[str, Any]] = [
    {"code": "HM", "name": "Гипермаркеты", "channel_group": "HM", "universe_outlets": 822},
    {"code": "SM", "name": "Супермаркеты", "channel_group": "SM", "universe_outlets": 34_083},
    {"code": "MM", "name": "Минимаркеты", "channel_group": "MM", "universe_outlets": 58_080},
    {"code": "TT", "name": "Традиционная розница", "channel_group": "TT", "universe_outlets": 91_444},
    {"code": "Beauty", "name": "Beauty (магазины красоты)", "channel_group": "OTHER", "universe_outlets": 600_000},
    {"code": "Beauty-NS", "name": "Beauty Non-Standard", "channel_group": "OTHER", "universe_outlets": 100},
    {"code": "DS_Pyaterochka", "name": "Пятерочка (Discounter)", "channel_group": "OTHER", "universe_outlets": 18_200},
    {"code": "DS_Magnit", "name": "Магнит (Discounter)", "channel_group": "OTHER", "universe_outlets": 13_528},
    {"code": "HDS", "name": "Hard Discounter", "channel_group": "OTHER", "universe_outlets": 10_003},
    {"code": "ALCO", "name": "Алкомаркеты", "channel_group": "OTHER", "universe_outlets": 18_500},
    {"code": "E-COM_OZ", "name": "E-Commerce Ozon", "channel_group": "E_COM", "universe_outlets": 1},
    {"code": "E-COM_WB", "name": "E-Commerce Wildberries", "channel_group": "E_COM", "universe_outlets": 1},
    {"code": "E-COM_YA", "name": "E-Commerce Яндекс Маркет", "channel_group": "E_COM", "universe_outlets": 1},
    {"code": "E-COM_SBER", "name": "E-Commerce Сбер Маркет", "channel_group": "E_COM", "universe_outlets": 1},
    {"code": "E_COM_E-grocery", "name": "E-Grocery (агрегатор)", "channel_group": "E_COM", "universe_outlets": 10},
    {"code": "HORECA_АЗС", "name": "HoReCa: АЗС", "channel_group": "HORECA", "universe_outlets": 10_000},
    {"code": "HORECA_СПОРТ", "name": "HoReCa: спортивные объекты", "channel_group": "HORECA", "universe_outlets": 355_000},
    {"code": "HORECA_HOTEL", "name": "HoReCa: отели", "channel_group": "HORECA", "universe_outlets": 30_000},
    {"code": "HORECA_Cafe&Rest", "name": "HoReCa: кафе и рестораны", "channel_group": "HORECA", "universe_outlets": 176_000},
    {"code": "Vkusno I tochka", "name": "Вкусно и точка", "channel_group": "QSR", "universe_outlets": 900},
    {"code": "Burger king", "name": "Burger King", "channel_group": "QSR", "universe_outlets": 817},
    {"code": "Rostics", "name": "Rostic's", "channel_group": "QSR", "universe_outlets": 1_150},
    {"code": "Do-Do_pizza", "name": "Додо Пицца", "channel_group": "QSR", "universe_outlets": 817},
    {"code": "VEND_machine", "name": "Вендинговые автоматы", "channel_group": "OTHER", "universe_outlets": 51_450},
    {"code": "E-COM_OZ_Fresh", "name": "E-Commerce Ozon Fresh", "channel_group": "E_COM", "universe_outlets": 1},
]
```

- [ ] **Step 15: Прогнать seed (идемпотентно) — должно отработать без ошибок**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend python -m scripts.seed_reference_data
# Expected output:
#   channels : existing=N  inserted=K  total=25  (где N+K=25, если БД свежая)
```

- [ ] **Step 16: Проверить downgrade reversibility**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic downgrade -1
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
# Expected: b9986ce73ab2 (предыдущий head)

docker compose -f infra/docker-compose.dev.yml exec -T backend alembic upgrade head
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current
# Expected: <rev> (новый head)
```

- [ ] **Step 17: Запустить full pytest — все тесты зелёные**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q --ignore=tests/integration | tail -3
# Expected: 527+ passed (было 514 + 13 миграционных + 4 новых channel).
```

- [ ] **Step 18: Commit T1**

```bash
git add backend/app/models/entities.py backend/app/schemas/channel.py \
        backend/migrations/versions/*c16_channel_group_source_type.py \
        backend/scripts/seed_reference_data.py \
        backend/tests/migrations/test_c16_backfill.py \
        backend/tests/api/test_channels.py \
        backend/tests/conftest.py
# (conftest.py — только если фабрика канала там обновлялась)

git commit -m "$(cat <<'EOF'
feat(c16-t1): добавить channel_group + source_type на channels

- Channel.channel_group (NOT NULL, default OTHER, CHECK 8 значений)
- Channel.source_type (nullable, CHECK 5 значений)
- Миграция c16_channel_group_source_type с auto-backfill через MAPPING_RULES
- Seed обновлён: 25 GORJI каналов получили channel_group
- 13 параметризованных миграционных unit-тестов + 4 теста channel CRUD

Pre-flight для прода: SELECT DISTINCT code FROM channels — кастомные
коды (не из 25 known) попадают в OTHER. UPDATE до миграции если другое.
EOF
)"
```

---

## Task 2: Bulk endpoint `POST /api/project-skus/{psk_id}/channels/bulk`

**Goal:** Добавить atomic bulk-endpoint для привязки N каналов к SKU за один HTTP-вызов с переиспользованием существующего `create_psk_channel`.

**Files:**
- Modify: `backend/app/schemas/project_sku_channel.py` (новые классы `ProjectSKUChannelDefaults`, `BulkChannelLinkCreate`)
- Modify: `backend/app/services/project_sku_channel_service.py` (новая функция `bulk_create_psk_channels`)
- Modify: `backend/app/api/project_sku_channels.py` (новый endpoint после строки 117)
- Modify: `backend/tests/api/test_psk_channels.py` (5 новых тестов)

### Шаги

- [ ] **Step 1: Написать 5 failing-тестов для bulk endpoint'а**

В `backend/tests/api/test_psk_channels.py` добавить (адаптируя fixture-стиль из существующих тестов в файле):
```python
async def test_bulk_create_pscs_success(
    authenticated_client: AsyncClient,
    seed_project_sku,  # существующая fixture, создаёт ProjectSKU
    seed_channels_factory,  # фабрика создаёт N тестовых каналов; добавить если отсутствует
):
    """C #16: POST /channels/bulk создаёт N PSC за один вызов."""
    psk = seed_project_sku
    ch_ids = [seed_channels_factory(group="HM").id, seed_channels_factory(group="SM").id]
    resp = await authenticated_client.post(
        f"/api/project-skus/{psk.id}/channels/bulk",
        json={
            "channel_ids": ch_ids,
            "defaults": {
                "nd_target": "0.5",
                "offtake_target": "10",
                "channel_margin": "0.4",
                "shelf_price_reg": "100",
            },
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body) == 2
    assert {psc["channel_id"] for psc in body} == set(ch_ids)


async def test_bulk_create_duplicate_returns_409(
    authenticated_client: AsyncClient,
    seed_project_sku,
    seed_channels_factory,
):
    """C #16: bulk с уже привязанным каналом → 409, БД не меняется."""
    psk = seed_project_sku
    ch1 = seed_channels_factory()
    # Сначала привязываем ch1 single-call'ом:
    await authenticated_client.post(
        f"/api/project-skus/{psk.id}/channels",
        json={"channel_id": ch1.id, "nd_target": "0.5", "offtake_target": "10",
              "channel_margin": "0.4", "shelf_price_reg": "100"},
    )
    # Теперь bulk с тем же ch1 + новым ch2 — должен 409, ch2 НЕ создан:
    ch2 = seed_channels_factory()
    resp = await authenticated_client.post(
        f"/api/project-skus/{psk.id}/channels/bulk",
        json={
            "channel_ids": [ch1.id, ch2.id],
            "defaults": {"nd_target": "0.5", "offtake_target": "10",
                         "channel_margin": "0.4", "shelf_price_reg": "100"},
        },
    )
    assert resp.status_code == 409

    # Проверяем что ch2 НЕ создан (atomic rollback):
    list_resp = await authenticated_client.get(
        f"/api/project-skus/{psk.id}/channels"
    )
    pscs = list_resp.json()
    linked_ids = {p["channel_id"] for p in pscs}
    assert ch1.id in linked_ids
    assert ch2.id not in linked_ids


async def test_bulk_create_missing_channel_returns_404(
    authenticated_client: AsyncClient,
    seed_project_sku,
):
    """C #16: bulk с несуществующим channel_id → 404."""
    resp = await authenticated_client.post(
        f"/api/project-skus/{seed_project_sku.id}/channels/bulk",
        json={
            "channel_ids": [999_999],
            "defaults": {"nd_target": "0.5", "offtake_target": "10",
                         "channel_margin": "0.4", "shelf_price_reg": "100"},
        },
    )
    assert resp.status_code == 404


async def test_bulk_create_predict_layer_generated(
    authenticated_client: AsyncClient,
    seed_project_sku,
    seed_channels_factory,
    db_session,
):
    """C #16: bulk-create генерирует 43×3=129 PeriodValue для каждого PSC."""
    from app.models import PeriodValue

    psk = seed_project_sku
    ch_ids = [seed_channels_factory().id, seed_channels_factory().id]
    resp = await authenticated_client.post(
        f"/api/project-skus/{psk.id}/channels/bulk",
        json={
            "channel_ids": ch_ids,
            "defaults": {"nd_target": "0.5", "offtake_target": "10",
                         "channel_margin": "0.4", "shelf_price_reg": "100"},
        },
    )
    assert resp.status_code == 201
    created = resp.json()

    # На каждый PSC должно быть 43 периода × 3 сценария × N полей
    # (детальную проверку количеств — adapt под фактический predict-layer).
    # Минимально: > 0 PeriodValue на каждый PSC.
    from sqlalchemy import select, func
    for psc in created:
        count = await db_session.scalar(
            select(func.count()).select_from(PeriodValue).where(
                PeriodValue.psc_id == psc["id"]
            )
        )
        assert count > 0, f"PSC {psc['id']} should have predict PeriodValue"


async def test_bulk_create_empty_list_422(
    authenticated_client: AsyncClient,
    seed_project_sku,
):
    """C #16: bulk с пустым channel_ids → Pydantic 422 (min_length=1)."""
    resp = await authenticated_client.post(
        f"/api/project-skus/{seed_project_sku.id}/channels/bulk",
        json={
            "channel_ids": [],
            "defaults": {"nd_target": "0.5", "offtake_target": "10",
                         "channel_margin": "0.4", "shelf_price_reg": "100"},
        },
    )
    assert resp.status_code == 422
```

Если `seed_channels_factory` отсутствует в `conftest.py` — добавить:
```python
# tests/conftest.py
@pytest_asyncio.fixture
async def seed_channels_factory(db_session: AsyncSession):
    """Фабрика для создания тестовых каналов с уникальными codes."""
    counter = {"n": 0}

    async def _factory(group: str = "OTHER", source_type: str | None = None):
        counter["n"] += 1
        ch = Channel(
            code=f"TEST_CH_{counter['n']}",
            name=f"Test Channel {counter['n']}",
            channel_group=group,
            source_type=source_type,
        )
        db_session.add(ch)
        await db_session.flush()
        return ch

    return _factory
```

- [ ] **Step 2: Запустить — все 5 тестов падают**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/api/test_psk_channels.py -v -k "bulk"
```
Expected: 5 failed (endpoint не существует — 404 Not Found).

- [ ] **Step 3: Добавить Pydantic schemas**

В `backend/app/schemas/project_sku_channel.py` после существующих классов добавить:
```python
class ProjectSKUChannelDefaults(BaseModel):
    """Метрики применяемые ко всем bulk-привязываемым каналам.

    = ProjectSKUChannelCreate минус channel_id. Юзер потом редактирует
    каждый PSC по отдельности через PATCH /api/psk-channels/{id}.
    """

    launch_year: int = Field(default=1, ge=1, le=10)
    launch_month: int = Field(default=1, ge=1, le=12)
    nd_target: Decimal = Field(..., ge=0, le=1)
    nd_ramp_months: int = Field(default=12, ge=1, le=36)
    offtake_target: Decimal = Field(..., ge=0)
    channel_margin: Decimal = Field(..., ge=0, le=1)
    promo_discount: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    promo_share: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    shelf_price_reg: Decimal = Field(..., ge=0)
    logistics_cost_per_kg: Decimal = Field(default=Decimal("0"), ge=0)
    ca_m_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    marketing_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    seasonality_profile_id: int | None = None


class BulkChannelLinkCreate(BaseModel):
    """Body для POST /api/project-skus/{psk_id}/channels/bulk."""

    channel_ids: list[int] = Field(..., min_length=1, max_length=50)
    defaults: ProjectSKUChannelDefaults
```

- [ ] **Step 4: Добавить service `bulk_create_psk_channels`**

В `backend/app/services/project_sku_channel_service.py` обновить импорт схем (добавить `ProjectSKUChannelDefaults`):
```python
from app.schemas.project_sku_channel import (
    ProjectSKUChannelCreate,
    ProjectSKUChannelDefaults,  # ← NEW
    ProjectSKUChannelUpdate,
)
```

И после `create_psk_channel` (строка ~96) добавить:
```python
async def bulk_create_psk_channels(
    session: AsyncSession,
    project_sku_id: int,
    channel_ids: list[int],
    defaults: ProjectSKUChannelDefaults,
) -> list[ProjectSKUChannel]:
    """C #16: создаёт N PSC в outer-транзакции через reuse `create_psk_channel`.

    Atomic: на любую ошибку (ChannelNotFoundError / ProjectSKUChannelDuplicateError)
    endpoint не commit'ит, FastAPI откатит outer transaction. Все ранее flushed
    PSC откатятся вместе.

    Внутренний savepoint pattern в `create_psk_channel` локализует IntegrityError
    per-channel; nested transactions не конфликтуют с outer rollback.

    Errors (пробрасываются как есть из create_psk_channel):
      - `ChannelNotFoundError` — первый невалидный channel_id
      - `ProjectSKUChannelDuplicateError` — первый duplicate (psk_id, channel_id)
    """
    created: list[ProjectSKUChannel] = []
    for ch_id in channel_ids:
        data = ProjectSKUChannelCreate(
            channel_id=ch_id,
            **defaults.model_dump(),
        )
        psc = await create_psk_channel(session, project_sku_id, data)
        created.append(psc)
    return created
```

- [ ] **Step 5: Добавить endpoint**

В `backend/app/api/project_sku_channels.py` после single-channel POST (строка ~117) вставить:
```python
@router.post(
    "/api/project-skus/{psk_id}/channels/bulk",
    response_model=list[ProjectSKUChannelRead],
    status_code=status.HTTP_201_CREATED,
)
async def bulk_link_channels_endpoint(
    psk_id: int,
    data: BulkChannelLinkCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ProjectSKUChannelRead]:
    """C #16: bulk-привязка каналов к SKU в одной транзакции (atomic)."""
    psk = await _require_psk_owned(session, psk_id, current_user)

    try:
        created = await project_sku_channel_service.bulk_create_psk_channels(
            session, psk_id, data.channel_ids, data.defaults
        )
    except project_sku_channel_service.ChannelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more channel_ids not found",
        )
    except project_sku_channel_service.ProjectSKUChannelDuplicateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more channels already attached to this ProjectSKU",
        )

    await invalidation_service.mark_project_stale(session, psk.project_id)
    await session.commit()
    return [ProjectSKUChannelRead.model_validate(psc) for psc in created]
```

И добавить в импорт:
```python
from app.schemas.project_sku_channel import (
    BulkChannelLinkCreate,
    ProjectSKUChannelCreate,
    ProjectSKUChannelRead,
    ProjectSKUChannelUpdate,
)
```

- [ ] **Step 6: Запустить bulk-тесты — должны пройти**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/api/test_psk_channels.py -v -k "bulk"
```
Expected: 5 passed.

- [ ] **Step 7: Запустить full pytest**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q --ignore=tests/integration | tail -3
```
Expected: 532+ passed (после T1 было 527+; T2 добавляет 5).

- [ ] **Step 8: Smoke через curl (опционально)**

```bash
# Получить JWT (см. test fixtures для тестового user'а)
TOKEN="<JWT>"
# Получить какой-нибудь PSK id из БД:
docker compose -f infra/docker-compose.dev.yml exec -T postgres psql -U db2_user -d db2 -c \
  "SELECT id FROM project_skus LIMIT 1;"

# Bulk вызов:
curl -X POST http://localhost:8000/api/project-skus/<psk_id>/channels/bulk \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_ids": [<ch_id_1>, <ch_id_2>],
    "defaults": {
      "nd_target": "0.5", "offtake_target": "10",
      "channel_margin": "0.4", "shelf_price_reg": "100"
    }
  }'
```
Expected: HTTP 201, body = list из 2 PSC объектов.

- [ ] **Step 9: Commit T2**

```bash
git add backend/app/schemas/project_sku_channel.py \
        backend/app/services/project_sku_channel_service.py \
        backend/app/api/project_sku_channels.py \
        backend/tests/api/test_psk_channels.py \
        backend/tests/conftest.py
git commit -m "$(cat <<'EOF'
feat(c16-t2): bulk endpoint POST /channels/bulk (atomic)

- ProjectSKUChannelDefaults + BulkChannelLinkCreate Pydantic schemas
- bulk_create_psk_channels service — reuse create_psk_channel в loop
- Endpoint atomic: на любую ошибку FastAPI откатывает outer transaction
- 5 тестов: success, 409 duplicate, 404 missing, predict layer, 422 empty
EOF
)"
```

---

## Task 3: Frontend — двухфазный `AddChannelsDialog` + grouping

**Goal:** Заменить `AddChannelDialog` (single-select) на `AddChannelsDialog` (двухфазный bulk-flow с группировкой по `channel_group`), обновить TypeScript types, добавить API-обёртки для bulk/create/update channel.

**Files:**
- Modify: `frontend/types/api.ts` (Channel + ChannelCreate + ChannelUpdate; новые типы)
- Create: `frontend/lib/channel-group.ts` (labels + order constants)
- Modify: `frontend/lib/channels.ts` (createChannel, updateChannel, bulkAddChannelsToPsk)
- Modify: `frontend/components/projects/channel-form.tsx` (новый prop `channelHidden`)
- Modify: `frontend/components/projects/channel-dialogs.tsx` (rebuild AddChannelDialog → AddChannelsDialog)
- Modify: `frontend/components/projects/channels-panel.tsx` (использовать AddChannelsDialog)
- Verify: `frontend/components/ui/checkbox.tsx` exists (add if missing)

### Шаги

- [ ] **Step 1: Проверить наличие shadcn/ui Checkbox**

```bash
ls frontend/components/ui/checkbox.tsx
# Если файла нет — добавить компонент через shadcn CLI или скопировать вручную:
# https://ui.shadcn.com/docs/components/checkbox
# (компонент тонкий — обёртка над @radix-ui/react-checkbox)
```
Если отсутствует — добавить минимальный shadcn Checkbox.

- [ ] **Step 2: Обновить `frontend/types/api.ts` — типы для каналов и bulk**

Найти и обновить interface `Channel` (поиск `interface Channel {`):
```typescript
export type ChannelGroup =
  | "HM"
  | "SM"
  | "MM"
  | "TT"
  | "E_COM"
  | "HORECA"
  | "QSR"
  | "OTHER";

export type ChannelSourceType =
  | "nielsen"
  | "tsrpt"
  | "gis2"
  | "infoline"
  | "custom";

export interface Channel {
  id: number;
  code: string;
  name: string;
  channel_group: ChannelGroup;
  source_type: ChannelSourceType | null;
  region: string | null;
  universe_outlets: number | null;
  created_at: string;
}

export interface ChannelCreate {
  code: string;
  name: string;
  channel_group: ChannelGroup;
  source_type?: ChannelSourceType | null;
  region?: string | null;
  universe_outlets?: number | null;
}

export interface ChannelUpdate {
  code?: string;
  name?: string;
  channel_group?: ChannelGroup;
  source_type?: ChannelSourceType | null;
  region?: string | null;
  universe_outlets?: number | null;
}

export interface ProjectSKUChannelDefaults {
  launch_year?: number;
  launch_month?: number;
  nd_target: string;
  nd_ramp_months?: number;
  offtake_target: string;
  channel_margin: string;
  promo_discount?: string;
  promo_share?: string;
  shelf_price_reg: string;
  logistics_cost_per_kg?: string;
  ca_m_rate?: string;
  marketing_rate?: string;
  seasonality_profile_id?: number | null;
}

export interface BulkChannelLinkCreate {
  channel_ids: number[];
  defaults: ProjectSKUChannelDefaults;
}
```

- [ ] **Step 3: Создать `frontend/lib/channel-group.ts`**

```typescript
/**
 * C #16: Display labels + ordering для ChannelGroup и ChannelSourceType.
 * Источник истины enum-значений = backend schemas/channel.py (Literal types).
 */
import type { ChannelGroup, ChannelSourceType } from "@/types/api";

export const CHANNEL_GROUP_LABELS: Record<ChannelGroup, string> = {
  HM: "Гипермаркеты",
  SM: "Супермаркеты",
  MM: "Минимаркеты",
  TT: "Традиционная розница",
  E_COM: "E-Commerce",
  HORECA: "HoReCa",
  QSR: "QSR / Фастфуд",
  OTHER: "Прочее",
};

export const CHANNEL_GROUP_ORDER: ChannelGroup[] = [
  "HM",
  "SM",
  "MM",
  "TT",
  "E_COM",
  "HORECA",
  "QSR",
  "OTHER",
];

export const CHANNEL_SOURCE_TYPE_LABELS: Record<ChannelSourceType, string> = {
  nielsen: "Nielsen",
  tsrpt: "ЦРПТ",
  gis2: "2GIS",
  infoline: "Infoline",
  custom: "Кастомный",
};
```

- [ ] **Step 4: Расширить `frontend/lib/channels.ts`**

Дописать после существующих экспортов:
```typescript
import type {
  BulkChannelLinkCreate,
  Channel,
  ChannelCreate,
  ChannelUpdate,
  ProjectSKUChannelRead,
} from "@/types/api";

// ============================================================
// Channel catalog CRUD (C #16)
// ============================================================

export function createChannel(data: ChannelCreate): Promise<Channel> {
  return apiPost<Channel>("/api/channels", data);
}

export function updateChannel(
  id: number,
  data: ChannelUpdate,
): Promise<Channel> {
  return apiPatch<Channel>(`/api/channels/${id}`, data);
}

export function deleteChannel(id: number): Promise<void> {
  return apiDelete<void>(`/api/channels/${id}`);
}

// ============================================================
// Bulk-link channels to PSK (C #16)
// ============================================================

export function bulkAddChannelsToPsk(
  pskId: number,
  data: BulkChannelLinkCreate,
): Promise<ProjectSKUChannelRead[]> {
  return apiPost<ProjectSKUChannelRead[]>(
    `/api/project-skus/${pskId}/channels/bulk`,
    data,
  );
}
```

- [ ] **Step 5: Добавить prop `channelHidden` в `ChannelForm`**

В `frontend/components/projects/channel-form.tsx`:
```typescript
interface ChannelFormProps {
  state: ChannelFormState;
  onChange: (next: ChannelFormState) => void;
  excludeChannelIds?: number[];
  channelLocked?: boolean;
  /** C #16: полностью скрыть Select канала (для Фазы 2 bulk-диалога). */
  channelHidden?: boolean;
  disabled?: boolean;
  onValidate?: (validateAll: () => boolean) => void;
}

export function ChannelForm({
  state,
  onChange,
  excludeChannelIds = [],
  channelLocked = false,
  channelHidden = false,  // ← новый prop
  disabled = false,
  onValidate,
}: ChannelFormProps) {
  // ... existing code ...

  return (
    <div className="space-y-4">
      {!channelHidden && (
        <div className="space-y-2">
          <Label htmlFor="channel_id">Канал *</Label>
          {/* ... existing Select block ... */}
        </div>
      )}

      {/* === Launch lag ===, остальные блоки без изменений === */}
      {/* ... */}
    </div>
  );
}
```

Также: при `channelHidden=true` уберём из `CHANNEL_FORM_RULES` требование `channel_id: { required: true }` — иначе validateAll вернёт false без выбранного канала. Реализация:
```typescript
const effectiveRules = channelHidden
  ? Object.fromEntries(
      Object.entries(CHANNEL_FORM_RULES).filter(([k]) => k !== "channel_id"),
    )
  : CHANNEL_FORM_RULES;
const { errors, validateOne, validateAll, clearError } =
  useFieldValidation<FormField>(effectiveRules);
```

- [ ] **Step 6: Переписать AddChannelDialog → AddChannelsDialog (двухфазный)**

В `frontend/components/projects/channel-dialogs.tsx` **заменить весь `AddChannelDialog` компонент** на `AddChannelsDialog` (множ. число):
```typescript
"use client";

import { Settings } from "lucide-react";  // или другой icon set если в проекте иной
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";

import {
  ChannelForm,
  EMPTY_CHANNEL_FORM,
  type ChannelFormState,
} from "@/components/projects/channel-form";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CollapsibleSection } from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError } from "@/lib/api";
import { listChannels, bulkAddChannelsToPsk } from "@/lib/channels";
import {
  CHANNEL_GROUP_LABELS,
  CHANNEL_GROUP_ORDER,
} from "@/lib/channel-group";

import type {
  Channel,
  ChannelGroup,
  ProjectSKUChannelDefaults,
} from "@/types/api";

type Phase = "pick" | "defaults";

interface AddChannelsDialogProps {
  pskId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** ID каналов которые уже привязаны — checked + disabled. */
  excludeChannelIds: number[];
  onAdded: () => void;
  /** C16-T4: дополнительные коллбэки для catalog-edit подключим в T4. */
  onCatalogChanged?: () => void;
}

function toDefaultsPayload(state: ChannelFormState): ProjectSKUChannelDefaults {
  // Тот же набор что toPscPayload, но без channel_id, launch_year/month
  // — оставляем как есть, defaults в Pydantic подхватят.
  return {
    launch_year: Number(state.launch_year) || 1,
    launch_month: Number(state.launch_month) || 1,
    nd_target: state.nd_target,
    nd_ramp_months: Number(state.nd_ramp_months),
    offtake_target: state.offtake_target,
    channel_margin: state.channel_margin,
    promo_discount: state.promo_discount,
    promo_share: state.promo_share,
    shelf_price_reg: state.shelf_price_reg,
    logistics_cost_per_kg: state.logistics_cost_per_kg,
    ca_m_rate: state.ca_m_rate,
    marketing_rate: state.marketing_rate,
    seasonality_profile_id:
      state.seasonality_profile_id === ""
        ? null
        : Number(state.seasonality_profile_id),
  };
}

export function AddChannelsDialog({
  pskId,
  open,
  onOpenChange,
  excludeChannelIds,
  onAdded,
}: AddChannelsDialogProps) {
  const [phase, setPhase] = useState<Phase>("pick");
  const [channels, setChannels] = useState<Channel[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [defaults, setDefaults] = useState<ChannelFormState>(EMPTY_CHANNEL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const validateRef = useRef<(() => boolean) | null>(null);

  // Загрузка каналов при открытии
  useEffect(() => {
    if (!open) return;
    listChannels()
      .then(setChannels)
      .catch(() => setError("Ошибка загрузки каналов"));
  }, [open]);

  // Reset при закрытии
  useEffect(() => {
    if (open) return;
    setPhase("pick");
    setSelectedIds(new Set());
    setDefaults(EMPTY_CHANNEL_FORM);
    setError(null);
    setSubmitting(false);
  }, [open]);

  const excludeSet = useMemo(
    () => new Set(excludeChannelIds),
    [excludeChannelIds],
  );

  const channelsByGroup = useMemo(() => {
    const grouped = new Map<ChannelGroup, Channel[]>();
    for (const c of channels) {
      const arr = grouped.get(c.channel_group) ?? [];
      arr.push(c);
      grouped.set(c.channel_group, arr);
    }
    // Сортируем каналы внутри группы по code
    for (const arr of grouped.values()) {
      arr.sort((a, b) => a.code.localeCompare(b.code, "ru"));
    }
    return grouped;
  }, [channels]);

  const toggleChannel = useCallback((id: number, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const handleValidateReady = useCallback((fn: () => boolean) => {
    validateRef.current = fn;
  }, []);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (validateRef.current && !validateRef.current()) return;
    setSubmitting(true);
    try {
      const result = await bulkAddChannelsToPsk(pskId, {
        channel_ids: Array.from(selectedIds),
        defaults: toDefaultsPayload(defaults),
      });
      toast.success(`Привязано ${result.length} каналов`);
      onAdded();
      onOpenChange(false);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось привязать: ${msg}`);
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        {phase === "pick" && (
          <>
            <DialogHeader>
              <DialogTitle>Выбор каналов</DialogTitle>
              <DialogDescription>
                Чекните каналы для привязки к SKU. Метрики (ND, цена, маржа) —
                на следующем шаге, одни для всех выбранных. Тонкую настройку
                сделаете позже через ✎.
              </DialogDescription>
            </DialogHeader>

            <div className="max-h-[60vh] overflow-y-auto space-y-1 py-2">
              {CHANNEL_GROUP_ORDER.map((group) => {
                const groupChannels = channelsByGroup.get(group) ?? [];
                if (groupChannels.length === 0) return null;
                const hasAvailable = groupChannels.some(
                  (c) => !excludeSet.has(c.id),
                );
                return (
                  <CollapsibleSection
                    key={group}
                    title={`${CHANNEL_GROUP_LABELS[group]} (${groupChannels.length})`}
                    defaultOpen={hasAvailable}
                  >
                    <div className="space-y-1 pl-3">
                      {groupChannels.map((c) => {
                        const isLinked = excludeSet.has(c.id);
                        const isChecked = selectedIds.has(c.id);
                        return (
                          <div
                            key={c.id}
                            className="flex items-center gap-2 py-1"
                          >
                            <Checkbox
                              id={`ch-${c.id}`}
                              checked={isLinked || isChecked}
                              disabled={isLinked}
                              onCheckedChange={(v) =>
                                toggleChannel(c.id, v === true)
                              }
                            />
                            <label
                              htmlFor={`ch-${c.id}`}
                              className="flex-1 text-sm cursor-pointer"
                            >
                              <span className="font-medium">{c.code}</span>
                              <span className="text-muted-foreground">
                                {" "}— {c.name}
                              </span>
                              {isLinked && (
                                <span className="ml-2 text-xs text-muted-foreground">
                                  (уже привязан)
                                </span>
                              )}
                            </label>
                            {/* T4: catalog ⚙ button здесь */}
                          </div>
                        );
                      })}
                    </div>
                  </CollapsibleSection>
                );
              })}
            </div>

            {error !== null && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}

            <DialogFooter>
              <span className="text-sm text-muted-foreground mr-auto">
                Выбрано: {selectedIds.size}
              </span>
              <Button
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Отмена
              </Button>
              <Button
                onClick={() => setPhase("defaults")}
                disabled={selectedIds.size === 0}
              >
                Далее →
              </Button>
            </DialogFooter>
          </>
        )}

        {phase === "defaults" && (
          <>
            <DialogHeader>
              <DialogTitle>
                Параметры для {selectedIds.size} выбранных каналов
              </DialogTitle>
              <DialogDescription>
                Одни значения применятся ко всем. Тонкая настройка по
                каждому каналу — позже через ✎ в списке.
              </DialogDescription>
            </DialogHeader>

            <form onSubmit={handleSubmit} className="space-y-4">
              <ChannelForm
                state={defaults}
                onChange={setDefaults}
                channelHidden
                disabled={submitting}
                onValidate={handleValidateReady}
              />

              {error !== null && (
                <p className="text-sm text-destructive" role="alert">
                  {error}
                </p>
              )}

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setPhase("pick")}
                  disabled={submitting}
                >
                  ← Назад
                </Button>
                <Button type="submit" disabled={submitting}>
                  {submitting
                    ? "Привязка..."
                    : `Привязать ${selectedIds.size} каналов`}
                </Button>
              </DialogFooter>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

И удалить старый `AddChannelDialog` компонент из файла (он больше не используется). Оставить `EditChannelDialog` без изменений — он для метрик PSC.

- [ ] **Step 7: Обновить `channels-panel.tsx` — использовать `AddChannelsDialog`**

В `frontend/components/projects/channels-panel.tsx`:
```typescript
import {
  AddChannelsDialog,            // ← было AddChannelDialog
  EditChannelDialog,
} from "@/components/projects/channel-dialogs";
```

И ниже в JSX:
```tsx
<AddChannelsDialog
  pskId={pskId}
  open={addOpen}
  onOpenChange={setAddOpen}
  excludeChannelIds={excludeChannelIds}
  onAdded={reload}
/>
```

- [ ] **Step 8: Frontend restart + purge .next**

```bash
docker compose -f infra/docker-compose.dev.yml stop frontend
docker compose -f infra/docker-compose.dev.yml run --rm frontend sh -c "rm -rf .next/* .next/.[!.]* 2>/dev/null"
docker compose -f infra/docker-compose.dev.yml up -d frontend
```

- [ ] **Step 9: `tsc --noEmit` — 0 ошибок**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```
Expected: пустой output (без ошибок).

- [ ] **Step 10: Manual smoke**

В браузере (http://localhost:3000):
1. Открыть `/projects/{GORJI_ID}/channels`, выбрать любой SKU
2. Нажать «+ Привязать канал»
3. Проверить: 8 групп показаны с (N) счётчиками. HORECA развёрнута (если в ней есть unlinked каналы).
4. Развернуть E-Commerce → чекнуть 2 канала из 6
5. Кнопка «Далее →» доступна, счётчик «Выбрано: 2»
6. Нажать Далее → форма метрик появилась (без Select канала)
7. Кнопка «← Назад» возвращает в Фазу 1 (selection сохранён)
8. Заполнить ND/offtake/margin/price → нажать «Привязать 2 каналов»
9. Toast «Привязано 2 каналов» → диалог закрылся → 2 новые строки в таблице

- [ ] **Step 11: Commit T3**

```bash
git add frontend/types/api.ts \
        frontend/lib/channel-group.ts \
        frontend/lib/channels.ts \
        frontend/components/projects/channel-form.tsx \
        frontend/components/projects/channel-dialogs.tsx \
        frontend/components/projects/channels-panel.tsx \
        frontend/components/ui/checkbox.tsx
# (checkbox.tsx — только если был добавлен в Step 1)
git commit -m "$(cat <<'EOF'
feat(c16-t3): двухфазный AddChannelsDialog с группировкой по channel_group

- Channel/ChannelCreate/ChannelUpdate TS-типы обновлены (channel_group, source_type)
- lib/channel-group.ts: CHANNEL_GROUP_LABELS + CHANNEL_GROUP_ORDER
- lib/channels.ts: createChannel, updateChannel, bulkAddChannelsToPsk
- ChannelForm: новый prop channelHidden (для Фазы 2 диалога)
- AddChannelsDialog (заменяет AddChannelDialog): Фаза pick (чекбоксы по
  группам в CollapsibleSection) → Фаза defaults (общая форма метрик) →
  POST bulk
- channels-panel.tsx использует новый компонент
EOF
)"
```

---

## Task 4: Inline catalog editing — CreateChannelDialog + EditChannelCatalogDialog

**Goal:** Добавить возможность создать кастомный канал и отредактировать существующий (name/group/source_type/region/universe_outlets) прямо из `AddChannelsDialog`.

**Files:**
- Modify: `frontend/components/projects/channel-dialogs.tsx` (extend с двумя новыми компонентами)

### Шаги

- [ ] **Step 1: Добавить `CreateChannelDialog` (sub-dialog)**

В `frontend/components/projects/channel-dialogs.tsx` добавить новый компонент:
```typescript
import {
  CHANNEL_GROUP_LABELS,
  CHANNEL_GROUP_ORDER,
  CHANNEL_SOURCE_TYPE_LABELS,
} from "@/lib/channel-group";
import { createChannel } from "@/lib/channels";
import type {
  ChannelCreate,
  ChannelGroup,
  ChannelSourceType,
} from "@/types/api";

interface CreateChannelDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Вызывается с созданным каналом — родитель добавит его в список и автоматически чекнет. */
  onCreated: (channel: Channel) => void;
}

interface CreateChannelFormState {
  code: string;
  name: string;
  channel_group: ChannelGroup;
  source_type: ChannelSourceType | "";
  region: string;
  universe_outlets: string;
}

const EMPTY_CREATE_CHANNEL_FORM: CreateChannelFormState = {
  code: "",
  name: "",
  channel_group: "OTHER",
  source_type: "custom",
  region: "",
  universe_outlets: "",
};

export function CreateChannelDialog({
  open,
  onOpenChange,
  onCreated,
}: CreateChannelDialogProps) {
  const [form, setForm] = useState<CreateChannelFormState>(
    EMPTY_CREATE_CHANNEL_FORM,
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setForm(EMPTY_CREATE_CHANNEL_FORM);
      setError(null);
      setSubmitting(false);
    }
  }, [open]);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (!form.code.trim() || !form.name.trim()) {
      setError("Код и название обязательны");
      return;
    }
    setSubmitting(true);
    try {
      const payload: ChannelCreate = {
        code: form.code.trim(),
        name: form.name.trim(),
        channel_group: form.channel_group,
        source_type: form.source_type === "" ? null : form.source_type,
        region: form.region.trim() || null,
        universe_outlets:
          form.universe_outlets === ""
            ? null
            : Number(form.universe_outlets),
      };
      const channel = await createChannel(payload);
      toast.success(`Канал «${channel.code}» создан`);
      onCreated(channel);
      onOpenChange(false);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось создать: ${msg}`);
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Новый канал</DialogTitle>
          <DialogDescription>
            Создание кастомного канала. После сохранения он появится в
            списке Фазы 1 и будет автоматически отмечен.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="cch_code">Код *</Label>
            <Input
              id="cch_code"
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
              maxLength={50}
              disabled={submitting}
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="cch_name">Название *</Label>
            <Input
              id="cch_name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              maxLength={255}
              disabled={submitting}
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="cch_group">Группа *</Label>
            <Select
              value={form.channel_group}
              onValueChange={(v) =>
                setForm({ ...form, channel_group: v as ChannelGroup })
              }
              disabled={submitting}
              items={Object.fromEntries(
                CHANNEL_GROUP_ORDER.map((g) => [g, CHANNEL_GROUP_LABELS[g]]),
              )}
            >
              <SelectTrigger id="cch_group">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CHANNEL_GROUP_ORDER.map((g) => (
                  <SelectItem key={g} value={g}>
                    {CHANNEL_GROUP_LABELS[g]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="cch_src">Источник данных</Label>
            <Select
              value={form.source_type === "" ? "__none__" : form.source_type}
              onValueChange={(v) =>
                setForm({
                  ...form,
                  source_type:
                    v === "__none__" ? "" : (v as ChannelSourceType),
                })
              }
              disabled={submitting}
              items={{
                __none__: "—",
                ...Object.fromEntries(
                  Object.entries(CHANNEL_SOURCE_TYPE_LABELS),
                ),
              }}
            >
              <SelectTrigger id="cch_src">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">—</SelectItem>
                {Object.entries(CHANNEL_SOURCE_TYPE_LABELS).map(
                  ([k, v]) => (
                    <SelectItem key={k} value={k}>{v}</SelectItem>
                  ),
                )}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="cch_region">Регион</Label>
              <Input
                id="cch_region"
                value={form.region}
                onChange={(e) =>
                  setForm({ ...form, region: e.target.value })
                }
                maxLength={100}
                disabled={submitting}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="cch_universe">ОКБ (шт.)</Label>
              <Input
                id="cch_universe"
                type="number"
                min="0"
                value={form.universe_outlets}
                onChange={(e) =>
                  setForm({ ...form, universe_outlets: e.target.value })
                }
                disabled={submitting}
              />
            </div>
          </div>

          {error !== null && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Отмена
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Создание..." : "Создать"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Добавить `EditChannelCatalogDialog` (sub-dialog)**

После `CreateChannelDialog` добавить:
```typescript
import { updateChannel } from "@/lib/channels";
import type { Channel } from "@/types/api";

interface EditChannelCatalogDialogProps {
  channel: Channel | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpdated: (channel: Channel) => void;
}

export function EditChannelCatalogDialog({
  channel,
  open,
  onOpenChange,
  onUpdated,
}: EditChannelCatalogDialogProps) {
  const [form, setForm] = useState<CreateChannelFormState>(
    EMPTY_CREATE_CHANNEL_FORM,
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && channel !== null) {
      setForm({
        code: channel.code,
        name: channel.name,
        channel_group: channel.channel_group,
        source_type: channel.source_type ?? "",
        region: channel.region ?? "",
        universe_outlets:
          channel.universe_outlets === null
            ? ""
            : String(channel.universe_outlets),
      });
      setError(null);
      setSubmitting(false);
    }
  }, [open, channel]);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (channel === null) return;
    setError(null);
    setSubmitting(true);
    try {
      const updated = await updateChannel(channel.id, {
        name: form.name.trim(),
        channel_group: form.channel_group,
        source_type: form.source_type === "" ? null : form.source_type,
        region: form.region.trim() || null,
        universe_outlets:
          form.universe_outlets === ""
            ? null
            : Number(form.universe_outlets),
      });
      toast.success(`Канал «${updated.code}» обновлён`);
      onUpdated(updated);
      onOpenChange(false);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось сохранить: ${msg}`);
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            Канал «{channel?.code ?? ""}»
          </DialogTitle>
          <DialogDescription>
            Редактирование канала в каталоге. Изменения видны во всех
            проектах. Код менять нельзя — это якорь для импорта/экспорта.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-3">
          {/* code disabled */}
          <div className="space-y-1">
            <Label htmlFor="ech_code">Код</Label>
            <Input id="ech_code" value={form.code} disabled />
          </div>
          {/* name, channel_group, source_type, region, universe_outlets — те же inputs что в CreateChannelDialog */}
          {/* DRY-tip: можно вынести общую <ChannelCatalogFormFields/> подкомпонент, но для MVP — копия-paste OK */}
          {/* ...копировать поля name/group/source_type/region/universe из CreateChannelDialog (Step 1)... */}

          {error !== null && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Отмена
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Сохранение..." : "Сохранить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

**DRY decision:** дублирование полей name/group/source_type/region/universe в обоих диалогах допустимо для MVP (~30 строк). Если возникнет необходимость третьего места — извлечь `<ChannelCatalogFormFields>` (выходит за scope T4).

- [ ] **Step 3: Подключить sub-dialogs в `AddChannelsDialog`**

В компоненте `AddChannelsDialog` (из T3) добавить state и handlers:
```typescript
const [createDialogOpen, setCreateDialogOpen] = useState(false);
const [editingChannel, setEditingChannel] = useState<Channel | null>(null);

function reloadChannels() {
  listChannels().then(setChannels).catch(() => {});
}

function handleCatalogCreated(channel: Channel) {
  reloadChannels();
  // Автоматически чекнуть новый канал
  setSelectedIds((prev) => new Set(prev).add(channel.id));
}

function handleCatalogUpdated(_channel: Channel) {
  reloadChannels();
}
```

В JSX Фазы 1 добавить:
1. Рядом с именем канала — кнопку ⚙ (Settings icon):
```tsx
<Button
  variant="ghost"
  size="icon"
  className="h-6 w-6 shrink-0"
  type="button"
  onClick={(e) => {
    e.preventDefault();
    setEditingChannel(c);
  }}
  title="Редактировать в каталоге"
>
  <Settings className="h-3 w-3" />
</Button>
```

2. Под списком — кнопку «+ Новый канал»:
```tsx
<Button
  variant="outline"
  size="sm"
  type="button"
  onClick={() => setCreateDialogOpen(true)}
>
  + Новый канал
</Button>
```

3. В конце JSX (после основного `<Dialog>`) рендерить sub-dialogs:
```tsx
<CreateChannelDialog
  open={createDialogOpen}
  onOpenChange={setCreateDialogOpen}
  onCreated={handleCatalogCreated}
/>
<EditChannelCatalogDialog
  channel={editingChannel}
  open={editingChannel !== null}
  onOpenChange={(o) => { if (!o) setEditingChannel(null); }}
  onUpdated={handleCatalogUpdated}
/>
```

- [ ] **Step 4: Frontend restart + purge .next**

```bash
docker compose -f infra/docker-compose.dev.yml stop frontend
docker compose -f infra/docker-compose.dev.yml run --rm frontend sh -c "rm -rf .next/* .next/.[!.]* 2>/dev/null"
docker compose -f infra/docker-compose.dev.yml up -d frontend
```

- [ ] **Step 5: `tsc --noEmit` — 0 ошибок**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

- [ ] **Step 6: Manual smoke**

В браузере:
1. Открыть «+ Привязать канал» на любом SKU
2. Развернуть E-Commerce → клик ⚙ на канале «E-COM_OZ»
3. Изменить «Источник данных» с «—» на «Nielsen» → Сохранить
4. Toast «Канал E-COM_OZ обновлён» → диалог закрылся
5. Повторно открыть ⚙ → проверить что source_type сохранился
6. Нажать «+ Новый канал»
7. Заполнить: Код «X5_CHIZHIK», Название «X5 Чижик», Группа «E-Commerce», Источник «Nielsen»
8. Создать → toast «Канал X5_CHIZHIK создан» → диалог закрылся
9. В Фазе 1 видим X5_CHIZHIK в группе E-Commerce, автоматически чекнут (Выбрано: +1)

- [ ] **Step 7: Commit T4**

```bash
git add frontend/components/projects/channel-dialogs.tsx
git commit -m "$(cat <<'EOF'
feat(c16-t4): inline-редактирование каталога каналов в add-диалоге

- CreateChannelDialog: создание кастомного канала с group + source_type
- EditChannelCatalogDialog: редактирование name/group/source_type/region
- ⚙ кнопка рядом с каждым каналом в Фазе 1
- + Новый канал кнопка под списком
- После create — канал автоматически чекнут в selection
- code immutable (PATCH только name и остальные поля)
EOF
)"
```

---

## Task 5: Integration smoke + acceptance + CHANGELOG + docs + merge

**Goal:** Полная регрессия (pytest + tsc + acceptance), обновление документации, merge в main.

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/CLIENT_FEEDBACK_v2_STATUS.md`
- Modify: `GO5.md`

### Шаги

- [ ] **Step 1: Full backend pytest**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q --ignore=tests/integration | tail -10
```
Expected: 532+ passed (514 base + 4 channel API + 13 migration param + 5 bulk = ~536). Если красные — исправить до commit T5.

- [ ] **Step 2: Acceptance GORJI**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend \
    pytest -q tests/acceptance -m acceptance | tail -5
```
Expected: 6 passed, drift < 0.03%. Если drift вырос — значит channel_group accidentally влияет на расчёт (НЕ должен). Изучить какой Step pipeline'а читает Channel — обычно нет.

- [ ] **Step 3: Frontend tsc**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```
Expected: пустой output (0 ошибок).

- [ ] **Step 4: Manual smoke — полный сценарий из спеки §4.6.2**

В браузере (`/projects/{GORJI_ID}/channels`):
1. Выбрать SKU
2. «+ Привязать канал» → Фаза 1 → проверить 8 групп
3. Развернуть HoReCa → чекнуть 2 канала → Далее → заполнить ND/offtake → Привязать
4. Проверить 2 строки в `ChannelsPanel`
5. Снова открыть диалог → «+ Новый канал» → создать «X5 Чижик» (E_COM, Nielsen)
6. Канал появился в E_COM группе → автоматически чекнут
7. Клик ⚙ на E-COM_OZ → изменить имя на «Ozon Розница» → сохранить
8. Перезагрузить страницу → имя сохранилось

- [ ] **Step 5: Обновить `CHANGELOG.md`**

В секцию `## [Unreleased]` добавить:
```markdown
### Added
- **C #16**: Каналы получили поля `channel_group` (HM/SM/MM/TT/E_COM/HORECA/QSR/OTHER) и `source_type` (Nielsen/ЦРПТ/2GIS/Infoline/custom). Существующие 25 GORJI seed-каналов автоматически отмапплены по паттерну кода. (MEMO 1.4)
- **C #16**: Новый bulk endpoint `POST /api/project-skus/{psk_id}/channels/bulk` для привязки нескольких каналов к SKU за одну atomic-транзакцию.
- **C #16**: Двухфазный диалог «+ Привязать канал»: выбор чекбоксами по группам → одна форма метрик → atomic POST. Заменил старый single-channel `AddChannelDialog`.
- **C #16**: Inline-редактирование каталога каналов из диалога: «+ Новый канал» (создать custom) и ⚙ (изменить name/group/source_type/region).

### Migrations
- `<rev>_c16_channel_group_source_type` — добавлены `channels.channel_group` (NOT NULL, default OTHER, CHECK 8 значений) и `channels.source_type` (nullable, CHECK 5 значений). Auto-backfill для 25 seed-кодов через MAPPING_RULES.

### Pre-flight для прода
Перед `alembic upgrade head` сверить `SELECT DISTINCT code FROM channels` с MAPPING_RULES в миграции. Незнакомые коды попадают в OTHER (тихо). Если есть кастомные каналы которые юзер хочет в специфическую группу — сделать UPDATE до миграции.
```

- [ ] **Step 6: Обновить `docs/CLIENT_FEEDBACK_v2_STATUS.md`**

В таблице Блока 4.1 (строки 117-121) обновить статусы:
```markdown
| Чекбоксы с группировкой HM/SM/MM/TT/E-COM | ✅ | `channel_group` enum на `Channel` (C #16, 8 значений). UI: двухфазный `AddChannelsDialog` с `CollapsibleSection` per группу. |
| Источник данных (Nielsen/ЦРПТ/2GIS/Infoline/кастомный) | ✅ | `source_type` enum на `Channel` (C #16, 5 значений, nullable). UI: Select в Create/Edit catalog диалогах. |
```

Строка про «баг верстки» оставить ⚠️ с пометкой «follow-up issue, отдельная мини-задача».

- [ ] **Step 7: Обновить `GO5.md`**

В секцию «Pre-flight для прода» добавить запись параллельно существующей про C #19:
```markdown
### Pre-flight для прода (важно перед `alembic upgrade head` на проде!)

C #19 (pack format) ... (как раньше)

C #16 (channel groups) добавила миграцию с auto-backfill `channel_group` по паттерну `code`. Перед выкаткой:
\`\`\`sql
SELECT DISTINCT code FROM channels;
\`\`\`
Сверить с MAPPING_RULES (`EXACT_RULES` + `PREFIX_RULES`) в миграции `<rev>_c16_channel_group_source_type.py`. Кастомные коды попадут в OTHER (тихо). Если для какого-то канала нужна другая группа — сделать UPDATE до миграции.
```

Также обновить таблицу статуса в разделе «Где остановились» — отметить C #16 как ✅.

- [ ] **Step 8: Финальный pytest + tsc + acceptance**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration | tail -3
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/acceptance -m acceptance | tail -3
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

- [ ] **Step 9: Commit T5 (docs only)**

```bash
git add CHANGELOG.md docs/CLIENT_FEEDBACK_v2_STATUS.md GO5.md
git commit -m "$(cat <<'EOF'
docs(c16): CHANGELOG + status + GO5 pre-flight для C #16

- Unreleased: channel_group, source_type, bulk endpoint, двухфазный диалог
- CLIENT_FEEDBACK_v2_STATUS: 4.1 чекбоксы ✅, source_type ✅
- GO5.md: Pre-flight для прода — sanity SELECT DISTINCT code FROM channels
EOF
)"
```

- [ ] **Step 10: Merge в main**

Эпик multi-task TDD-цепочка → `--no-ff` (как было в C #13, C #14):
```bash
git checkout main
git merge --no-ff feat/c16-channel-groups -m "$(cat <<'EOF'
Merge C #16 — каналы группы + source_type + bulk endpoint

5-task subagent-driven эпик:
- T1 schema/migration + auto-backfill 25 GORJI каналов
- T2 bulk endpoint POST /channels/bulk (atomic)
- T3 двухфазный AddChannelsDialog с группировкой
- T4 inline catalog edit (Create + EditCatalog диалоги)
- T5 integration smoke + docs

Разблокирует C #15 (P&L pivot), #17 (АКБ авторасчёт), #18 (Waterfall).
EOF
)"
git push origin main
```

- [ ] **Step 11: Удалить feature ветку**

```bash
git branch -d feat/c16-channel-groups
git push origin --delete feat/c16-channel-groups
```

- [ ] **Step 12: Финальная проверка**

```bash
git log --oneline -10            # должны видеть merge commit + 5 T-commits
git status                       # clean
docker compose -f infra/docker-compose.dev.yml exec -T backend alembic current  # <rev> (head)
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration | tail -1  # 532+ passed
```

---

## Чек-лист coverage (spec → plan)

| §spec | Покрыто в | Note |
|---|---|---|
| §4.1.1 Channel.channel_group + source_type SQLAlchemy | T1 Step 9 | ✅ |
| §4.1.2 Pydantic schemas | T1 Step 10 | ✅ |
| §4.1.3 TS types | T3 Step 2 | ✅ |
| §4.2 Миграция + backfill | T1 Step 4-7 + tests Step 2-6 | ✅ |
| §4.3 Seed update | T1 Step 14 | ✅ |
| §4.4.1-4 Bulk endpoint | T2 Step 1-5 | ✅ |
| §4.5.1 AddChannelsDialog двухфазный | T3 Step 6 | ✅ |
| §4.5.2 CreateChannelDialog | T4 Step 1 | ✅ |
| §4.5.3 EditChannelCatalogDialog | T4 Step 2 | ✅ |
| §4.5.4 lib/channels.ts | T3 Step 4 | ✅ |
| §4.6.1 Backend tests | T1 + T2 | ✅ |
| §4.6.2 Frontend smoke | T3 Step 10 + T4 Step 6 + T5 Step 4 | ✅ |
| §4.7 CHANGELOG + docs | T5 Step 5-7 | ✅ |

---

## Спека → план: отклонения

Ни одного. План реализует §4 спеки точка-в-точку.

---

## Open notes для исполнителя

- **Frontend Checkbox:** если в проекте уже есть `@base-ui/react` Checkbox или другой паттерн — использовать существующий, не плодить дубли.
- **`<CollapsibleSection>`:** компонент уже есть из C #22 — проверить точное API (`title`, `defaultOpen`, children). Не переоткрывать.
- **DRY между Create и Edit catalog dialogs:** дублирование полей (~30 строк) допустимо для MVP. Если будет третий потребитель — извлечь `<ChannelCatalogFormFields>`.
- **Pre-flight для прода:** деплой делает пользователь по команде. Не пушить feat/c16-channel-groups в master без явного ok.
- **Branch convention:** `feat/c16-channel-groups`, merge `--no-ff` (TDD цепочка).
