"""Tests for engine.geo."""

import pandas as pd

from engine.geo import build_ball_tree, haversine_m, query_radius


def test_haversine_known_distance() -> None:
    # Calgary downtown to the airport, straight-line ~9-10 km.
    d = haversine_m(51.0447, -114.0719, 51.1225, -114.0076)
    assert 9_000 < d < 11_000


def test_haversine_same_point_is_zero() -> None:
    assert haversine_m(51.0, -114.0, 51.0, -114.0) == 0.0


def test_query_radius_finds_nearby_excludes_far() -> None:
    df = pd.DataFrame({"latitude": [51.0, 51.001, 52.0], "longitude": [-114.0, -114.001, -114.0]})
    tree = build_ball_tree(df)
    idx = query_radius(tree, 51.0, -114.0, 500)
    assert set(idx) == {0, 1}
