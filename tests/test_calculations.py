from __future__ import annotations

import pytest

from app.decoder.calculations import calculate_group_value
from app.decoder.types import CalcGroupSpec


@pytest.mark.parametrize(
    ("stat", "expected"),
    [
        ("min", 1.0),
        ("max", 4.0),
        ("diff", 3.0),
        ("sum", 8.0),
        ("avg", 2.0),
    ],
)
def test_calculate_group_value(stat, expected):
    calc = CalcGroupSpec(group="Cells", stat=stat, unit="V")
    assert calculate_group_value(calc, [1.0, 2.0, 1.0, 4.0]) == pytest.approx(expected)


def test_calculate_group_value_rejects_empty_values():
    calc = CalcGroupSpec(group="Cells", stat="avg", unit="V")
    with pytest.raises(ValueError, match="empty"):
        calculate_group_value(calc, [])
