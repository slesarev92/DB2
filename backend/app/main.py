"""FastAPI entry point цифрового паспорта проекта.

Роуты CRUD добавляются в Фазе 1, pipeline endpoint — в задаче 2.4.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth as auth_router
from app.api import bom as bom_router
from app.api import channels as channels_router
from app.api import period_values as period_values_router
from app.api import project_sku_channels as project_sku_channels_router
from app.api import project_skus as project_skus_router
from app.api import projects as projects_router
from app.api import skus as skus_router
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

app.include_router(auth_router.router)
app.include_router(projects_router.router)
app.include_router(skus_router.router)
app.include_router(project_skus_router.router)
app.include_router(bom_router.router)
app.include_router(channels_router.router)
app.include_router(project_sku_channels_router.router)
app.include_router(period_values_router.router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Liveness probe. Используется Docker healthcheck в compose."""
    return {"status": "ok"}
