"""Incrementally refreshed, filterable activity feed."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

import streamlit as st

from dashboard.utils.formatters import relative_time

ICONS = {"new": "🔵", "merged": "🔄", "rerank": "⚡", "hazard": "⚠️", "fixed": "✅", "reset": "🔁"}


def add_events(events: list[dict[str, Any]]) -> None:
    known = st.session_state.event_keys
    for event in events:
        key = (event.get("at"), event.get("type"), event.get("light_id"), event.get("message"))
        if key not in known:
            known.add(key)
            st.session_state.events.append(event)
    st.session_state.events = st.session_state.events[-1000:]
    st.session_state.event_keys = {
        (e.get("at"), e.get("type"), e.get("light_id"), e.get("message")) for e in st.session_state.events
    }
    if events:
        st.session_state.last_event_at = max(
            (e.get("at", "") for e in events), default=st.session_state.last_event_at
        )


def render_activity(events: list[dict[str, Any]]) -> None:
    st.subheader("Live activity")
    types = sorted({str(e.get("type", "other")) for e in events} | set(ICONS))
    selected_types = st.multiselect(
        "Event types", types, default=types, key="event_filter", label_visibility="collapsed"
    )
    visible = [e for e in events if e.get("type") in selected_types]
    if not visible:
        st.caption("No activity yet. New reports will appear here.")
        return
    groups: dict[str, list[dict]] = defaultdict(list)
    today = date.today()
    for event in reversed(visible):
        at = str(event.get("at", ""))
        try:
            day = datetime.fromisoformat(at.replace("Z", "+00:00")).date()
            label = (
                "Today"
                if day == today
                else "Yesterday"
                if (today - day).days == 1
                else day.strftime("%b %d, %Y")
            )
        except ValueError:
            label = "Earlier"
        groups[label].append(event)
    for day, items in groups.items():
        st.markdown(f"**{day}**")
        for event in items[:30]:
            stamp, absolute = relative_time(str(event.get("at", "")))
            kind = str(event.get("type", "event"))
            st.markdown(
                f"{ICONS.get(kind, '•')} **{kind.title()}** · {event.get('message', 'Activity recorded')}",
                help=f"{absolute} · {event.get('light_id') or 'No ticket'}",
            )
            st.caption(stamp)
    if len(visible) >= 1000:
        st.caption("Showing the most recent 1,000 events.")
