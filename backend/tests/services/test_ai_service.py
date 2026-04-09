"""Тесты Polza AI клиента (Phase 7.1 + 7.2 tier registry).

Все вызовы мокаются на уровне `AsyncOpenAI.chat.completions.create`:
реальный Polza не дёргается (см. `tests/integration/test_polza_smoke.py`
с маркером `live` для отдельного запуска с настоящим ключом).

Покрываемые сценарии:
1. Successful call → `AICallResult[T]` с `.parsed` Pydantic инстансом
   и заполненными usage-метриками.
2. Network error (`APIConnectionError`) → `AIServiceUnavailableError`.
3. Невалидный JSON в `choices[0].message.content` → `AIServiceUnavailableError`.
4. JSON не соответствует Pydantic-схеме → `AIServiceUnavailableError`.
5. Пустой `POLZA_AI_API_KEY` → `AIServiceUnavailableError` ещё на
   создании клиента, без обращения к Polza.
6. `APITimeoutError` → `AIServiceUnavailableError` (graceful degradation).
7. `AuthenticationError` → `AIServiceUnavailableError`.
8. Backward compat `model=` (Phase 7.1 путь).

Phase 7.2 scaffolding:
9. `resolve_model(feature)` — дефолт из FEATURE_DEFAULT_TIER.
10. `resolve_model(feature, tier_override)` — override работает.
11. `complete_json(feature=...)` — резолвит модель из feature без model=.
12. `complete_json(feature=..., tier_override=...)` — override работает.
13. `calculate_cost` — правильная арифметика per-1k-tokens.
14. `calculate_cost` — unknown model → Decimal("0").
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
)
from pydantic import BaseModel

from app.core.config import settings
from app.services import ai_service
from app.services.ai_service import (
    AICallResult,
    AIFeature,
    AIModelTier,
    AIServiceUnavailableError,
    calculate_cost,
    complete_json,
    resolve_model,
    reset_client_cache,
)


# ============================================================
# Fixtures & helpers
# ============================================================


class _DummyResponse(BaseModel):
    """Мини-схема для тестов: имитирует shape of a real AI response."""

    summary: str
    confidence: float


def _make_chat_response(
    content: str,
    *,
    prompt_tokens: int = 42,
    completion_tokens: int = 17,
    model: str = "anthropic/claude-sonnet-4.6",
) -> SimpleNamespace:
    """Фейковый ChatCompletion — такой же shape как настоящий.

    openai SDK возвращает Pydantic-объект с `.choices`, `.usage`, `.model`.
    Для моков достаточно `SimpleNamespace` — `ai_service.complete_json`
    обращается только к этим полям.
    """
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    return SimpleNamespace(
        choices=[choice],
        usage=usage,
        model=model,
    )


@pytest.fixture(autouse=True)
def _isolate_client_cache():
    """Сбрасываем singleton до и после каждого теста.

    `_get_client` кеширует клиент через `@lru_cache` — без сброса
    между тестами monkeypatch'инг `polza_ai_api_key` не повлияет на
    уже созданный клиент.
    """
    reset_client_cache()
    yield
    reset_client_cache()


@pytest.fixture
def _api_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Устанавливаем фейковый ключ, чтобы `_get_client` не падал."""
    monkeypatch.setattr(settings, "polza_ai_api_key", "test-key-not-real")


@pytest.fixture
def _mock_openai_create(
    monkeypatch: pytest.MonkeyPatch, _api_key_set: None
) -> AsyncMock:
    """Подменяет `_get_client` так, что `client.chat.completions.create`
    — AsyncMock. Тесты настраивают `.return_value` или `.side_effect`.
    """
    create_mock = AsyncMock()
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock

    def _fake_get_client() -> MagicMock:
        return fake_client

    monkeypatch.setattr(ai_service, "_get_client", _fake_get_client)
    return create_mock


# ============================================================
# Tests
# ============================================================


async def test_complete_json_successful_call(
    _mock_openai_create: AsyncMock,
) -> None:
    """Happy path: валидный JSON → parsed instance + usage метрики."""
    _mock_openai_create.return_value = _make_chat_response(
        '{"summary": "NPV положителен", "confidence": 0.87}',
        prompt_tokens=100,
        completion_tokens=20,
    )

    result = await complete_json(
        system_prompt="Ты FMCG финансовый аналитик. Отвечай JSON.",
        user_prompt="Объясни NPV.",
        schema=_DummyResponse,
        endpoint="test_explain",
    )

    assert isinstance(result, AICallResult)
    assert isinstance(result.parsed, _DummyResponse)
    assert result.parsed.summary == "NPV положителен"
    assert result.parsed.confidence == 0.87
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 20
    assert result.total_tokens == 120
    assert result.latency_ms >= 0
    assert result.model == "anthropic/claude-sonnet-4.6"

    # Проверяем, что клиент вызван с правильными параметрами
    _mock_openai_create.assert_awaited_once()
    call_kwargs = _mock_openai_create.await_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-sonnet-4.6"
    assert call_kwargs["response_format"] == {"type": "json_object"}
    assert call_kwargs["temperature"] == 0.2
    assert len(call_kwargs["messages"]) == 2
    assert call_kwargs["messages"][0]["role"] == "system"
    assert call_kwargs["messages"][1]["role"] == "user"


async def test_complete_json_network_error_becomes_unavailable(
    _mock_openai_create: AsyncMock,
) -> None:
    """APIConnectionError от SDK → AIServiceUnavailableError.

    Endpoint-слой должен поймать это и вернуть placeholder, а не 500.
    """
    _mock_openai_create.side_effect = APIConnectionError(request=MagicMock())

    with pytest.raises(AIServiceUnavailableError, match="подключиться"):
        await complete_json(
            system_prompt="sys",
            user_prompt="usr",
            schema=_DummyResponse,
        )


async def test_complete_json_invalid_json_becomes_unavailable(
    _mock_openai_create: AsyncMock,
) -> None:
    """LLM иногда возвращает мусор вместо JSON — ловим на парсинге."""
    _mock_openai_create.return_value = _make_chat_response(
        "Конечно, я с радостью помогу! Вот ответ: NPV положителен."
    )

    with pytest.raises(AIServiceUnavailableError, match="невалидный JSON"):
        await complete_json(
            system_prompt="sys",
            user_prompt="usr",
            schema=_DummyResponse,
        )


async def test_complete_json_schema_mismatch_becomes_unavailable(
    _mock_openai_create: AsyncMock,
) -> None:
    """JSON валидный, но поля не те / wrong types → ValidationError."""
    _mock_openai_create.return_value = _make_chat_response(
        '{"title": "wrong field", "score": "not a number"}'
    )

    with pytest.raises(AIServiceUnavailableError, match="не соответствует схеме"):
        await complete_json(
            system_prompt="sys",
            user_prompt="usr",
            schema=_DummyResponse,
        )


async def test_complete_json_missing_api_key_raises_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Без POLZA_AI_API_KEY — раннее падение, Polza не дёргается.

    Graceful degradation: endpoint должен поймать и вернуть placeholder
    "AI-модуль отключён".
    """
    monkeypatch.setattr(settings, "polza_ai_api_key", "")

    with pytest.raises(AIServiceUnavailableError, match="POLZA_AI_API_KEY не задан"):
        await complete_json(
            system_prompt="sys",
            user_prompt="usr",
            schema=_DummyResponse,
        )


async def test_complete_json_timeout_becomes_unavailable(
    _mock_openai_create: AsyncMock,
) -> None:
    """APITimeoutError → graceful degradation."""
    _mock_openai_create.side_effect = APITimeoutError(request=MagicMock())

    with pytest.raises(AIServiceUnavailableError, match="timeout"):
        await complete_json(
            system_prompt="sys",
            user_prompt="usr",
            schema=_DummyResponse,
        )


async def test_complete_json_auth_error_becomes_unavailable(
    _mock_openai_create: AsyncMock,
) -> None:
    """AuthenticationError (401 от Polza) — неверный ключ.

    Частый случай в проде — ключ ротнули, а `.env` не обновили.
    """
    _mock_openai_create.side_effect = AuthenticationError(
        message="Invalid API key",
        response=MagicMock(status_code=401),
        body=None,
    )

    with pytest.raises(AIServiceUnavailableError, match="auth failed"):
        await complete_json(
            system_prompt="sys",
            user_prompt="usr",
            schema=_DummyResponse,
        )


async def test_complete_json_respects_custom_model(
    _mock_openai_create: AsyncMock,
) -> None:
    """Передача `model=COMPLEX_CHAT_MODEL` для критичных задач (ADR-16)."""
    _mock_openai_create.return_value = _make_chat_response(
        '{"summary": "ok", "confidence": 0.9}',
        model="anthropic/claude-opus-4.6",
    )

    result = await complete_json(
        system_prompt="sys",
        user_prompt="usr",
        schema=_DummyResponse,
        model=ai_service.COMPLEX_CHAT_MODEL,
    )

    assert result.model == "anthropic/claude-opus-4.6"
    call_kwargs = _mock_openai_create.await_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-opus-4.6"


# ============================================================
# Phase 7.2 — Model tier registry
# ============================================================


def test_resolve_model_uses_feature_default_tier() -> None:
    """`resolve_model(EXPLAIN_KPI)` возвращает модель BALANCED tier'а.

    FEATURE_DEFAULT_TIER[EXPLAIN_KPI] = BALANCED = claude-sonnet-4.6.
    Это критично: endpoint'ы получают стабильное имя модели без
    hard-code'а и без знания tier'ов.
    """
    assert resolve_model(AIFeature.EXPLAIN_KPI) == "anthropic/claude-sonnet-4.6"
    assert resolve_model(AIFeature.CONTENT_FIELD) == "anthropic/claude-haiku-4.5"
    assert resolve_model(AIFeature.EXECUTIVE_SUMMARY) == "anthropic/claude-opus-4.6"


def test_resolve_model_tier_override() -> None:
    """`tier_override` перекрывает default для фичи.

    UI Standard/Deep toggle: пользователь кликнул Deep → endpoint
    передал `tier_override=HEAVY` → модель claude-opus-4.6 вместо
    дефолтной claude-sonnet-4.6.
    """
    # Default — BALANCED → sonnet
    default = resolve_model(AIFeature.EXPLAIN_KPI)
    # Deep override — HEAVY → opus
    override = resolve_model(AIFeature.EXPLAIN_KPI, AIModelTier.HEAVY)

    assert default == "anthropic/claude-sonnet-4.6"
    assert override == "anthropic/claude-opus-4.6"
    assert default != override


async def test_complete_json_accepts_feature(
    _mock_openai_create: AsyncMock,
) -> None:
    """`complete_json(feature=EXPLAIN_KPI)` резолвит модель из tier registry."""
    _mock_openai_create.return_value = _make_chat_response(
        '{"summary": "ok", "confidence": 0.9}',
        model="anthropic/claude-sonnet-4.6",
    )

    result = await complete_json(
        system_prompt="sys",
        user_prompt="usr",
        schema=_DummyResponse,
        feature=AIFeature.EXPLAIN_KPI,
    )

    assert result.model == "anthropic/claude-sonnet-4.6"
    # Клиенту передана резолвленная модель, не None
    call_kwargs = _mock_openai_create.await_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-sonnet-4.6"


async def test_complete_json_feature_with_tier_override(
    _mock_openai_create: AsyncMock,
) -> None:
    """`tier_override=HEAVY` → opus, даже для EXPLAIN_KPI где default BALANCED."""
    _mock_openai_create.return_value = _make_chat_response(
        '{"summary": "deep analysis", "confidence": 0.95}',
        model="anthropic/claude-opus-4.6",
    )

    result = await complete_json(
        system_prompt="sys",
        user_prompt="usr",
        schema=_DummyResponse,
        feature=AIFeature.EXPLAIN_KPI,
        tier_override=AIModelTier.HEAVY,
    )

    assert result.model == "anthropic/claude-opus-4.6"
    call_kwargs = _mock_openai_create.await_args.kwargs
    assert call_kwargs["model"] == "anthropic/claude-opus-4.6"


# ============================================================
# Phase 7.2 — Pricing / cost calculation
# ============================================================


def test_calculate_cost_sonnet() -> None:
    """claude-sonnet-4.6: 0.30₽/1k prompt + 1.50₽/1k completion.

    2500 prompt tokens × 0.30 = 0.75₽
    400 completion tokens × 1.50 = 0.60₽
    ИТОГО: 1.35₽
    """
    cost = calculate_cost("anthropic/claude-sonnet-4.6", 2500, 400)
    assert cost == Decimal("1.350000")


def test_calculate_cost_haiku() -> None:
    """claude-haiku-4.5: самый дешёвый, ~0.5₽ для типичного content-field."""
    # 1500 prompt + 300 completion
    cost = calculate_cost("anthropic/claude-haiku-4.5", 1500, 300)
    # 1.5 × 0.08 + 0.3 × 0.40 = 0.12 + 0.12 = 0.24₽
    assert cost == Decimal("0.240000")


def test_calculate_cost_opus() -> None:
    """claude-opus-4.6 для executive summary — дороже sonnet в 5 раз."""
    cost = calculate_cost("anthropic/claude-opus-4.6", 3000, 800)
    # 3 × 1.50 + 0.8 × 7.50 = 4.5 + 6.0 = 10.5₽
    assert cost == Decimal("10.500000")


def test_calculate_cost_unknown_model_returns_zero() -> None:
    """Модель не в таблице → 0₽ + caller должен залогировать warning.

    Conservative: мы не падаем, не угадываем цену — просто отдаём 0,
    чтобы cost_rub в ai_usage_log был сигналом для investigation
    (строки с 0₽ при непустых токенах = модель не в MODEL_PRICING).
    """
    cost = calculate_cost("openai/gpt-4.2-new-unknown", 1000, 500)
    assert cost == Decimal("0")


def test_calculate_cost_zero_tokens() -> None:
    """Пограничный кейс — 0 токенов = 0₽, без ZeroDivisionError."""
    cost = calculate_cost("anthropic/claude-sonnet-4.6", 0, 0)
    assert cost == Decimal("0.000000")
