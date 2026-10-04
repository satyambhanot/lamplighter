"""Dispatcher controls and explicit demo reset confirmation."""

from __future__ import annotations

import streamlit as st


def render_sidebar(scenario_date: str) -> tuple[str, int, bool, bool]:
    with st.sidebar:
        st.markdown("## Lamplighter")
        st.caption("Street lighting dispatch")
        labels = {"FIFO": "FIFO · oldest first", "v1": "Version 1 · hand-set", "tuned": "Tuned · recommended"}
        policy = st.radio(
            "Prioritization policy",
            list(labels),
            index=2,
            format_func=labels.__getitem__,
            key="policy_choice",
            help="Choose how reported lights are ranked for repair.",
        )
        budget = st.slider(
            "Weekly crew budget",
            min_value=70,
            max_value=120,
            step=5,
            value=100,
            format="%d%%",
            key="budget_choice",
            help="Set crew capacity relative to a normal week.",
        )
        apply = st.button("Apply plan", type="primary", use_container_width=True)
        st.caption("Changes take effect when you apply the plan.")
        st.divider()
        st.toggle("Dark appearance", key="dark_mode")
        st.markdown("**Scenario date**")
        st.caption(scenario_date)
        st.divider()
        st.markdown("**Reset demo**")
        st.caption("Restore the sample reports and activity feed.")
        confirm = st.checkbox("Confirm reset", key="confirm_reset")
        reset = st.button("Reset demo", disabled=not confirm, use_container_width=True)
    return policy, budget, apply, reset
