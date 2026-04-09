"""Task-specific AI context builders (Phase 7.2, ADR-16).

Каждая AI-фича получает минимально достаточный контекст, а не "весь проект
всегда". Причины (ratified 2026-04-09, см. IMPLEMENTATION_PLAN Phase 7
решение №2):

1. **Cost scales linearly with tokens.** Contexts 10k+ tokens × 100 calls
   в день = легко 500₽/день только на prompt'ы.
2. **Diminishing returns.** После baseline KPI+params+top-N SKU
   модель не улучшает интерпретацию — только проигрывает важные
   сигналы в шуме.
3. **Prompt injection surface.** Content-поля паспорта содержат user
   input (project_goal, rationale, ...). Чем больше их в user_prompt,
   тем больше рисков что злонамеренный текст поломает system prompt.

Каждый метод строит `dict[str, Any]` готовый для `json.dumps()` —
финальный serialization делает caller в endpoint'е. Decimal-поля
сериализуются как float (через `float(x)`) — LLM не нужна
финансовая точность, важна читаемость.

## Добавление новой фичи

При добавлении 7.3..7.8 фич — добавляйте новый метод `for_<feature>`,
не расширяйте существующие. Это держит ответственность каждого метода
узкой, упрощает unit-тесты и не ломает прод-фичи при refactor'е.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    PeriodScope,
    Project,
    ProjectSKU,
    SKU,
    Scenario,
    ScenarioResult,
    ScenarioType,
)
from app.services.scenario_service import SCENARIO_ORDER, SCOPE_ORDER


class AIContextBuilderError(Exception):
    """Не удалось построить контекст — проект/сценарий не найдены,
    отсутствуют результаты расчёта и т.п. Endpoint ловит и возвращает
    4xx (не 5xx — это не AI-проблема, это состояние данных)."""


def _decimal_or_none(value: Any) -> float | None:
    """Конвертирует Decimal → float для JSON dump, пропускает None."""
    return float(value) if value is not None else None


class AIContextBuilder:
    """Сборщик контекста для AI-фич.

    Все методы async, читают из БД через переданную `session`. Не
    кэшируют ничего самостоятельно — кэширование на уровне
    финального LLM-вызова в `ai_cache.py` (input_hash включает
    context dict → если данные не менялись, кэш отдаст старый ответ).

    Usage:
        >>> builder = AIContextBuilder(session)
        >>> ctx = await builder.for_kpi_explanation(project_id=1,
        ...                                         scenario_id=3,
        ...                                         scope=PeriodScope.Y1Y5)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def for_kpi_explanation(
        self,
        *,
        project_id: int,
        scenario_id: int,
        scope: PeriodScope,
    ) -> dict[str, Any]:
        """Контекст для объяснения KPI одного сценария на одном scope.

        **Что включаем (~2-4k токенов):**

        - `project`: id, name, horizon_years, params (wacc, tax, wc, vat),
          gate_stage, project_goal (до 500 символов — anti-injection trim)
        - `focus`: {scenario_id, scenario_type, scope} — что AI должна
          объяснять в первую очередь
        - `scenarios`: все 3 (base/conservative/aggressive) с их дельтами
          и результатами по всем 3 scope'ам. Это даёт AI возможность
          сравнить фокусный сценарий с соседними и отметить аномалии.
        - `top_skus`: топ-3 ProjectSKU (сортировка условная по порядку
          id — volume/offtake хранится в PeriodValue и требует отдельного
          запроса; для MVP достаточно списка названий + rates)

        **Что НЕ включаем:**

        - PeriodValue (помесячные данные) — слишком много токенов, AI
          их не сможет осмыслить как числа. Если нужно — pull отдельно
          по запросу через freeform chat (7.3).
        - Channels — не критично для KPI explanation, добавим если
          ручная верификация покажет что AI не видит channel mix.
        - Content fields кроме project_goal — они включаются в
          `for_executive_summary` (7.4), не здесь.

        Raises:
            AIContextBuilderError: project/scenario не найдены или
                scenario не принадлежит проекту.
        """
        # --- 1. Project ---
        project = await self._session.get(Project, project_id)
        if project is None or project.deleted_at is not None:
            raise AIContextBuilderError(
                f"Project {project_id} не найден или удалён"
            )

        # --- 2. All scenarios of this project (для cross-comparison) ---
        scenarios_stmt = select(Scenario).where(Scenario.project_id == project_id)
        scenarios = list((await self._session.scalars(scenarios_stmt)).all())
        scenarios.sort(key=lambda s: SCENARIO_ORDER[s.type])

        # Валидация: запрошенный scenario принадлежит проекту
        focus_scenario = next(
            (s for s in scenarios if s.id == scenario_id), None
        )
        if focus_scenario is None:
            raise AIContextBuilderError(
                f"Scenario {scenario_id} не принадлежит project {project_id}"
            )

        # --- 3. All ScenarioResult rows для всех сценариев ---
        scenario_ids = [s.id for s in scenarios]
        results_stmt = select(ScenarioResult).where(
            ScenarioResult.scenario_id.in_(scenario_ids)
        )
        results = list((await self._session.scalars(results_stmt)).all())
        results_by_scenario: dict[int, list[ScenarioResult]] = {}
        for r in results:
            results_by_scenario.setdefault(r.scenario_id, []).append(r)
        for rows in results_by_scenario.values():
            rows.sort(key=lambda r: SCOPE_ORDER[r.period_scope])

        # --- 4. Top-3 ProjectSKU (с подгруженным SKU) ---
        skus_stmt = (
            select(ProjectSKU)
            .where(ProjectSKU.project_id == project_id)
            .where(ProjectSKU.include.is_(True))
            .options(selectinload(ProjectSKU.sku))
            .order_by(ProjectSKU.id)
            .limit(3)
        )
        project_skus = list((await self._session.scalars(skus_stmt)).all())

        # --- Собираем итоговый dict ---
        return {
            "project": {
                "id": project.id,
                "name": project.name,
                "horizon_years": project.horizon_years,
                "gate_stage": project.gate_stage,
                # Anti-injection trim: user-controlled тексты обрезаем
                # до 500 символов. Остальное LLM всё равно не осмыслит.
                "project_goal": _trim(project.project_goal, 500),
                "target_audience": _trim(project.target_audience, 300),
                "params": {
                    "wacc": float(project.wacc),
                    "tax_rate": float(project.tax_rate),
                    "wc_rate": float(project.wc_rate),
                    "vat_rate": float(project.vat_rate),
                    "currency": project.currency,
                },
            },
            "focus": {
                "scenario_id": scenario_id,
                "scenario_type": focus_scenario.type.value,
                "scope": scope.value,
            },
            "scenarios": [
                _serialize_scenario(s, results_by_scenario.get(s.id, []))
                for s in scenarios
            ],
            "top_skus": [_serialize_project_sku(ps) for ps in project_skus],
        }


def _trim(text: str | None, max_len: int) -> str | None:
    """Обрезает строку до `max_len` символов с суффиксом «…»."""
    if text is None:
        return None
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _serialize_scenario(
    scenario: Scenario,
    results: list[ScenarioResult],
) -> dict[str, Any]:
    """Сценарий + его результаты по всем scope'ам для контекста AI."""
    return {
        "id": scenario.id,
        "type": scenario.type.value,
        "deltas": {
            "nd": float(scenario.delta_nd),
            "offtake": float(scenario.delta_offtake),
            "opex": float(scenario.delta_opex),
        },
        "notes": _trim(scenario.notes, 200),
        "results": [
            {
                "scope": r.period_scope.value,
                "npv": _decimal_or_none(r.npv),
                "irr": _decimal_or_none(r.irr),
                "roi": _decimal_or_none(r.roi),
                "payback_simple": _decimal_or_none(r.payback_simple),
                "payback_discounted": _decimal_or_none(r.payback_discounted),
                "contribution_margin": _decimal_or_none(r.contribution_margin),
                "ebitda_margin": _decimal_or_none(r.ebitda_margin),
                "go_no_go": r.go_no_go,
            }
            for r in results
        ],
    }


def _serialize_project_sku(project_sku: ProjectSKU) -> dict[str, Any]:
    """ProjectSKU + SKU reference — минимум для контекста.

    Requires `selectinload(ProjectSKU.sku)` — см. паттерн #1 в CLAUDE.md
    (lazy='raise_on_sql' запрещает неявные загрузки).
    """
    sku: SKU = project_sku.sku
    return {
        "id": project_sku.id,
        "brand": sku.brand,
        "name": sku.name,
        "format": sku.format,
        "volume_l": _decimal_or_none(sku.volume_l),
        "segment": sku.segment,
        "production_cost_rate": float(project_sku.production_cost_rate),
        "ca_m_rate": float(project_sku.ca_m_rate),
        "marketing_rate": float(project_sku.marketing_rate),
    }
