"""Headline operational and historical evaluation metrics."""

from __future__ import annotations

import streamlit as st


def render_kpis(plan: dict, baseline: dict | None, evaluation: dict | None) -> None:
    cols = st.columns(4)
    current_risk = plan.get("risk_weighted_dark_nights")
    base_risk = baseline.get("risk_weighted_dark_nights") if baseline else None
    improvement = (
        ((base_risk - current_risk) / base_risk * 100) if base_risk and current_risk is not None else None
    )
    with cols[0]:
        st.metric(
            "Risk weighted dark nights",
            _number(current_risk),
            delta=f"{improvement:.1f}% vs FIFO" if improvement is not None else "FIFO baseline unavailable",
        )
    with cols[1]:
        st.metric("Fixes per crew hour", _number(plan.get("fixes_per_crew_hour")))
    with cols[2]:
        st.metric(
            "Median days dark",
            _number((evaluation or {}).get("median_days_dark")),
            help="Held-out July–August historical result; not provided by the live plan API.",
        )
    with cols[3]:
        st.metric(
            "Still dark at test end",
            _number((evaluation or {}).get("still_dark_at_end")),
            help="Held-out July–August historical result; not provided by the live plan API.",
        )


def _number(value: object) -> str:
    try:
        return f"{float(value):,.1f}" if value is not None else "—"
    except (ValueError, TypeError):
        return "—"
