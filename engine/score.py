"""Policy scoring: the one score() function used by the replay, the API,
and the dashboard alike.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from engine.features import build_features


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
    age_weeks = features["age_days"] / 7.0
    repeat_calls = (features["call_count"] - 1).clip(lower=0)
    return (
        weights["w_age"] * age_weeks
        + weights["w_damage"] * features["is_damage"].astype(float)
        + weights["w_school"] * features["near_school"].astype(float)
        + weights["w_transit"] * features["near_transit"].astype(float)
        + weights["w_repeat"] * repeat_calls
        + weights["w_cluster"] * features["neighbours_dark"]
    ).rename("score")


def reasons(features: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Human-readable rank explanation per light, e.g. "damage ticket,
    near a school, 3 calls".

    Used by the dashboard list and by the voice agent's status replies.
    """

    def _reason_for(row: pd.Series) -> str:
        parts = []
        if row["is_damage"]:
            parts.append("damage ticket")
        if row["near_school"]:
            parts.append("near a school")
        if row["near_transit"]:
            parts.append("near transit")
        if row["call_count"] > 1:
            parts.append(f"{int(row['call_count'])} calls")
        if row["neighbours_dark"] > 0:
            parts.append(f"{int(row['neighbours_dark'])} nearby dark lights")
        parts.append(f"{row['age_days'] / 7.0:.1f} weeks old")
        return ", ".join(parts)

    return features.apply(_reason_for, axis=1).rename("reasons")


def make_score_policy(
    layers: dict[str, pd.DataFrame],
    weights: dict[str, float],
) -> Callable[[pd.DataFrame, pd.Timestamp], list[str]]:
    """Build a Policy (see engine.simulate.Policy) that ranks the open
    queue by score(), highest first. Used for both the v1 hand-set
    policy and the tuned policy — same scoring, different weights.
    """

    def policy(queue: pd.DataFrame, as_of: pd.Timestamp) -> list[str]:
        features = build_features(queue, layers, as_of)
        return score(features, weights).sort_values(ascending=False).index.tolist()

    return policy
