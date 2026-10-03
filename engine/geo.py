"""Haversine distance and BallTree radius-search helpers.

Used by features.py (school/transit/cluster lookups) and simulate.py
(duplicate merging and routing). Implemented in Phase 2/3.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in meters."""
    raise NotImplementedError("Phase 2")


def build_ball_tree(df: pd.DataFrame, lat_col: str = "latitude", lon_col: str = "longitude") -> BallTree:
    """Build a haversine BallTree over a DataFrame's coordinates.

    Args:
        df: DataFrame containing latitude/longitude columns.
        lat_col: Name of the latitude column.
        lon_col: Name of the longitude column.

    Returns:
        A scikit-learn BallTree built with ``metric="haversine"`` over
        radians, so query radii must be converted to radians first.
    """
    raise NotImplementedError("Phase 2")


def query_radius(tree: BallTree, lat: float, lon: float, radius_m: float) -> np.ndarray:
    """Return indices of all points within radius_m of (lat, lon)."""
    raise NotImplementedError("Phase 2")
