"""Per-light features used by score(): school, transit, calls, cluster."""

from __future__ import annotations

import pandas as pd

from config import CLUSTER_RADIUS_M, SCHOOL_RADIUS_M, TRANSIT_RADIUS_M
from engine.geo import build_ball_tree, query_radius


def _near_any(lights: pd.DataFrame, layer: pd.DataFrame | None, radius_m: float) -> pd.Series:
    """True per light if layer has at least one point within radius_m.
    False for every light if the layer is missing or empty.
    """
    if layer is None or layer.empty:
        return pd.Series(False, index=lights.index)
    tree = build_ball_tree(layer)
    hits = [len(query_radius(tree, row.latitude, row.longitude, radius_m)) > 0 for row in lights.itertuples()]
    return pd.Series(hits, index=lights.index)


def _neighbours_dark(lights: pd.DataFrame) -> pd.Series:
    """Count of other open lights within CLUSTER_RADIUS_M, per light."""
    if len(lights) < 2:
        return pd.Series(0, index=lights.index)
    tree = build_ball_tree(lights)
    counts = [
        len(query_radius(tree, row.latitude, row.longitude, CLUSTER_RADIUS_M)) - 1
        for row in lights.itertuples()
    ]
    return pd.Series(counts, index=lights.index)


def build_features(
    lights: pd.DataFrame,
    layers: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Compute scoring features for each open light.

    Adds ``near_school`` (within SCHOOL_RADIUS_M), ``near_transit``
    (within TRANSIT_RADIUS_M), ``age_days``, and ``neighbours_dark``
    (other unfixed lights within CLUSTER_RADIUS_M). ``call_count`` and
    ``is_damage`` already exist on ``lights`` and pass through
    unchanged.

    Args:
        lights: Open lights (one row per light, not per raw ticket).
        layers: External layers, e.g. {"schools": df, "transit": df}.
            A missing or empty layer means "no nearby schools/transit"
            rather than an error.
        as_of: Date to measure age from. Defaults to now, for live API
            use; the replay passes the current simulated Monday.

    Returns:
        ``lights`` with the feature columns appended.
    """
    as_of = as_of if as_of is not None else pd.Timestamp.now()
    features = lights.copy()
    features["near_school"] = _near_any(lights, layers.get("schools"), SCHOOL_RADIUS_M)
    features["near_transit"] = _near_any(lights, layers.get("transit"), TRANSIT_RADIUS_M)
    features["age_days"] = (as_of - lights["first_reported"]).dt.days
    features["neighbours_dark"] = _neighbours_dark(lights)
    return features
