"""Week-by-week historical replay and the metrics suite."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from config import (
    DUPLICATE_RADIUS_M,
    RISK_WEIGHT_BASE,
    RISK_WEIGHT_DAMAGE,
    RISK_WEIGHT_PER_EXTRA_CALL,
    RISK_WEIGHT_PER_EXTRA_CALL_MAX,
    RISK_WEIGHT_SCHOOL,
    RISK_WEIGHT_TRANSIT,
)
from engine.geo import build_ball_tree, query_radius
from engine.plan import plan_week, route_minutes

LIGHT_COLUMNS = ["latitude", "longitude", "comm_name", "is_damage", "first_reported", "call_count"]
WORKDAYS_PER_WEEK = 5


class Policy(Protocol):
    """A policy takes the open queue plus the current simulated date and
    returns an ordered list of light ids (best first). ``as_of`` is
    needed for age-based scoring; fifo_policy ignores it.
    """

    def __call__(self, queue: pd.DataFrame, as_of: pd.Timestamp) -> list[str]: ...


@dataclass
class RunResult:
    """Metrics and per-week detail from one simulate() run.

    Attributes:
        lights_fixed: Lights fixed over the run (within ``window`` if given).
        total_dark_nights: Unweighted sum of days each light was dark.
        risk_weighted_dark_nights: Main metric; see config.RISK_WEIGHT_*.
        fixes_per_crew_hour: lights_fixed / (crew minutes used / 60).
        median_days_dark: Median days-to-fix across fixed lights.
        still_dark_at_end: Lights never fixed by the end of the run.
        dark_nights_by_community: Risk-weighted dark nights per comm_name.
        fixed_by_community: Count of lights fixed per comm_name (within
            ``window`` if given) — used by the crew-cut comparison.
        weekly_log: One row per simulated week (for debugging/plots).
    """

    lights_fixed: int
    total_dark_nights: int
    risk_weighted_dark_nights: float
    fixes_per_crew_hour: float
    median_days_dark: float
    still_dark_at_end: int
    dark_nights_by_community: pd.Series
    fixed_by_community: pd.Series
    weekly_log: pd.DataFrame


def fifo_policy(queue: pd.DataFrame, as_of: pd.Timestamp | None = None) -> list[str]:
    """Oldest-first baseline: rank by first_reported ascending.
    as_of is unused — FIFO doesn't need the current date.
    """
    return queue.sort_values("first_reported").index.tolist()


def _week_start(ts: pd.Timestamp) -> pd.Timestamp:
    """Monday on or before ts."""
    ts = ts.normalize()
    return ts - pd.Timedelta(days=ts.weekday())


def _risk_weight(row: pd.Series) -> float:
    """config.RISK_WEIGHT_* combined for one light. near_school/near_transit
    default to False until engine/features.py (Phase 3) fills them in.
    """
    weight = RISK_WEIGHT_BASE
    if row["is_damage"]:
        weight += RISK_WEIGHT_DAMAGE
    if row.get("near_school", False):
        weight += RISK_WEIGHT_SCHOOL
    if row.get("near_transit", False):
        weight += RISK_WEIGHT_TRANSIT
    weight += min(
        RISK_WEIGHT_PER_EXTRA_CALL * max(row["call_count"] - 1, 0),
        RISK_WEIGHT_PER_EXTRA_CALL_MAX,
    )
    return weight


def _days_in_window(start: pd.Timestamp, end: pd.Timestamp, window: tuple[pd.Timestamp, pd.Timestamp]) -> int:
    """Days of overlap between [start, end] and the reporting window."""
    lo = max(start, window[0])
    hi = min(end, window[1])
    return max((hi - lo).days, 0)


def _assign_workdays(visit_order: list[str]) -> list[tuple[int, str]]:
    """Split a week's visit order evenly across WORKDAYS_PER_WEEK days."""
    n = len(visit_order)
    return [(min(WORKDAYS_PER_WEEK - 1, i * WORKDAYS_PER_WEEK // n), light_id) for i, light_id in enumerate(visit_order)]


def _merge_or_create(open_lights: dict[str, dict], ticket: dict) -> None:
    """Merge ``ticket`` into an existing open light within
    DUPLICATE_RADIUS_M, or create a new light keyed by the ticket's id.
    """
    if open_lights:
        light_ids = list(open_lights.keys())
        coords = pd.DataFrame(
            {
                "latitude": [open_lights[lid]["latitude"] for lid in light_ids],
                "longitude": [open_lights[lid]["longitude"] for lid in light_ids],
            },
            index=light_ids,
        )
        tree = build_ball_tree(coords)
        nearby = query_radius(tree, ticket["latitude"], ticket["longitude"], DUPLICATE_RADIUS_M)
        if len(nearby):
            light = open_lights[light_ids[nearby[0]]]
            light["call_count"] += 1
            light["is_damage"] = light["is_damage"] or ticket["is_damage"]
            return

    open_lights[ticket["service_request_id"]] = {
        "latitude": ticket["latitude"],
        "longitude": ticket["longitude"],
        "comm_name": ticket["comm_name"],
        "is_damage": ticket["is_damage"],
        "first_reported": ticket["requested_date"],
        "call_count": 1,
    }


def simulate(
    tickets: pd.DataFrame,
    policy: Callable[[pd.DataFrame, pd.Timestamp], list[str]],
    budget_min: int,
    window: tuple[str, str] | None = None,
) -> RunResult:
    """Replay the full ticket history week by week under one policy.

    Every Monday, tickets reported during the prior calendar week merge
    into the open queue (within DUPLICATE_RADIUS_M of an existing
    unfixed light, or as a new light). The policy ranks the queue,
    plan_week() picks this week's route under budget_min, and fixed
    lights leave the queue, distributed across the week's workdays by
    visit order.

    Args:
        tickets: Output of load_tickets().
        policy: FIFO, v1, or tuned — see engine/score.py for v1/tuned.
        budget_min: Weekly crew minutes.
        window: Optional (start_date, end_date) to restrict metrics
            reporting to (e.g. the Jul-Aug test window), without
            changing the replay itself.

    Returns:
        A RunResult with the full metrics suite.
    """
    tickets = tickets.sort_values("requested_date").reset_index(drop=True)
    ticket_records = tickets.to_dict("records")

    first_monday = _week_start(tickets["requested_date"].min())
    last_monday = _week_start(tickets["requested_date"].max()) + pd.Timedelta(weeks=1)

    open_lights: dict[str, dict] = {}
    fixed_lights: list[dict] = []
    weekly_log_rows: list[dict] = []

    ptr = 0
    monday = first_monday
    while monday <= last_monday:
        while ptr < len(ticket_records) and ticket_records[ptr]["requested_date"] < monday:
            _merge_or_create(open_lights, ticket_records[ptr])
            ptr += 1

        queue_size_before = len(open_lights)
        if open_lights:
            queue_df = pd.DataFrame.from_dict(open_lights, orient="index")
            order = policy(queue_df, monday)
            selected = plan_week(queue_df, order, budget_min)
            minutes_used = route_minutes(queue_df, selected)
        else:
            selected = []
            minutes_used = 0.0

        for day_offset, light_id in _assign_workdays(selected):
            light = open_lights.pop(light_id)
            light["light_id"] = light_id
            light["fixed_at"] = monday + pd.Timedelta(days=day_offset)
            fixed_lights.append(light)

        weekly_log_rows.append(
            {
                "week_start": monday,
                "queue_size_before_plan": queue_size_before,
                "lights_fixed": len(selected),
                "minutes_used": minutes_used,
            }
        )
        monday += pd.Timedelta(weeks=1)

    run_end_date = last_monday
    default_window = (tickets["requested_date"].min(), run_end_date)
    win = (pd.Timestamp(window[0]), pd.Timestamp(window[1])) if window else default_window

    fixed_df = pd.DataFrame(fixed_lights)
    if not fixed_df.empty:
        fixed_df = fixed_df.set_index("light_id")
    open_df = pd.DataFrame.from_dict(open_lights, orient="index") if open_lights else pd.DataFrame(columns=LIGHT_COLUMNS)

    total_dark_nights = 0
    risk_weighted_dark_nights = 0.0
    community_rows = []

    for _, row in fixed_df.iterrows():
        days = _days_in_window(row["first_reported"], row["fixed_at"], win)
        weight = _risk_weight(row)
        total_dark_nights += days
        risk_weighted_dark_nights += days * weight
        community_rows.append({"comm_name": row["comm_name"], "weighted_days": days * weight})

    for _, row in open_df.iterrows():
        days = _days_in_window(row["first_reported"], run_end_date, win)
        weight = _risk_weight(row)
        total_dark_nights += days
        risk_weighted_dark_nights += days * weight
        community_rows.append({"comm_name": row["comm_name"], "weighted_days": days * weight})

    dark_nights_by_community = (
        pd.DataFrame(community_rows).groupby("comm_name")["weighted_days"].sum().sort_values(ascending=False)
        if community_rows
        else pd.Series(dtype=float)
    )

    median_days_dark = (
        float((fixed_df["fixed_at"] - fixed_df["first_reported"]).dt.days.median()) if not fixed_df.empty else float("nan")
    )

    weekly_log = pd.DataFrame(weekly_log_rows)
    if not fixed_df.empty:
        fixed_in_window = fixed_df[(fixed_df["fixed_at"] >= win[0]) & (fixed_df["fixed_at"] <= win[1])]
    else:
        fixed_in_window = fixed_df
    weeks_in_window = weekly_log[(weekly_log["week_start"] >= win[0]) & (weekly_log["week_start"] <= win[1])]
    crew_hours_in_window = weeks_in_window["minutes_used"].sum() / 60
    fixes_per_crew_hour = len(fixed_in_window) / crew_hours_in_window if crew_hours_in_window > 0 else float("nan")

    fixed_by_community = (
        fixed_in_window.groupby("comm_name").size().sort_values(ascending=False) if not fixed_in_window.empty else pd.Series(dtype=int)
    )

    return RunResult(
        lights_fixed=len(fixed_in_window) if window else len(fixed_df),
        total_dark_nights=total_dark_nights,
        risk_weighted_dark_nights=risk_weighted_dark_nights,
        fixes_per_crew_hour=fixes_per_crew_hour,
        median_days_dark=median_days_dark,
        still_dark_at_end=len(open_df),
        dark_nights_by_community=dark_nights_by_community,
        fixed_by_community=fixed_by_community,
        weekly_log=weekly_log,
    )


def project_fix_dates(queue: pd.DataFrame, weights: dict[str, float], budget_min: int) -> dict[str, str]:
    """Estimate each queued light's fix date from its rank and weekly
    crew capacity. Used by /report and /status.

    Args:
        queue: Open lights, already featured and scored.
        weights: Policy weights to rank by.
        budget_min: Weekly crew minutes.

    Returns:
        Mapping of light id to an ISO date string.
    """
    raise NotImplementedError("Phase 6")
