"""Tests for engine.plan.plan_week()."""

import pandas as pd

from config import DEPOT_LAT, DEPOT_LON
from engine.plan import plan_week, route_minutes


def _queue(n: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "latitude": [DEPOT_LAT + 0.001 * i for i in range(n)],
            "longitude": [DEPOT_LON + 0.001 * i for i in range(n)],
        },
        index=[f"L{i}" for i in range(n)],
    )


def test_plan_week_respects_budget() -> None:
    queue = _queue(10)
    order = list(queue.index)
    selected = plan_week(queue, order, budget_min=60)
    assert route_minutes(queue, selected) <= 60
    assert len(selected) < 10


def test_plan_week_empty_order() -> None:
    queue = _queue(5)
    assert plan_week(queue, [], budget_min=1000) == []


def test_plan_week_unlimited_budget_takes_all() -> None:
    queue = _queue(4)
    order = list(queue.index)
    selected = plan_week(queue, order, budget_min=10_000)
    assert set(selected) == set(order)
