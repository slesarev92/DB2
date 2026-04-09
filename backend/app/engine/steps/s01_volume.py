"""Шаг 1 — Объём (Volume).

Формула (Excel: VOLUME sheet, DASH rows 25-27):
    ACTIVE_OUTLETS[t] = UNIVERSE_OUTLETS × ND[t]
    VOLUME_UNITS[t]   = ACTIVE_OUTLETS[t] × OFFTAKE[t] × SEASONALITY[t] × PERIOD_UNITS[t]
    VOLUME_LITERS[t]  = VOLUME_UNITS[t] × SKU.volume_l

Где `PERIOD_UNITS[t]`:
- 1 для monthly периодов (M1..M36) — input хранит monthly offtake
- 12 для yearly периодов (Y4..Y10) — input хранит monthly average
  offtake, годовой объём = monthly × 12. Так Excel хранит данные в DASH
  yearly cols: монтли среднее, агрегация × 12 в листах VOLUME / NET REVENUE.

Сезонность применяется **только** к monthly периодам (M1..M36).
Для годовых периодов (Y4..Y10) в `input.seasonality[t]` должно быть 1.0
(контракт PipelineInput — service формирует корректное значение).

Граничные случаи:
- `nd=0` → active_outlets=0 → volume=0. Не падаем, так и должно быть
  (канал ещё не запущен).
- `universe_outlets=0` → volume=0 по всему горизонту. Канал не имеет
  розничной сети (по сути пустая строка). Тоже не ошибка.

История:
- 2026-04-09: добавлен `period_units` множитель 12 для yearly periods.
  До этого pipeline считал yearly volume как одно "мгновение" (не × 12),
  что давало 12-кратное занижение Y4-Y10 NR/Contribution и катастрофически
  отрицательный NPV в полном GORJI импорте (4.2.1). test_gorji_reference
  не покрывал yearly, поэтому баг прошёл незамеченным до Discovery V2.
"""
from app.engine.context import PipelineContext


def step(ctx: PipelineContext) -> PipelineContext:
    inp = ctx.input
    n = inp.period_count

    active_outlets: list[float] = [0.0] * n
    volume_units: list[float] = [0.0] * n
    volume_liters: list[float] = [0.0] * n

    universe = float(inp.universe_outlets)

    for t in range(n):
        # Yearly periods: input.offtake[t] = monthly average, нужен × 12
        # для получения годового объёма (Excel-семантика).
        period_units = 1.0 if inp.period_is_monthly[t] else 12.0

        active = universe * inp.nd[t]
        vol_u = active * inp.offtake[t] * inp.seasonality[t] * period_units
        vol_l = vol_u * inp.sku_volume_l

        active_outlets[t] = active
        volume_units[t] = vol_u
        volume_liters[t] = vol_l

    ctx.active_outlets = active_outlets
    ctx.volume_units = volume_units
    ctx.volume_liters = volume_liters
    return ctx
