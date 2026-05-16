"""C #27: catalog of PDF sections for selective export."""
from typing import Literal

SectionId = Literal[
    "title",
    "general",
    "concept",
    "tech",
    "validation",
    "product_mix",
    "macro",
    "kpi",
    "pnl",
    "sensitivity",
    "pricing",
    "unit_econ",
    "cost_stack",
    "risks",
    "roadmap",
    "market",
    "executive_summary",
]

ALL_SECTIONS: tuple[SectionId, ...] = (
    "title",
    "general",
    "concept",
    "tech",
    "validation",
    "product_mix",
    "macro",
    "kpi",
    "pnl",
    "sensitivity",
    "pricing",
    "unit_econ",
    "cost_stack",
    "risks",
    "roadmap",
    "market",
    "executive_summary",
)

SECTION_LABELS: dict[SectionId, str] = {
    "title": "Титульный лист",
    "general": "1. Общая информация",
    "concept": "2. Концепция продукта",
    "tech": "3. Технология и обоснование",
    "validation": "4. Результаты валидации",
    "product_mix": "5. Продуктовый микс",
    "macro": "6. Макро-факторы",
    "kpi": "7. Ключевые KPI",
    "pnl": "8. PnL по годам",
    "sensitivity": "Анализ чувствительности",
    "pricing": "Цены: полка/ex-factory/COGS",
    "unit_econ": "Стакан: per-unit экономика",
    "cost_stack": "9. Стакан себестоимости + фин-план",
    "risks": "10. Риски и готовность функций",
    "roadmap": "11. Дорожная карта",
    "market": "Рынок и поставки",
    "executive_summary": "12. Executive Summary",
}


def parse_sections(raw: str | None) -> set[SectionId]:
    """Parse query param value into a set of SectionId.

    Args:
        raw: The raw query param string, or None if param was omitted.

    Returns:
        Full set of ALL_SECTIONS when raw is None (backward-compat).
        Subset of sections when raw is a comma-separated list of valid IDs.

    Raises:
        ValueError: When raw is empty string or contains invalid IDs.
    """
    if raw is None:
        return set(ALL_SECTIONS)
    parts = [s.strip() for s in raw.split(",") if s.strip()]
    if not parts:
        raise ValueError("sections must contain at least one ID")
    invalid = [p for p in parts if p not in ALL_SECTIONS]
    if invalid:
        raise ValueError(f"Invalid section IDs: {sorted(invalid)}")
    return set(parts)  # type: ignore[arg-type]
