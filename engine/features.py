"""Per-light features used by score(): school, transit, calls, cluster.

Implemented in Phase 3.
"""

from __future__ import annotations

import pandas as pd


def build_features(lights: pd.DataFrame, layers: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compute scoring features for each open light.

    Adds ``near_school`` (within SCHOOL_RADIUS_M), ``near_transit``
    (within TRANSIT_RADIUS_M), ``call_count``, ``is_damage``,
    ``age_days``, and ``neighbours_dark`` (other unfixed lights within
    CLUSTER_RADIUS_M).

    Args:
        lights: Open lights (one row per light, not per raw ticket).
        layers: External layers, e.g. {"schools": df, "transit": df}.

    Returns:
        ``lights`` with the feature columns appended.
    """
    raise NotImplementedError("Phase 3")
