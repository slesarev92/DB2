"""API tests для /api/projects/{id}/ai/explain-kpi (Phase 7.2).

Интеграция pytest + реальный postgres + мок Polza через monkeypatch
`ai_service._get_client`. Реальный Polza не дёргается — это
unit-тесты endpoint'а против мокнутого клиента и реальной БД/Redis
слоя.

Покрытие:
1. 401 без JWT
2. Happy path → 200 + запись в ai_usage_log + кэш записан
3. Cache hit → cached=true, без вызова Polza
4. Dedupe: второй запрос ждёт первый (integration-level сложно, проверяем
   лишь что set_cached вызывается)
5. AIServiceUnavailableError → 503 + error log
6. Invalid scenario (не принадлежит проекту) → 404
7. Deleted project → 404
8. Daily budget exceeded → 429
9. LLM возвращает corrupt JSON → 503 (через AIServiceUnavailableError)
10. tier_override работает — другая модель

Не тестируем здесь rate limit 10/min — slowapi сложно юнит-тестить
без замусоривания окружения (нужен session-scope reset). Для Phase 7.2
достаточно что endpoint обёрнут декоратором; реальное поведение ловим
в staging / manual smoke.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AIUsageLog,
    PeriodScope,
    Project,
    ProjectSKU,
    Scenario,
    ScenarioResult,
    ScenarioType,
    User,
)
from app.services import ai_cache, ai_service


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
async def gorji_project(db_session: AsyncSession) -> Project:
    """Минимальный проект с 3 сценариями + results для explain-kpi."""
    project = Project(
        name="Test Project for AI",
        start_date=date(2026, 1, 1),
        horizon_years=10,
        wacc=Decimal("0.19"),
        tax_rate=Decimal("0.20"),
        wc_rate=Decimal("0.12"),
        vat_rate=Decimal("0.20"),
        gate_stage="G2",
        project_goal="Вывод нового SKU в premium сегмент",
    )
    db_session.add(project)
    await db_session.flush()

    for s_type in [
        ScenarioType.BASE,
        ScenarioType.CONSERVATIVE,
        ScenarioType.AGGRESSIVE,
    ]:
        scenario = Scenario(
            project_id=project.id,
            type=s_type,
            delta_nd=Decimal("0"),
            delta_offtake=Decimal("0"),
            delta_opex=Decimal("0"),
        )
        db_session.add(scenario)
        await db_session.flush()

        for scope in [PeriodScope.Y1Y3, PeriodScope.Y1Y5, PeriodScope.Y1Y10]:
            db_session.add(
                ScenarioResult(
                    scenario_id=scenario.id,
                    period_scope=scope,
                    npv=Decimal("15000000"),
                    irr=Decimal("0.28"),
                    payback_discounted=Decimal("4.1"),
                    go_no_go=True,
                )
            )
    await db_session.flush()
    return project


@pytest.fixture
async def base_scenario(
    db_session: AsyncSession, gorji_project: Project
) -> Scenario:
    """BASE сценарий тестового проекта."""
    return (
        await db_session.scalars(
            select(Scenario)
            .where(Scenario.project_id == gorji_project.id)
            .where(Scenario.type == ScenarioType.BASE)
        )
    ).one()


@pytest.fixture
def mock_polza(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Подменяет `_get_client()` → мок AsyncOpenAI client.

    По умолчанию return успешный JSON ответ. Тесты override'ят
    `.side_effect` для error-case'ов.
    """
    create_mock = AsyncMock()
    # Дефолтный успешный ответ
    llm_output = {
        "summary": "NPV положительный во всех сценариях.",
        "key_drivers": [
            "WACC 19% дисконтирует Y4-Y10 в 0.35x",
            "Offtake base 1.2M уп/год",
            "Margin contribution ~30%",
        ],
        "risks": [
            "Гипер-чувствительность к ND",
            "Payback 4.1 года > целевых 3.5",
        ],
        "recommendation": "go",
        "confidence": 0.78,
        "rationale": "Во всех 3 сценариях NPV > 0, IRR > WACC.",
    }
    create_mock.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(llm_output))
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=2500, completion_tokens=400, total_tokens=2900
        ),
        model="anthropic/claude-sonnet-4.6",
    )

    # Сбрасываем singleton ДО подмены (после — нельзя, lambda не имеет
    # cache_clear). Это очищает возможный кэшированный AsyncOpenAI клиент
    # от предыдущих тестов.
    ai_service.reset_client_cache()

    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock
    monkeypatch.setattr(ai_service, "_get_client", lambda: fake_client)
    monkeypatch.setattr(
        "app.core.config.settings.polza_ai_api_key", "fake-test-key"
    )
    return create_mock


@pytest.fixture
def mock_redis(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Подменяет Redis клиент — cache всегда miss, SETNX всегда успех."""
    ai_cache.reset_redis_cache()

    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)

    monkeypatch.setattr(ai_cache, "_get_redis_client", lambda: client)
    return client


# ============================================================
# Tests
# ============================================================


async def test_explain_kpi_requires_auth(
    client: AsyncClient, gorji_project: Project, base_scenario: Scenario
) -> None:
    """401 если нет JWT."""
    resp = await client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-kpi",
        json={
            "scenario_id": base_scenario.id,
            "scope": "y1y5",
        },
    )
    assert resp.status_code == 401


async def test_explain_kpi_happy_path(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    base_scenario: Scenario,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Успешный вызов → 200 + правильная структура + лог в ai_usage_log."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-kpi",
        json={
            "scenario_id": base_scenario.id,
            "scope": "y1y5",
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Структура ответа
    assert data["summary"].startswith("NPV")
    assert len(data["key_drivers"]) == 3
    assert len(data["risks"]) == 2
    assert data["recommendation"] == "go"
    assert 0 <= data["confidence"] <= 1
    assert data["cached"] is False
    assert data["model"] == "anthropic/claude-sonnet-4.6"
    # Cost: 2500 × 0.30/1k + 400 × 1.50/1k = 0.75 + 0.60 = 1.35
    assert Decimal(data["cost_rub"]) == Decimal("1.350000")

    # Polza вызван один раз
    mock_polza.assert_awaited_once()

    # ai_usage_log содержит запись explain_kpi с корректной стоимостью
    logs = (
        await db_session.scalars(
            select(AIUsageLog).where(AIUsageLog.endpoint == "explain_kpi")
        )
    ).all()
    assert len(logs) == 1
    assert logs[0].model == "anthropic/claude-sonnet-4.6"
    assert logs[0].cost_rub == Decimal("1.350000")
    assert logs[0].error is None

    # Redis set_cached был вызван
    mock_redis.set.assert_awaited()


async def test_explain_kpi_cache_hit_skips_polza(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    base_scenario: Scenario,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Если cache hit → cached=true, Polza не вызывается."""
    cached_payload = {
        "summary": "Cached summary",
        "key_drivers": ["a", "b", "c"],
        "risks": ["r1", "r2"],
        "recommendation": "review",
        "confidence": 0.6,
        "rationale": "From cache",
        "cost_rub": "2.4",
        "model": "anthropic/claude-sonnet-4.6",
    }
    mock_redis.get.return_value = json.dumps(cached_payload)

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-kpi",
        json={
            "scenario_id": base_scenario.id,
            "scope": "y1y5",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == "Cached summary"
    assert data["cached"] is True
    # Polza не вызван
    mock_polza.assert_not_awaited()

    # ai_usage_log содержит запись с endpoint=explain_kpi_cache
    logs = (
        await db_session.scalars(
            select(AIUsageLog).where(
                AIUsageLog.endpoint == "explain_kpi_cache"
            )
        )
    ).all()
    assert len(logs) == 1
    assert logs[0].cost_rub == Decimal("0")


async def test_explain_kpi_polza_unavailable_returns_503(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    base_scenario: Scenario,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """AIServiceUnavailableError → 503 с placeholder + error log."""
    from openai import APIConnectionError

    mock_polza.side_effect = APIConnectionError(request=MagicMock())

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-kpi",
        json={
            "scenario_id": base_scenario.id,
            "scope": "y1y5",
        },
    )

    assert resp.status_code == 503
    assert "Polza AI" in resp.json()["detail"]

    # Error заnлогирован в ai_usage_log
    logs = (
        await db_session.scalars(select(AIUsageLog))
    ).all()
    assert len(logs) == 1
    assert logs[0].error is not None
    assert "подключиться" in logs[0].error


async def test_explain_kpi_corrupt_json_returns_503(
    auth_client: AsyncClient,
    gorji_project: Project,
    base_scenario: Scenario,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """LLM вернул текст вместо JSON → 503."""
    mock_polza.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Конечно, вот моё объяснение KPI..."
                )
            )
        ],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
        model="anthropic/claude-sonnet-4.6",
    )

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-kpi",
        json={
            "scenario_id": base_scenario.id,
            "scope": "y1y5",
        },
    )

    assert resp.status_code == 503


async def test_explain_kpi_deleted_project_returns_404(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    base_scenario: Scenario,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Soft-deleted project → 404."""
    gorji_project.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-kpi",
        json={
            "scenario_id": base_scenario.id,
            "scope": "y1y5",
        },
    )
    assert resp.status_code == 404


async def test_explain_kpi_wrong_scenario_returns_404(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Сценарий из другого проекта → 404."""
    other = Project(
        name="Other",
        start_date=date(2026, 1, 1),
        horizon_years=10,
    )
    db_session.add(other)
    await db_session.flush()
    other_scenario = Scenario(project_id=other.id, type=ScenarioType.BASE)
    db_session.add(other_scenario)
    await db_session.flush()

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-kpi",
        json={
            "scenario_id": other_scenario.id,
            "scope": "y1y5",
        },
    )
    assert resp.status_code == 404


async def test_explain_kpi_invalid_scope_returns_422(
    auth_client: AsyncClient,
    gorji_project: Project,
    base_scenario: Scenario,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Невалидный scope (не из PeriodScope enum) → 422."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-kpi",
        json={
            "scenario_id": base_scenario.id,
            "scope": "y1y7",  # не существует
        },
    )
    assert resp.status_code == 422


async def test_explain_kpi_daily_budget_exceeded_returns_429(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    base_scenario: Scenario,
    test_user: User,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Дневной лимит 100₽ исчерпан → 429."""
    db_session.add(
        AIUsageLog(
            endpoint="explain_kpi",
            model="anthropic/claude-sonnet-4.6",
            prompt_tokens=100000,
            completion_tokens=20000,
            cost_rub=Decimal("100"),
            latency_ms=5000,
            user_id=test_user.id,
        )
    )
    await db_session.flush()

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-kpi",
        json={
            "scenario_id": base_scenario.id,
            "scope": "y1y5",
        },
    )
    assert resp.status_code == 429
    assert "daily_user_budget_exceeded" in resp.json()["detail"]["error"]
    # Polza не вызывался
    mock_polza.assert_not_awaited()


async def test_explain_kpi_tier_override_uses_heavy_model(
    auth_client: AsyncClient,
    gorji_project: Project,
    base_scenario: Scenario,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """tier_override=HEAVY → вызов с claude-opus-4.6."""
    # Override response model, чтобы соответствовать вызову на opus
    mock_polza.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {
                            "summary": "Deep analysis says review.",
                            "key_drivers": ["d1", "d2", "d3"],
                            "risks": ["r1"],
                            "recommendation": "review",
                            "confidence": 0.55,
                            "rationale": "Conflict between scenarios.",
                        }
                    )
                )
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=3000, completion_tokens=800, total_tokens=3800
        ),
        model="anthropic/claude-opus-4.6",
    )

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-kpi",
        json={
            "scenario_id": base_scenario.id,
            "scope": "y1y5",
            "tier_override": "heavy",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "anthropic/claude-opus-4.6"
    # Cost на opus выше: 3000 × 1.5/1k + 800 × 7.5/1k = 4.5 + 6.0 = 10.5
    assert Decimal(data["cost_rub"]) == Decimal("10.500000")

    # Проверяем что в Polza улетела opus модель
    call_kwargs = mock_polza.await_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-opus-4.6"


# ============================================================
# Phase 7.3 — EXPLAIN SENSITIVITY
# ============================================================


@pytest.fixture
def mock_sensitivity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подменяет compute_sensitivity чтобы не прогонять pipeline в тестах."""
    from app.services import ai_context_builder

    async def fake_compute(session, project_id, scenario_id):
        return {
            "base_npv_y1y10": 80000000.0,
            "base_cm_ratio": 0.35,
            "deltas": [-0.20, -0.10, 0.0, 0.10, 0.20],
            "params": ["nd", "offtake", "shelf_price", "cogs"],
            "cells": [
                {"parameter": p, "delta": d, "npv_y1y10": 80000000.0 * (1 + d), "cm_ratio": 0.35}
                for p in ["nd", "offtake", "shelf_price", "cogs"]
                for d in [-0.20, -0.10, 0.0, 0.10, 0.20]
            ],
        }

    monkeypatch.setattr(ai_context_builder, "compute_sensitivity", fake_compute)


@pytest.fixture
def mock_polza_sensitivity(mock_polza: AsyncMock) -> AsyncMock:
    """Override mock_polza return для sensitivity schema."""
    sensitivity_output = {
        "most_sensitive_param": "nd",
        "most_sensitive_impact": "+20% ND → +16 млн ₽ NPV",
        "least_sensitive_param": "cogs",
        "narrative": "ND является главным драйвером NPV. При +20% увеличении ND NPV растёт на 16 млн ₽.",
        "actionable_levers": ["Увеличить ND в первые 12 месяцев", "Расширить дистрибуцию"],
        "warning_flags": [],
    }
    mock_polza.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(sensitivity_output))
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=1500, completion_tokens=300, total_tokens=1800
        ),
        model="anthropic/claude-sonnet-4.6",
    )
    return mock_polza


async def test_explain_sensitivity_happy_path(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    base_scenario: Scenario,
    mock_polza_sensitivity: AsyncMock,
    mock_redis: MagicMock,
    mock_sensitivity: None,
) -> None:
    """Successful sensitivity interpretation → 200 + correct structure."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-sensitivity",
        json={"scenario_id": base_scenario.id},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["most_sensitive_param"] == "nd"
    assert "ND" in data["most_sensitive_impact"]
    assert data["cached"] is False
    assert data["model"] == "anthropic/claude-sonnet-4.6"

    mock_polza_sensitivity.assert_awaited_once()

    logs = (
        await db_session.scalars(
            select(AIUsageLog).where(AIUsageLog.endpoint == "explain_sensitivity")
        )
    ).all()
    assert len(logs) == 1


async def test_explain_sensitivity_cache_hit(
    auth_client: AsyncClient,
    gorji_project: Project,
    base_scenario: Scenario,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
    mock_sensitivity: None,
) -> None:
    """Cache hit → cached=true, Polza not called."""
    cached_payload = {
        "most_sensitive_param": "nd",
        "most_sensitive_impact": "cached",
        "least_sensitive_param": "cogs",
        "narrative": "cached narrative",
        "actionable_levers": ["lever1"],
        "warning_flags": [],
        "cost_rub": "1.2",
        "model": "anthropic/claude-sonnet-4.6",
    }
    mock_redis.get.return_value = json.dumps(cached_payload)

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-sensitivity",
        json={"scenario_id": base_scenario.id},
    )

    assert resp.status_code == 200
    assert resp.json()["cached"] is True
    mock_polza.assert_not_awaited()


async def test_explain_sensitivity_missing_scenario(
    auth_client: AsyncClient,
    gorji_project: Project,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
    mock_sensitivity: None,
) -> None:
    """Non-existent scenario → 404."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-sensitivity",
        json={"scenario_id": 999999},
    )
    assert resp.status_code == 404


async def test_explain_sensitivity_polza_unavailable(
    auth_client: AsyncClient,
    gorji_project: Project,
    base_scenario: Scenario,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
    mock_sensitivity: None,
) -> None:
    """Polza down → 503."""
    from openai import APIConnectionError
    mock_polza.side_effect = APIConnectionError(request=MagicMock())

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-sensitivity",
        json={"scenario_id": base_scenario.id},
    )
    assert resp.status_code == 503


# ============================================================
# Phase 7.3 — FREEFORM CHAT (SSE)
# ============================================================


@pytest.fixture
def mock_polza_stream(mock_polza: AsyncMock) -> AsyncMock:
    """Мок для streaming chat — возвращает async iterator of chunks."""

    class _FakeChunk:
        def __init__(self, content: str | None, usage=None):
            self.choices = [SimpleNamespace(delta=SimpleNamespace(content=content))]
            self.usage = usage

    async def fake_stream():
        yield _FakeChunk("Привет")
        yield _FakeChunk(", NPV")
        yield _FakeChunk(" положителен.")
        yield _FakeChunk(None, usage=SimpleNamespace(prompt_tokens=5000, completion_tokens=50))

    # Override mock — chat endpoint calls client.chat.completions.create
    # with stream=True, which returns an async iterator
    mock_polza.return_value = fake_stream()
    return mock_polza


async def test_chat_happy_path_sse(
    auth_client: AsyncClient,
    gorji_project: Project,
    mock_polza_stream: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Chat SSE: first event=conversation_id, tokens, done with cost."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/chat",
        json={"question": "Почему NPV положителен?"},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    body = resp.text
    events = [
        json.loads(line.removeprefix("data: "))
        for line in body.strip().split("\n")
        if line.startswith("data: ")
    ]

    # First event: conversation_id
    assert events[0]["type"] == "conversation_id"
    assert "id" in events[0]

    # Token events
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) >= 2
    full_text = "".join(e["content"] for e in token_events)
    assert "NPV" in full_text

    # Done event
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
    assert "cost_rub" in done_events[0]
    assert "model" in done_events[0]


async def test_chat_requires_auth(
    client: AsyncClient, gorji_project: Project
) -> None:
    """401 без JWT."""
    resp = await client.post(
        f"/api/projects/{gorji_project.id}/ai/chat",
        json={"question": "test"},
    )
    assert resp.status_code == 401


async def test_chat_empty_question_returns_422(
    auth_client: AsyncClient, gorji_project: Project,
    mock_polza: AsyncMock, mock_redis: MagicMock,
) -> None:
    """Empty question → 422 validation error."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/chat",
        json={"question": ""},
    )
    assert resp.status_code == 422


# ============================================================
# Phase 7.4 — EXECUTIVE SUMMARY
# ============================================================


@pytest.fixture
def mock_polza_exec_summary(mock_polza: AsyncMock) -> AsyncMock:
    """Override mock_polza for executive summary schema."""
    exec_output = {
        "title": "GORJI+ Premium ICE: NPV +80М₽, Go",
        "bullets": [
            "NPV Base Y1-Y10: 80.3 млн ₽",
            "IRR 28% vs WACC 19% (gap +9 п.п.)",
            "Payback discounted 4.1 лет",
            "Ключевой risk: гипер-чувствительность к ND",
        ],
        "key_numbers": [
            {"label": "NPV Base Y1-Y10", "value": "80.3 млн ₽"},
            {"label": "IRR Base", "value": "28.0%"},
            {"label": "Payback", "value": "4.1 лет"},
        ],
        "risks_section": ["ND sensitivity", "Payback >4 лет"],
        "one_line_summary": "Проект GORJI+ рекомендован к запуску с NPV 80.3 млн ₽.",
        "recommendation": "go",
        "confidence": 0.85,
    }
    mock_polza.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(exec_output))
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=5000, completion_tokens=800, total_tokens=5800
        ),
        model="anthropic/claude-opus-4.6",
    )
    return mock_polza


async def test_generate_executive_summary_happy_path(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    mock_polza_exec_summary: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Executive summary generation → 200 + opus model + correct structure."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-executive-summary",
        json={},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["title"].startswith("GORJI+")
    assert len(data["bullets"]) == 4
    assert len(data["key_numbers"]) == 3
    assert data["recommendation"] == "go"
    assert data["model"] == "anthropic/claude-opus-4.6"
    assert data["cached"] is False

    logs = (
        await db_session.scalars(
            select(AIUsageLog).where(
                AIUsageLog.endpoint == "executive_summary"
            )
        )
    ).all()
    assert len(logs) == 1


async def test_generate_executive_summary_cache_hit(
    auth_client: AsyncClient,
    gorji_project: Project,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Cache hit → cached=true."""
    cached_payload = {
        "title": "Cached title",
        "bullets": ["b1"],
        "key_numbers": [{"label": "NPV", "value": "10₽"}],
        "risks_section": [],
        "one_line_summary": "cached",
        "recommendation": "review",
        "confidence": 0.5,
        "cost_rub": "10.5",
        "model": "anthropic/claude-opus-4.6",
    }
    mock_redis.get.return_value = json.dumps(cached_payload)

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-executive-summary",
        json={},
    )

    assert resp.status_code == 200
    assert resp.json()["cached"] is True
    mock_polza.assert_not_awaited()


async def test_save_executive_summary(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """PATCH saves ai_executive_summary to Project."""
    resp = await auth_client.patch(
        f"/api/projects/{gorji_project.id}/ai/executive-summary",
        json={"ai_executive_summary": "Отредактированный executive summary текст"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "saved"

    # Verify in DB
    await db_session.refresh(gorji_project)
    assert gorji_project.ai_executive_summary == "Отредактированный executive summary текст"
    assert gorji_project.ai_commentary_updated_at is not None


async def test_save_executive_summary_deleted_project(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """PATCH on deleted project → 404."""
    from datetime import datetime, timezone
    gorji_project.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()

    resp = await auth_client.patch(
        f"/api/projects/{gorji_project.id}/ai/executive-summary",
        json={"ai_executive_summary": "text"},
    )
    assert resp.status_code == 404


# ============================================================
# Phase 7.5 — PROJECT BUDGET ENFORCEMENT
# ============================================================


async def test_explain_kpi_project_budget_exceeded_returns_429(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    base_scenario: Scenario,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Месячный бюджет проекта исчерпан → 429."""
    # Default budget = 500₽ (server_default)
    db_session.add(
        AIUsageLog(
            project_id=gorji_project.id,
            endpoint="explain_kpi",
            model="anthropic/claude-sonnet-4.6",
            cost_rub=Decimal("500"),
            latency_ms=1000,
        )
    )
    await db_session.flush()

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-kpi",
        json={
            "scenario_id": base_scenario.id,
            "scope": "y1y5",
        },
    )
    assert resp.status_code == 429
    assert "project_budget_exceeded" in resp.json()["detail"]["error"]
    mock_polza.assert_not_awaited()


async def test_explain_kpi_null_budget_allows_unlimited(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    base_scenario: Scenario,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """ai_budget_rub_monthly = NULL → unlimited, запрос проходит."""
    gorji_project.ai_budget_rub_monthly = None
    db_session.add(
        AIUsageLog(
            project_id=gorji_project.id,
            endpoint="explain_kpi",
            model="anthropic/claude-sonnet-4.6",
            cost_rub=Decimal("999999"),
            latency_ms=1000,
        )
    )
    await db_session.flush()

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/explain-kpi",
        json={
            "scenario_id": base_scenario.id,
            "scope": "y1y5",
        },
    )
    # Должен пройти — бюджет без лимита
    assert resp.status_code == 200
    mock_polza.assert_awaited_once()


# ============================================================
# Phase 7.5 — GET /ai/usage
# ============================================================


async def test_get_ai_usage_requires_auth(
    client: AsyncClient, gorji_project: Project
) -> None:
    """401 без JWT."""
    resp = await client.get(
        f"/api/projects/{gorji_project.id}/ai/usage"
    )
    assert resp.status_code == 401


async def test_get_ai_usage_empty(
    auth_client: AsyncClient,
    gorji_project: Project,
) -> None:
    """Нет вызовов → zero stats с правильной структурой."""
    resp = await auth_client.get(
        f"/api/projects/{gorji_project.id}/ai/usage"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == gorji_project.id
    assert Decimal(data["spent_rub"]) == Decimal("0")
    assert Decimal(data["budget_rub"]) == Decimal("500.00")
    assert Decimal(data["budget_remaining_rub"]) == Decimal("500.00")
    assert data["budget_percent_used"] == 0.0
    assert data["daily_history"] == []
    assert data["recent_calls"] == []


async def test_get_ai_usage_with_calls(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
) -> None:
    """Есть вызовы → correct aggregation."""
    for i in range(5):
        db_session.add(
            AIUsageLog(
                project_id=gorji_project.id,
                endpoint="explain_kpi" if i < 4 else "explain_kpi_cache",
                model="anthropic/claude-sonnet-4.6",
                cost_rub=Decimal("5") if i < 4 else Decimal("0"),
                latency_ms=1000,
                prompt_tokens=1000,
                completion_tokens=200,
            )
        )
    await db_session.flush()

    resp = await auth_client.get(
        f"/api/projects/{gorji_project.id}/ai/usage"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert Decimal(data["spent_rub"]) == Decimal("20")
    assert len(data["recent_calls"]) == 5
    cached_calls = [c for c in data["recent_calls"] if c["cached"]]
    assert len(cached_calls) == 1


# ============================================================
# Phase 7.5 — PATCH /ai/budget
# ============================================================


async def test_update_ai_budget_requires_auth(
    client: AsyncClient, gorji_project: Project
) -> None:
    """401 без JWT."""
    resp = await client.patch(
        f"/api/projects/{gorji_project.id}/ai/budget",
        json={"ai_budget_rub_monthly": 1000},
    )
    assert resp.status_code == 401


async def test_update_ai_budget_happy_path(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
) -> None:
    """Обновление бюджета → возвращает AIUsageResponse с новым лимитом."""
    resp = await auth_client.patch(
        f"/api/projects/{gorji_project.id}/ai/budget",
        json={"ai_budget_rub_monthly": "1000.00"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert Decimal(data["budget_rub"]) == Decimal("1000.00")
    assert Decimal(data["budget_remaining_rub"]) == Decimal("1000.00")

    # Verify in DB
    await db_session.refresh(gorji_project)
    assert gorji_project.ai_budget_rub_monthly == Decimal("1000.00")


async def test_update_ai_budget_to_null_means_unlimited(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
) -> None:
    """null → unlimited (no budget enforcement)."""
    resp = await auth_client.patch(
        f"/api/projects/{gorji_project.id}/ai/budget",
        json={"ai_budget_rub_monthly": None},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["budget_rub"] is None
    assert data["budget_remaining_rub"] is None

    await db_session.refresh(gorji_project)
    assert gorji_project.ai_budget_rub_monthly is None


async def test_update_ai_budget_deleted_project(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
) -> None:
    """Deleted project → 404."""
    gorji_project.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()

    resp = await auth_client.patch(
        f"/api/projects/{gorji_project.id}/ai/budget",
        json={"ai_budget_rub_monthly": 1000},
    )
    assert resp.status_code == 404


async def test_update_ai_budget_negative_rejected(
    auth_client: AsyncClient,
    gorji_project: Project,
) -> None:
    """Negative budget → 422 validation error."""
    resp = await auth_client.patch(
        f"/api/projects/{gorji_project.id}/ai/budget",
        json={"ai_budget_rub_monthly": -100},
    )
    assert resp.status_code == 422


# ============================================================
# Phase 7.6 — GENERATE CONTENT FIELD
# ============================================================


@pytest.fixture
def mock_polza_content(mock_polza: AsyncMock) -> AsyncMock:
    """Override mock_polza for content field schema (haiku response)."""
    content_output = {"generated_text": "Цель проекта — вывод нового SKU в premium сегмент."}
    mock_polza.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(content_output))
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=800, completion_tokens=100, total_tokens=900
        ),
        model="anthropic/claude-haiku-4.5",
    )
    return mock_polza


async def test_generate_content_happy_path(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    mock_polza_content: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Successful content field generation → 200 + haiku model."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-content",
        json={"field": "project_goal"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["field"] == "project_goal"
    assert "SKU" in data["generated_text"]
    assert data["model"] == "anthropic/claude-haiku-4.5"
    assert data["cached"] is False
    # Cost on haiku: 800 × 0.08/1k + 100 × 0.40/1k = 0.064 + 0.040 = 0.104
    assert Decimal(data["cost_rub"]) == Decimal("0.104000")

    mock_polza_content.assert_awaited_once()

    logs = (
        await db_session.scalars(
            select(AIUsageLog).where(AIUsageLog.endpoint == "content_field")
        )
    ).all()
    assert len(logs) == 1
    assert logs[0].model == "anthropic/claude-haiku-4.5"


async def test_generate_content_with_user_hint(
    auth_client: AsyncClient,
    gorji_project: Project,
    mock_polza_content: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """user_hint передаётся в промпт."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-content",
        json={
            "field": "target_audience",
            "user_hint": "Акцент на молодёжь 18-25 лет",
        },
    )
    assert resp.status_code == 200
    # Проверяем что Polza был вызван (hint включён в context)
    mock_polza_content.assert_awaited_once()


async def test_generate_content_invalid_field_returns_422(
    auth_client: AsyncClient,
    gorji_project: Project,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Несуществующее поле → 422 от Pydantic."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-content",
        json={"field": "nonexistent_field"},
    )
    assert resp.status_code == 422


async def test_generate_content_cache_hit(
    auth_client: AsyncClient,
    gorji_project: Project,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Cache hit → cached=true, Polza не вызван."""
    cached_payload = {
        "field": "project_goal",
        "generated_text": "Cached goal text.",
        "cost_rub": "0.10",
        "model": "anthropic/claude-haiku-4.5",
    }
    mock_redis.get.return_value = json.dumps(cached_payload)

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-content",
        json={"field": "project_goal"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["cached"] is True
    assert data["generated_text"] == "Cached goal text."
    mock_polza.assert_not_awaited()


async def test_generate_content_tier_override_to_balanced(
    auth_client: AsyncClient,
    gorji_project: Project,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """tier_override=balanced → sonnet model."""
    content_output = {"generated_text": "Deeper rationale text."}
    mock_polza.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(content_output))
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=1000, completion_tokens=200, total_tokens=1200
        ),
        model="anthropic/claude-sonnet-4.6",
    )

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-content",
        json={"field": "rationale", "tier_override": "balanced"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "anthropic/claude-sonnet-4.6"
    call_kwargs = mock_polza.await_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-sonnet-4.6"


async def test_generate_content_deleted_project_returns_404(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Deleted project → 404."""
    gorji_project.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-content",
        json={"field": "project_goal"},
    )
    assert resp.status_code == 404


async def test_generate_content_project_budget_exceeded(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Budget exceeded → 429."""
    db_session.add(
        AIUsageLog(
            project_id=gorji_project.id,
            endpoint="content_field",
            model="anthropic/claude-haiku-4.5",
            cost_rub=Decimal("500"),
            latency_ms=100,
        )
    )
    await db_session.flush()

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-content",
        json={"field": "project_goal"},
    )
    assert resp.status_code == 429
    mock_polza.assert_not_awaited()


async def test_generate_content_requires_auth(
    client: AsyncClient, gorji_project: Project
) -> None:
    """401 без JWT."""
    resp = await client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-content",
        json={"field": "project_goal"},
    )
    assert resp.status_code == 401


# ============================================================
# Phase 7.7 — MARKETING RESEARCH
# ============================================================


@pytest.fixture
def mock_polza_research(mock_polza: AsyncMock) -> AsyncMock:
    """Override mock_polza for marketing research schema (opus response)."""
    research_output = {
        "research_text": "Рынок энергетических напитков в России растёт на 8-10% ежегодно.",
        "sources": [],
        "key_findings": [
            "Объём рынка ~45 млрд ₽ (2025)",
            "Лидеры: Red Bull 28%, Adrenaline Rush 22%, Burn 15%",
            "Premium сегмент растёт на 15% vs mass 5%",
        ],
        "confidence_notes": "Основано на обучающих данных до 2025, цифры требуют верификации через Nielsen.",
    }
    mock_polza.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(research_output))
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=3000, completion_tokens=600, total_tokens=3600
        ),
        model="anthropic/claude-opus-4.6",
    )
    return mock_polza


async def test_marketing_research_happy_path(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    mock_polza_research: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Successful marketing research → 200 + saved in JSONB."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/marketing-research",
        json={"topic": "competitive_analysis"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["topic"] == "competitive_analysis"
    assert "энергетических" in data["research_text"]
    assert len(data["key_findings"]) == 3
    assert data["web_sources_used"] is False
    assert data["model"] == "anthropic/claude-opus-4.6"

    mock_polza_research.assert_awaited_once()

    # Verify saved in project JSONB
    await db_session.refresh(gorji_project)
    assert gorji_project.marketing_research is not None
    assert "competitive_analysis" in gorji_project.marketing_research
    saved = gorji_project.marketing_research["competitive_analysis"]
    assert "энергетических" in saved["text"]


async def test_marketing_research_custom_topic(
    auth_client: AsyncClient,
    gorji_project: Project,
    mock_polza_research: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Custom topic with custom_query."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/marketing-research",
        json={"topic": "custom", "custom_query": "Анализ ценовой эластичности"},
    )
    assert resp.status_code == 200


async def test_marketing_research_custom_without_query_422(
    auth_client: AsyncClient,
    gorji_project: Project,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Custom topic without custom_query → 422."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/marketing-research",
        json={"topic": "custom"},
    )
    assert resp.status_code == 422


async def test_marketing_research_budget_exceeded(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    mock_polza: AsyncMock,
    mock_redis: MagicMock,
) -> None:
    """Budget exceeded → 429."""
    db_session.add(
        AIUsageLog(
            project_id=gorji_project.id,
            endpoint="marketing_research",
            model="anthropic/claude-opus-4.6",
            cost_rub=Decimal("500"),
            latency_ms=5000,
        )
    )
    await db_session.flush()

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/marketing-research",
        json={"topic": "market_size"},
    )
    assert resp.status_code == 429


async def test_edit_marketing_research(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
) -> None:
    """PATCH edit research text."""
    # Seed research data
    gorji_project.marketing_research = {
        "competitive_analysis": {
            "text": "Original text",
            "sources": [],
            "key_findings": [],
            "confidence_notes": "",
            "generated_at": "2026-04-10T00:00:00Z",
            "cost_rub": "15.0",
            "model": "anthropic/claude-opus-4.6",
        }
    }
    await db_session.flush()

    resp = await auth_client.patch(
        f"/api/projects/{gorji_project.id}/ai/marketing-research",
        json={
            "topic": "competitive_analysis",
            "edited_text": "Edited research text",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"

    await db_session.refresh(gorji_project)
    assert gorji_project.marketing_research["competitive_analysis"]["text"] == "Edited research text"


async def test_edit_marketing_research_missing_topic(
    auth_client: AsyncClient,
    gorji_project: Project,
) -> None:
    """PATCH on non-existent topic → 404."""
    resp = await auth_client.patch(
        f"/api/projects/{gorji_project.id}/ai/marketing-research",
        json={"topic": "market_size", "edited_text": "text"},
    )
    assert resp.status_code == 404


async def test_delete_marketing_research(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
) -> None:
    """DELETE research topic."""
    gorji_project.marketing_research = {
        "competitive_analysis": {"text": "data", "sources": []},
        "market_size": {"text": "data", "sources": []},
    }
    await db_session.flush()

    resp = await auth_client.delete(
        f"/api/projects/{gorji_project.id}/ai/marketing-research/competitive_analysis",
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    await db_session.refresh(gorji_project)
    assert "competitive_analysis" not in gorji_project.marketing_research
    assert "market_size" in gorji_project.marketing_research


async def test_delete_marketing_research_missing_topic(
    auth_client: AsyncClient,
    gorji_project: Project,
) -> None:
    """DELETE non-existent topic → 404."""
    resp = await auth_client.delete(
        f"/api/projects/{gorji_project.id}/ai/marketing-research/nonexistent",
    )
    assert resp.status_code == 404


async def test_marketing_research_requires_auth(
    client: AsyncClient, gorji_project: Project
) -> None:
    """401 без JWT."""
    resp = await client.post(
        f"/api/projects/{gorji_project.id}/ai/marketing-research",
        json={"topic": "market_size"},
    )
    assert resp.status_code == 401


# ============================================================
# Phase 7.8 — PACKAGE MOCKUP
# ============================================================


@pytest.fixture
async def gorji_sku(db_session: AsyncSession, gorji_project: Project) -> "ProjectSKU":
    """ProjectSKU с подгруженным SKU для тестов mockup."""
    from app.models import ProjectSKU as PSKU, SKU as SKUModel

    sku = SKUModel(
        brand="GORJI",
        name="Premium ICE",
        format=None,
        volume_l=Decimal("0.5"),
        segment="premium",
    )
    db_session.add(sku)
    await db_session.flush()

    psku = PSKU(
        project_id=gorji_project.id,
        sku_id=sku.id,
    )
    db_session.add(psku)
    await db_session.flush()
    return psku


@pytest.fixture
def mock_polza_mockup(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Мокает и vision (complete_vision) и flux (generate_image)."""
    import base64
    from unittest.mock import AsyncMock as AM

    # Mock vision — returns art direction
    vision_mock = AM()
    vision_output = {"art_direction": "Premium bottle, blue gradient, white logo top-left."}
    vision_mock.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(vision_output))
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=5000, completion_tokens=300, total_tokens=5300
        ),
        model="anthropic/claude-opus-4.6",
    )

    # Mock flux — returns fake b64 PNG (1x1 red pixel)
    fake_png_b64 = base64.b64encode(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    ).decode("ascii")
    flux_mock = AM()
    flux_mock.return_value = SimpleNamespace(
        data=[SimpleNamespace(b64_json=fake_png_b64)]
    )

    ai_service.reset_client_cache()

    fake_client = MagicMock()
    fake_client.chat.completions.create = vision_mock
    fake_client.images.generate = flux_mock
    monkeypatch.setattr(ai_service, "_get_client", lambda: fake_client)
    monkeypatch.setattr(
        "app.core.config.settings.polza_ai_api_key", "fake-test-key"
    )

    # generate_image uses httpx directly (not OpenAI client) — mock it too
    gen_img_mock = AM(return_value={
        "b64_json": fake_png_b64,
        "model": "openai/gpt-image-1.5",
        "latency_ms": 100,
    })
    monkeypatch.setattr(ai_service, "generate_image", gen_img_mock)

    return {"vision": vision_mock, "flux": gen_img_mock}


async def test_generate_mockup_without_reference(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    gorji_sku: "ProjectSKU",
    mock_polza_mockup: dict,
    mock_redis: MagicMock,
) -> None:
    """Generate mockup without reference image → skip vision, only flux."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-mockup",
        json={
            "project_sku_id": gorji_sku.id,
            "prompt": "Modern minimalist bottle design",
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["media_asset_id"] > 0
    assert data["media_url"].startswith("/api/media/")
    assert "Modern minimalist" in data["prompt"]

    # Vision NOT called (no reference)
    mock_polza_mockup["vision"].assert_not_awaited()
    # Flux called
    mock_polza_mockup["flux"].assert_awaited_once()


async def test_generate_mockup_with_reference(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    gorji_sku: "ProjectSKU",
    mock_polza_mockup: dict,
    mock_redis: MagicMock,
) -> None:
    """Generate with reference → vision + flux both called."""
    from app.models import MediaAsset as MA

    # Create a reference asset
    ref = MA(
        project_id=gorji_project.id,
        kind="ai_reference",
        filename="logo.png",
        content_type="image/png",
        storage_path="test/logo.png",
        size_bytes=100,
    )
    db_session.add(ref)
    await db_session.flush()

    # Write a tiny file so read_media_file works
    from app.services.media_service import _absolute_path

    path = _absolute_path(ref.storage_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-mockup",
        json={
            "project_sku_id": gorji_sku.id,
            "prompt": "Bottle with brand logo",
            "reference_asset_id": ref.id,
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "art_direction" in data
    assert "Premium bottle" in data["art_direction"]

    # Both called
    mock_polza_mockup["vision"].assert_awaited_once()
    mock_polza_mockup["flux"].assert_awaited_once()


async def test_generate_mockup_requires_auth(
    client: AsyncClient, gorji_project: Project
) -> None:
    """401 без JWT."""
    resp = await client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-mockup",
        json={"project_sku_id": 1, "prompt": "test"},
    )
    assert resp.status_code == 401


async def test_generate_mockup_invalid_sku(
    auth_client: AsyncClient,
    gorji_project: Project,
    mock_polza_mockup: dict,
    mock_redis: MagicMock,
) -> None:
    """Non-existent SKU → 404."""
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-mockup",
        json={"project_sku_id": 999999, "prompt": "test"},
    )
    assert resp.status_code == 404


async def test_list_mockups_empty(
    auth_client: AsyncClient,
    gorji_project: Project,
) -> None:
    """Empty gallery → empty list."""
    resp = await auth_client.get(
        f"/api/projects/{gorji_project.id}/ai/mockups",
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_set_mockup_as_primary(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    gorji_sku: "ProjectSKU",
    mock_polza_mockup: dict,
    mock_redis: MagicMock,
) -> None:
    """Set generated mockup as primary package image."""
    # Generate a mockup first
    resp = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-mockup",
        json={
            "project_sku_id": gorji_sku.id,
            "prompt": "Clean design",
        },
    )
    assert resp.status_code == 200
    mockup_id = resp.json()["id"]
    media_asset_id = resp.json()["media_asset_id"]

    # Set as primary
    resp2 = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/mockups/{mockup_id}/set-primary",
    )
    assert resp2.status_code == 200
    assert resp2.json()["package_image_id"] == media_asset_id

    # Verify in DB
    await db_session.refresh(gorji_sku)
    assert gorji_sku.package_image_id == media_asset_id


async def test_generate_mockup_iteration_includes_history(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    gorji_project: Project,
    gorji_sku: "ProjectSKU",
    mock_polza_mockup: dict,
    mock_redis: MagicMock,
) -> None:
    """Second mockup generation includes art_direction from the first one."""
    # First generation
    resp1 = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-mockup",
        json={
            "project_sku_id": gorji_sku.id,
            "prompt": "Minimalist bottle",
        },
    )
    assert resp1.status_code == 200, resp1.text

    # Second generation — should carry history from the first
    resp2 = await auth_client.post(
        f"/api/projects/{gorji_project.id}/ai/generate-mockup",
        json={
            "project_sku_id": gorji_sku.id,
            "prompt": "Make the background darker",
        },
    )
    assert resp2.status_code == 200, resp2.text

    # Verify that generate_image was called with prompt containing
    # previous art direction context
    flux_call = mock_polza_mockup["flux"]
    assert flux_call.await_count == 2
    second_call_kwargs = flux_call.call_args_list[1].kwargs
    flux_prompt = second_call_kwargs.get("prompt", "")
    # The no-reference path injects "PREVIOUS ART DIRECTION" into the prompt
    assert "PREVIOUS ART DIRECTION" in flux_prompt
