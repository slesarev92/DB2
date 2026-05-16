"""ProjectSKUChannel bulk endpoint tests (C #16, Task 2).

5 тестов для POST /api/project-skus/{psk_id}/channels/bulk.
Паттерн fixtures: auth_client + db_session + helper _create_psk.
Channel'ы создаются напрямую через db_session (нет seed_channels_factory
в conftest — инлайн-хелпер _make_channel достаточен).
"""
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel

# ============================================================
# Helpers — повторяем паттерн из test_channels.py
# ============================================================

SKU_BODY = {
    "brand": "Gorji",
    "name": "Gorji Bulk Test 0.5L",
}

PROJECT_BODY = {
    "name": "Test project for bulk channels",
    "start_date": "2025-01-01",
}

_ch_counter = {"n": 0}


async def _create_psk(client: AsyncClient) -> int:
    """Создаёт project + sku + project_sku, возвращает psk.id."""
    project_resp = await client.post("/api/projects", json=PROJECT_BODY)
    project_id = project_resp.json()["id"]

    sku_resp = await client.post("/api/skus", json=SKU_BODY)
    sku_id = sku_resp.json()["id"]

    psk_resp = await client.post(
        f"/api/projects/{project_id}/skus", json={"sku_id": sku_id}
    )
    return psk_resp.json()["id"]


async def _make_channel(
    db_session: AsyncSession,
    group: str = "OTHER",
    source_type: str | None = None,
) -> Channel:
    """Создаёт тестовый канал с уникальным кодом в текущей транзакции."""
    _ch_counter["n"] += 1
    ch = Channel(
        code=f"BULK_TEST_CH_{_ch_counter['n']}",
        name=f"Bulk Test Channel {_ch_counter['n']}",
        channel_group=group,
        source_type=source_type,
    )
    db_session.add(ch)
    await db_session.flush()
    return ch


_DEFAULTS_JSON = {
    "nd_target": "0.5",
    "offtake_target": "10",
    "channel_margin": "0.4",
    "shelf_price_reg": "100",
}

# ============================================================
# C #16 T2: 5 bulk endpoint tests
# ============================================================


async def test_bulk_create_pscs_success(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """C #16: POST /channels/bulk создаёт N PSC за один вызов."""
    psk_id = await _create_psk(auth_client)
    ch1 = await _make_channel(db_session, group="HM")
    ch2 = await _make_channel(db_session, group="SM")

    resp = await auth_client.post(
        f"/api/project-skus/{psk_id}/channels/bulk",
        json={
            "channel_ids": [ch1.id, ch2.id],
            "defaults": _DEFAULTS_JSON,
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert len(body) == 2
    assert {psc["channel_id"] for psc in body} == {ch1.id, ch2.id}


async def test_bulk_create_duplicate_returns_409(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """C #16: bulk с уже привязанным каналом → 409, БД не меняется (atomic)."""
    psk_id = await _create_psk(auth_client)
    ch1 = await _make_channel(db_session)
    ch2 = await _make_channel(db_session)

    # Сначала привязываем ch1 через single-channel endpoint
    single_resp = await auth_client.post(
        f"/api/project-skus/{psk_id}/channels",
        json={
            "channel_id": ch1.id,
            **_DEFAULTS_JSON,
        },
    )
    assert single_resp.status_code == 201

    # Bulk с НОВЫМ ch2 (вставится первым) + duplicate ch1 (упадёт)
    # — порядок [ch2, ch1] критичен: ch2 успешно flush'нется + predict-
    # layer (129 PeriodValue), затем ch1 поднимет DuplicateError. Outer
    # transaction должна откатить ВСЁ (ch2 + 129 PeriodValue).
    # Если порядок [ch1, ch2] — failure на iter1, ch2 не вставлялся
    # никогда → assert тривиально проходит даже без rollback.
    bulk_resp = await auth_client.post(
        f"/api/project-skus/{psk_id}/channels/bulk",
        json={
            "channel_ids": [ch2.id, ch1.id],
            "defaults": _DEFAULTS_JSON,
        },
    )
    assert bulk_resp.status_code == 409

    # Atomic guarantee: ch2 НЕ должен быть в БД (rollback после ch1 failure)
    list_resp = await auth_client.get(f"/api/project-skus/{psk_id}/channels")
    assert list_resp.status_code == 200
    linked_ids = {p["channel_id"] for p in list_resp.json()}
    assert ch1.id in linked_ids
    assert ch2.id not in linked_ids, (
        "atomic rollback нарушен: ch2 был вставлен до DuplicateError на ch1, "
        "но остался в БД после rollback'а outer transaction"
    )

    # Дополнительно: проверяем что predict-layer ch2 (129 PeriodValue)
    # тоже откатился — это финальный hardening atomic guarantee.
    from sqlalchemy import func, select

    from app.models import PeriodValue, ProjectSKUChannel

    orphan_pv_count = await db_session.scalar(
        select(func.count())
        .select_from(PeriodValue)
        .join(
            ProjectSKUChannel,
            PeriodValue.psk_channel_id == ProjectSKUChannel.id,
        )
        .where(ProjectSKUChannel.channel_id == ch2.id)
    )
    assert orphan_pv_count == 0, (
        f"ch2 predict-layer not rolled back: {orphan_pv_count} orphan PeriodValues"
    )


async def test_bulk_create_missing_channel_returns_404(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """C #16: bulk с несуществующим channel_id → 404."""
    psk_id = await _create_psk(auth_client)

    resp = await auth_client.post(
        f"/api/project-skus/{psk_id}/channels/bulk",
        json={
            "channel_ids": [999_999],
            "defaults": _DEFAULTS_JSON,
        },
    )
    assert resp.status_code == 404


async def test_bulk_create_predict_layer_generated(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """C #16: bulk-create генерирует PeriodValue predict-слой для каждого PSC."""
    from app.models import PeriodValue

    psk_id = await _create_psk(auth_client)
    ch1 = await _make_channel(db_session)
    ch2 = await _make_channel(db_session)

    resp = await auth_client.post(
        f"/api/project-skus/{psk_id}/channels/bulk",
        json={
            "channel_ids": [ch1.id, ch2.id],
            "defaults": _DEFAULTS_JSON,
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    assert len(created) == 2

    # Каждый PSC должен иметь хотя бы один PeriodValue (predict-слой)
    for psc in created:
        count = await db_session.scalar(
            select(func.count())
            .select_from(PeriodValue)
            .where(PeriodValue.psk_channel_id == psc["id"])
        )
        assert count is not None and count > 0, (
            f"PSC id={psc['id']} должен иметь predict PeriodValue, но count={count}"
        )


async def test_bulk_create_empty_list_422(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """C #16: bulk с пустым channel_ids → Pydantic 422 (min_length=1)."""
    psk_id = await _create_psk(auth_client)

    resp = await auth_client.post(
        f"/api/project-skus/{psk_id}/channels/bulk",
        json={
            "channel_ids": [],
            "defaults": _DEFAULTS_JSON,
        },
    )
    assert resp.status_code == 422
