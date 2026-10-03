"""Policy scoring: the one score() function used by the replay, the API,
and the dashboard alike.

Implemented in Phase 3.
"""

from __future__ import annotations

import pandas as pd


def score(features: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Rank open lights by policy score (higher = fix sooner).

    score = w_age*age_weeks + w_damage*is_damage + w_school*near_school
          + w_transit*near_transit + w_repeat*(call_count - 1)
          + w_cluster*neighbours_dark

    Args:
        features: Output of build_features(), one row per open light.
        weights: Policy weights (FIFO doesn't call this; v1/tuned do).

    Returns:
        A Series of scores aligned to ``features``' index.
    """
    raise NotImplementedError("Phase 3")


def reasons(features: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Human-readable rank explanation per light, e.g. "damage ticket,
    near a school, 3 calls".

    Used by the dashboard list and by the voice agent's status replies.
    """
    raise NotImplementedError("Phase 3")
