"""Live smoke-тест Polza AI (Phase 7.1).

**НЕ запускается в обычном pytest прогоне.** Маркер `@pytest.mark.live`
отфильтровывается через `-m "not live and not acceptance"` в CI и
локальных проверках. Запускать вручную:

    docker compose -f infra/docker-compose.dev.yml exec backend \\
        pytest -v -m live tests/integration/test_polza_smoke.py

Предназначение: проверить, что `POLZA_AI_API_KEY` из `.env` рабочий,
`polza_ai_base_url` корректен и Polza возвращает ответ в ожидаемом
формате. Тест пропускается, если ключ не задан (например, на CI без
GitHub Secret).

Стоимость одного прогона: ~0.01₽ (2 токена prompt + ~10 токенов
ответа × claude-sonnet-4-6 pricing).
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.ai_service import complete_json, reset_client_cache


class _PingResponse(BaseModel):
    """Минимальная схема: просим Polza вернуть 'pong' и число."""

    reply: str = Field(description="Должно быть 'pong'")
    lucky_number: int = Field(description="Любое целое от 1 до 100")


@pytest.mark.live
async def test_polza_smoke_chat_completion() -> None:
    """Реальный вызов Polza AI с минимальным промптом.

    Проверяет:
    - POLZA_AI_API_KEY работает (нет AuthenticationError)
    - `base_url=https://polza.ai/v1` отвечает
    - Модель `anthropic/claude-sonnet-4-6` доступна
    - JSON-response с Pydantic-схемой парсится успешно
    - Usage-метрики заполнены (> 0 токенов)
    """
    if not settings.polza_ai_api_key:
        pytest.skip("POLZA_AI_API_KEY не задан — smoke-тест пропускается")

    # На всякий случай сбрасываем singleton: если в этой же сессии
    # запускались моковые тесты, они могли подменить _get_client.
    reset_client_cache()

    result = await complete_json(
        system_prompt=(
            "Ты — тестовый эндпоинт. Верни строго JSON с двумя полями: "
            '{"reply": "pong", "lucky_number": <целое 1..100>}. '
            "Никаких объяснений, только JSON."
        ),
        user_prompt="ping",
        schema=_PingResponse,
        endpoint="smoke_test",
    )

    assert result.parsed.reply.lower() == "pong"
    assert 1 <= result.parsed.lucky_number <= 100
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0
    assert result.total_tokens == result.prompt_tokens + result.completion_tokens
    assert result.latency_ms > 0
    # Polza может вернуть версионированное имя модели (например,
    # "anthropic/claude-sonnet-4-6-20250101"), поэтому проверяем
    # только префикс.
    assert "claude" in result.model.lower()
