"""Клиент Polza AI — тонкая обёртка над `openai` SDK (ADR-16, Phase 7.1).

Почему не свой HTTP-клиент: `openai` SDK обеспечивает встроенные
retry с exponential backoff, rate-limit handling, streaming и
timeout'ы из коробки. Polza AI — OpenAI-совместимый прокси, поэтому
достаточно подставить `base_url=https://polza.ai/api/v1` (именно с
`/api/v1`, не `/v1` — см. ERRORS_AND_ISSUES "Polza AI base URL").

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
- `polza_ai_base_url` — endpoint (`https://polza.ai/api/v1` — ADR-16
  corrected after Phase 7.1 smoke test)
- `polza_ai_timeout_seconds` — timeout на один вызов
- `polza_ai_max_retries` — retry внутри SDK при 5xx/connection errors
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
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


# ============================================================
# Model tier registry (Phase 7.2, ratified 2026-04-09)
# ============================================================
# Полный каталог Polza — ~380 моделей. Чтобы не hard-code'ить имя
# в каждом endpoint'е и не принимать архитектурных решений в UI,
# вводим 5 tier'ов с чёткими use case'ами. Endpoint получает
# `feature: AIFeature` и резолвит модель через FEATURE_DEFAULT_TIER.
# UI может override'нуть tier (Standard/Deep toggle) — тогда endpoint
# передаёт `tier_override`. Hard-coded model в endpoint — запрещено.


class AIModelTier(str, Enum):
    """Уровни моделей Polza AI по стоимости / мощности.

    Значения — stable string id'ы для сериализации в API запросах
    (tier_override в body) и в ai_usage_log для агрегации.
    """

    FAST_CHEAP = "fast_cheap"
    """claude-haiku-4.5: content fields bulk generation (7.6), audit, где
    скорость важнее качества. ~0.1-0.5₽/вызов."""

    BALANCED = "balanced"
    """claude-sonnet-4.6: default для 80% задач — explain KPI, sensitivity,
    короткие summary. ~1-3₽/вызов."""

    HEAVY = "heavy"
    """claude-opus-4.6: executive summary, аудит формул, сложные «почему».
    ~5-15₽/вызов. Используется когда UI явно требует Deep."""

    RESEARCH = "research"
    """claude-opus-4.6 + `web_search` tool: marketing research (7.7).
    ~10-30₽/вызов."""

    IMAGE = "image"
    """flux-2-pro: package mockups (7.8). ~5-10₽/картинка."""


TIER_MODEL: dict[AIModelTier, str] = {
    AIModelTier.FAST_CHEAP: "anthropic/claude-haiku-4.5",
    AIModelTier.BALANCED: DEFAULT_CHAT_MODEL,  # claude-sonnet-4.6
    AIModelTier.HEAVY: COMPLEX_CHAT_MODEL,  # claude-opus-4.6
    AIModelTier.RESEARCH: COMPLEX_CHAT_MODEL,  # + web_search tool (7.7)
    AIModelTier.IMAGE: "openai/gpt-image-1.5",
}
"""Маппинг tier → Polza model identifier. Изменение — через PR, не runtime."""


class AIFeature(str, Enum):
    """AI-фичи приложения. Stable string id'ы — используются в:

    - `ai_usage_log.endpoint` для агрегации расходов
    - Redis cache key (`ai_cache:{project_id}:{feature}:{hash}`)
    - Rate-limit key (`{user_id}:{feature}` → 10/min)
    - FEATURE_DEFAULT_TIER mapping ниже
    """

    EXPLAIN_KPI = "explain_kpi"
    """7.2 — объяснение NPV/IRR/Payback + Go/No-Go рекомендация."""

    EXPLAIN_SENSITIVITY = "explain_sensitivity"
    """7.3 — интерпретация tornado chart."""

    FREEFORM_CHAT = "freeform_chat"
    """7.3 — свободный чат про проект с SSE streaming."""

    EXECUTIVE_SUMMARY = "executive_summary"
    """7.4 — draft executive summary для PPT/PDF."""

    CONTENT_FIELD = "content_field"
    """7.6 — генерация текстовых полей паспорта (описание, цель, ...)."""

    MARKETING_RESEARCH = "marketing_research"
    """7.7 — web-поиск + синтез (competitors, market size, trends)."""

    PACKAGE_MOCKUP = "package_mockup"
    """7.8 — генерация изображения упаковки (flux-2-pro)."""


FEATURE_DEFAULT_TIER: dict[AIFeature, AIModelTier] = {
    AIFeature.EXPLAIN_KPI: AIModelTier.BALANCED,
    AIFeature.EXPLAIN_SENSITIVITY: AIModelTier.BALANCED,
    AIFeature.FREEFORM_CHAT: AIModelTier.BALANCED,
    AIFeature.EXECUTIVE_SUMMARY: AIModelTier.HEAVY,  # длинный вывод, важна связность
    AIFeature.CONTENT_FIELD: AIModelTier.FAST_CHEAP,  # 15 полей × 0.3₽ vs × 3₽
    AIFeature.MARKETING_RESEARCH: AIModelTier.RESEARCH,
    AIFeature.PACKAGE_MOCKUP: AIModelTier.IMAGE,
}
"""Default tier для каждой фичи. UI может override'нуть через `tier_override`."""


def resolve_model(
    feature: AIFeature, tier_override: AIModelTier | None = None
) -> str:
    """Резолвит Polza model identifier для данной фичи.

    Единственное разрешённое место для получения имени модели —
    через эту функцию. Hard-coded строки в endpoint'ах запрещены
    (усложняет change management: Polza переименует модель →
    придётся искать по всему коду).

    Args:
        feature: Enum фичи (EXPLAIN_KPI, EXECUTIVE_SUMMARY, ...).
        tier_override: Опциональный override tier'а из UI. Используется
            в Standard/Deep toggle: кликнули Deep → tier_override=HEAVY.

    Returns:
        Model identifier в Polza-формате, например
        `"anthropic/claude-sonnet-4.6"`.
    """
    tier = tier_override or FEATURE_DEFAULT_TIER[feature]
    return TIER_MODEL[tier]


# ============================================================
# Pricing table (Phase 7.2, ratified 2026-04-09)
# ============================================================
# ₽ per 1000 tokens для каждой модели. Значения — актуальные цены
# Polza AI по состоянию на 2026-04-09 (взяты из polza.ai/dashboard/pricing).
#
# TODO в Phase 7.5: проверить доступен ли `/api/v1/pricing` endpoint
# в Polza — если да, заменить на runtime fetch с 1h TTL. Пока — ручная
# таблица с датой обновления. При ошибке цены (модель отсутствует)
# `calculate_cost` возвращает `Decimal("0")` и логирует warning —
# не падаем, но получаем сигнал для investigation.

MODEL_PRICING: dict[str, tuple[Decimal, Decimal]] = {
    # model_id: (prompt_per_1k_rub, completion_per_1k_rub)
    "anthropic/claude-haiku-4.5": (Decimal("0.08"), Decimal("0.40")),
    "anthropic/claude-sonnet-4.6": (Decimal("0.30"), Decimal("1.50")),
    "anthropic/claude-opus-4.6": (Decimal("1.50"), Decimal("7.50")),
    # flux-2-pro — по изображениям, не по токенам. Cost вычисляется
    # отдельно в 7.8 (размер + quality). В MODEL_PRICING не кладём —
    # calculate_cost вернёт 0.
}
"""₽ per 1000 tokens. Обновлено 2026-04-09."""


def calculate_cost(
    model: str, prompt_tokens: int, completion_tokens: int
) -> Decimal:
    """Вычислить стоимость вызова в рублях по токенам.

    Args:
        model: Polza model identifier как в MODEL_PRICING.
        prompt_tokens: Токены prompt'а из `response.usage.prompt_tokens`.
        completion_tokens: Токены ответа.

    Returns:
        Decimal сумма в рублях с точностью до 6 знаков (Numeric(12, 6) в
        ai_usage_log.cost_rub). Если модель не в таблице — возвращает
        `Decimal("0")` (caller может залогировать warning).

    Пример:
        >>> calculate_cost("anthropic/claude-sonnet-4.6", 2500, 400)
        Decimal('1.35')  # 2.5k × 0.30 + 0.4k × 1.50
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return Decimal("0")
    prompt_per_1k, completion_per_1k = pricing
    return (
        (Decimal(prompt_tokens) / Decimal(1000)) * prompt_per_1k
        + (Decimal(completion_tokens) / Decimal(1000)) * completion_per_1k
    ).quantize(Decimal("0.000001"))


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
    feature: AIFeature | None = None,
    tier_override: AIModelTier | None = None,
    model: str | None = None,
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
        feature: Enum фичи (EXPLAIN_KPI, CONTENT_FIELD, ...). Резолвит
            модель через FEATURE_DEFAULT_TIER[feature]. Предпочтительный
            способ указать модель, начиная с Phase 7.2 — тогда tier
            меняется централизованно, без правок в endpoint'ах.
        tier_override: Опциональный override tier'а от UI (Standard→Deep).
            Игнорируется если `feature` не задан.
        model: Явный Polza model identifier (legacy Phase 7.1 путь).
            Используется только если `feature` не передан. По умолчанию
            — DEFAULT_CHAT_MODEL (claude-sonnet-4.6). Новый код должен
            использовать `feature=`.
        endpoint: Имя вызывающей фичи/endpoint'а для Phase 7.5 cost
            logging (`explain_kpi`, `marketing_research`, ...). Может
            совпадать с `feature.value` либо быть более специфичным
            (например, `explain_kpi_debug` для Prompt Lab). В 7.2
            передаётся в `ai_usage_log.endpoint` через caller'а.
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
    # Резолвим модель: feature → tier → model, либо явный model=, либо default.
    if feature is not None:
        resolved_model = resolve_model(feature, tier_override)
    elif model is not None:
        resolved_model = model
    else:
        resolved_model = DEFAULT_CHAT_MODEL

    # endpoint зарезервирован под запись в ai_usage_log.endpoint —
    # caller (log_ai_usage helper) использует его отдельно после
    # получения AICallResult. Здесь мы его просто принимаем.
    del endpoint  # noqa: F841

    try:
        client = _get_client()
    except AIServiceUnavailableError:
        raise

    start = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=resolved_model,
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

    # --- Strip markdown code fences (```json ... ```) if present ---
    cleaned = content.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1:]
        # Remove closing fence
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()

    # --- Parse JSON ---
    try:
        raw_dict: dict[str, Any] = json.loads(cleaned)
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
        model=response.model or resolved_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
    )


async def complete_vision(
    *,
    system_prompt: str,
    user_prompt: str,
    image_base64: str,
    image_media_type: str = "image/png",
    schema: type[T],
    feature: AIFeature | None = None,
    tier_override: AIModelTier | None = None,
    endpoint: str = "unknown",
    temperature: float = 0.2,
) -> AICallResult[T]:
    """Claude vision: анализ изображения + JSON output.

    Отправляет изображение как base64 в content block (OpenAI vision
    format). Используется в Phase 7.8 для анализа reference-изображения
    (логотип) и генерации art direction для flux.

    Args:
        image_base64: Base64-encoded изображение (без data: prefix).
        image_media_type: MIME type изображения.
        Остальные аргументы — как в complete_json.
    """
    if feature is not None:
        resolved_model = resolve_model(feature, tier_override)
    else:
        resolved_model = COMPLEX_CHAT_MODEL

    try:
        client = _get_client()
    except AIServiceUnavailableError:
        raise

    start = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=resolved_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{image_media_type};base64,{image_base64}",
                            },
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
        )
    except AuthenticationError as exc:
        raise AIServiceUnavailableError(f"Polza AI auth failed: {exc}") from exc
    except RateLimitError as exc:
        raise AIServiceUnavailableError(f"Polza AI rate limit: {exc}") from exc
    except APITimeoutError as exc:
        raise AIServiceUnavailableError(f"Polza AI timeout: {exc}") from exc
    except APIConnectionError as exc:
        raise AIServiceUnavailableError(f"Polza AI connection error: {exc}") from exc
    except APIError as exc:
        raise AIServiceUnavailableError(f"Polza AI error: {exc}") from exc

    latency_ms = int((time.monotonic() - start) * 1000)

    if not response.choices:
        raise AIServiceUnavailableError("Polza AI: empty choices[]")
    content = response.choices[0].message.content
    if not content:
        raise AIServiceUnavailableError("Polza AI: content=None")

    # Strip markdown code fences if present
    cleaned = content.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1:]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()

    try:
        raw_dict: dict[str, Any] = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AIServiceUnavailableError(
            f"Invalid JSON from vision: {exc}; content={content[:200]!r}"
        ) from exc

    try:
        parsed = schema.model_validate(raw_dict)
    except ValidationError as exc:
        raise AIServiceUnavailableError(
            f"Vision schema mismatch {schema.__name__}: {exc}"
        ) from exc

    usage = response.usage
    return AICallResult(
        parsed=parsed,
        model=response.model or resolved_model,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        total_tokens=usage.total_tokens if usage else 0,
        latency_ms=latency_ms,
    )


async def generate_image(
    *,
    prompt: str,
    model: str = "openai/gpt-image-1.5",
    aspect_ratio: str = "1:1",
    n: int = 1,
) -> dict[str, Any]:
    """Генерация изображения через Polza Media API (POST /v1/media).

    Polza Media API: POST /v1/media → {id, status} → GET /v1/media/{id} poll.
    Docs: https://polza.ai/docs/api-reference/media/create.md

    Returns:
        {"b64_json": str, "model": str, "latency_ms": int}

    Raises:
        AIServiceUnavailableError
    """
    import asyncio
    import base64 as b64mod
    import httpx

    if not settings.polza_ai_api_key:
        raise AIServiceUnavailableError(
            "POLZA_AI_API_KEY не задан в .env — AI-модуль отключён. "
            "Получите ключ в polza.ai/dashboard/api-keys и добавьте в .env."
        )

    base_url = settings.polza_ai_base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {settings.polza_ai_api_key}",
        "Content-Type": "application/json",
    }

    start = time.monotonic()

    async with httpx.AsyncClient(timeout=180) as http:
        # 1. Submit via Media API (POST /v1/media)
        resp = await http.post(
            f"{base_url}/media",
            headers=headers,
            json={
                "model": model,
                "input": {
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "image_resolution": "1K",
                },
                "async": True,
            },
        )
        if resp.status_code >= 300:
            raise AIServiceUnavailableError(
                f"Polza media submit {resp.status_code}: {resp.text[:500]}"
            )

        data = resp.json()
        gen_id = data.get("id")

        # Check if already completed (sync response)
        if data.get("status") == "completed" and data.get("data"):
            items = data["data"] if isinstance(data["data"], list) else [data["data"]]
            for item in items:
                url = item.get("url")
                if url:
                    img_resp = await http.get(url)
                    img_resp.raise_for_status()
                    b64 = b64mod.b64encode(img_resp.content).decode()
                    latency_ms = int((time.monotonic() - start) * 1000)
                    return {"b64_json": b64, "model": model, "latency_ms": latency_ms}

        if not gen_id:
            raise AIServiceUnavailableError(
                f"Polza media: no id in response: {str(data)[:300]}"
            )

        # 2. Poll GET /v1/media/{id} (max 120s, every 4s)
        for _ in range(30):
            await asyncio.sleep(4)
            try:
                poll_resp = await http.get(
                    f"{base_url}/media/{gen_id}",
                    headers=headers,
                )
                poll_data = poll_resp.json()
            except httpx.HTTPError:
                continue

            status = poll_data.get("status", "")

            if status == "failed":
                err = poll_data.get("error", {})
                err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                raise AIServiceUnavailableError(f"Polza image failed: {err_msg}")

            if status == "completed":
                latency_ms = int((time.monotonic() - start) * 1000)
                result_data = poll_data.get("data", {})
                items = result_data if isinstance(result_data, list) else [result_data] if result_data else []

                for item in items:
                    url = item.get("url")
                    if url:
                        try:
                            img_resp = await http.get(url)
                            img_resp.raise_for_status()
                            b64 = b64mod.b64encode(img_resp.content).decode()
                            return {"b64_json": b64, "model": model, "latency_ms": latency_ms}
                        except httpx.HTTPError as exc:
                            raise AIServiceUnavailableError(
                                f"Failed to download image: {exc}"
                            ) from exc

                raise AIServiceUnavailableError(
                    f"Polza: completed but no URL in data: {str(poll_data)[:300]}"
                )

        raise AIServiceUnavailableError("Polza image generation timeout (120s)")
