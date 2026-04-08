"""Шаг 1 — Объём (Volume).

Формула (Excel: VOLUME sheet, DASH rows 25-27):
    ACTIVE_OUTLETS[t] = UNIVERSE_OUTLETS × ND[t]
    VOLUME_UNITS[t]   = ACTIVE_OUTLETS[t] × OFFTAKE[t] × SEASONALITY[t]
    VOLUME_LITERS[t]  = VOLUME_UNITS[t] × SKU.volume_l

Сезонность применяется **только** к monthly периодам (M1..M36).
Для годовых периодов (Y4..Y10) в `input.seasonality[t]` должно быть 1.0
(контракт PipelineInput — service формирует корректное значение).

Граничные случаи:
- `nd=0` → active_outlets=0 → volume=0. Не падаем, так и должно быть
  (канал ещё не запущен).
- `universe_outlets=0` → volume=0 по всему горизонту. Канал не имеет
  розничной сети (по сути пустая строка). Тоже не ошибка.
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
        active = universe * inp.nd[t]
        vol_u = active * inp.offtake[t] * inp.seasonality[t]
        vol_l = vol_u * inp.sku_volume_l

        active_outlets[t] = active
        volume_units[t] = vol_u
        volume_liters[t] = vol_l

    ctx.active_outlets = active_outlets
    ctx.volume_units = volume_units
    ctx.volume_liters = volume_liters
    return ctx
