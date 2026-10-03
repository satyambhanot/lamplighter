"""Regenerate every file in results/ from scratch.

Run with: python -m engine.run_all

Phase 3: FIFO vs v1 comparison. Phase 4 adds tuning/crew-cut/
sensitivity outputs and charts.
"""

from __future__ import annotations

import logging

import pandas as pd

from config import DEFAULT_POLICY_WEIGHTS, RESULTS_DIR, SUMMARY_CSV, WEEKLY_CREW_MINUTES
from engine.data import load_layers, load_tickets
from engine.score import make_score_policy
from engine.simulate import RunResult, fifo_policy, simulate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _summary_row(policy_name: str, result: RunResult) -> dict:
    return {
        "policy": policy_name,
        "lights_fixed": result.lights_fixed,
        "total_dark_nights": result.total_dark_nights,
        "risk_weighted_dark_nights": round(result.risk_weighted_dark_nights, 1),
        "fixes_per_crew_hour": round(result.fixes_per_crew_hour, 3),
        "median_days_dark": result.median_days_dark,
        "still_dark_at_end": result.still_dark_at_end,
    }


def main() -> None:
    """Load tickets, run every policy, and write results/* outputs."""
    RESULTS_DIR.mkdir(exist_ok=True)
    tickets = load_tickets()
    layers = load_layers()
    logger.info("Loaded %d tickets, layers: %s", len(tickets), list(layers.keys()))

    fifo_result = simulate(tickets, fifo_policy, WEEKLY_CREW_MINUTES)
    logger.info(
        "FIFO: %d fixed, %.1f risk-weighted dark nights, %.3f fixes/crew-hour, %d still dark",
        fifo_result.lights_fixed,
        fifo_result.risk_weighted_dark_nights,
        fifo_result.fixes_per_crew_hour,
        fifo_result.still_dark_at_end,
    )

    v1_policy = make_score_policy(layers, DEFAULT_POLICY_WEIGHTS)
    v1_result = simulate(tickets, v1_policy, WEEKLY_CREW_MINUTES)
    logger.info(
        "v1: %d fixed, %.1f risk-weighted dark nights, %.3f fixes/crew-hour, %d still dark",
        v1_result.lights_fixed,
        v1_result.risk_weighted_dark_nights,
        v1_result.fixes_per_crew_hour,
        v1_result.still_dark_at_end,
    )

    improvement_pct = 100 * (fifo_result.risk_weighted_dark_nights - v1_result.risk_weighted_dark_nights) / fifo_result.risk_weighted_dark_nights
    logger.info("v1 improves risk-weighted dark nights by %.1f%% over FIFO", improvement_pct)

    summary = pd.DataFrame([_summary_row("FIFO", fifo_result), _summary_row("v1", v1_result)])
    summary.to_csv(SUMMARY_CSV, index=False)
    logger.info("Wrote %s", SUMMARY_CSV)


if __name__ == "__main__":
    main()
