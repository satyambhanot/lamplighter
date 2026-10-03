"""Self-tuning: random search over policy weights.

200 trials, seed 42 (config.TUNING_TRIALS / TUNING_SEED). Trials are
scored on the Mar-Jun tuning window only (config.TUNE_START/TUNE_END);
Jul-Aug is held out for reporting. Implemented in Phase 4.
"""

from __future__ import annotations

import pandas as pd


def random_search(
    tickets: pd.DataFrame,
    budget_min: int,
    n_trials: int,
    seed: int,
) -> dict[str, float]:
    """Search policy weights that minimize risk-weighted dark nights on
    the tuning window (tie-break: maximize fixes per crew-hour).

    Logs every trial's weights and tuning-window metrics to
    TUNING_LOG_CSV as it goes.

    Args:
        tickets: Output of load_tickets().
        budget_min: Weekly crew minutes.
        n_trials: Number of random weight sets to try.
        seed: RNG seed, for a reproducible search.

    Returns:
        The best-performing weights dict, same shape as
        config.DEFAULT_POLICY_WEIGHTS.
    """
    raise NotImplementedError("Phase 4")
