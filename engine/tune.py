"""Self-tuning: random search over policy weights.

200 trials, seed 42 (config.TUNING_TRIALS / TUNING_SEED). Trials are
scored on the Mar-Jun tuning window only (config.TUNE_START/TUNE_END);
Jul-Aug is held out for reporting.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from config import TUNE_END, TUNE_START, TUNING_LOG_CSV
from engine.score import make_score_policy
from engine.simulate import simulate

logger = logging.getLogger(__name__)

WEIGHT_NAMES = ["w_age", "w_damage", "w_school", "w_transit", "w_repeat", "w_cluster"]
WEIGHT_MAX = 2.0


def random_search(
    tickets: pd.DataFrame,
    layers: dict[str, pd.DataFrame],
    budget_min: int,
    n_trials: int,
    seed: int,
    log_path: Path = TUNING_LOG_CSV,
) -> dict[str, float]:
    """Search policy weights that minimize risk-weighted dark nights on
    the tuning window (tie-break: maximize fixes per crew-hour).

    Each trial replays the full ticket history (so the queue carries
    realistic state into the tuning window) but is scored only on
    config.TUNE_START..TUNE_END. Logs every trial's weights and
    tuning-window metrics to ``log_path`` as it goes.

    Args:
        tickets: Output of load_tickets().
        layers: School/transit layers, from engine.data.load_layers().
        budget_min: Weekly crew minutes.
        n_trials: Number of random weight sets to try.
        seed: RNG seed, for a reproducible search.
        log_path: Where to write the trial log. Defaults to the real
            committed TUNING_LOG_CSV — tests must override this with a
            tmp_path so a small n_trials run doesn't clobber the real
            200-trial log.

    Returns:
        The best-performing weights dict, same shape as
        config.DEFAULT_POLICY_WEIGHTS.
    """
    rng = np.random.RandomState(seed)
    window = (TUNE_START, TUNE_END)

    best_weights: dict[str, float] | None = None
    best_key: tuple[float, float] | None = None
    trial_rows: list[dict] = []

    for trial in range(n_trials):
        weights = {name: float(rng.uniform(0, WEIGHT_MAX)) for name in WEIGHT_NAMES}
        policy = make_score_policy(layers, weights)
        result = simulate(tickets, policy, budget_min, window=window, layers=layers)

        key = (result.risk_weighted_dark_nights, -result.fixes_per_crew_hour)
        if best_key is None or key < best_key:
            best_key = key
            best_weights = weights

        trial_rows.append(
            {
                "trial": trial,
                **weights,
                "risk_weighted_dark_nights": result.risk_weighted_dark_nights,
                "fixes_per_crew_hour": result.fixes_per_crew_hour,
            }
        )
        if (trial + 1) % 50 == 0:
            logger.info("Tuning trial %d/%d, best so far: %.1f", trial + 1, n_trials, best_key[0])

    pd.DataFrame(trial_rows).to_csv(log_path, index=False)
    logger.info("Wrote %d trials to %s", n_trials, log_path)

    assert best_weights is not None
    return best_weights
