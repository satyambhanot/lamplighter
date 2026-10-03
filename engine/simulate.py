"""Week-by-week historical replay and the metrics suite.

Implemented in Phase 2 (FIFO baseline), extended in later phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

import pandas as pd


class Policy(Protocol):
    """A policy takes the open queue and returns an ordered list of light ids."""

    def __call__(self, queue: pd.DataFrame) -> list[str]: ...


@dataclass
class RunResult:
    """Metrics and per-week detail from one simulate() run.

    Attributes:
        lights_fixed: Total lights fixed over the run.
        total_dark_nights: Unweighted sum of days each light was dark.
        risk_weighted_dark_nights: Main metric; see config.RISK_WEIGHT_*.
        fixes_per_crew_hour: lights_fixed / (crew minutes used / 60).
        median_days_dark: Median days-to-fix across fixed lights.
        still_dark_at_end: Lights never fixed by the end of the run.
        dark_nights_by_community: Risk-weighted dark nights per comm_name.
        weekly_log: One row per simulated week (for debugging/plots).
    """

    lights_fixed: int
    total_dark_nights: int
    risk_weighted_dark_nights: float
    fixes_per_crew_hour: float
    median_days_dark: float
    still_dark_at_end: int
    dark_nights_by_community: pd.Series
    weekly_log: pd.DataFrame


def simulate(
    tickets: pd.DataFrame,
    policy: Callable[[pd.DataFrame], list[str]],
    budget_min: int,
    window: tuple[str, str] | None = None,
) -> RunResult:
    """Replay the full ticket history week by week under one policy.

    Each week: new tickets join the queue (merging into any unfixed
    light within DUPLICATE_RADIUS_M), the policy ranks the queue,
    plan_week() picks this week's route under budget_min, and fixed
    lights leave the queue.

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
    raise NotImplementedError("Phase 2")


def fifo_policy(queue: pd.DataFrame) -> list[str]:
    """Oldest-first baseline: rank by first_reported ascending."""
    raise NotImplementedError("Phase 2")


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
