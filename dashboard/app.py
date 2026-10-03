"""Lamplighter dispatcher dashboard. Run with: streamlit run dashboard/app.py"""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

import streamlit as st

from dashboard.components.activity_log import add_events, render_activity
from dashboard.components.dispatcher_note import render_note
from dashboard.components.kpi_cards import render_kpis
from dashboard.components.map_view import render_map
from dashboard.components.repair_plan import render_repair_plan
from dashboard.components.sidebar import render_sidebar
from dashboard.styles.theme import CSS, DARK_CSS
from dashboard.utils import api_client
from config import DEMO_DATE as SCENARIO_DATE

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_LABEL = date.fromisoformat(SCENARIO_DATE).strftime("%A, %B %d, %Y").replace(" 0", " ")

st.set_page_config(
    page_title="Lamplighter Dispatch", page_icon="💡", layout="wide", initial_sidebar_state="expanded"
)


def init_state() -> None:
    defaults = {
        "events": [],
        "event_keys": set(),
        "last_event_at": "1970-01-01T00:00:00",
        "plan": None,
        "current_signature": None,
        "plan_error": None,
        "last_plan_updated": None,
        "dark_mode": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


@st.cache_data(ttl=30, show_spinner=False)
def load_evaluation() -> dict[str, dict[str, float]]:
    path = ROOT / "results" / "summary.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["policy"]: {key: float(value) for key, value in row.items() if key != "policy" and value}
            for row in csv.DictReader(handle)
        }


@st.cache_data(ttl=60, show_spinner=False)
def load_crew_cut_communities() -> list[dict[str, str]]:
    path = ROOT / "results" / "crew_cut_communities.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def fetch_plan(policy: str, budget: int) -> dict | None:
    try:
        result = api_client.get_plan(policy, budget)
        st.session_state.plan_error = None
        return result
    except api_client.APIError as exc:
        st.session_state.plan_error = str(exc)
        return None


init_state()
st.markdown(CSS + (DARK_CSS if st.session_state.dark_mode else ""), unsafe_allow_html=True)
policy, budget, apply_clicked, reset_clicked = render_sidebar(SCENARIO_LABEL)

if reset_clicked:
    try:
        api_client.post_demo_reset()
        st.session_state.events.clear()
        st.session_state.event_keys.clear()
        st.session_state.last_event_at = "1970-01-01T00:00:00"
        st.session_state.plan = None
        st.session_state.current_signature = None
        st.toast("Demo state restored", icon="✅")
    except api_client.APIError as exc:
        st.error(f"Could not reset demo: {exc}")

requested_signature = (policy, budget)
if st.session_state.plan is None or apply_clicked:
    plan = fetch_plan(policy, budget)
    if plan is not None:
        st.session_state.plan = plan
        st.session_state.current_signature = requested_signature

preview_mode = st.session_state.current_signature != requested_signature
preview_plan = fetch_plan(policy, budget) if preview_mode else None
if preview_mode and preview_plan is None:
    preview_mode = False

st.markdown("<div class='eyebrow'>City of Calgary | Roads / Street Lighting</div>", unsafe_allow_html=True)
st.title("Street light dispatch")
st.caption(f"Prioritize repairs to reduce risk-weighted dark nights · Scenario date: {SCENARIO_LABEL}")


@st.fragment(run_every=3)
def live_dashboard(active_policy: str, active_budget: int, is_preview: bool) -> None:
    """Refresh the map/queue and activity log together for live report updates."""
    try:
        api_client.get_health()
        api_online = True
    except api_client.APIError:
        api_online = False
    updated = st.session_state.last_plan_updated
    if api_online:
        st.markdown("<span class='status status-live'>● API connected</span>", unsafe_allow_html=True)
    else:
        st.markdown("<span class='status status-offline'>● API disconnected · retrying automatically</span>", unsafe_allow_html=True)
    if updated:
        st.caption(f"Plan last updated {updated}")
    if is_preview:
        active_plan = fetch_plan(active_policy, active_budget)
    else:
        fresh_plan = fetch_plan(active_policy, active_budget)
        if fresh_plan is not None:
            st.session_state.plan = fresh_plan
            st.session_state.current_signature = (active_policy, active_budget)
            st.session_state.last_plan_updated = datetime.now().astimezone().strftime("%I:%M:%S %p %Z")
        active_plan = st.session_state.plan

    if st.session_state.plan_error:
        st.error("Live plan unavailable. Historical results are shown where available; map and schedule need the API.")
        with st.expander("Connection details and next steps"):
            st.write("Start or restart the Lamplighter API, then select **Apply plan** to retry.")
            st.code(st.session_state.plan_error, language=None)
    if is_preview:
        st.markdown(
            "<div class='preview'>Preview mode | proposed policy or crew budget differs from the applied plan.</div>",
            unsafe_allow_html=True,
        )
    evaluation = load_evaluation()
    if active_plan:
        baseline = evaluation.get("FIFO")
        policy_result = evaluation.get(str(active_plan.get("policy", "tuned")))
        render_kpis(active_plan, baseline, policy_result)
    else:
        historical = evaluation.get(active_policy)
        if historical:
            st.info("Showing held-out historical KPIs while the live API is unavailable.")
            render_kpis(
                {
                    "risk_weighted_dark_nights": historical.get("risk_weighted_dark_nights"),
                    "fixes_per_crew_hour": historical.get("fixes_per_crew_hour"),
                    "queue": [],
                    "policy": active_policy,
                },
                evaluation.get("FIFO"),
                historical,
            )
        else:
            st.info("Waiting for a plan from the API. Start the API and retry.")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("Open lights map")
        queue = (active_plan or {}).get("queue", [])
        if active_plan is not None and not queue:
            st.info("No open lights are in this plan.")
            if st.button("Reset demo data", key="empty_reset"):
                try:
                    api_client.post_demo_reset()
                    st.session_state.plan = None
                    st.toast("Demo state restored", icon="✅")
                except api_client.APIError as exc:
                    st.error(str(exc))
        else:
            selected = render_map(queue, depot=(51.04062, -114.05793))
            if selected:
                with st.expander(f"Selected light | {selected.get('ticket_id', 'ticket')}", expanded=True):
                    st.write(f"Rank: {selected.get('rank', '—')} | Score: {selected.get('score', '—')}")
                    st.write(f"Reasons: {selected.get('reasons', '—')}")
                    st.write(f"Location: {selected.get('lat', '—')}, {selected.get('lon', '—')}")
        if is_preview and active_plan:
            current_ids = {
                str(item.get("ticket_id")) for item in (st.session_state.plan or {}).get("queue", [])
            }
            proposed_ids = {str(item.get("ticket_id")) for item in queue}
            col_a, col_b = st.columns(2)
            col_a.metric("Current scheduled", len(current_ids))
            col_b.metric(
                "Proposed scheduled", len(proposed_ids), delta=f"{len(proposed_ids) - len(current_ids):+d}"
            )
            st.caption("Community visit comparisons require community-level fields in GET /plan.")
            if active_budget == 80:
                affected = [
                    row for row in load_crew_cut_communities() if int(row.get("lost_visits", 0) or 0) > 0
                ]
                if affected:
                    st.info(
                        f"Historical crew-cut analysis: {len(affected)} communities lost visits at 80% capacity."
                    )
                    with st.expander("View affected communities"):
                        st.dataframe(affected, use_container_width=True, hide_index=True)
    with right:
        try:
            add_events(api_client.get_events(st.session_state.last_event_at))
        except api_client.APIError as exc:
            st.warning(f"Activity feed temporarily unavailable: {exc}")
        render_activity(st.session_state.events)

    st.divider()
    if active_plan:
        render_repair_plan(active_plan)
        render_note(active_plan)


live_dashboard(policy, budget, preview_mode)
