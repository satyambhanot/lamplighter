"""Tests for engine.features.build_features()."""

import pandas as pd

from engine.features import build_features


def _lights() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "latitude": [51.0, 51.1],
            "longitude": [-114.0, -114.2],
            "comm_name": ["A", "B"],
            "is_damage": [False, True],
            "first_reported": [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-08")],
            "call_count": [1, 3],
        },
        index=["L1", "L2"],
    )


def test_build_features_no_layers_defaults_false() -> None:
    features = build_features(_lights(), {}, as_of=pd.Timestamp("2026-01-15"))
    assert not features["near_school"].any()
    assert not features["near_transit"].any()


def test_build_features_age_days() -> None:
    features = build_features(_lights(), {}, as_of=pd.Timestamp("2026-01-15"))
    assert features.loc["L1", "age_days"] == 14
    assert features.loc["L2", "age_days"] == 7


def test_build_features_near_school_hit() -> None:
    schools = pd.DataFrame({"latitude": [51.0001], "longitude": [-114.0001], "name": ["Test School"]})
    features = build_features(_lights(), {"schools": schools}, as_of=pd.Timestamp("2026-01-15"))
    assert bool(features.loc["L1", "near_school"]) is True
    assert bool(features.loc["L2", "near_school"]) is False


def test_build_features_neighbours_dark() -> None:
    lights = pd.DataFrame(
        {
            "latitude": [51.0, 51.0001, 52.0],
            "longitude": [-114.0, -114.0001, -114.0],
            "comm_name": ["A", "A", "B"],
            "is_damage": [False, False, False],
            "first_reported": [pd.Timestamp("2026-01-01")] * 3,
            "call_count": [1, 1, 1],
        },
        index=["L1", "L2", "L3"],
    )
    features = build_features(lights, {}, as_of=pd.Timestamp("2026-01-15"))
    assert features.loc["L1", "neighbours_dark"] == 1
    assert features.loc["L3", "neighbours_dark"] == 0
