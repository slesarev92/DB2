"""FastAPI entry point цифрового паспорта проекта.

В задаче 0.2 — минимальное приложение с /health endpoint. Роуты CRUD
добавляются в Фазе 1, pipeline endpoint — в задаче 2.4.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(
    title="Цифровой паспорт проекта",
    version="0.1.0",
    description=(
        "Backend API системы расчёта и управления проектами вывода новых SKU. "
        "См. docs/ADR.md и docs/IMPLEMENTATION_PLAN.md."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Liveness probe. Используется Docker healthcheck в compose."""
    return {"status": "ok"}
