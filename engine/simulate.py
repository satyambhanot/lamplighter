"""Week-by-week historical replay and the metrics suite."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

from config import (
    DEMO_DATE,
    DUPLICATE_RADIUS_M,
    RISK_WEIGHT_BASE,
    RISK_WEIGHT_DAMAGE,
    RISK_WEIGHT_PER_EXTRA_CALL,
    RISK_WEIGHT_PER_EXTRA_CALL_MAX,
    RISK_WEIGHT_SCHOOL,
    RISK_WEIGHT_TRANSIT,
    SCHOOL_RADIUS_M,
    TRANSIT_RADIUS_M,
)
from engine.geo import build_ball_tree, query_radius
from engine.plan import plan_week, route_minutes

logger = logging.getLogger(__name__)

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
            Fact-aware: a later report can't retroactively inflate the
            risk already accrued by earlier days — see
            risk_weighted_days().
        fixes_per_crew_hour: lights_fixed / (crew minutes used / 60).
        median_days_dark: Median days-to-fix across fixed lights.
        still_dark_at_end: Lights never fixed by the end of the full
            replay — always whole-run, regardless of ``window``; there's
            one replay, so this isn't "still dark at window end."
        dark_nights_by_community: Risk-weighted dark nights per comm_name.
        fixed_by_community: Count of lights fixed per comm_name (within
            ``window`` if given) — used by the crew-cut comparison.
        weekly_log: One row per simulated week (for debugging/plots).
        snapshot_queue: The open queue as merged as of ``snapshot_at``
            (before that week's plan runs), if requested — None
            otherwise. Used by engine.live.demo_queue() to build a
            realistic demo state without re-deriving replay logic.
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
    snapshot_queue: pd.DataFrame | None = field(default=None)


def fifo_policy(queue: pd.DataFrame, as_of: pd.Timestamp | None = None) -> list[str]:
    """Oldest-first baseline: rank by first_reported ascending.
    as_of is unused — FIFO doesn't need the current date.
    """
    return queue.sort_values("first_reported").index.tolist()


def _week_start(ts: pd.Timestamp) -> pd.Timestamp:
    """Monday on or before ts."""
    ts = ts.normalize()
    return ts - pd.Timedelta(days=ts.weekday())


def risk_weight(row: pd.Series) -> float:
    """config.RISK_WEIGHT_* combined for one light (see CLAUDE.md's
    "Risk weight per dark night" row). ``row`` needs is_damage and
    call_count; near_school/near_transit default to False if absent.
    Public — engine/live.py reuses this so the live API's metrics can't
    drift from the offline replay's definition.
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


def risk_weighted_days(
    row: pd.Series, resolved: pd.Timestamp, window: tuple[pd.Timestamp, pd.Timestamp]
) -> tuple[int, float]:
    """Days dark and risk-weighted days dark for one light, valuing each
    day by the facts known as of that day rather than the light's
    eventual final state — a July damage report must not retroactively
    inflate the risk already accrued by that light's June days.

    Walks ``row["history"]`` (from _merge_or_create(): a list of
    (date, is_damage, call_count) state changes, earliest first) and
    sums each interval's days-in-window at that interval's own state.
    Total days always equals _days_in_window(row["first_reported"],
    resolved, window) — only the weighting changes.

    Args:
        row: A fixed_df/open_df row — needs history, near_school,
            near_transit.
        resolved: fixed_at for a fixed light, or the replay's end date
            for one still open.
        window: Reporting window, as in simulate().

    Returns:
        (total days dark in window, risk-weighted days dark in window).
    """
    history = row["history"]
    total_days = 0
    weighted = 0.0
    for i, (change_date, is_damage, call_count) in enumerate(history):
        interval_end = history[i + 1][0] if i + 1 < len(history) else resolved
        days = _days_in_window(change_date, interval_end, window)
        if days <= 0:
            continue
        weight = risk_weight(
            {
                "is_damage": is_damage,
                "call_count": call_count,
                "near_school": row["near_school"],
                "near_transit": row["near_transit"],
            }
        )
        total_days += days
        weighted += days * weight
    return total_days, weighted


def _assign_workdays(visit_order: list[str]) -> list[tuple[int, str]]:
    """Split a week's visit order evenly across WORKDAYS_PER_WEEK days."""
    n = len(visit_order)
    return [
        (min(WORKDAYS_PER_WEEK - 1, i * WORKDAYS_PER_WEEK // n), light_id)
        for i, light_id in enumerate(visit_order)
    ]


def _merge_or_create(
    open_lights: dict[str, dict],
    ticket: dict,
    school_tree: object | None = None,
    transit_tree: object | None = None,
) -> None:
    """Merge ``ticket`` into an existing open light within
    DUPLICATE_RADIUS_M, or create a new light keyed by the ticket's id.

    near_school/near_transit are geographic facts about the light's fixed
    location, so they're computed once at creation (school_tree/
    transit_tree let the caller build those BallTrees once per simulate()
    call instead of once per ticket). ``history`` records every
    (date, is_damage, call_count) state change so dark-time accounting
    can value each day by what was actually known that day — see
    risk_weighted_days() — rather than by the light's eventual final
    state, which would let a later report retroactively inflate the risk
    of days that already passed.
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
            light["history"].append((ticket["requested_date"], light["is_damage"], light["call_count"]))
            return

    near_school = bool(
        school_tree is not None
        and len(query_radius(school_tree, ticket["latitude"], ticket["longitude"], SCHOOL_RADIUS_M))
    )
    near_transit = bool(
        transit_tree is not None
        and len(query_radius(transit_tree, ticket["latitude"], ticket["longitude"], TRANSIT_RADIUS_M))
    )
    open_lights[ticket["service_request_id"]] = {
        "latitude": ticket["latitude"],
        "longitude": ticket["longitude"],
        "comm_name": ticket["comm_name"],
        "is_damage": ticket["is_damage"],
        "first_reported": ticket["requested_date"],
        "call_count": 1,
        "near_school": near_school,
        "near_transit": near_transit,
        "history": [(ticket["requested_date"], ticket["is_damage"], 1)],
    }


def build_open_queue(tickets: pd.DataFrame) -> pd.DataFrame:
    """Merge every ticket into its light (within DUPLICATE_RADIUS_M of
    an existing light, else a new one) as a single one-shot pass — the
    queue as if nothing had ever been fixed. simulate()'s weekly loop
    does this incrementally instead (fixing removes lights from the
    pool between merges); this is for one-shot snapshots: examples,
    demos, and anything that doesn't need the week-by-week fix history.
    """
    open_lights: dict[str, dict] = {}
    for ticket in tickets.sort_values("requested_date").to_dict("records"):
        _merge_or_create(open_lights, ticket)
    return (
        pd.DataFrame.from_dict(open_lights, orient="index")
        if open_lights
        else pd.DataFrame(columns=LIGHT_COLUMNS)
    )


def simulate(
    tickets: pd.DataFrame,
    policy: Callable[[pd.DataFrame, pd.Timestamp], list[str]],
    budget_min: int,
    window: tuple[str, str] | None = None,
    snapshot_at: str | None = None,
    layers: dict[str, pd.DataFrame] | None = None,
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
        snapshot_at: Optional ISO date (a Monday); if given, capture the
            merged-but-not-yet-planned open queue for that week into
            RunResult.snapshot_queue.
        layers: School/transit layers (engine.data.load_layers()), used
            to set each light's near_school/near_transit once at
            creation so risk_weighted_days() can account for them. A
            missing layer means every light counts as not-nearby for it
            — logged once, since that silently changes the risk
            objective rather than erroring.

    Returns:
        A RunResult with the full metrics suite.
    """
    tickets = tickets.sort_values("requested_date").reset_index(drop=True)
    ticket_records = tickets.to_dict("records")
    layers = layers or {}
    if "schools" not in layers or "transit" not in layers:
        logger.warning(
            "simulate() called without full layers (schools/transit) — near_school/near_transit will be False for every light, which understates risk-weighted dark nights"
        )
    school_tree = (
        build_ball_tree(layers["schools"])
        if layers.get("schools") is not None and not layers["schools"].empty
        else None
    )
    transit_tree = (
        build_ball_tree(layers["transit"])
        if layers.get("transit") is not None and not layers["transit"].empty
        else None
    )

    first_monday = _week_start(tickets["requested_date"].min())
    last_monday = _week_start(tickets["requested_date"].max()) + pd.Timedelta(weeks=1)
    snapshot_monday = pd.Timestamp(snapshot_at) if snapshot_at else None

    open_lights: dict[str, dict] = {}
    fixed_lights: list[dict] = []
    weekly_log_rows: list[dict] = []
    snapshot_queue: pd.DataFrame | None = None

    ptr = 0
    monday = first_monday
    while monday <= last_monday:
        while ptr < len(ticket_records) and ticket_records[ptr]["requested_date"] < monday:
            _merge_or_create(open_lights, ticket_records[ptr], school_tree, transit_tree)
            ptr += 1

        if snapshot_monday is not None and monday == snapshot_monday:
            snapshot_queue = (
                pd.DataFrame.from_dict(open_lights, orient="index")
                if open_lights
                else pd.DataFrame(columns=LIGHT_COLUMNS)
            )

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
    # run_end_date is the final week's Monday, but fixes that week land
    # on any of its workdays through Friday — a default window that
    # stopped at Monday silently excluded Tue-Fri fixes from
    # fixed_in_window (and therefore fixed_by_community) even on a
    # whole, unwindowed run.
    default_window = (
        tickets["requested_date"].min(),
        run_end_date + pd.Timedelta(days=WORKDAYS_PER_WEEK - 1),
    )
    win = (pd.Timestamp(window[0]), pd.Timestamp(window[1])) if window else default_window

    fixed_df = pd.DataFrame(fixed_lights)
    if not fixed_df.empty:
        fixed_df = fixed_df.set_index("light_id")
    open_df = (
        pd.DataFrame.from_dict(open_lights, orient="index")
        if open_lights
        else pd.DataFrame(columns=LIGHT_COLUMNS)
    )

    total_dark_nights = 0
    risk_weighted_dark_nights = 0.0
    community_rows = []

    for _, row in fixed_df.iterrows():
        days, weighted = risk_weighted_days(row, row["fixed_at"], win)
        total_dark_nights += days
        risk_weighted_dark_nights += weighted
        community_rows.append({"comm_name": row["comm_name"], "weighted_days": weighted})

    for _, row in open_df.iterrows():
        days, weighted = risk_weighted_days(row, run_end_date, win)
        total_dark_nights += days
        risk_weighted_dark_nights += weighted
        community_rows.append({"comm_name": row["comm_name"], "weighted_days": weighted})

    dark_nights_by_community = (
        pd.DataFrame(community_rows).groupby("comm_name")["weighted_days"].sum().sort_values(ascending=False)
        if community_rows
        else pd.Series(dtype=float)
    )

    weekly_log = pd.DataFrame(weekly_log_rows)
    if not fixed_df.empty:
        fixed_in_window = fixed_df[(fixed_df["fixed_at"] >= win[0]) & (fixed_df["fixed_at"] <= win[1])]
    else:
        fixed_in_window = fixed_df

    median_days_dark = (
        float((fixed_in_window["fixed_at"] - fixed_in_window["first_reported"]).dt.days.median())
        if not fixed_in_window.empty
        else float("nan")
    )

    # Crew hours in window: prorate each week's minutes by the fraction
    # of THAT week's fixes that land in-window, not by whether the
    # week's Monday happens to fall in-window — a week starting just
    # before the window still spends some of its minutes on in-window
    # fixes (and vice versa at the far boundary), and a Monday-only test
    # would count those fixes with none, or all, of that week's hours.
    if not fixed_df.empty:
        fixed_df = fixed_df.assign(week_start=fixed_df["fixed_at"].apply(_week_start))
        fixes_per_week_total = fixed_df.groupby("week_start").size()
    else:
        fixes_per_week_total = pd.Series(dtype=int)
    if not fixed_in_window.empty:
        fixes_per_week_in_window = (
            fixed_in_window.assign(week_start=fixed_in_window["fixed_at"].apply(_week_start))
            .groupby("week_start")
            .size()
        )
    else:
        fixes_per_week_in_window = pd.Series(dtype=int)
    minutes_by_week = weekly_log.set_index("week_start")["minutes_used"]

    crew_hours_in_window = 0.0
    for week_start, in_window_count in fixes_per_week_in_window.items():
        total_count = fixes_per_week_total.get(week_start, 0)
        if total_count > 0:
            crew_hours_in_window += (
                minutes_by_week.get(week_start, 0.0) * (in_window_count / total_count) / 60
            )

    fixes_per_crew_hour = (
        len(fixed_in_window) / crew_hours_in_window if crew_hours_in_window > 0 else float("nan")
    )

    fixed_by_community = (
        fixed_in_window.groupby("comm_name").size().sort_values(ascending=False)
        if not fixed_in_window.empty
        else pd.Series(dtype=int)
    )

    return RunResult(
        lights_fixed=len(fixed_in_window) if window else len(fixed_df),
        total_dark_nights=total_dark_nights,
        risk_weighted_dark_nights=risk_weighted_dark_nights,
        fixes_per_crew_hour=fixes_per_crew_hour,
        median_days_dark=median_days_dark,
        # Always the backlog at the end of the FULL replay, regardless
        # of `window` — there's one replay, not a window-scoped one, so
        # this is a whole-run concept, not an in-window one. Don't read
        # it as "still dark at window end."
        still_dark_at_end=len(open_df),
        dark_nights_by_community=dark_nights_by_community,
        fixed_by_community=fixed_by_community,
        weekly_log=weekly_log,
        snapshot_queue=snapshot_queue,
    )


MAX_PROJECTION_WEEKS = 12


def project_fix_dates(
    queue: pd.DataFrame, weights: dict[str, float], budget_min: int, *, as_of: pd.Timestamp | None = None
) -> dict[str, str]:
    """Estimate each queued light's fix date from its rank and weekly
    crew capacity. Used by /report and /status.

    queue must already carry a ``rank`` or ``score`` column — ``weights``
    isn't re-applied here, it's just documenting which weights produced
    that ranking. ``rank`` (ascending, 1 = first) wins if both are
    present, since it reflects the actual policy decision (e.g. FIFO's
    order isn't a sort-by-score); fall back to ``score`` (descending)
    otherwise. Projects from the planning Monday on or after ``as_of``
    (defaults to config.DEMO_DATE). Reports arriving on that Monday
    become eligible the following week. Capped at
    MAX_PROJECTION_WEEKS (12) out — lights beyond that horizon get no
    date rather than an unreliable guess.

    Args:
        queue: Open lights, already featured and ranked (via ``rank``
            or ``score``).
        weights: Policy weights that produced ``queue``'s ranking
            (unused directly; ranking already reflects them).
        budget_min: Weekly crew minutes.
        as_of: The date of the queue snapshot, used as the projection origin.

    Returns:
        Mapping of light id to an ISO date string (only for lights fixed
        within MAX_PROJECTION_WEEKS; lights beyond that are omitted).
    """
    if queue.empty:
        return {}

    if "rank" in queue.columns and queue["rank"].notna().any():
        remaining = queue.sort_values("rank").index.tolist()
    elif "score" in queue.columns:
        remaining = queue.sort_values("score", ascending=False).index.tolist()
    else:
        remaining = queue.index.tolist()
    dates: dict[str, str] = {}
    as_of = pd.Timestamp(as_of if as_of is not None else DEMO_DATE).normalize()
    monday = _week_start(as_of)
    if monday < as_of:
        monday += pd.Timedelta(weeks=1)

    for _ in range(MAX_PROJECTION_WEEKS):
        if not remaining:
            break
        eligible = [
            light_id for light_id in remaining if pd.Timestamp(queue.loc[light_id, "first_reported"]) < monday
        ]
        selected = plan_week(queue, eligible, budget_min)
        if not selected and eligible and len(eligible) == len(remaining):
            break
        for day_offset, light_id in _assign_workdays(selected):
            dates[light_id] = (monday + pd.Timedelta(days=day_offset)).date().isoformat()
        selected_set = set(selected)
        remaining = [light_id for light_id in remaining if light_id not in selected_set]
        monday += pd.Timedelta(weeks=1)

    return dates
