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
from dashboard.icons import icon
from dashboard.maps import build_map, reference_layers, ticket_from_selection

load_dotenv(ROOT_DIR / ".env")
API_BASE_URL = os.environ.get("LAMPLIGHTER_API_URL", "http://localhost:8000")
DISPATCH_TOKEN = os.environ.get("DISPATCH_SHARED_SECRET", "")
st.set_page_config(page_title="Lamplighter · Dispatch", page_icon="◉", layout="wide")
st.markdown(f"<style>{Path(__file__).with_name('styles.css').read_text()}</style>", unsafe_allow_html=True)


def markup(value: str) -> None:
    st.markdown(value, unsafe_allow_html=True)


def panel(title: str, detail: str = "", icon_name: str = "") -> None:
    lead = icon(icon_name, 16) if icon_name else ""
    markup(
        f'<div class="panel-head"><span class="panel-title">{lead}{html.escape(title)}</span>'
        f'<span class="panel-meta">{html.escape(detail)}</span></div>'
    )


def empty(title: str, detail: str, icon_name: str = "search") -> None:
    markup(
        f'<div class="empty-state">{icon(icon_name, 26)}<strong>{html.escape(title)}</strong>'
        f'<p>{html.escape(detail)}</p></div>'
    )


def metric(label: str, value: str, detail: str, accent: bool = False, icon_name: str = "") -> None:
    lead = icon(icon_name, 14) if icon_name else ""
    markup(
        f'<div class="metric-card {"accent" if accent else ""}"><div class="metric-label">{lead}{html.escape(label)}</div>'
        f'<div class="metric-value">{html.escape(value)}</div><div class="metric-sub">{html.escape(detail)}</div></div>'
    )


def skeleton_cards(n: int = 3) -> None:
    markup('<div style="display:flex;gap:16px">' + '<div class="skeleton skeleton-card" style="flex:1"></div>' * n + "</div>")


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
    panel("City map", "ROUTE & REPORTS", "map")
    flags = {}
    with st.expander("Map layers", expanded=False):
        cols = st.columns(3)
        for i, (name, label, default) in enumerate(
            zip(
                ["planned", "waiting", "schools", "transit", "route"],
                ["Planned", "Waiting", "Schools", "Transit", "Visit order"],
                [True, True, False, False, True],
                strict=True,
            )
        ):
            flags[name] = cols[i % 3].checkbox(label, value=default, key=f"layer-{name}")
        focus = st.checkbox("Focus on selected light", key="focus-map")
    if not view.queue:
        empty("No lights in this view", "There are no open reports to plan.", "map-pin")
        return
    deck = build_map(view, st.session_state["selected_ticket"], community, flags, references(), focus)
    st.pydeck_chart(
        deck,
        key="dispatch-map",
        on_select=select_map,
        selection_mode="single-object",
        width="stretch",
        height=520,
    )
    markup(
        '<div class="map-legend"><span><i class="legend-dot" style="background:#2563eb"></i>Numbered visit</span>'
        '<span><i class="legend-dot" style="background:#6b809a"></i>Waiting</span>'
        '<span><i class="legend-dot" style="background:#0d9488"></i>Selected</span>'
        '<span><i class="legend-dot" style="background:#bd3d54"></i>Removed vs 100%</span></div>'
    )
    st.caption("Lines show visit order; travel estimates use straight-line distances, not road directions.")


def render_history(ticket: str, view: DispatchView, historical: bool) -> None:
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


def render_detail(view: DispatchView, historical: bool, stale: bool) -> None:
    panel("Light details", "SELECTED REPORT", "map-pin")
    ids = [item.ticket_id for item in view.queue]
    by_id = {item.ticket_id: item for item in view.queue}
    confirmed = view.confirmed_plan
    completed = {
        visit.ticket_id: visit
        for visit in (confirmed.visits if confirmed else [])
        if visit.status == "fixed" and visit.ticket_id not in by_id
    }
    ticket = st.selectbox(
        "Inspect light",
        [""] + ids + list(completed),
        key="selected_ticket",
        format_func=lambda value: (
            f"{value} · {by_id[value].comm_name.title()}"
            if value in by_id
            else f"{value} · {completed[value].comm_name.title()} · Repaired"
            if value in completed
            else "Select a light from the worklist or map"
        ),
        on_change=lambda: st.session_state.pop("repair_ack", None),
        label_visibility="collapsed",
    )
    if not ticket:
        empty("Select a light", "Inspect its reports, priority reasons, and planned route position.", "map-pin")
        return
    if ticket in completed:
        visit = completed[ticket]
        markup(f'<div class="detail-title">{html.escape(visit.comm_name.title())}</div>')
        st.success(f"Repair recorded · stop {visit.position}")
        st.caption(
            f"Ticket {ticket} · completed {visit.fixed_at.strftime('%d %b %Y') if visit.fixed_at else 'date unavailable'}"
        )
        render_history(ticket, view, historical)
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
    render_history(ticket, view, historical)
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


def render_worklist(view: DispatchView, community: str) -> None:
    with st.container(border=True, key="worklist-panel"):
        panel("Worklist", f"{len(view.queue)} OPEN LIGHTS", "list")
        search = st.text_input(
            "Search lights",
            placeholder="Search ticket, area, or reason",
            key="queue-search",
            label_visibility="collapsed",
        )
        tabs = st.tabs([f"Route · {view.plan.lights_planned}", f"Waiting · {view.plan.skipped_count}"])
        for tab, status in zip(tabs, ["planned", "waiting"], strict=True):
            with tab:
                rows = queue_rows(view, community, search, status=status)
                if not rows:
                    empty(
                        "No matching reports",
                        "Try another area or search term." if search else "No lights in this worklist.",
                    )
                    continue
                frame = pd.DataFrame(
                    [
                        {
                            "Stop": row["Route stop"] or "—",
                            "Area": row["Community"],
                            "Priority": f"#{row['Priority']}",
                            "Reports": row["Calls"],
                        }
                        for row in rows
                    ],
                    index=[row["Ticket"] for row in rows],
                )
                selected = st.session_state["selected_ticket"]
                index_position = {ticket_id: i for i, ticket_id in enumerate(frame.index)}

                def _row_style(row, selected=selected, index_position=index_position):
                    if row.name == selected:
                        return ["background-color: #dbe9fd; font-weight: 600"] * len(row)
                    zebra = index_position[row.name] % 2 == 1
                    return ["background-color: #f7f9fc" if zebra else ""] * len(row)

                styled = frame.style.apply(_row_style, axis=1)
                table_key = (
                    f"worklist-{status}-{source}-{policy}-{budget}-{view.revision}-{community}-{search}"
                )
                st.dataframe(
                    styled,
                    hide_index=True,
                    width="stretch",
                    key=table_key,
                    on_select=lambda k=table_key, ids=list(frame.index): select_row(k, ids),
                    selection_mode="single-row",
                    height=min(340, 38 + 35 * len(rows)),
                )
                st.caption("Select a row to inspect its reports and route status.")


def render_queue(view: DispatchView, community: str, historical: bool) -> None:
    with st.expander("All route data and exports"):
        search = st.session_state.get("queue-search", "")
        tabs = st.tabs(["Planned visits", "Waiting backlog"])
        for tab, status in zip(tabs, ["planned", "waiting"], strict=True):
            with tab:
                rows = queue_rows(view, community, search, status=status)
                if rows:
                    st.dataframe(
                        pd.DataFrame(rows),
                        hide_index=True,
                        width="stretch",
                        height=min(360, 38 + 35 * len(rows)),
                        column_config={
                            "Priority": st.column_config.NumberColumn(format="#%d", width="small"),
                            "Route stop": st.column_config.NumberColumn(format="%d", width="small"),
                            "Dispatch reason": st.column_config.TextColumn(width="large"),
                        },
                    )
                else:
                    st.caption("No reports match the current filters.")
                st.download_button(
                    f"Export {status} CSV",
                    data=export_csv(rows),
                    mime="text/csv",
                    file_name=f"lamplighter-{'preview' if historical else 'live'}-{policy}-{status}.csv",
                    key=f"export-{status}",
                )
        st.caption("Priority sets which lights are chosen. Stop number is the crew's visit order.")


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


def render_hazards(view: DispatchView, stale: bool) -> None:
    if not view.hazards:
        return
    with st.container(border=True, key="hazard-panel"):
        st.error(f"{len(view.hazards)} urgent report{'s' if len(view.hazards) != 1 else ''} need a handoff")
        st.caption(
            "Keep hazards outside the routine crew route. Contact emergency services for immediate danger."
        )
        for hazard in view.hazards:
            with st.expander(f"{hazard.location_text or hazard.ticket_id} · {hazard.ticket_id}"):
                st.write(hazard.description or "No description was recorded.")
                st.caption(
                    f"Reported {hazard.first_reported.strftime('%d %b %Y')} · {hazard.call_count} call(s)"
                )
                note = st.text_input(
                    "Handoff destination and reference",
                    key=f"hazard-note-{hazard.ticket_id}",
                    placeholder="e.g. Utilities emergency desk · case 1234",
                )
                if st.button(
                    "Record hazard handoff",
                    key=f"hazard-handoff-{hazard.ticket_id}",
                    disabled=stale or not DISPATCH_TOKEN or len(note.strip()) < 3,
                ):
                    write(
                        f"hazards/{hazard.ticket_id}/handoff",
                        {"revision": view.revision, "note": note},
                        f"Handoff recorded for {hazard.ticket_id}.",
                    )


def render_review(view: DispatchView, historical: bool, stale: bool) -> None:
    context = (source, policy, budget, view.revision, view.plan.candidate_id)
    if "review_context" in st.session_state and st.session_state["review_context"] != context:
        clear_review()
    confirmed = view.confirmed_plan
    with st.container(border=True, key="plan-command"):
        panel("Proposed route", f"{POLICY_LABELS[policy].upper()} · {budget}% CAPACITY", "route")
        if confirmed and confirmed.status == "needs_review":
            st.warning(
                "A report changed the queue after confirmation. Review the new route before recording repairs."
            )
        elif confirmed and confirmed.status == "confirmed":
            st.caption(
                f"Crew route {confirmed.id} is confirmed · {len(confirmed.remaining_ids)} visits remain"
            )
        else:
            st.caption("Review the proposed stops and capacity before dispatching the crew.")
        st.write(view.plan.note)
        if st.button(
            "Review proposed route →",
            type="primary",
            disabled=not view.plan.queue or stale,
            key="review-plan",
        ):
            st.session_state["review_context"] = context
        if st.session_state.get("review_context") == context:
            st.divider()
            panel(
                "Route review",
                f"{view.plan.lights_planned} VISITS · {view.plan.minutes_used / 60:.1f} CREW HOURS",
                "check-circle",
            )
            impact = capacity_impact(view)
            st.caption(
                f"{view.plan.skipped_count} waiting · {len(impact['removed'])} removed and "
                f"{len(impact['added'])} added compared with the full-capacity route"
            )
            st.dataframe(
                pd.DataFrame(queue_rows(view, status="planned")),
                hide_index=True,
                width="stretch",
                height=280,
            )
            if historical:
                st.info("This is a historical preview. Select Live dispatch to confirm and record crew work.")
            elif not DISPATCH_TOKEN:
                st.info("Run make configure, then restart the dashboard and API for dispatcher access.")
            elif not stale and view.revision is not None and view.plan.candidate_id:
                ack = st.checkbox("I reviewed the stops and capacity change", key="review_ack")
                if st.button("Confirm crew route", type="primary", disabled=not ack, key="confirm-plan"):
                    write(
                        "plans/confirm",
                        {
                            "revision": view.revision,
                            "policy": policy,
                            "budget_pct": budget / 100,
                            "candidate_id": view.plan.candidate_id,
                        },
                        "Crew route confirmed. Select a visit to record its completed repair.",
                    )
            elif not stale:
                st.warning("This route cannot be confirmed until the service supplies a review token.")


def render_confirmed(view: DispatchView) -> None:
    confirmed = view.confirmed_plan
    if not confirmed:
        return
    with st.expander(
        f"Confirmed assignments · {len(confirmed.remaining_ids)} remaining · {confirmed.completed_count} repaired"
    ):
        st.caption(
            f"{POLICY_LABELS[confirmed.policy]} · {confirmed.budget_pct:.0%} capacity · "
            f"plan {confirmed.id}. Original stop numbers stay fixed."
        )
        rows = [
            {
                "Stop": visit.position,
                "Ticket": visit.ticket_id,
                "Area": visit.comm_name.title(),
                "Status": visit.status.title(),
            }
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
                height=320,
            )


def render_evaluation() -> None:
    st.info(
        "Historical experiments are provisional. Risk weighting and reporting-window defects are documented in the engineering review; these are not live performance metrics."
    )
    rows = load_evaluation()
    if rows:
        chart_a, chart_b = st.columns(2)
        with chart_a:
            st.image(ROOT_DIR / "results" / "policy_comparison.png", caption="Policy comparison")
        with chart_b:
            st.image(ROOT_DIR / "results" / "sensitivity.png", caption="Capacity sensitivity")
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
        f'<div class="brand"><span class="brand-mark">{icon("lamp", 21, color="#0e2b42", stroke=2)}</span>'
        '<span class="brand-name">lamplighter</span></div><div class="brand-sub">Street lighting operations</div>'
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
    # A branded skeleton only on this session's very first load — showing
    # it on every periodic live refresh too would flicker, not feel premium.
    first_load = "dispatch_loaded" not in st.session_state
    loading_placeholder = st.empty()
    if first_load:
        with loading_placeholder.container():
            skeleton_cards()

    stale = False
    key = f"live:{policy}:{budget}"
    try:
        view = (
            preview(policy, budget)
            if historical
            else fetch_live(API_BASE_URL, policy, budget, DISPATCH_TOKEN)
        )
        checked = datetime.now().strftime("%H:%M:%S")
        if not historical:
            st.session_state[key] = (view, checked)
    except DataUnavailable as exc:
        loading_placeholder.empty()
        st.session_state["dispatch_loaded"] = True
        st.warning(str(exc))
        if not historical and key in st.session_state:
            view, checked = st.session_state[key]
            stale = True
        else:
            empty(
                "Dispatch data is unavailable",
                "Choose Historical preview or retry once the service is ready.",
                "alert-triangle",
            )
            return
    loading_placeholder.empty()
    st.session_state["dispatch_loaded"] = True
    ids = {item.ticket_id for item in view.queue}
    if view.confirmed_plan:
        ids.update(visit.ticket_id for visit in view.confirmed_plan.visits if visit.status == "fixed")
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
    if not historical:
        render_hazards(view, stale)
    with st.container(key="overview-metrics"):
        a, b, c = st.columns(3)
        with a:
            metric("Planned visits", str(view.plan.lights_planned), "Selected for the crew route", True, "route")
        with b:
            metric(
                "Crew-hours allocated",
                f"{view.plan.minutes_used / 60:.1f}",
                f"of {WEEKLY_CREW_MINUTES * budget / 100 / 60:.1f} available",
                icon_name="clock",
            )
        with c:
            metric("Waiting backlog", str(view.plan.skipped_count), "Carried to a later repair week", icon_name="alert-triangle")
    render_review(view, historical, stale)
    communities = ["All communities"] + sorted({item.comm_name for item in view.queue})
    if st.session_state.get("community", "All communities") not in communities:
        st.session_state["community"] = "All communities"
    community = st.selectbox(
        "Community", communities, format_func=lambda value: value.title(), key="community"
    )
    work_col, map_col = st.columns([1, 1.35], gap="medium")
    with work_col:
        render_worklist(view, community)
        with st.container(border=True, key="detail-panel"):
            render_detail(view, historical, stale)
    with map_col, st.container(border=True, key="city-panel"):
        render_map(view, community)
    render_confirmed(view)
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
