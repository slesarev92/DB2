"""Клиент Polza AI — тонкая обёртка над `openai` SDK (ADR-16, Phase 7.1).

Почему не свой HTTP-клиент: `openai` SDK обеспечивает встроенные
retry с exponential backoff, rate-limit handling, streaming и
timeout'ы из коробки. Polza AI — OpenAI-совместимый прокси, поэтому
достаточно подставить `base_url=https://polza.ai/v1`.

Архитектурные принципы (ADR-16 + IMPLEMENTATION_PLAN.md Phase 7):

1. **Изоляция от engine/.** Сервис не знает про расчётное ядро,
   получает готовые строки/объекты от вызывающего endpoint'а.
2. **Graceful degradation.** Если `POLZA_AI_API_KEY` не задан или
   Polza недоступен, поднимается `AIServiceUnavailableError` —
   endpoint'ы 7.2..7.8 ловят его и возвращают placeholder вместо
   AI-ответа. Расчёт/UI продолжают работать.
3. **Output validation.** Все вызовы идут через `complete_json`,
   который парсит JSON-ответ через Pydantic-схему. Свободного текста
   в API не бывает — всегда строго типизированный результат.
4. **Cost monitoring (Phase 7.5).** `complete_json` возвращает
   `AICallResult[T]` с `.parsed` (Pydantic instance) и usage-метриками
   (prompt_tokens, completion_tokens, latency_ms). Phase 7.5 подключит
   запись в `ai_usage_log` на уровне endpoint'ов. В 7.1 логирование
   в БД не включается — только возврат метрик.
5. **Промпты — Python-константы.** См. `ai_prompts.py`. Заполняется
   начиная с 7.2.

Ключевые параметры из `settings` (`app/core/config.py`):
- `polza_ai_api_key` — секрет, пустая строка = AI отключён
- `polza_ai_base_url` — endpoint (`https://polza.ai/v1` по ADR-16)
- `polza_ai_timeout_seconds` — timeout на один вызов
- `polza_ai_max_retries` — retry внутри SDK при 5xx/connection errors
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Generic, TypeVar

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from app.core.config import settings

# Дефолтные модели Polza AI. Верифицировано live smoke-тестом Phase 7.1
# через `/api/v1/models` endpoint: Polza использует формат с точками
# ("claude-sonnet-4.6"), а не с дефисами ("claude-sonnet-4-6") как в
# первой версии ADR-16. Формат "<provider>/<model_id>".
DEFAULT_CHAT_MODEL = "anthropic/claude-sonnet-4.6"
"""Обычные задачи: summary, комментарии KPI, объяснение дельт сценариев."""

COMPLEX_CHAT_MODEL = "anthropic/claude-opus-4.6"
"""Критичные задачи: аудит формул, ответы "почему модель так считает"."""


T = TypeVar("T", bound=BaseModel)


class AIServiceError(Exception):
    """Базовое исключение ai_service."""


class AIServiceUnavailableError(AIServiceError):
    """Polza AI недоступен или ответ невалиден.

    Endpoint-слой должен ловить это исключение и возвращать placeholder
    (`"AI-комментарий недоступен"`) вместо того чтобы падать 500. Это
    обеспечивает graceful degradation — расчёт и UI продолжают работать,
    AI-фича показывает friendly message.

    Причины: отсутствие API ключа, network timeout, 5xx от Polza,
    невалидный JSON в ответе, несоответствие response-схеме.
    """


@dataclass(frozen=True, slots=True)
class AICallResult(Generic[T]):
    """Результат одного вызова `complete_json`.

    Attributes:
        parsed: Валидированный Pydantic-инстанс схемы-ответа.
        model: Фактически использованная модель (на случай fallback'а
            Polza на другую модель той же категории).
        prompt_tokens: Токены в prompt'е (для cost calc в 7.5).
        completion_tokens: Токены в ответе.
        total_tokens: Сумма. Polza возвращает поле явно, дублируем.
        latency_ms: Время round-trip от начала create() до получения
            parsed-объекта, включая network + provider processing.
    """

    parsed: T
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int


@lru_cache(maxsize=1)
def _get_client() -> AsyncOpenAI:
    """Singleton AsyncOpenAI клиент, настроенный на Polza AI endpoint.

    `@lru_cache` гарантирует один клиент на процесс (connection pooling
    httpx под капотом). Клиент создаётся лениво при первом вызове.

    Raises:
        AIServiceUnavailableError: если `POLZA_AI_API_KEY` не задан.
            Проверка здесь, а не в `complete_json`, — ранняя ошибка,
            чтобы не тратить время на формирование messages.
    """
    if not settings.polza_ai_api_key:
        raise AIServiceUnavailableError(
            "POLZA_AI_API_KEY не задан в .env — AI-модуль отключён. "
            "Получите ключ в polza.ai/dashboard/api-keys и добавьте в .env."
        )

    return AsyncOpenAI(
        api_key=settings.polza_ai_api_key,
        base_url=settings.polza_ai_base_url,
        timeout=settings.polza_ai_timeout_seconds,
        max_retries=settings.polza_ai_max_retries,
    )


def reset_client_cache() -> None:
    """Сбросить singleton-клиент. Нужно только в тестах.

    `_get_client` кеширует клиент навсегда. Если тест меняет
    `settings.polza_ai_api_key` через monkeypatch, следующий вызов
    должен пересоздать клиент с новым ключом — для этого вызывается
    `reset_client_cache`.
    """
    _get_client.cache_clear()


async def complete_json(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: type[T],
    model: str = DEFAULT_CHAT_MODEL,
    endpoint: str = "unknown",
    temperature: float = 0.2,
) -> AICallResult[T]:
    """Вызвать Polza chat completion с JSON-response и распарсить в Pydantic.

    Args:
        system_prompt: System role — задаёт роль ассистента, формат
            ответа (JSON), ограничения. Должен явно упоминать "JSON"
            — некоторые провайдеры (OpenAI) требуют это при
            `response_format={"type": "json_object"}`.
        user_prompt: User role — конкретный запрос + входные данные.
        schema: Pydantic-класс, которым валидируется JSON-ответ.
            Должен быть `BaseModel` subclass с корректными полями.
        model: Polza model identifier. По умолчанию
            `anthropic/claude-sonnet-4-6` (ADR-16). Для критичных
            задач вызывающий код передаёт `COMPLEX_CHAT_MODEL`.
        endpoint: Имя вызывающей фичи/endpoint'а для Phase 7.5 cost
            logging (`explain_kpi`, `marketing_research`, ...).
            В 7.1 не используется для записи в БД.
        temperature: По умолчанию 0.2 — низкая креативность, финансовые
            интерпретации должны быть детерминистичными.

    Returns:
        `AICallResult[T]` — `.parsed` содержит валидированный schema
        инстанс, остальные поля — метрики для 7.5 cost logging.

    Raises:
        AIServiceUnavailableError: API ключ не задан / network error /
            timeout / 5xx / невалидный JSON / schema mismatch.
            Caller должен поймать и вернуть placeholder.
    """
    # endpoint используется вызывающим кодом в 7.5 для записи в
    # ai_usage_log.endpoint. В 7.1 мы его просто принимаем, чтобы
    # не ломать сигнатуру при включении логирования.
    del endpoint  # noqa: F841 — зарезервирован для Phase 7.5

    try:
        client = _get_client()
    except AIServiceUnavailableError:
        raise

    start = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
        )
    except AuthenticationError as exc:
        raise AIServiceUnavailableError(
            f"Polza AI auth failed: проверьте POLZA_AI_API_KEY ({exc})"
        ) from exc
    except RateLimitError as exc:
        raise AIServiceUnavailableError(
            f"Polza AI rate limit превышен: {exc}"
        ) from exc
    except APITimeoutError as exc:
        raise AIServiceUnavailableError(
            f"Polza AI timeout после {settings.polza_ai_timeout_seconds}s: {exc}"
        ) from exc
    except APIConnectionError as exc:
        raise AIServiceUnavailableError(
            f"Не удалось подключиться к Polza AI ({settings.polza_ai_base_url}): {exc}"
        ) from exc
    except APIError as exc:
        # Любая другая ошибка от провайдера (5xx, 4xx кроме выше)
        raise AIServiceUnavailableError(
            f"Polza AI вернул ошибку: {exc}"
        ) from exc

    latency_ms = int((time.monotonic() - start) * 1000)

    # --- Extract content ---
    if not response.choices:
        raise AIServiceUnavailableError(
            "Polza AI вернул пустой choices[] — нечего парсить"
        )
    content = response.choices[0].message.content
    if not content:
        raise AIServiceUnavailableError(
            "Polza AI вернул choices[0].message.content=None"
        )

    # --- Parse JSON ---
    try:
        raw_dict: dict[str, Any] = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AIServiceUnavailableError(
            f"Polza AI вернул невалидный JSON: {exc}; content={content[:200]!r}"
        ) from exc

    # --- Validate against Pydantic schema ---
    try:
        parsed = schema.model_validate(raw_dict)
    except ValidationError as exc:
        raise AIServiceUnavailableError(
            f"Ответ Polza AI не соответствует схеме {schema.__name__}: {exc}"
        ) from exc

    # --- Extract usage metrics for Phase 7.5 cost logging ---
    # Polza возвращает usage в OpenAI-совместимом формате. Если провайдер
    # по какой-то причине не отдал usage (редкое), заполняем нулями —
    # логирование в 7.5 зафиксирует, но это сигнал для investigation.
    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    total_tokens = usage.total_tokens if usage else 0

    return AICallResult(
        parsed=parsed,
        model=response.model or model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
    )
