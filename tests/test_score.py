"""Tests for engine.score."""

import pandas as pd

from engine.score import make_score_policy, reasons, score


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "is_damage": [False, True],
            "near_school": [False, True],
            "near_transit": [False, False],
            "call_count": [1, 3],
            "neighbours_dark": [0, 2],
            "age_days": [7, 14],
        },
        index=["L1", "L2"],
    )


WEIGHTS = {"w_age": 1.0, "w_damage": 1.0, "w_school": 1.0, "w_transit": 0.5, "w_repeat": 0.5, "w_cluster": 0.25}


def test_score_higher_for_damage_school_repeat() -> None:
    s = score(_features(), WEIGHTS)
    assert s["L2"] > s["L1"]


def test_score_age_only() -> None:
    features = pd.DataFrame(
        {
            "is_damage": [False],
            "near_school": [False],
            "near_transit": [False],
            "call_count": [1],
            "neighbours_dark": [0],
            "age_days": [14],
        },
        index=["L1"],
    )
    s = score(features, WEIGHTS)
    assert s["L1"] == 2.0  # 2 weeks old * w_age=1.0


def test_reasons_mentions_damage_and_school() -> None:
    r = reasons(_features(), WEIGHTS)
    assert "damage ticket" in r["L2"]
    assert "near a school" in r["L2"]


def test_make_score_policy_orders_by_score() -> None:
    lights = pd.DataFrame(
        {
            "latitude": [51.0, 51.1],
            "longitude": [-114.0, -114.2],
            "comm_name": ["A", "B"],
            "is_damage": [False, True],
            "first_reported": [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-01")],
            "call_count": [1, 1],
        },
        index=["L1", "L2"],
    )
    policy = make_score_policy({}, WEIGHTS)
    order = policy(lights, pd.Timestamp("2026-01-15"))
    assert order[0] == "L2"  # damage ticket should rank first, same age
