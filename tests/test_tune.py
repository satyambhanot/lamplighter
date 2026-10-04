"""Tests for engine.tune.random_search() — small trial counts only;
the real 200-trial search is run via `make results`, not in CI.

Always pass log_path=tmp_path/... — the default log_path is the real
committed results/tuning_log.csv, and a 3-trial test run must never
overwrite that 200-trial file.
"""

from config import WEEKLY_CREW_MINUTES
from engine.data import load_tickets
from engine.tune import WEIGHT_MAX, WEIGHT_NAMES, random_search


def test_random_search_returns_valid_weights(tmp_path) -> None:
    tickets = load_tickets()
    log_path = tmp_path / "tuning_log.csv"
    weights = random_search(tickets, {}, WEEKLY_CREW_MINUTES, n_trials=3, seed=1, log_path=log_path)

    assert set(weights.keys()) == set(WEIGHT_NAMES)
    assert all(0 <= v <= WEIGHT_MAX for v in weights.values())
    assert log_path.exists()


def test_random_search_deterministic_with_seed(tmp_path) -> None:
    tickets = load_tickets()
    weights_a = random_search(
        tickets, {}, WEEKLY_CREW_MINUTES, n_trials=3, seed=7, log_path=tmp_path / "a.csv"
    )
    weights_b = random_search(
        tickets, {}, WEEKLY_CREW_MINUTES, n_trials=3, seed=7, log_path=tmp_path / "b.csv"
    )

    assert weights_a == weights_b


def test_random_search_does_not_touch_real_tuning_log(tmp_path) -> None:
    from config import TUNING_LOG_CSV

    before = TUNING_LOG_CSV.read_bytes() if TUNING_LOG_CSV.exists() else None
    tickets = load_tickets()
    random_search(tickets, {}, WEEKLY_CREW_MINUTES, n_trials=2, seed=3, log_path=tmp_path / "scratch.csv")
    after = TUNING_LOG_CSV.read_bytes() if TUNING_LOG_CSV.exists() else None

    assert before == after
