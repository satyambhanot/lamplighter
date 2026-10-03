"""Haversine distance and BallTree radius-search helpers.

Used by simulate.py (duplicate merging), plan.py (routing), and
features.py (school/transit/cluster lookups, Phase 3).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


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
    coords_rad = np.radians(df[[lat_col, lon_col]].to_numpy())
    return BallTree(coords_rad, metric="haversine")


def query_radius(tree: BallTree, lat: float, lon: float, radius_m: float) -> np.ndarray:
    """Return indices of all points within radius_m of (lat, lon),
    nearest first.
    """
    point_rad = np.radians([[lat, lon]])
    indices, _ = tree.query_radius(point_rad, r=radius_m / EARTH_RADIUS_M, sort_results=True, return_distance=True)
    return indices[0]
