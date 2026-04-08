"""IRR (Internal Rate of Return) — собственная реализация без внешних зависимостей.

Newton-Raphson с несколькими начальными приближениями + fallback на bisection.
Возвращает None если решения нет (например, все cashflows одного знака —
тогда NPV монотонна и не пересекает ноль).

Почему не numpy-financial:
- Заброшен с 2020 года
- Тяжело тащить ради одной функции
- Newton-Raphson + bisection — 50 строк кода, полностью под нашим контролем

Почему не scipy.optimize.brentq:
- scipy ≈ 50 МБ зависимостей ради одной функции
- Newton-Raphson сходится быстрее brentq на хороших данных,
  bisection как fallback работает на любых

Алгоритм:
1. Проверка существования решения: должна быть смена знака в cashflows.
2. Newton-Raphson из нескольких guess'ов (-0.5, 0.0, 0.1, 0.5).
3. Если NR расходится / NPV''=0 → fallback на bisection в [-0.99, 10.0].
4. Если bisection не сходится → return None.
"""
from __future__ import annotations

from collections.abc import Sequence

# Дефолтные начальные приближения для Newton-Raphson.
# Покрывают: глубокий убыток (-50%), ноль, скромный возврат (10%),
# высокий возврат (50%). Из них хотя бы один обычно сходится.
_NR_INITIAL_GUESSES: tuple[float, ...] = (-0.5, 0.0, 0.1, 0.5, 1.0)

# Границы bisection. Нижняя > -1 — иначе (1+r) ≤ 0, формула NPV ломается
# (отрицательное число в дробной степени). Верхняя 10.0 = 1000% годовых,
# покрывает любой реалистичный IRR.
_BISECT_LOW = -0.999
_BISECT_HIGH = 10.0


def npv(rate: float, cashflows: Sequence[float]) -> float:
    """NPV cashflows при ставке rate. Cashflows[0] = период 0 (не дисконтируется)."""
    one_plus = 1.0 + rate
    if one_plus <= 0:
        # Защита: (1+r)^t для t=0 = 1, для t>0 = 0 → математически невалидно.
        return float("inf") if cashflows[0] >= 0 else float("-inf")
    total = 0.0
    factor = 1.0
    for cf in cashflows:
        total += cf / factor
        factor *= one_plus
    return total


def _npv_derivative(rate: float, cashflows: Sequence[float]) -> float:
    """d(NPV)/d(rate) — нужна для Newton-Raphson.

    NPV = Σ cf[t] / (1+r)^t
    d/dr = Σ -t × cf[t] / (1+r)^(t+1)
    """
    one_plus = 1.0 + rate
    if one_plus <= 0:
        return 0.0
    total = 0.0
    factor = one_plus  # (1+r)^(t+1) для t=0 = (1+r)^1
    for t, cf in enumerate(cashflows):
        if t > 0:  # член с t=0 = 0 в производной
            total -= t * cf / factor
        factor *= one_plus
    return total


def _has_sign_change(cashflows: Sequence[float]) -> bool:
    """Решение IRR существует только если есть хотя бы одна смена знака."""
    pos = any(cf > 0 for cf in cashflows)
    neg = any(cf < 0 for cf in cashflows)
    return pos and neg


def irr(
    cashflows: Sequence[float],
    *,
    tol: float = 1e-9,
    max_iter: int = 100,
) -> float | None:
    """Internal Rate of Return для последовательности cashflows.

    Args:
        cashflows: список денежных потоков, [0] = период 0 (обычно отрицательный),
                   [1..n] = последующие периоды.
        tol: допуск по |NPV(rate)| для сходимости.
        max_iter: максимум итераций для каждого guess'а Newton-Raphson и для bisection.

    Returns:
        Ставка IRR в долях единицы (0.15 = 15%) или None если решения нет
        (например, все cashflows одного знака) или ни один метод не сошёлся.
    """
    if len(cashflows) < 2:
        return None
    if not _has_sign_change(cashflows):
        return None

    # 1. Newton-Raphson из разных guess'ов
    for guess in _NR_INITIAL_GUESSES:
        rate = guess
        for _ in range(max_iter):
            f = npv(rate, cashflows)
            if abs(f) < tol:
                return rate
            df = _npv_derivative(rate, cashflows)
            if df == 0.0:
                break  # производная нулевая → шаг невалиден, пробуем следующий guess
            new_rate = rate - f / df
            # Защита от выхода за нижнюю границу (1+r > 0).
            if new_rate <= -1.0:
                new_rate = (rate - 1.0) / 2.0
            if abs(new_rate - rate) < tol:
                return new_rate
            rate = new_rate

    # 2. Bisection fallback
    return _bisect_irr(cashflows, tol=tol, max_iter=max_iter * 2)


def _bisect_irr(
    cashflows: Sequence[float],
    *,
    tol: float,
    max_iter: int,
) -> float | None:
    """Bisection IRR в [-0.999, 10.0]. Гарантирует сходимость если решение есть."""
    low, high = _BISECT_LOW, _BISECT_HIGH
    f_low = npv(low, cashflows)
    f_high = npv(high, cashflows)

    if f_low == 0:
        return low
    if f_high == 0:
        return high
    if (f_low > 0) == (f_high > 0):
        # Знаки одинаковы — решения нет в пределах диапазона.
        return None

    for _ in range(max_iter):
        mid = (low + high) / 2.0
        f_mid = npv(mid, cashflows)
        if abs(f_mid) < tol:
            return mid
        if (f_mid > 0) == (f_low > 0):
            low, f_low = mid, f_mid
        else:
            high, f_high = mid, f_mid
        if abs(high - low) < tol:
            return (low + high) / 2.0

    return None
