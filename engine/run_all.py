"""Regenerate every file in results/ from scratch.

Run with: python -m engine.run_all  (takes a few minutes — the 200-trial
random search dominates).

Writes: summary.csv, weights.json, tuning_log.csv,
crew_cut_communities.csv, policy_comparison.png, sensitivity.png.
"""

from __future__ import annotations

import json
import logging

import matplotlib.pyplot as plt
import pandas as pd

from config import (
    CREW_CUT_BUDGET_PCT,
    CREW_CUT_COMMUNITIES_CSV,
    DEFAULT_POLICY_WEIGHTS,
    POLICY_COMPARISON_PNG,
    RESULTS_DIR,
    SENSITIVITY_BUDGET_PCTS,
    SENSITIVITY_PNG,
    SUMMARY_CSV,
    TEST_END,
    TEST_START,
    TUNING_SEED,
    TUNING_TRIALS,
    WEEKLY_CREW_MINUTES,
    WEIGHTS_JSON,
)
from engine.data import load_layers, load_tickets
from engine.score import make_score_policy
from engine.simulate import RunResult, fifo_policy, simulate
from engine.tune import random_search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Fixed categorical colors (validated palette, slots 1/2/3) — same policy
# always gets the same color across both charts.
POLICY_COLORS = {"FIFO": "#2a78d6", "v1": "#1baf7a", "tuned": "#eda100"}
POLICY_ORDER = ["FIFO", "v1", "tuned"]
INK = "#0b0b0b"
MUTED = "#898781"
GRIDLINE = "#e1e0d9"


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


def _crew_cut_table(full: RunResult, cut: RunResult) -> pd.DataFrame:
    """Communities that lost visits when budget drops to CREW_CUT_BUDGET_PCT,
    and the extra risk-weighted dark nights that costs each one.
    """
    combined = (
        pd.DataFrame({"fixed_full": full.fixed_by_community, "fixed_cut": cut.fixed_by_community})
        .fillna(0)
        .astype(int)
    )
    combined["lost_visits"] = combined["fixed_full"] - combined["fixed_cut"]

    dark_diff = (cut.dark_nights_by_community - full.dark_nights_by_community).fillna(0).round(1)
    combined["extra_risk_weighted_dark_nights"] = dark_diff.reindex(combined.index).fillna(0.0)

    lost = combined[combined["lost_visits"] > 0].sort_values(
        "extra_risk_weighted_dark_nights", ascending=False
    )
    return lost.reset_index().rename(columns={"index": "comm_name"})


def _style_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED)
    ax.yaxis.grid(True, color=GRIDLINE, linewidth=1)
    ax.set_axisbelow(True)


def _plot_policy_comparison(summary: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(6, 4.5))
    policies = [p for p in POLICY_ORDER if p in summary["policy"].values]
    values = [summary.set_index("policy").loc[p, "risk_weighted_dark_nights"] for p in policies]
    colors = [POLICY_COLORS[p] for p in policies]

    bars = ax.bar(policies, values, width=0.6, color=colors)
    fifo_value = values[0]
    for bar, policy, value in zip(bars, policies, values):
        label = f"{value:,.0f}"
        if policy != "FIFO":
            pct = 100 * (fifo_value - value) / fifo_value
            label += f"\n(-{pct:.1f}%)"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            label,
            ha="center",
            va="bottom",
            color=INK,
            fontsize=10,
        )

    ax.set_ylabel("Risk-weighted dark nights (Jul-Aug test window)", color=INK)
    ax.set_title("FIFO vs v1 vs tuned", color=INK, fontsize=13, loc="left")
    _style_axes(ax)
    ax.set_ylim(0, max(values) * 1.2)
    fig.tight_layout()
    fig.savefig(POLICY_COMPARISON_PNG, dpi=150)
    plt.close(fig)


def _plot_sensitivity(sensitivity: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for policy in POLICY_ORDER:
        rows = sensitivity[sensitivity["policy"] == policy].sort_values("budget_pct")
        x = rows["budget_pct"] * 100
        y = rows["risk_weighted_dark_nights"]
        ax.plot(x, y, color=POLICY_COLORS[policy], linewidth=2, marker="o", markersize=9, label=policy)
        ax.annotate(
            f"{y.iloc[-1]:,.0f}",
            (x.iloc[-1], y.iloc[-1]),
            textcoords="offset points",
            xytext=(8, 0),
            va="center",
            color=INK,
            fontsize=10,
        )

    ax.set_xticks(list(sensitivity["budget_pct"].unique() * 100))
    ax.set_xlabel("Weekly crew budget (% of 840 min)", color=INK)
    ax.set_ylabel("Risk-weighted dark nights (Jul-Aug test window)", color=INK)
    ax.set_title("Sensitivity to crew budget", color=INK, fontsize=13, loc="left")
    _style_axes(ax)
    ax.legend(frameon=False, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(SENSITIVITY_PNG, dpi=150)
    plt.close(fig)


def main() -> None:
    """Load tickets, tune, run every policy, and write results/* outputs."""
    RESULTS_DIR.mkdir(exist_ok=True)
    tickets = load_tickets()
    layers = load_layers()
    logger.info("Loaded %d tickets, layers: %s", len(tickets), list(layers.keys()))

    tuned_weights = random_search(tickets, layers, WEEKLY_CREW_MINUTES, TUNING_TRIALS, TUNING_SEED)
    WEIGHTS_JSON.write_text(json.dumps(tuned_weights, indent=2))
    logger.info("Tuned weights: %s", tuned_weights)

    policies = {
        "FIFO": fifo_policy,
        "v1": make_score_policy(layers, DEFAULT_POLICY_WEIGHTS),
        "tuned": make_score_policy(layers, tuned_weights),
    }

    # Headline comparison: held-out Jul-Aug test window only, so the
    # tuned policy isn't graded on data it was tuned on.
    test_window = (TEST_START, TEST_END)
    test_results = {
        name: simulate(tickets, policy, WEEKLY_CREW_MINUTES, window=test_window, layers=layers)
        for name, policy in policies.items()
    }
    for name, result in test_results.items():
        logger.info(
            "%s: %d fixed, %.1f risk-weighted dark nights, %.3f fixes/crew-hour, %d still dark",
            name,
            result.lights_fixed,
            result.risk_weighted_dark_nights,
            result.fixes_per_crew_hour,
            result.still_dark_at_end,
        )

    summary = pd.DataFrame([_summary_row(name, test_results[name]) for name in POLICY_ORDER])
    summary.to_csv(SUMMARY_CSV, index=False)
    logger.info("Wrote %s", SUMMARY_CSV)

    # Crew cut: tuned policy, full run, 100% vs CREW_CUT_BUDGET_PCT.
    full_tuned = simulate(tickets, policies["tuned"], WEEKLY_CREW_MINUTES, layers=layers)
    cut_budget = round(WEEKLY_CREW_MINUTES * CREW_CUT_BUDGET_PCT)
    cut_tuned = simulate(tickets, policies["tuned"], cut_budget, layers=layers)
    crew_cut_df = _crew_cut_table(full_tuned, cut_tuned)
    crew_cut_df.to_csv(CREW_CUT_COMMUNITIES_CSV, index=False)
    logger.info(
        "Crew cut (%.0f%% budget): %d communities lost visits. Wrote %s",
        CREW_CUT_BUDGET_PCT * 100,
        len(crew_cut_df),
        CREW_CUT_COMMUNITIES_CSV,
    )

    # Sensitivity: all three policies at each budget level, test window.
    sensitivity_rows = []
    for pct in SENSITIVITY_BUDGET_PCTS:
        budget = round(WEEKLY_CREW_MINUTES * pct)
        for name, policy in policies.items():
            result = simulate(tickets, policy, budget, window=test_window, layers=layers)
            sensitivity_rows.append(
                {
                    "budget_pct": pct,
                    "policy": name,
                    "risk_weighted_dark_nights": result.risk_weighted_dark_nights,
                    "fixes_per_crew_hour": result.fixes_per_crew_hour,
                }
            )
    sensitivity_df = pd.DataFrame(sensitivity_rows)

    _plot_policy_comparison(summary)
    _plot_sensitivity(sensitivity_df)
    logger.info("Wrote %s and %s", POLICY_COMPARISON_PNG, SENSITIVITY_PNG)


if __name__ == "__main__":
    main()
