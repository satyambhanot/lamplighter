"""Tests for engine.simulate — the FIFO baseline over the real seed data."""

import pandas as pd

from config import WEEKLY_CREW_MINUTES
from engine.data import load_layers, load_tickets
from engine.simulate import fifo_policy, risk_weighted_days, simulate


def test_fifo_simulate_sane_metrics() -> None:
    tickets = load_tickets()
    layers = load_layers()
    result = simulate(tickets, fifo_policy, WEEKLY_CREW_MINUTES, layers=layers)

    assert result.lights_fixed > 0
    assert result.still_dark_at_end >= 0
    assert result.total_dark_nights > 0
    assert result.risk_weighted_dark_nights >= result.total_dark_nights
    assert result.fixes_per_crew_hour > 0
    assert not result.dark_nights_by_community.empty
    assert len(result.weekly_log) > 0


def test_fifo_simulate_conserves_lights() -> None:
    tickets = load_tickets()
    layers = load_layers()
    result = simulate(tickets, fifo_policy, WEEKLY_CREW_MINUTES, layers=layers)

    total_fixed_over_run = result.weekly_log["lights_fixed"].sum()
    assert total_fixed_over_run == result.lights_fixed
    # Every fix recorded in the weekly log must land in exactly one
    # community in the breakdown — none silently dropped or duplicated.
    assert int(result.fixed_by_community.sum()) == result.lights_fixed


def test_fifo_simulate_without_layers_warns_but_runs(caplog) -> None:
    tickets = load_tickets()
    result = simulate(tickets, fifo_policy, WEEKLY_CREW_MINUTES)
    assert result.lights_fixed > 0
    assert "without full layers" in caplog.text


def test_school_transit_risk_reaches_the_metric() -> None:
    """Regression test for CODE_REVIEW.md finding #1: near_school/
    near_transit were computed for ranking only and never reached
    risk_weighted_dark_nights. With real layers, some lights are near a
    school or transit stop and must contribute their extra risk weight.
    """
    tickets = load_tickets()
    layers = load_layers()
    with_layers = simulate(tickets, fifo_policy, WEEKLY_CREW_MINUTES, layers=layers)
    without_layers = simulate(tickets, fifo_policy, WEEKLY_CREW_MINUTES)

    # Same policy, same data: total dark-night days must be identical —
    # only the risk weighting should differ once geography counts.
    assert with_layers.total_dark_nights == without_layers.total_dark_nights
    assert with_layers.risk_weighted_dark_nights > without_layers.risk_weighted_dark_nights


def test_future_report_does_not_inflate_past_risk() -> None:
    """Regression test for CODE_REVIEW.md finding #2: a light reported
    June 1 (routine) that later gets a damage report on July 1 must
    still be valued at the routine weight for its June days — a later
    report can't retroactively inflate risk already accrued.
    """
    window = (pd.Timestamp("2026-06-01"), pd.Timestamp("2026-08-01"))
    row = pd.Series(
        {
            "first_reported": pd.Timestamp("2026-06-01"),
            "near_school": False,
            "near_transit": False,
            "history": [
                (pd.Timestamp("2026-06-01"), False, 1),  # routine report
                (pd.Timestamp("2026-07-01"), True, 2),  # later damage report
            ],
        }
    )
    resolved = pd.Timestamp("2026-07-15")
    days, weighted = risk_weighted_days(row, resolved, window)

    june_days = 30  # Jun 1 - Jul 1
    july_days = 14  # Jul 1 - Jul 15
    assert days == june_days + july_days
    # June days: base weight 1.0 (routine). July days: base 1.0 + damage
    # 1.0 + one extra call 0.25 = 2.25.
    expected = june_days * 1.0 + july_days * 2.25
    assert weighted == expected
