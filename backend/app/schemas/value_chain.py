"""Pydantic схемы для Value Chain / Стакан (Phase 8.2).

Per-unit waterfall экономика по SKU × канал:
Shelf Price → Ex-Factory → COGS → GP → Logistics → Contribution → CA&M → Marketing → EBITDA.
"""
from decimal import Decimal

from pydantic import BaseModel


class ValueChainCell(BaseModel):
    """Per-unit waterfall для одной комбинации SKU × канал."""

    channel_code: str
    channel_name: str

    # Price waterfall (per unit, ₽)
    shelf_price_reg: Decimal
    shelf_price_weighted: Decimal
    ex_factory: Decimal

    # COGS breakdown (per unit, ₽)
    cogs_material: Decimal
    cogs_production: Decimal
    cogs_total: Decimal

    # P&L waterfall (per unit, ₽)
    gross_profit: Decimal
    logistics: Decimal
    contribution: Decimal
    ca_m: Decimal
    marketing: Decimal
    ebitda: Decimal

    # Margins (доли 0..1, frontend переведёт в %)
    gp_margin: Decimal
    cm_margin: Decimal
    ebitda_margin: Decimal


class ValueChainSKU(BaseModel):
    """Колонка = один SKU со всеми каналами."""

    sku_brand: str
    sku_name: str
    sku_format: str | None
    sku_volume_l: Decimal | None
    channels: list[ValueChainCell]


class ValueChainResponse(BaseModel):
    """Value Chain: колонки = SKU, строки = waterfall steps × каналы."""

    vat_rate: Decimal
    skus: list[ValueChainSKU]
