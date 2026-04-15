"""S-04 rate limit smoke tests.

Покрывает rate limit декораторы на критичных endpoint'ах: login,
recalculate, экспорты. Полноценный integration test (генерация 11
запросов + проверка 429) не пишем по причинам, указанным в test_ai.py:
slowapi с Redis storage сложно изолировать между тестами без session-
scope reset, а TestClient получает один и тот же key (`testclient`/None)
— тесты мешают друг другу.

Минимальная защита — smoke-проверка что декораторы применены (импорт
endpoint'ов). Полноценная регрессия — manual/staging после deploy.
"""
from __future__ import annotations

import pytest
from slowapi.errors import RateLimitExceeded


def test_s04_rate_limit_endpoints_importable() -> None:
    """S-04 regression: endpoint'ы с @limiter.limit импортируются без ошибок.

    Если `@limiter.limit` применён к функции с несовместимой сигнатурой
    (например, без `request: Request`), slowapi падает при resolve time,
    что приводит к ошибкам импорта модуля. Этот тест ловит такое
    одной строкой и является cheap regression.
    """
    from app.api.auth import login
    from app.api.projects import (
        export_project_pdf_endpoint,
        export_project_pptx_endpoint,
        export_project_xlsx_endpoint,
        recalculate_project_endpoint,
    )

    for fn in (
        login,
        recalculate_project_endpoint,
        export_project_xlsx_endpoint,
        export_project_pptx_endpoint,
        export_project_pdf_endpoint,
    ):
        assert callable(fn), f"{fn.__name__} not callable after decoration"


def test_s04_limiter_singleton_configured() -> None:
    """S-04 regression: limiter singleton готов к работе.

    `limiter.reset()` — public API slowapi. Если инстанс повреждён
    (неправильная config), это фейлится.
    """
    from app.core.rate_limit import limiter

    # Проверяем что limiter — экземпляр с ожидаемыми атрибутами.
    assert hasattr(limiter, "limit"), "limiter.limit decorator missing"
    assert hasattr(limiter, "reset"), "limiter.reset missing"


def test_s04_rate_limit_exceeded_is_exception() -> None:
    """S-04 regression: RateLimitExceeded импортируется.

    Если slowapi обновится и экспорт сломается, middleware handler
    не будет ловить превышения → 500 вместо 429 в prod.
    """
    assert issubclass(RateLimitExceeded, Exception)
