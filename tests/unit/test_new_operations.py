"""
Unit tests for the new calculation types added in this iteration.

These exercise the SQLAlchemy polymorphic models directly, the same way
``tests/e2e/test_fastapi_calculator.py`` already exercises Addition,
Subtraction, Multiplication, and Division. No HTTP server or database
is involved — we instantiate the models in memory and call
``get_result()``.
"""

import math
from uuid import uuid4

import pytest

from app.models.calculation import (
    Calculation,
    Power,
    Modulus,
    SquareRoot,
)


@pytest.fixture()
def user_id():
    """A throwaway UUID, used as the ``user_id`` for in-memory calculations."""
    return uuid4()


# ---------------------------------------------------------------------------
# Power (exponentiation)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "inputs, expected",
    [
        ([2, 3], 8.0),                    # 2 ** 3
        ([2, 3, 2], 64.0),                # (2 ** 3) ** 2
        ([10, 0], 1.0),                   # x ** 0 == 1
        ([5, 1], 5.0),                    # identity
        ([2, -1], 0.5),                   # negative exponent
        ([4, 0.5], 2.0),                  # fractional exponent
    ],
    ids=[
        "two_then_three",
        "left_associative_chain",
        "exponent_zero",
        "exponent_one",
        "negative_exponent",
        "fractional_exponent",
    ],
)
def test_power_get_result(user_id, inputs, expected):
    calc = Calculation.create("power", user_id, inputs)
    assert isinstance(calc, Power)
    assert math.isclose(calc.get_result(), expected, rel_tol=1e-9)


def test_power_zero_to_negative_raises(user_id):
    calc = Calculation.create("power", user_id, [0, -1])
    with pytest.raises(ValueError, match="zero to a negative power"):
        calc.get_result()


def test_power_requires_at_least_two_inputs(user_id):
    calc = Calculation.create("power", user_id, [2])
    with pytest.raises(ValueError):
        calc.get_result()


def test_power_rejects_non_list(user_id):
    calc = Power(user_id=user_id, inputs="not a list")
    with pytest.raises(ValueError):
        calc.get_result()


# ---------------------------------------------------------------------------
# Modulus
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "inputs, expected",
    [
        ([10, 3], 1.0),
        ([100, 7, 4], 2.0),       # (100 % 7) % 4 = 2 % 4 = 2
        ([10, 5], 0.0),
        ([7.5, 2], 1.5),
    ],
    ids=[
        "simple_remainder",
        "left_associative_chain",
        "exact_division",
        "float_inputs",
    ],
)
def test_modulus_get_result(user_id, inputs, expected):
    calc = Calculation.create("modulus", user_id, inputs)
    assert isinstance(calc, Modulus)
    assert math.isclose(calc.get_result(), expected, rel_tol=1e-9)


def test_modulus_by_zero_raises(user_id):
    calc = Calculation.create("modulus", user_id, [10, 0])
    with pytest.raises(ValueError, match="modulus by zero"):
        calc.get_result()


def test_modulus_requires_at_least_two_inputs(user_id):
    calc = Calculation.create("modulus", user_id, [10])
    with pytest.raises(ValueError):
        calc.get_result()


# ---------------------------------------------------------------------------
# Square root
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value, expected",
    [
        (16, 4.0),
        (0, 0.0),
        (2, math.sqrt(2)),
        (1.21, 1.1),
    ],
    ids=["perfect_square", "zero", "non_square_int", "non_square_float"],
)
def test_square_root_get_result(user_id, value, expected):
    calc = Calculation.create("square_root", user_id, [value])
    assert isinstance(calc, SquareRoot)
    assert math.isclose(calc.get_result(), expected, rel_tol=1e-9)


def test_square_root_negative_raises(user_id):
    calc = Calculation.create("square_root", user_id, [-1])
    with pytest.raises(ValueError, match="negative number"):
        calc.get_result()


def test_square_root_rejects_extra_inputs(user_id):
    calc = Calculation.create("square_root", user_id, [4, 9])
    with pytest.raises(ValueError, match="exactly one input"):
        calc.get_result()


def test_square_root_rejects_empty(user_id):
    calc = SquareRoot(user_id=user_id, inputs=[])
    with pytest.raises(ValueError):
        calc.get_result()


# ---------------------------------------------------------------------------
# Factory dispatch
# ---------------------------------------------------------------------------
def test_factory_unknown_type_raises(user_id):
    with pytest.raises(ValueError, match="Unsupported calculation type"):
        Calculation.create("totally_made_up", user_id, [1, 2])


@pytest.mark.parametrize(
    "name, cls",
    [("power", Power), ("modulus", Modulus), ("square_root", SquareRoot)],
)
def test_factory_returns_correct_subclass(user_id, name, cls):
    inputs = [1] if name == "square_root" else [1, 2]
    instance = Calculation.create(name, user_id, inputs)
    assert isinstance(instance, cls)
    assert instance.type == name
