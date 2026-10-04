"""Lamplighter's dispatch workspace. Run with ``make dash``."""

from __future__ import annotations

import html
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from config import DEMO_DATE, ROOT_DIR, WEEKLY_CREW_MINUTES
from dashboard.data import (
    POLICY_LABELS,
    DataUnavailable,
    DispatchView,
    capacity_impact,
    export_csv,
    fetch_history,
    fetch_live,
    load_evaluation,
    load_preview,
    mutate,
    preview_history,
    queue_rows,
)
from dashboard.maps import build_map, reference_layers, ticket_from_selection

load_dotenv(ROOT_DIR / ".env")
API_BASE_URL = os.environ.get("LAMPLIGHTER_API_URL", "http://localhost:8000")
DISPATCH_TOKEN = os.environ.get("DISPATCH_SHARED_SECRET", "")
st.set_page_config(page_title="Lamplighter · Dispatch", page_icon="◉", layout="wide")
st.markdown(f"<style>{Path(__file__).with_name('styles.css').read_text()}</style>", unsafe_allow_html=True)


def markup(value: str) -> None:
    st.markdown(value, unsafe_allow_html=True)


def panel(title: str, detail: str = "") -> None:
    markup(
        f'<div class="panel-head"><span class="panel-title">{html.escape(title)}</span>'
        f'<span class="panel-meta">{html.escape(detail)}</span></div>'
    )


def empty(title: str, detail: str) -> None:
    markup(
        f'<div class="empty-state"><strong>{html.escape(title)}</strong><p>{html.escape(detail)}</p></div>'
    )


def metric(label: str, value: str, detail: str, accent: bool = False) -> None:
    markup(
        f'<div class="metric-card {"accent" if accent else ""}"><div class="metric-label">{html.escape(label)}</div>'
        f'<div class="metric-value">{html.escape(value)}</div><div class="metric-sub">{html.escape(detail)}</div></div>'
    )


@st.cache_data(show_spinner=False, ttl=30)
def preview(policy: str, budget: int) -> DispatchView:
    return load_preview(policy, budget)


@st.cache_data(show_spinner=False, ttl=300)
def references() -> dict:
    return reference_layers()


@st.cache_data(show_spinner=False, ttl=5)
def live_history(ticket: str, revision: int, token: str):
    return fetch_history(API_BASE_URL, ticket, token)


def clear_review() -> None:
    st.session_state.pop("review_context", None)
    st.session_state.pop("review_ack", None)
    st.session_state.pop("repair_ack", None)


def change_source() -> None:
    clear_review()
    st.session_state["selected_ticket"] = ""


def select_map() -> None:
    ticket = ticket_from_selection(st.session_state.get("dispatch-map", {}))
    if ticket:
        st.session_state["selected_ticket"] = ticket
        st.session_state.pop("repair_ack", None)


def select_row(key: str, ids: list[str]) -> None:
    rows = st.session_state.get(key, {}).get("selection", {}).get("rows", [])
    if rows and rows[0] < len(ids):
        st.session_state["selected_ticket"] = ids[rows[0]]
        st.session_state.pop("repair_ack", None)


def reset_settings() -> None:
    st.session_state["policy"] = "tuned"
    st.session_state["budget"] = 100
    clear_review()


def write(endpoint: str, payload: dict, success: str) -> None:
    try:
        mutate(API_BASE_URL, endpoint, DISPATCH_TOKEN, payload)
    except DataUnavailable as exc:
        st.session_state["feedback"] = ("error", str(exc))
        clear_review()
    else:
        st.session_state["feedback"] = ("success", success)
        clear_review()
    st.rerun()


def render_map(view: DispatchView, community: str) -> None:
    panel("Crew route", "CLICK A LIGHT TO INSPECT")
    cols = st.columns(5)
    flags = {}
    for col, name, label, default in zip(
        cols,
        ["planned", "waiting", "schools", "transit", "route"],
        ["Planned", "Waiting", "Schools", "Transit", "Visit order"],
        [True, True, False, False, True],
        strict=True,
    ):
        flags[name] = col.checkbox(label, value=default, key=f"layer-{name}")
    focus = st.checkbox("Focus on selected light", key="focus-map")
    if not view.queue:
        empty("No lights in this view", "There are no open reports to plan.")
        return
    deck = build_map(view, st.session_state["selected_ticket"], community, flags, references(), focus)
    st.pydeck_chart(
        deck,
        key="dispatch-map",
        on_select=select_map,
        selection_mode="single-object",
        width="stretch",
        height=420,
    )
    markup(
        '<div class="map-legend"><span><i class="legend-dot" style="background:#be8024"></i>Numbered visit</span>'
        '<span><i class="legend-dot" style="background:#718496"></i>Waiting</span>'
        '<span><i class="legend-dot" style="background:#1e8083"></i>Selected</span>'
        '<span><i class="legend-dot" style="background:#bb5a44"></i>Removed vs 100%</span></div>'
    )
    st.caption("Lines show visit order; travel estimates use straight-line distances, not road directions.")


def render_detail(view: DispatchView, historical: bool, stale: bool) -> None:
    panel("Light details", "REPORT & PRIORITY")
    ids = [item.ticket_id for item in view.queue]
    by_id = {item.ticket_id: item for item in view.queue}
    ticket = st.selectbox(
        "Inspect light",
        [""] + ids,
        key="selected_ticket",
        format_func=lambda value: (
            f"{value} · {by_id[value].comm_name.title()}" if value else "Select a map pin or queue row"
        ),
        on_change=lambda: st.session_state.pop("repair_ack", None),
        label_visibility="collapsed",
    )
    if not ticket:
        empty("Select a light", "Inspect its reports, priority reasons, and planned route position.")
        return
    item = by_id[ticket]
    stop = next((i + 1 for i, light in enumerate(view.plan.queue) if light.ticket_id == ticket), None)
    markup(f'<div class="detail-title">{html.escape(item.comm_name.title())}</div>')
    st.caption(f"{ticket} · {item.lat:.5f}, {item.lon:.5f}")
    facts = [
        ("Priority", f"#{item.rank}"),
        ("Visit position", f"Stop {stop}" if stop else "Waiting for capacity"),
        ("Reports", str(item.call_count)),
        ("Outage age", f"{item.age_days} days" if item.age_days is not None else "Unavailable"),
    ]
    for label, value in facts:
        markup(f'<div class="brief-stat"><span>{label}</span><strong>{html.escape(value)}</strong></div>')
    st.markdown("**Why this light ranks here**")
    st.write(item.reasons)
    tags = []
    if item.near_school:
        tags.append("Near a school")
    if item.near_transit:
        tags.append("Near transit")
    if item.is_damage:
        tags.append("Damage reported")
    if item.neighbours_dark:
        tags.append(f"{item.neighbours_dark} nearby outages")
    if tags:
        st.caption(" · ".join(tags))
    if item.expected_fix_date:
        st.caption(
            f"Estimated repair week: {item.expected_fix_date[:10]} · assumes unchanged queue and capacity"
        )
    with st.expander("Report history"):
        try:
            history = (
                preview_history(ticket)
                if historical
                else live_history(ticket, view.revision or 0, DISPATCH_TOKEN)
            )
            if not history.complete:
                st.caption(
                    "Partial history: historical call counts are available, but individual repeat calls were not retained."
                )
            if not history.history:
                st.caption("No individual report details are available.")
            for report in history.history:
                st.caption(f"{report.at.strftime('%d %b %Y · %H:%M')} · {report.channel.title()}")
                st.write(report.description or "No description recorded.")
        except DataUnavailable as exc:
            st.caption(str(exc))
    confirmed = view.confirmed_plan
    if confirmed:
        visit = next((visit for visit in confirmed.visits if visit.ticket_id == ticket), None)
        if visit:
            st.caption(f"Confirmed crew assignment: stop {visit.position} · {visit.status}")
    can_repair = (
        not historical
        and not stale
        and bool(DISPATCH_TOKEN)
        and view.revision is not None
        and confirmed is not None
        and confirmed.status == "confirmed"
        and ticket in confirmed.remaining_ids
    )
    if can_repair:
        st.divider()
        checked = st.checkbox("Crew has completed this repair", key="repair_ack")
        if st.button("Mark repaired", type="primary", disabled=not checked, key="mark-repaired"):
            write(
                f"fixed/{ticket}",
                {"revision": view.revision, "plan_id": confirmed.id},
                f"{ticket} marked repaired. The queue has been updated.",
            )


def render_queue(view: DispatchView, community: str, historical: bool) -> None:
    with st.container(border=True, key="queue-panel"):
        panel("This week’s work", "SELECT A ROW TO INSPECT")
        search = st.text_input(
            "Search queue",
            placeholder="Ticket, community, or priority reason…",
            key="queue-search",
            label_visibility="collapsed",
        )
        tabs = st.tabs(
            [f"Planned visits ({view.plan.lights_planned})", f"Waiting backlog ({view.plan.skipped_count})"]
        )
        for tab, status in zip(tabs, ["planned", "waiting"], strict=True):
            with tab:
                rows = queue_rows(view, community, search, status=status)
                if rows:
                    frame = pd.DataFrame(rows)
                    selected = st.session_state["selected_ticket"]
                    styled = frame.style.apply(
                        lambda row, selected=selected: (
                            ["background-color: #e3f2f1" if row.Ticket == selected else ""] * len(row)
                        ),
                        axis=1,
                    )
                    table_key = (
                        f"queue-{status}-{source}-{policy}-{budget}-{view.revision}-{community}-{search}"
                    )
                    st.dataframe(
                        styled,
                        hide_index=True,
                        width="stretch",
                        key=table_key,
                        on_select=lambda k=table_key, items=[row["Ticket"] for row in rows]: select_row(
                            k, items
                        ),
                        selection_mode="single-row",
                        height=min(350, 38 + 35 * len(rows)),
                        column_config={
                            "Priority": st.column_config.NumberColumn(format="#%d", width="small"),
                            "Route stop": st.column_config.NumberColumn(format="%d", width="small"),
                            "Dispatch reason": st.column_config.TextColumn(width="large"),
                        },
                    )
                else:
                    empty(
                        "No matching reports",
                        "Try another community or a shorter search."
                        if search
                        else "No lights in this category.",
                    )
                st.download_button(
                    f"Export {status} ↓",
                    data=export_csv(rows),
                    mime="text/csv",
                    file_name=f"lamplighter-{'preview' if historical else 'live'}-{policy}-{status}.csv",
                    key=f"export-{status}",
                )
        st.caption("Priority controls selection. Route stop shows crew visit order.")


def render_impact(view: DispatchView, budget: int) -> None:
    impact = capacity_impact(view)
    with st.expander(f"Capacity impact · {budget}% compared with 100%", expanded=budget != 100):
        st.caption(
            "Same open queue and dispatch policy. Counts compare actual route membership, including replacements."
        )
        a, b, c = st.columns(3)
        a.metric("Visits removed", len(impact["removed"]))
        b.metric("Visits added", len(impact["added"]))
        c.metric("Allocated hours change", f"{impact['minutes_delta'] / 60:+.1f}")
        st.caption(f"{impact['unchanged']} visits retained in both plans")
        if impact["communities"]:
            st.dataframe(pd.DataFrame(impact["communities"]), hide_index=True, width="stretch")
        changed = [
            {
                "Change": label,
                "Ticket": item.ticket_id,
                "Community": item.comm_name.title(),
                "Estimated repair week": (item.expected_fix_date or "Unavailable")[:10],
            }
            for label, items in [("Removed", impact["removed"]), ("Added", impact["added"])]
            for item in items
        ]
        if changed:
            st.dataframe(pd.DataFrame(changed), hide_index=True, width="stretch")
        else:
            st.caption("Route membership is unchanged.")


def render_review(view: DispatchView, historical: bool, stale: bool) -> None:
    context = (source, policy, budget, view.revision)
    if "review_context" in st.session_state and st.session_state["review_context"] != context:
        clear_review()
    confirmed = view.confirmed_plan
    if confirmed:
        text = f"Plan {confirmed.id} · {confirmed.status.replace('_', ' ')} · {len(confirmed.remaining_ids)} remaining · {confirmed.completed_count} repaired"
        if confirmed.status == "needs_review":
            st.warning(
                text + ". Reports changed after confirmation. Review a new plan before recording repairs."
            )
        else:
            st.caption(text)
        with st.expander("Confirmed crew assignments", expanded=confirmed.status == "confirmed"):
            st.caption(
                f"{POLICY_LABELS[confirmed.policy]} · {confirmed.budget_pct:.0%} capacity. "
                "Original stop numbers stay fixed as repairs are completed. The proposal below recalculates available work."
            )
            rows = [
                {"Route stop": visit.position, "Ticket": visit.ticket_id, "Status": visit.status.title()}
                for visit in confirmed.visits
            ]
            if rows:
                key = f"confirmed-route-{confirmed.id}-{view.revision}"
                st.dataframe(
                    pd.DataFrame(rows),
                    hide_index=True,
                    width="stretch",
                    key=key,
                    selection_mode="single-row",
                    on_select=lambda: select_row(key, [row["Ticket"] for row in rows]),
                )
    st.caption(view.plan.note)
    if st.button("Review this plan", disabled=not view.plan.queue or stale, key="review-plan"):
        st.session_state["review_context"] = context
    if st.session_state.get("review_context") == context:
        with st.container(border=True):
            panel("Plan review", f"{POLICY_LABELS[policy].upper()} · {budget}% CAPACITY")
            st.write(
                f"{view.plan.lights_planned} visits · {view.plan.minutes_used / 60:.1f} crew-hours · {view.plan.skipped_count} waiting"
            )
            st.dataframe(pd.DataFrame(queue_rows(view, status="planned")), hide_index=True, width="stretch")
            if historical:
                st.info(
                    "Historical preview supports plan review. Switch to Live dispatch to confirm work and record repairs."
                )
            elif not DISPATCH_TOKEN:
                st.info(
                    "Dispatcher access needs local configuration. Run make configure, then restart the dashboard and API."
                )
            elif not stale and view.revision is not None:
                ack = st.checkbox("I reviewed the visit order and capacity impact", key="review_ack")
                if st.button("Confirm plan", type="primary", disabled=not ack, key="confirm-plan"):
                    write(
                        "plans/confirm",
                        {"revision": view.revision, "policy": policy, "budget_pct": budget / 100},
                        "Plan confirmed. Select a planned light to record its completed repair.",
                    )


def render_evaluation() -> None:
    st.info(
        "Historical experiments are provisional. Risk weighting and reporting-window defects are documented in the engineering review; these are not live performance metrics."
    )
    rows = load_evaluation()
    if rows:
        st.dataframe(
            pd.DataFrame(rows).rename(
                columns={
                    "policy": "Policy",
                    "lights_fixed": "Simulated fixes",
                    "risk_weighted_dark_nights": "Modeled dark-night cost",
                }
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("No saved evaluation is available.")


with st.sidebar:
    markup(
        '<div class="brand"><span class="brand-mark">◉</span><span class="brand-name">lamplighter</span></div><div class="brand-sub">Street lighting operations</div>'
    )
    workspace = st.radio("Workspace", ["Dispatch", "Evaluation"], key="workspace")
    markup('<div class="sidebar-label">DATA SOURCE</div>')
    source = st.selectbox(
        "Data source", ["Historical preview", "Live dispatch"], key="source", on_change=change_source
    )
    st.caption(
        "Real Calgary reports · simulated repairs"
        if source == "Historical preview"
        else "Updates every 5 seconds · demo planning clock"
    )
    markup('<div class="sidebar-label">PLAN SETTINGS</div>')
    policy = st.selectbox(
        "Dispatch policy",
        list(POLICY_LABELS),
        format_func=POLICY_LABELS.get,
        key="policy",
        on_change=clear_review,
    )
    st.session_state.setdefault("budget", 100)
    budget = st.slider("Crew capacity", 50, 120, step=5, format="%d%%", key="budget", on_change=clear_review)
    st.caption(f"{WEEKLY_CREW_MINUTES * budget / 100 / 60:.1f} crew-hours available this week")
    st.button("Reset plan settings", width="stretch", on_click=reset_settings, key="reset-settings")
    markup(
        '<div class="sidebar-foot">CALGARY, ALBERTA<br>Team NO Dark Night<br>Built for fewer dark nights.</div>'
    )

historical = source == "Historical preview"
markup(
    '<div class="page-head"><div><div class="eyebrow">OPERATIONS / ' + workspace.upper() + "</div>"
    f"<h1>{'This week’s plan' if workspace == 'Dispatch' else 'Policy evaluation'}</h1>"
    "<p>Review priorities. Set crew capacity. Dispatch with confidence.</p></div>"
    f'<div class="date-block"><span class="eyebrow">DEMO PLANNING CLOCK</span><strong>{datetime.fromisoformat(DEMO_DATE).strftime("%A, %d %B %Y")}</strong></div></div>'
)


@st.fragment(run_every=None if historical else 5)
def dispatch() -> None:
    stale = False
    key = f"live:{policy}:{budget}"
    try:
        view = preview(policy, budget) if historical else fetch_live(API_BASE_URL, policy, budget)
        checked = datetime.now().strftime("%H:%M:%S")
        if not historical:
            st.session_state[key] = (view, checked)
    except DataUnavailable as exc:
        st.warning(str(exc))
        if not historical and key in st.session_state:
            view, checked = st.session_state[key]
            stale = True
        else:
            empty(
                "Dispatch data is unavailable",
                "Choose Historical preview or retry once the service is ready.",
            )
            return
    ids = {item.ticket_id for item in view.queue}
    repair_context = (source, view.revision)
    if st.session_state.get("repair_context") != repair_context:
        st.session_state.pop("repair_ack", None)
        st.session_state["repair_context"] = repair_context
    if st.session_state.get("selected_ticket", "") not in ids:
        st.session_state["selected_ticket"] = ""
    st.session_state.setdefault("selected_ticket", "")
    if feedback := st.session_state.pop("feedback", None):
        getattr(st, feedback[0])(feedback[1])
    badge = (
        "Historical preview" if historical else ("Connection lost · saved view" if stale else "Live dispatch")
    )
    detail = (
        f"{len(view.queue)} OPEN LIGHTS · SIMULATED REPAIRS"
        if historical
        else f"Last successful update {checked} · Revision {view.revision}"
    )
    markup(
        f'<div class="status-line"><span class="status-badge {"live" if not historical and not stale else ""}"><i class="status-dot"></i>{badge}</span><span>{detail}</span></div>'
    )
    with st.container(key="overview-metrics"):
        a, b, c = st.columns(3)
        with a:
            metric("Planned visits", str(view.plan.lights_planned), "Selected for the crew route", True)
        with b:
            metric(
                "Crew-hours allocated",
                f"{view.plan.minutes_used / 60:.1f}",
                f"of {WEEKLY_CREW_MINUTES * budget / 100 / 60:.1f} available",
            )
        with c:
            metric("Waiting backlog", str(view.plan.skipped_count), "Carried to a later repair week")
    render_review(view, historical, stale)
    communities = ["All communities"] + sorted({item.comm_name for item in view.queue})
    if st.session_state.get("community", "All communities") not in communities:
        st.session_state["community"] = "All communities"
    community = st.selectbox(
        "Community", communities, format_func=lambda value: value.title(), key="community"
    )
    map_col, detail_col = st.columns([1.9, 1], gap="medium")
    with map_col, st.container(border=True, key="city-panel"):
        render_map(view, community)
    with detail_col, st.container(border=True, key="detail-panel"):
        render_detail(view, historical, stale)
    render_queue(view, community, historical)
    render_impact(view, budget)
    if not historical:
        with st.expander("Recent activity"):
            if not view.events_available:
                st.caption("Activity is temporarily unavailable.")
            for event in view.events[:4]:
                st.caption(
                    f"{event.at.strftime('%d %b · %H:%M:%S')} · {event.type.replace('_', ' ').title()}"
                )
                st.write(event.message)
    markup(
        '<div class="page-footer"><span>LAMPLIGHTER · STREET LIGHTING OPERATIONS</span><span>Source: City of Calgary open data · Open Government Licence</span></div>'
    )


if workspace == "Evaluation":
    render_evaluation()
else:
    dispatch()
