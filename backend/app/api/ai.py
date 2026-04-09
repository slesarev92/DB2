"""AI endpoints (Phase 7.2..7.8).

Все AI-фичи живут здесь. Каждый endpoint следует единому flow:

1. `Depends(get_current_user)` — требует авторизацию
2. `@limiter.limit("10/minute", key_func=...)` — rate limit
3. `await check_daily_user_budget(...)` — daily cap safety net
4. Context build через `AIContextBuilder`
5. Cache check через `ai_cache`
6. `ai_service.complete_json(feature=..., ...)` — реальный Polza вызов
7. `log_ai_usage(...)` — в БД
8. Response со строкой `cached: bool`, `cost_rub`, `model`

Phase 7.2 добавляет explain-kpi. Следующие endpoint'ы (7.3..7.8)
расширяют этот файл по мере добавления фич.
"""
from __future__ import annotations

from fastapi import APIRouter

# Префикс /api/projects/{project_id}/ai — все AI endpoint'ы привязаны
# к проекту. Исключение — админ endpoint'ы (в MVP не нужны).
router = APIRouter(
    prefix="/api/projects/{project_id}/ai",
    tags=["ai"],
)

# Endpoint'ы добавляются в commit 2 (explain-kpi) и далее 7.3..7.8.
