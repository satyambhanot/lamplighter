"""Streamlit dashboard: reads the queue from the API and the headline
numbers from results/. Designed for a projector — large fonts, few
colors, no clutter.

Run with: streamlit run dashboard/app.py
Layout implemented in Phase 8.
"""

from __future__ import annotations

import streamlit as st

API_BASE_URL = "http://localhost:8000"

st.set_page_config(page_title="Lamplighter", layout="wide")

st.title("Lamplighter — Street Light Dispatch")

top = st.columns(3)
with top[0]:
    st.metric("Risk-weighted dark nights (FIFO)", "—")
with top[1]:
    st.metric("Risk-weighted dark nights (tuned)", "—")
with top[2]:
    st.metric("Fixes per crew-hour", "—")

middle = st.columns([2, 1])
with middle[0]:
    st.subheader("Map")
    st.info("Pydeck map — coming in Phase 8")
with middle[1]:
    st.subheader("Activity log")
    st.info("Live events from GET /events — coming in Phase 8")

st.subheader("This week's list")
st.info("Ranked table — coming in Phase 8")

st.subheader("Dispatcher note")
st.info("engine/note.py output — coming in Phase 8")

with st.sidebar:
    st.header("Controls")
    st.selectbox("Policy", ["FIFO", "v1", "tuned"], index=2, disabled=True)
    st.slider("Crew budget %", min_value=50, max_value=120, value=100, disabled=True)
    st.caption("Wired up to GET /plan in Phase 8")
