"""Тесты Polza AI клиента (Phase 7.1).

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
"""
from __future__ import annotations

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
    AIServiceUnavailableError,
    complete_json,
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
