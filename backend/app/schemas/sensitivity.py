"""Pydantic схемы для анализа чувствительности (4.4 / E-09)."""
from pydantic import BaseModel


class SensitivityCell(BaseModel):
    """Одна ячейка матрицы: (parameter × delta) → KPI."""

    parameter: str   # "nd" | "offtake" | "shelf_price" | "cogs"
    delta: float     # доля: -0.20, -0.10, 0.0, 0.10, 0.20
    npv_y1y10: float | None
    cm_ratio: float | None


class SensitivityResponse(BaseModel):
    """Полный результат sensitivity analysis для одного сценария.

    Структура:
    - `scope`: горизонт NPV (y1y3 / y1y5 / y1y10)
    - `base_*`: значения без модификаций (для reference в UI header)
    - `deltas`, `params`: список уровней и параметров (для построения
      table grid в UI без хардкода порядка)
    - `cells`: 4 параметра × 5 уровней = 20 ячеек
    """

    scope: str = "y1y10"
    base_npv_y1y10: float | None
    base_cm_ratio: float | None
    deltas: list[float]
    params: list[str]
    cells: list[SensitivityCell]
