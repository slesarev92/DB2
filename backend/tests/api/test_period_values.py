"""PeriodValues API tests (задача 1.5).

Покрывает критерии:
  - GET возвращает значения с правильным приоритетом (actual > finetuned > predict)
  - PATCH создаёт новую версию (append-only), is_overridden = true
  - DELETE override убирает finetuned-версии, GET возвращает predict
  - view_mode: hybrid, fact_only, plan_only, compare

Predict-слой в задаче 1.5 не генерируется автоматически (это задача 2.5).
Тесты создают predict вручную через сервис, чтобы проверить приоритеты.
Actual endpoint не реализован (B-02 в backlog), но архитектурно
поддерживается через source_type — тесты вставляют actual напрямую через
db_session для проверки приоритета слоёв.
"""
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Period,
    PeriodValue,
    Scenario,
    ScenarioType,
    SourceType,
)


# ============================================================
# Helpers
# ============================================================


SKU_BODY = {"brand": "Gorji", "name": "Test SKU"}
PROJECT_BODY = {"name": "Period values test", "start_date": "2025-01-01"}


async def _setup_psk_channel(
    auth_client: AsyncClient, db_session: AsyncSession
) -> tuple[int, int, int]:
    """Создаёт project + sku + project_sku + project_sku_channel.

    Возвращает (project_id, base_scenario_id, psk_channel_id).
    """
    project_id = (await auth_client.post("/api/projects", json=PROJECT_BODY)).json()["id"]
    sku_id = (await auth_client.post("/api/skus", json=SKU_BODY)).json()["id"]
    psk_id = (
        await auth_client.post(
            f"/api/projects/{project_id}/skus", json={"sku_id": sku_id}
        )
    ).json()["id"]

    # HM канал из засеянных в conftest
    from app.models import Channel

    hm = await db_session.scalar(select(Channel).where(Channel.code == "HM"))
    assert hm is not None

    psk_channel_id = (
        await auth_client.post(
            f"/api/project-skus/{psk_id}/channels", json={"channel_id": hm.id}
        )
    ).json()["id"]

    base_scenario = await db_session.scalar(
        select(Scenario).where(
            Scenario.project_id == project_id,
            Scenario.type == ScenarioType.BASE,
        )
    )
    assert base_scenario is not None

    return project_id, base_scenario.id, psk_channel_id


async def _get_period(db_session: AsyncSession, period_number: int) -> int:
    period = await db_session.scalar(
        select(Period).where(Period.period_number == period_number)
    )
    assert period is not None
    return period.id


async def _add_layer_directly(
    db_session: AsyncSession,
    psk_channel_id: int,
    scenario_id: int,
    period_id: int,
    source_type: SourceType,
    values: dict,
    version_id: int = 1,
    is_overridden: bool = False,
) -> None:
    """Добавляет PeriodValue напрямую через session — для setup'а тестов
    приоритетов (predict / actual создаются не через API)."""
    db_session.add(
        PeriodValue(
            psk_channel_id=psk_channel_id,
            scenario_id=scenario_id,
            period_id=period_id,
            source_type=source_type,
            version_id=version_id,
            values=values,
            is_overridden=is_overridden,
        )
    )
    await db_session.flush()


# ============================================================
# 1. PATCH создаёт finetuned v1 + is_overridden=True
# ============================================================


async def test_patch_creates_finetuned_version_1(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psk_channel_id = await _setup_psk_channel(
        auth_client, db_session
    )
    period_id = await _get_period(db_session, 1)

    resp = await auth_client.patch(
        f"/api/project-sku-channels/{psk_channel_id}/values/{period_id}"
        f"?scenario_id={scenario_id}",
        json={"values": {"nd": 0.5, "offtake": 12.3}},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "finetuned"
    assert data["version_id"] == 1
    assert data["is_overridden"] is True
    assert data["values"] == {"nd": 0.5, "offtake": 12.3}


# ============================================================
# 2. PATCH второй раз — version_id = 2 (append-only)
# ============================================================


async def test_patch_twice_creates_two_versions(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psk_channel_id = await _setup_psk_channel(
        auth_client, db_session
    )
    period_id = await _get_period(db_session, 1)
    url = (
        f"/api/project-sku-channels/{psk_channel_id}/values/{period_id}"
        f"?scenario_id={scenario_id}"
    )

    first = await auth_client.patch(url, json={"values": {"nd": 0.5}})
    second = await auth_client.patch(url, json={"values": {"nd": 0.6}})

    assert first.json()["version_id"] == 1
    assert second.json()["version_id"] == 2

    # Проверяем что в БД действительно 2 строки finetuned
    rows = (
        await db_session.scalars(
            select(PeriodValue).where(
                PeriodValue.psk_channel_id == psk_channel_id,
                PeriodValue.period_id == period_id,
                PeriodValue.source_type == SourceType.FINETUNED,
            )
        )
    ).all()
    assert len(rows) == 2


# ============================================================
# 3. GET hybrid с только predict — возвращает predict
# ============================================================


async def test_hybrid_returns_predict_when_only_predict(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psk_channel_id = await _setup_psk_channel(
        auth_client, db_session
    )
    period_id = await _get_period(db_session, 1)

    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, period_id,
        source_type=SourceType.PREDICT,
        values={"nd": 0.20, "offtake": 8.0},
    )

    resp = await auth_client.get(
        f"/api/project-sku-channels/{psk_channel_id}/values"
        f"?scenario_id={scenario_id}"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source_type"] == "predict"
    assert data[0]["values"]["nd"] == 0.20
    assert data[0]["is_overridden"] is False


# ============================================================
# 4. GET hybrid: finetuned побеждает predict
# ============================================================


async def test_hybrid_finetuned_beats_predict(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psk_channel_id = await _setup_psk_channel(
        auth_client, db_session
    )
    period_id = await _get_period(db_session, 1)

    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, period_id,
        source_type=SourceType.PREDICT,
        values={"nd": 0.20},
    )
    # PATCH через API — создаст finetuned v1
    await auth_client.patch(
        f"/api/project-sku-channels/{psk_channel_id}/values/{period_id}"
        f"?scenario_id={scenario_id}",
        json={"values": {"nd": 0.45}},
    )

    resp = await auth_client.get(
        f"/api/project-sku-channels/{psk_channel_id}/values"
        f"?scenario_id={scenario_id}"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source_type"] == "finetuned"
    assert data[0]["values"]["nd"] == 0.45  # finetuned побеждает
    assert data[0]["is_overridden"] is True


# ============================================================
# 5. GET hybrid: actual побеждает всё
# ============================================================


async def test_hybrid_actual_beats_finetuned_and_predict(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psk_channel_id = await _setup_psk_channel(
        auth_client, db_session
    )
    period_id = await _get_period(db_session, 1)

    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, period_id,
        SourceType.PREDICT, {"nd": 0.20},
    )
    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, period_id,
        SourceType.FINETUNED, {"nd": 0.45}, version_id=1, is_overridden=True,
    )
    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, period_id,
        SourceType.ACTUAL, {"nd": 0.52}, is_overridden=False,
    )

    resp = await auth_client.get(
        f"/api/project-sku-channels/{psk_channel_id}/values"
        f"?scenario_id={scenario_id}"
    )

    data = resp.json()
    assert len(data) == 1
    assert data[0]["source_type"] == "actual"
    assert data[0]["values"]["nd"] == 0.52


# ============================================================
# 6. GET hybrid: berёт latest finetuned версию
# ============================================================


async def test_hybrid_takes_latest_finetuned_version(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psk_channel_id = await _setup_psk_channel(
        auth_client, db_session
    )
    period_id = await _get_period(db_session, 1)
    url = (
        f"/api/project-sku-channels/{psk_channel_id}/values/{period_id}"
        f"?scenario_id={scenario_id}"
    )

    await auth_client.patch(url, json={"values": {"nd": 0.30}})  # v1
    await auth_client.patch(url, json={"values": {"nd": 0.40}})  # v2
    await auth_client.patch(url, json={"values": {"nd": 0.50}})  # v3

    resp = await auth_client.get(
        f"/api/project-sku-channels/{psk_channel_id}/values"
        f"?scenario_id={scenario_id}"
    )

    data = resp.json()
    assert data[0]["values"]["nd"] == 0.50  # latest version


# ============================================================
# 7. fact_only: только actual, predict/finetuned игнорируются
# ============================================================


async def test_fact_only_returns_only_actual(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psk_channel_id = await _setup_psk_channel(
        auth_client, db_session
    )
    p1 = await _get_period(db_session, 1)
    p2 = await _get_period(db_session, 2)

    # p1: predict + finetuned + actual
    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, p1, SourceType.PREDICT, {"nd": 0.2}
    )
    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, p1, SourceType.FINETUNED,
        {"nd": 0.4}, is_overridden=True,
    )
    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, p1, SourceType.ACTUAL, {"nd": 0.5}
    )
    # p2: только predict
    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, p2, SourceType.PREDICT, {"nd": 0.25}
    )

    resp = await auth_client.get(
        f"/api/project-sku-channels/{psk_channel_id}/values"
        f"?scenario_id={scenario_id}&view_mode=fact_only"
    )

    data = resp.json()
    # Только p1 (где есть actual)
    assert len(data) == 1
    assert data[0]["period_number"] == 1
    assert data[0]["source_type"] == "actual"
    assert data[0]["values"]["nd"] == 0.5


# ============================================================
# 8. plan_only: actual игнорируется, finetuned > predict
# ============================================================


async def test_plan_only_excludes_actual(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psk_channel_id = await _setup_psk_channel(
        auth_client, db_session
    )
    period_id = await _get_period(db_session, 1)

    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, period_id,
        SourceType.PREDICT, {"nd": 0.20},
    )
    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, period_id,
        SourceType.FINETUNED, {"nd": 0.45}, is_overridden=True,
    )
    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, period_id,
        SourceType.ACTUAL, {"nd": 0.52},
    )

    resp = await auth_client.get(
        f"/api/project-sku-channels/{psk_channel_id}/values"
        f"?scenario_id={scenario_id}&view_mode=plan_only"
    )

    data = resp.json()
    assert len(data) == 1
    # Actual игнорируется → finetuned побеждает
    assert data[0]["source_type"] == "finetuned"
    assert data[0]["values"]["nd"] == 0.45


# ============================================================
# 9. compare: все три слоя в одной структуре
# ============================================================


async def test_compare_returns_all_layers(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psk_channel_id = await _setup_psk_channel(
        auth_client, db_session
    )
    period_id = await _get_period(db_session, 1)

    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, period_id,
        SourceType.PREDICT, {"nd": 0.20},
    )
    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, period_id,
        SourceType.FINETUNED, {"nd": 0.45}, is_overridden=True,
    )
    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, period_id,
        SourceType.ACTUAL, {"nd": 0.52},
    )

    resp = await auth_client.get(
        f"/api/project-sku-channels/{psk_channel_id}/values"
        f"?scenario_id={scenario_id}&view_mode=compare"
    )

    data = resp.json()
    assert len(data) == 1
    item = data[0]
    assert item["predict"] == {"nd": 0.20}
    assert item["finetuned"] == {"nd": 0.45}
    assert item["actual"] == {"nd": 0.52}


# ============================================================
# 10. DELETE override: удаляет ВСЕ finetuned версии
# ============================================================


async def test_delete_override_removes_all_finetuned(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psk_channel_id = await _setup_psk_channel(
        auth_client, db_session
    )
    period_id = await _get_period(db_session, 1)
    url = (
        f"/api/project-sku-channels/{psk_channel_id}/values/{period_id}"
        f"?scenario_id={scenario_id}"
    )

    await auth_client.patch(url, json={"values": {"nd": 0.3}})
    await auth_client.patch(url, json={"values": {"nd": 0.4}})
    await auth_client.patch(url, json={"values": {"nd": 0.5}})

    delete_resp = await auth_client.delete(
        f"/api/project-sku-channels/{psk_channel_id}/values/{period_id}/override"
        f"?scenario_id={scenario_id}"
    )

    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted_versions"] == 3

    # Должно остаться 0 finetuned строк
    rows = (
        await db_session.scalars(
            select(PeriodValue).where(
                PeriodValue.psk_channel_id == psk_channel_id,
                PeriodValue.period_id == period_id,
                PeriodValue.source_type == SourceType.FINETUNED,
            )
        )
    ).all()
    assert len(rows) == 0


# ============================================================
# 11. DELETE override + GET → возвращает predict
# ============================================================


async def test_after_reset_hybrid_returns_predict(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, scenario_id, psk_channel_id = await _setup_psk_channel(
        auth_client, db_session
    )
    period_id = await _get_period(db_session, 1)

    # predict есть в БД (поставили вручную, как в задаче 2.5 будет делать predict generator)
    await _add_layer_directly(
        db_session, psk_channel_id, scenario_id, period_id,
        SourceType.PREDICT, {"nd": 0.20},
    )

    # PATCH создаёт finetuned
    await auth_client.patch(
        f"/api/project-sku-channels/{psk_channel_id}/values/{period_id}"
        f"?scenario_id={scenario_id}",
        json={"values": {"nd": 0.45}},
    )

    # DELETE override
    await auth_client.delete(
        f"/api/project-sku-channels/{psk_channel_id}/values/{period_id}/override"
        f"?scenario_id={scenario_id}"
    )

    # GET hybrid должен вернуть predict
    resp = await auth_client.get(
        f"/api/project-sku-channels/{psk_channel_id}/values"
        f"?scenario_id={scenario_id}"
    )
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source_type"] == "predict"
    assert data[0]["values"]["nd"] == 0.20
    assert data[0]["is_overridden"] is False


# ============================================================
# 12. PATCH с scenario из чужого проекта → 400
# ============================================================


async def test_patch_with_foreign_scenario_returns_400(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Setup 1: project A с psk_channel
    _, _, psk_channel_id = await _setup_psk_channel(auth_client, db_session)

    # Setup 2: отдельный project B с другим scenario
    project_b_id = (
        await auth_client.post(
            "/api/projects", json={"name": "Other", "start_date": "2025-01-01"}
        )
    ).json()["id"]
    foreign_scenario = await db_session.scalar(
        select(Scenario).where(
            Scenario.project_id == project_b_id,
            Scenario.type == ScenarioType.BASE,
        )
    )
    assert foreign_scenario is not None

    period_id = await _get_period(db_session, 1)

    resp = await auth_client.patch(
        f"/api/project-sku-channels/{psk_channel_id}/values/{period_id}"
        f"?scenario_id={foreign_scenario.id}",
        json={"values": {"nd": 0.5}},
    )

    assert resp.status_code == 400
    assert "does not belong" in resp.json()["detail"].lower()
