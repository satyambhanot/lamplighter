"""Tests for engine.tune.random_search() — small trial counts only;
the real 200-trial search is run via `make results`, not in CI.
"""

from config import WEEKLY_CREW_MINUTES
from engine.data import load_tickets
from engine.tune import WEIGHT_MAX, WEIGHT_NAMES, random_search


def test_random_search_returns_valid_weights() -> None:
    tickets = load_tickets()
    weights = random_search(tickets, {}, WEEKLY_CREW_MINUTES, n_trials=3, seed=1)

    assert set(weights.keys()) == set(WEIGHT_NAMES)
    assert all(0 <= v <= WEIGHT_MAX for v in weights.values())


def test_random_search_deterministic_with_seed() -> None:
    tickets = load_tickets()
    weights_a = random_search(tickets, {}, WEEKLY_CREW_MINUTES, n_trials=3, seed=7)
    weights_b = random_search(tickets, {}, WEEKLY_CREW_MINUTES, n_trials=3, seed=7)

    assert weights_a == weights_b
