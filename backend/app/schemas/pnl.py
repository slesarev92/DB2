"""Pydantic схемы для P&L endpoint (Phase 8.5).

Per-period P&L метрики из pipeline. Frontend группирует
по месяцам/кварталам/годам через toggle.
"""
from pydantic import BaseModel


class PnlPeriod(BaseModel):
    """P&L метрики для одного периода."""

    period_label: str          # "M1", "M2", ..., "M36", "Y4", ..., "Y10"
    period_type: str           # "monthly" | "annual"
    model_year: int            # 1..10
    month_num: int | None      # 1..12 для monthly, None для annual
    quarter: int | None        # 1..4 для monthly, None для annual

    # P&L метрики (₽, агрегат по всем SKU × Channel)
    volume_units: float
    volume_liters: float
    net_revenue: float
    cogs_total: float
    gross_profit: float
    logistics_cost: float
    contribution: float
    ca_m_cost: float
    marketing_cost: float
    ebitda: float
    free_cash_flow: float


class PnlResponse(BaseModel):
    """Per-period P&L для проекта."""

    scenario_type: str         # "base" | "conservative" | "aggressive"
    periods: list[PnlPeriod]
