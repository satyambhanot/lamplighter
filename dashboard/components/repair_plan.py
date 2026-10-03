"""Sortable current-week plan table."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def render_repair_plan(plan: dict) -> None:
    queue = plan.get("queue", [])
    st.subheader("This week's repair plan")
    if not queue:
        st.info("No lights are currently scheduled in this plan.")
        return
    frame = pd.DataFrame(queue)
    # Add optional API fields when available; keep this view compatible with current QueueItem schema.
    frame = frame.rename(
        columns={
            "ticket_id": "Ticket ID",
            "rank": "Rank",
            "comm_name": "Community",
            "score": "Score",
            "reasons": "Reasons",
            "expected_fix_date": "Expected fix",
            "call_count": "Calls",
        }
    )
    wanted = ["Rank", "Ticket ID", "Community", "Score", "Reasons", "Expected fix", "Calls"]
    for col in wanted:
        if col not in frame:
            frame[col] = "—"
    frame = frame[wanted].sort_values("Rank", kind="stable")
    st.dataframe(
        frame,
        use_container_width=True,
        hide_index=True,
        height=min(460, 38 * min(len(frame), 12) + 40),
        column_config={
            "Rank": st.column_config.NumberColumn(format="%d", help="Priority rank; lower is sooner"),
            "Ticket ID": st.column_config.TextColumn(),
            "Score": st.column_config.NumberColumn(format="%.2f"),
        },
    )
    minutes = plan.get("minutes_used")
    budget = plan.get("budget_minutes")
    footer = f"Total: {len(queue):,} scheduled lights"
    if minutes is not None and budget is not None:
        footer += f" · {minutes:,.0f} of {budget:,.0f} crew minutes"
    else:
        footer += " · Crew-minute totals are not yet included in the plan API response."
    st.caption(footer)
