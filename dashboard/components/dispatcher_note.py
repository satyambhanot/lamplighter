"""Dispatcher explanation with a reliable local fallback."""

from __future__ import annotations

from html import escape

import streamlit as st


def render_note(plan: dict) -> None:
    note = plan.get("dispatcher_note") or plan.get("note")
    if not note:
        queue = plan.get("queue", [])
        policy = plan.get("policy", "selected")
        budget = float(plan.get("budget_pct", 1)) * 100
        note = (
            f"The {policy} plan schedules {len(queue)} lights at {budget:.0f}% crew capacity. "
            "Priorities reflect the ranking reasons shown in the queue. "
            "The live API does not yet provide an AI dispatcher note."
        )
    st.subheader("Dispatcher note")
    st.markdown(f"<div class='note'>{escape(str(note))}</div>", unsafe_allow_html=True)
