"""Сервис для построения price waterfall и value chain.

Phase 8.1 / 8.2: вычисление per-unit ценовой и P&L экономики из
статических параметров (ProjectSKU + ProjectSKUChannel + BOM).
Не требует запуска pipeline — формулы детерминированы.

Используется как API endpoint'ами (pricing_summary, value_chain),
так и экспортерами (PPT/PDF).
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import BOMItem, Project, ProjectSKU, ProjectSKUChannel
from app.schemas.pricing import (
    PricingCell,
    PricingSummaryResponse,
    SKUPricingColumn,
)
from app.schemas.value_chain import (
    ValueChainCell,
    ValueChainResponse,
    ValueChainSKU,
)


async def build_pricing_summary(
    session: AsyncSession,
    project: Project,
) -> PricingSummaryResponse:
    """Вычисляет ценовую сводку для всех SKU × каналов проекта.

    Возвращает PricingSummaryResponse с shelf / promo / weighted /
    ex_factory / channel_margin для каждой комбинации + COGS per unit
    из BOM.
    """
    vat_rate = project.vat_rate

    psk_stmt = (
        select(ProjectSKU)
        .where(ProjectSKU.project_id == project.id, ProjectSKU.include.is_(True))
        .options(selectinload(ProjectSKU.sku))
        .order_by(ProjectSKU.id)
    )
    psks = (await session.scalars(psk_stmt)).all()

    skus: list[SKUPricingColumn] = []
    for psk in psks:
        # COGS per unit from BOM
        boms = (
            await session.scalars(
                select(BOMItem).where(BOMItem.project_sku_id == psk.id)
            )
        ).all()
        cogs = Decimal("0")
        for b in boms:
            cogs += b.quantity_per_unit * b.price_per_unit * (Decimal("1") + b.loss_pct)

        psc_stmt = (
            select(ProjectSKUChannel)
            .where(ProjectSKUChannel.project_sku_id == psk.id)
            .options(selectinload(ProjectSKUChannel.channel))
            .order_by(ProjectSKUChannel.id)
        )
        pscs = (await session.scalars(psc_stmt)).all()

        channels: list[PricingCell] = []
        for psc in pscs:
            sp_reg = psc.shelf_price_reg
            sp_promo = sp_reg * (Decimal("1") - psc.promo_discount)
            sp_weighted = (
                sp_reg * (Decimal("1") - psc.promo_share)
                + sp_promo * psc.promo_share
            )
            ex_factory = (
                sp_weighted
                / (Decimal("1") + vat_rate)
                * (Decimal("1") - psc.channel_margin)
            )
            channels.append(
                PricingCell(
                    channel_code=psc.channel.code,
                    channel_name=psc.channel.name,
                    shelf_price_reg=sp_reg,
                    shelf_price_promo=sp_promo,
                    shelf_price_weighted=sp_weighted,
                    ex_factory=ex_factory,
                    channel_margin=psc.channel_margin,
                    promo_discount=psc.promo_discount,
                    promo_share=psc.promo_share,
                )
            )

        skus.append(
            SKUPricingColumn(
                sku_brand=psk.sku.brand,
                sku_name=psk.sku.name,
                sku_format=psk.sku.format,
                sku_volume_l=psk.sku.volume_l,
                cogs_per_unit=cogs,
                channels=channels,
            )
        )

    return PricingSummaryResponse(vat_rate=vat_rate, skus=skus)


async def build_value_chain(
    session: AsyncSession,
    project: Project,
) -> ValueChainResponse:
    """Вычисляет per-unit waterfall для всех SKU × каналов проекта.

    Возвращает Shelf → Ex-Factory → COGS → GP → Logistics → CM →
    CA&M → Marketing → EBITDA + margins.
    """
    vat_rate = project.vat_rate
    ZERO = Decimal("0")
    ONE = Decimal("1")
    DENSITY = Decimal("1")  # D-09: product_density ≈ 1.0 для напитков

    psk_stmt = (
        select(ProjectSKU)
        .where(ProjectSKU.project_id == project.id, ProjectSKU.include.is_(True))
        .options(selectinload(ProjectSKU.sku))
        .order_by(ProjectSKU.id)
    )
    psks = (await session.scalars(psk_stmt)).all()

    skus: list[ValueChainSKU] = []
    for psk in psks:
        boms = (
            await session.scalars(
                select(BOMItem).where(BOMItem.project_sku_id == psk.id)
            )
        ).all()
        bom_cost = ZERO
        for b in boms:
            bom_cost += b.quantity_per_unit * b.price_per_unit * (ONE + b.loss_pct)

        volume_l = psk.sku.volume_l or ZERO
        prod_rate = psk.production_cost_rate

        psc_stmt = (
            select(ProjectSKUChannel)
            .where(ProjectSKUChannel.project_sku_id == psk.id)
            .options(selectinload(ProjectSKUChannel.channel))
            .order_by(ProjectSKUChannel.id)
        )
        pscs = (await session.scalars(psc_stmt)).all()

        channels: list[ValueChainCell] = []
        for psc in pscs:
            sp_reg = psc.shelf_price_reg
            sp_promo = sp_reg * (ONE - psc.promo_discount)
            sp_weighted = sp_reg * (ONE - psc.promo_share) + sp_promo * psc.promo_share
            ex_factory = sp_weighted / (ONE + vat_rate) * (ONE - psc.channel_margin)

            cogs_material = bom_cost
            cogs_production = ex_factory * prod_rate
            cogs_total = cogs_material + cogs_production

            gross_profit = ex_factory - cogs_total
            logistics = psc.logistics_cost_per_kg * volume_l * DENSITY
            contribution = gross_profit - logistics
            # Q6 (2026-05-15): CA&M и Marketing per-channel
            ca_m = ex_factory * psc.ca_m_rate
            marketing = ex_factory * psc.marketing_rate
            ebitda = contribution - ca_m - marketing

            if ex_factory > ZERO:
                gp_margin = gross_profit / ex_factory
                cm_margin = contribution / ex_factory
                ebitda_margin = ebitda / ex_factory
            else:
                gp_margin = cm_margin = ebitda_margin = ZERO

            channels.append(
                ValueChainCell(
                    channel_code=psc.channel.code,
                    channel_name=psc.channel.name,
                    shelf_price_reg=sp_reg,
                    shelf_price_weighted=sp_weighted,
                    ex_factory=ex_factory,
                    cogs_material=cogs_material,
                    cogs_production=cogs_production,
                    cogs_total=cogs_total,
                    gross_profit=gross_profit,
                    logistics=logistics,
                    contribution=contribution,
                    ca_m=ca_m,
                    marketing=marketing,
                    ebitda=ebitda,
                    gp_margin=gp_margin,
                    cm_margin=cm_margin,
                    ebitda_margin=ebitda_margin,
                )
            )

        skus.append(
            ValueChainSKU(
                sku_brand=psk.sku.brand,
                sku_name=psk.sku.name,
                sku_format=psk.sku.format,
                sku_volume_l=psk.sku.volume_l,
                channels=channels,
            )
        )

    return ValueChainResponse(vat_rate=vat_rate, skus=skus)
