"""Pydantic схемы для ценовой сводки (Phase 8.1)."""
from decimal import Decimal

from pydantic import BaseModel


class PricingCell(BaseModel):
    """Ценовые показатели для одной комбинации SKU × канал."""

    channel_code: str
    channel_name: str
    shelf_price_reg: Decimal
    shelf_price_promo: Decimal
    shelf_price_weighted: Decimal
    ex_factory: Decimal
    channel_margin: Decimal
    promo_discount: Decimal
    promo_share: Decimal


class SKUPricingColumn(BaseModel):
    """Колонка = один SKU со всеми каналами."""

    sku_brand: str
    sku_name: str
    sku_format: str | None
    sku_volume_l: Decimal | None
    # C #23: единица измерения объёма/массы SKU ("л" | "кг")
    sku_unit_of_measure: str
    cogs_per_unit: Decimal
    channels: list[PricingCell]


class PricingSummaryResponse(BaseModel):
    """Сводная ценовая таблица: колонки = SKU, строки = каналы."""

    vat_rate: Decimal
    skus: list[SKUPricingColumn]
