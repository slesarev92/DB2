"""Integration tests для sensitivity_service + endpoint (4.4 / E-09).

Стратегия:
- Проверяем service напрямую (compute_sensitivity на минимальном проекте)
- Endpoint проверяем через httpx auth_client
- Структуру response: 4 параметра × 5 уровней = 20 cells
- Базовое поведение: delta=0 для каждого параметра == base values
- Direction sanity: -20% ND → меньше NPV; -20% COGS → больше NPV
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sensitivity_service import (
    PARAM_COGS,
    PARAM_ND,
    PARAM_OFFTAKE,
    PARAM_SHELF,
    SENSITIVITY_DELTAS,
    SENSITIVITY_PARAMS,
    compute_sensitivity,
)
from tests.api.test_calculation import _seed_minimal_project


# ============================================================
# Service-level tests
# ============================================================


class TestComputeSensitivity:
    async def test_returns_correct_structure(
        self, db_session: AsyncSession
    ):
        """Response содержит 4 params × 5 deltas = 20 cells + base метрики."""
        project_id, scenario_id, _, _ = await _seed_minimal_project(db_session)

        result = await compute_sensitivity(db_session, project_id, scenario_id)

        assert "base_npv_y1y10" in result
        assert "base_cm_ratio" in result
        assert result["deltas"] == list(SENSITIVITY_DELTAS)
        assert result["params"] == list(SENSITIVITY_PARAMS)
        assert len(result["cells"]) == 4 * 5  # 20

        # Каждая cell имеет нужные ключи
        for cell in result["cells"]:
            assert "parameter" in cell
            assert "delta" in cell
            assert "npv_y1y10" in cell
            assert "cm_ratio" in cell

    async def test_delta_zero_matches_base(self, db_session: AsyncSession):
        """delta=0 для любого параметра == base_npv (sanity check)."""
        project_id, scenario_id, _, _ = await _seed_minimal_project(db_session)
        result = await compute_sensitivity(db_session, project_id, scenario_id)

        base_npv = result["base_npv_y1y10"]
        # Все 4 параметра при delta=0 должны давать тот же NPV
        for cell in result["cells"]:
            if cell["delta"] == 0.0:
                assert cell["npv_y1y10"] == pytest.approx(base_npv)
                assert cell["cm_ratio"] == pytest.approx(
                    result["base_cm_ratio"]
                )

    async def test_nd_changes_npv(self, db_session: AsyncSession):
        """ND изменение даёт ОТЛИЧНЫЙ от base NPV (sign зависит от unit economics).

        Note: _seed_minimal_project имеет negative GP/unit (test fixture
        для ROI overflow protection D-06), поэтому больше volume = больше
        loss = меньше NPV. Direction assertion ниже (для COGS/shelf) валид
        независимо от unit economics, для ND/offtake — нет.
        """
        project_id, scenario_id, _, _ = await _seed_minimal_project(db_session)
        result = await compute_sensitivity(db_session, project_id, scenario_id)

        base_npv = result["base_npv_y1y10"]
        nd_minus20 = next(
            c for c in result["cells"]
            if c["parameter"] == PARAM_ND and c["delta"] == -0.20
        )
        nd_plus20 = next(
            c for c in result["cells"]
            if c["parameter"] == PARAM_ND and c["delta"] == 0.20
        )
        # Значения отличаются от base
        assert nd_minus20["npv_y1y10"] != pytest.approx(base_npv)
        assert nd_plus20["npv_y1y10"] != pytest.approx(base_npv)
        # Симметрия: -20 и +20 отличаются (movement)
        assert nd_minus20["npv_y1y10"] != pytest.approx(nd_plus20["npv_y1y10"])

    async def test_lower_cogs_increases_npv(self, db_session: AsyncSession):
        """-20% COGS → меньше material cost → больше CM → больше NPV.

        Direction COGS валид независимо от unit economics — снижение
        затрат всегда улучшает NPV (при прочих равных).
        """
        project_id, scenario_id, _, _ = await _seed_minimal_project(db_session)
        result = await compute_sensitivity(db_session, project_id, scenario_id)

        cogs_minus20 = next(
            c for c in result["cells"]
            if c["parameter"] == PARAM_COGS and c["delta"] == -0.20
        )
        cogs_plus20 = next(
            c for c in result["cells"]
            if c["parameter"] == PARAM_COGS and c["delta"] == 0.20
        )
        # -20% COGS даёт БОЛЬШИЙ NPV (меньше затрат), +20% меньший
        assert cogs_minus20["npv_y1y10"] > result["base_npv_y1y10"]
        assert cogs_plus20["npv_y1y10"] < result["base_npv_y1y10"]

    async def test_higher_shelf_increases_npv(
        self, db_session: AsyncSession
    ):
        """+20% shelf → больше revenue (тот же volume) → больше NPV.

        Direction shelf валид независимо от unit economics — повышение
        цены при том же объёме всегда увеличивает revenue → NPV.
        """
        project_id, scenario_id, _, _ = await _seed_minimal_project(db_session)
        result = await compute_sensitivity(db_session, project_id, scenario_id)

        shelf_plus20 = next(
            c for c in result["cells"]
            if c["parameter"] == PARAM_SHELF and c["delta"] == 0.20
        )
        shelf_minus20 = next(
            c for c in result["cells"]
            if c["parameter"] == PARAM_SHELF and c["delta"] == -0.20
        )
        assert shelf_plus20["npv_y1y10"] > result["base_npv_y1y10"]
        assert shelf_minus20["npv_y1y10"] < result["base_npv_y1y10"]

    async def test_offtake_changes_npv(self, db_session: AsyncSession):
        """Offtake изменение даёт отличный от base NPV (как ND)."""
        project_id, scenario_id, _, _ = await _seed_minimal_project(db_session)
        result = await compute_sensitivity(db_session, project_id, scenario_id)

        off_plus20 = next(
            c for c in result["cells"]
            if c["parameter"] == PARAM_OFFTAKE and c["delta"] == 0.20
        )
        off_minus20 = next(
            c for c in result["cells"]
            if c["parameter"] == PARAM_OFFTAKE and c["delta"] == -0.20
        )
        assert off_plus20["npv_y1y10"] != pytest.approx(
            result["base_npv_y1y10"]
        )
        assert off_minus20["npv_y1y10"] != pytest.approx(
            result["base_npv_y1y10"]
        )


# ============================================================
# Endpoint tests
# ============================================================


class TestSensitivityEndpoint:
    async def test_returns_full_response(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """POST /api/projects/{id}/sensitivity без scenario_id → Base."""
        project_id, _, _, _ = await _seed_minimal_project(db_session)
        await db_session.commit()  # endpoint открывает свою сессию

        resp = await auth_client.post(
            f"/api/projects/{project_id}/sensitivity"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "base_npv_y1y10" in body
        assert "cells" in body
        assert len(body["cells"]) == 20

    async def test_404_for_unknown_project(
        self, auth_client: AsyncClient
    ):
        resp = await auth_client.post("/api/projects/999999/sensitivity")
        assert resp.status_code == 404

    async def test_unauthorized(self, client: AsyncClient):
        resp = await client.post("/api/projects/1/sensitivity")
        assert resp.status_code == 401
