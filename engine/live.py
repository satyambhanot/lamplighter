"""The only engine module api/ is allowed to import from.

Keeps the live API's scoring identical to the offline replay's — same
build_features()/score()/plan_week()/project_fix_dates() calls — without
the API reaching into engine/ internals directly. Also keeps the DB
schema free of derived-feature columns (CLAUDE.md: "the database stores
facts and decisions; the engine owns the features" — near_school,
near_transit, age_days, and neighbours_dark are never stored, always
recomputed here on every re-rank).
"""

from __future__ import annotations

import json
import logging

import pandas as pd

from config import DEFAULT_POLICY_WEIGHTS, WEEKLY_CREW_MINUTES, WEIGHTS_JSON
from engine.data import load_layers, load_tickets
from engine.features import build_features
from engine.geo import build_ball_tree, query_radius
from engine.note import dispatcher_note
from engine.plan import plan_week, route_minutes
from engine.score import make_score_policy
from engine.score import reasons as compute_reasons
from engine.score import score as compute_score
from engine.simulate import LIGHT_COLUMNS, fifo_policy, project_fix_dates, simulate

logger = logging.getLogger(__name__)

LIVE_POLICIES = ("fifo", "v1", "tuned")

RERANK_OUTPUT_COLUMNS = [
    *LIGHT_COLUMNS,
    "near_school",
    "near_transit",
    "age_days",
    "neighbours_dark",
    "score",
    "rank",
    "reasons",
    "expected_fix_date",
]


def nearest_light(lights: pd.DataFrame, lat: float, lon: float, radius_m: float) -> str | None:
    """Return the nearest open light within the shared haversine radius."""
    if lights.empty:
        return None
    hits = query_radius(build_ball_tree(lights), lat, lon, radius_m)
    return str(lights.index[hits[0]]) if len(hits) else None


def load_tuned_weights() -> dict[str, float]:
    """results/weights.json, else config.DEFAULT_POLICY_WEIGHTS."""
    if WEIGHTS_JSON.exists():
        return json.loads(WEIGHTS_JSON.read_text())
    logger.warning(
        "%s not found; falling back to DEFAULT_POLICY_WEIGHTS (run `make results` to tune)", WEIGHTS_JSON
    )
    return dict(DEFAULT_POLICY_WEIGHTS)


def load_live_layers() -> dict[str, pd.DataFrame]:
    """School and transit layers — load once at API startup, reuse
    across requests.
    """
    return load_layers()


def _empty_rerank_result(lights: pd.DataFrame) -> pd.DataFrame:
    extra = {col: pd.Series(dtype=object) for col in RERANK_OUTPUT_COLUMNS if col not in lights.columns}
    return lights.assign(**extra)


def rerank(
    lights: pd.DataFrame,
    layers: dict[str, pd.DataFrame],
    weights: dict[str, float],
    budget_min: int,
    as_of: pd.Timestamp,
) -> pd.DataFrame:
    """Featurize, score, and rank every open light — the single scoring
    path the live API uses (always with the tuned weights in practice;
    what_if() is the only caller that scores with other weights).

    Args:
        lights: index = light id; columns latitude, longitude, comm_name,
            is_damage (bool), first_reported (Timestamp), call_count (int).
        layers: From load_live_layers().
        weights: From load_tuned_weights(), or another weights dict.
        budget_min: Weekly crew minutes, for expected_fix_date.
        as_of: The frozen "now" for age/score — config.DEMO_DATE for the
            live demo.

    Returns:
        ``lights`` plus near_school, near_transit, age_days,
        neighbours_dark, score, reasons, expected_fix_date, sorted by
        rank (1 = fixed next). Empty in, empty out.
    """
    if lights.empty:
        return _empty_rerank_result(lights)

    features = build_features(lights, layers, as_of)
    features["score"] = compute_score(features, weights)
    features["reasons"] = compute_reasons(features, weights)
    features = features.sort_values("score", ascending=False)
    features["rank"] = range(1, len(features) + 1)

    fix_dates = project_fix_dates(features, weights, budget_min, as_of=as_of)
    features["expected_fix_date"] = [fix_dates.get(light_id) for light_id in features.index]
    return features


def what_if(
    lights: pd.DataFrame,
    layers: dict[str, pd.DataFrame],
    policy: str,
    budget_pct: float,
    as_of: pd.Timestamp,
    *,
    use_llm: bool = True,
) -> dict:
    """A what-if plan for the dashboard's policy/budget controls —
    read-only, never touches the database.

    Args:
        lights: Same shape as rerank()'s input — the current open queue.
        layers: From load_live_layers().
        policy: One of LIVE_POLICIES ("fifo", "v1", "tuned").
        budget_pct: Fraction of WEEKLY_CREW_MINUTES to plan against.
        as_of: The frozen "now".

    Returns:
        {"planned": DataFrame (rerank()'s output columns, in visit
         order), "skipped": DataFrame (same columns, by rank),
         "minutes_used": float, "note": str (dispatcher note)}.
    """
    if policy not in LIVE_POLICIES:
        raise ValueError(f"unknown policy: {policy!r} (expected one of {LIVE_POLICIES})")

    weights = load_tuned_weights() if policy == "tuned" else dict(DEFAULT_POLICY_WEIGHTS)
    budget_min = round(WEEKLY_CREW_MINUTES * budget_pct)

    if lights.empty:
        empty = _empty_rerank_result(lights)
        return {
            "planned": empty,
            "skipped": empty,
            "minutes_used": 0.0,
            "note": dispatcher_note(empty, empty, use_llm=use_llm),
        }

    features = build_features(lights, layers, as_of)
    features["score"] = compute_score(features, weights)
    features["reasons"] = compute_reasons(features, weights)

    # FIFO's order isn't a score sort — rank from the policy's actual
    # decision, not from the (still-computed, informational) score.
    order = (
        fifo_policy(lights, as_of)
        if policy == "fifo"
        else features.sort_values("score", ascending=False).index.tolist()
    )
    rank_position = {light_id: i + 1 for i, light_id in enumerate(order)}
    features["rank"] = features.index.map(rank_position)
    features = features.sort_values("rank")

    fix_dates = project_fix_dates(features, weights, budget_min, as_of=as_of)
    features["expected_fix_date"] = [fix_dates.get(light_id) for light_id in features.index]

    # Reports received on this planning Monday enter the following week's
    # route, matching the weekly replay and the projected repair dates.
    planning_monday = as_of.normalize() + pd.Timedelta(days=(7 - as_of.weekday()) % 7)
    eligible = [lid for lid in order if features.loc[lid, "first_reported"] < planning_monday]
    selected = plan_week(features, eligible, budget_min)
    minutes_used = route_minutes(features, selected)

    planned = features.loc[selected]  # .loc with a list preserves that list's (visit) order
    skipped_ids = [light_id for light_id in features.index if light_id not in set(selected)]
    skipped = features.loc[skipped_ids]

    crew_cut_pct = budget_pct if budget_pct < 1.0 else None
    note = dispatcher_note(planned, skipped, crew_cut_pct, use_llm=use_llm)

    return {"planned": planned, "skipped": skipped, "minutes_used": minutes_used, "note": note}


def demo_queue(as_of: str) -> pd.DataFrame:
    """The open queue at ``as_of``, from a tuned-policy historical
    replay — a realistic mid-run snapshot (tens of lights), not
    engine.simulate.build_open_queue()'s cold-start "nothing was ever
    fixed" snapshot (hundreds of lights, unrepresentative of a live
    demo state).

    Args:
        as_of: ISO date string (a Monday) — config.DEMO_DATE for the
            live demo.

    Returns:
        Same input columns as rerank() expects (not yet featured/scored).
    """
    tickets = load_tickets()
    layers = load_live_layers()
    weights = load_tuned_weights()
    policy = make_score_policy(layers, weights)

    result = simulate(tickets, policy, WEEKLY_CREW_MINUTES, snapshot_at=as_of, layers=layers)
    if result.snapshot_queue is None:
        logger.warning("No snapshot queue captured at %s; returning an empty queue", as_of)
        return pd.DataFrame(columns=LIGHT_COLUMNS)
    return result.snapshot_queue
