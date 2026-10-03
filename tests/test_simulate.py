"""Tests for engine.simulate — the FIFO baseline over the real seed data."""

from config import WEEKLY_CREW_MINUTES
from engine.data import load_tickets
from engine.simulate import fifo_policy, simulate


def test_fifo_simulate_sane_metrics() -> None:
    tickets = load_tickets()
    result = simulate(tickets, fifo_policy, WEEKLY_CREW_MINUTES)

    assert result.lights_fixed > 0
    assert result.still_dark_at_end >= 0
    assert result.total_dark_nights > 0
    assert result.risk_weighted_dark_nights >= result.total_dark_nights
    assert result.fixes_per_crew_hour > 0
    assert not result.dark_nights_by_community.empty
    assert len(result.weekly_log) > 0


def test_fifo_simulate_conserves_lights() -> None:
    tickets = load_tickets()
    result = simulate(tickets, fifo_policy, WEEKLY_CREW_MINUTES)

    total_fixed_over_run = result.weekly_log["lights_fixed"].sum()
    assert total_fixed_over_run == result.lights_fixed
