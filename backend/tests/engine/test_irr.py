"""Unit-тесты собственного IRR solver (backend/app/engine/irr.py).

Стандартные кейсы и crash-кейсы. Сравнение со школьной формулой
для простых случаев + сравнение с known answers для сложных.
"""
from __future__ import annotations

import math

import pytest

from app.engine.irr import irr, npv


class TestNPV:
    def test_zero_rate_npv_equals_sum(self):
        assert npv(0.0, [-100.0, 50.0, 50.0, 50.0]) == pytest.approx(50.0)

    def test_simple_npv(self):
        # NPV([−100, 110], 0.10) = −100 + 110/1.10 = −100 + 100 = 0
        assert npv(0.10, [-100.0, 110.0]) == pytest.approx(0.0, abs=1e-12)

    def test_npv_protects_against_neg_one_rate(self):
        # rate = −1 → 1+r = 0 → div by zero. Должны вернуть ±inf, не падать.
        result = npv(-1.0, [-100.0, 50.0])
        assert math.isinf(result)


class TestIRR:
    def test_simple_two_period(self):
        # IRR([−100, 110]) = 10% (один период доходности)
        result = irr([-100.0, 110.0])
        assert result is not None
        assert result == pytest.approx(0.10, abs=1e-6)

    def test_three_period_known_answer(self):
        # Initial -1000, +500/year × 3 года → IRR ≈ 23.38%
        result = irr([-1000.0, 500.0, 500.0, 500.0])
        assert result is not None
        assert result == pytest.approx(0.23375, abs=1e-4)

    def test_zero_irr(self):
        # Сумма = 0 → IRR = 0
        result = irr([-100.0, 100.0])
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_negative_irr(self):
        # Убыточный проект — IRR отрицательный
        result = irr([-100.0, 50.0])
        assert result is not None
        # NPV(-0.5, [-100, 50]) = -100 + 50/0.5 = 0 → IRR = -50%
        assert result == pytest.approx(-0.5, abs=1e-6)

    def test_no_sign_change_returns_none(self):
        # Все cashflows положительные → IRR не существует
        assert irr([100.0, 200.0, 300.0]) is None

    def test_all_negative_returns_none(self):
        assert irr([-100.0, -200.0, -300.0]) is None

    def test_empty_returns_none(self):
        assert irr([]) is None

    def test_single_returns_none(self):
        assert irr([-100.0]) is None

    def test_npv_at_irr_is_zero(self):
        """Для любого валидного IRR должно быть NPV(irr, cashflows) ≈ 0."""
        cf = [-1000.0, 200.0, 300.0, 400.0, 500.0]
        result = irr(cf)
        assert result is not None
        assert npv(result, cf) == pytest.approx(0.0, abs=1e-6)

    def test_high_irr_via_bisection(self):
        # Очень высокий IRR — Newton может расходиться, bisection должен спасти
        # cf = [-1, 0, 0, 0, 100] → 100^(1/4) − 1 ≈ 2.162 = 216.2%
        result = irr([-1.0, 0.0, 0.0, 0.0, 100.0])
        assert result is not None
        assert result == pytest.approx(100.0**0.25 - 1.0, abs=1e-4)

    def test_gorji_y1y10_full_irr(self):
        """Эталонный IRR Y1-Y10 = 78.6% из GORJI Excel KPI sheet.

        Исходные FCF — агрегаты GORJI Y0..Y9 (DATA row 43).
        """
        gorji_fcf = [
            -6546718.438654163,
            -10183029.581260249,
             4971323.773837056,
            19414536.056252077,
            27400692.921349034,
            32597353.806356624,
            38503715.36199582,
            45211635.21374282,
            52814368.209492534,
            60586701.27051398,
        ]
        result = irr(gorji_fcf)
        assert result is not None
        # Excel: 0.786343390702773
        assert result == pytest.approx(0.786343390702773, rel=1e-6)

    def test_gorji_y1y3_irr(self):
        """IRR Y1-Y3: 3 элемента, очень отрицательный (-61%)."""
        fcf3 = [
            -6546718.438654163,
            -10183029.581260249,
             4971323.773837056,
        ]
        result = irr(fcf3)
        assert result is not None
        # Excel: -0.6097262251770428
        assert result == pytest.approx(-0.6097262251770428, rel=1e-6)

    def test_gorji_y1y5_irr_6_elements(self):
        """IRR Y1-Y5 в Excel — 6 элементов (B43:G43), не 5. См. D-12."""
        fcf6 = [
            -6546718.438654163,
            -10183029.581260249,
             4971323.773837056,
            19414536.056252077,
            27400692.921349034,
            32597353.806356624,
        ]
        result = irr(fcf6)
        assert result is not None
        # Excel: 0.641219209682006
        assert result == pytest.approx(0.641219209682006, rel=1e-6)
