"""Configured group calculations for decoded signals."""

from __future__ import annotations

from typing import Iterable, List

from .types import CalcGroupSpec


def calculate_group_value(calc: CalcGroupSpec, values: Iterable[float]) -> float:
    data: List[float] = list(values)
    if not data:
        raise ValueError("Cannot calculate an empty group")
    if calc.stat == "min":
        return min(data)
    if calc.stat == "max":
        return max(data)
    if calc.stat == "diff":
        return max(data) - min(data)
    if calc.stat == "sum":
        return sum(data)
    if calc.stat == "avg":
        return sum(data) / len(data)
    raise ValueError(f"Unsupported calc stat: {calc.stat!r}")
