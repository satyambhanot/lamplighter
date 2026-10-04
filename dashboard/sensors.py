"""Sensors workspace: pole readings, fault detection and reporting to dispatch.

Two data sources:

* Simulated fleet: poles at real Calgary 311 locations, faults that start
  shortly before the real 311 call, and SYNTHETIC lamp-current readings.
* Uploaded time series: a real readings file the user provides. The same
  detector runs on it; there is no ground truth to score it against.

Detected faults can be sent to the live dispatch queue through the same
``POST /report`` route the voice agent uses, so a sensor alarm is ranked
and planned like a resident's call.
"""

from __future__ import annotations

import html
import io

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st

from config import VOICE_SHARED_SECRET_HEADER
from engine import sensors

COLORS = {
    "healthy": [90, 150, 90],
    "fault caught": [220, 60, 50],
    "fault missed": [240, 170, 30],
    "false alarm": [150, 90, 200],
    "alarm": [220, 60, 50],
    "no alarm": [90, 150, 90],
}
SIM_SOURCE = "Simulated fleet"
UPLOAD_SOURCE = "Upload a time series"
MAX_SEND = 25


def _card(label: str, value: str, detail: str, accent: bool = False) -> None:
    st.markdown(
        f'<div class="metric-card {"accent" if accent else ""}"><div class="metric-label">{html.escape(label)}</div>'
        f'<div class="metric-value">{html.escape(value)}</div><div class="metric-sub">{html.escape(detail)}</div></div>',
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner="Simulating the pole fleet...")
def cached_simulation(start: str, days: int, n_poles: int, seed: int):
    poles, readings, _faults, alarms, events, summary = sensors.run_simulation(
        pd.Timestamp(start), days, n_poles, seed
    )
    return poles, readings, alarms, events, summary


@st.cache_data(show_spinner="Reading the file and looking for faults...")
def cached_upload(data: bytes, ts_col: str, id_col: str | None, value_col: str):
    raw = pd.read_csv(io.BytesIO(data))
    return sensors.run_uploaded(raw, ts_col, id_col, value_col)


def _guess(columns: list[str], words: tuple[str, ...], fallback: int = 0) -> int:
    for i, name in enumerate(columns):
        if any(word in name.lower() for word in words):
            return i
    return min(fallback, len(columns) - 1)


def _source_notice(source: str) -> None:
    if source == SIM_SOURCE:
        st.warning(
            "Simulation. Pole locations and fault dates come from real Calgary 311 tickets. "
            "The lamp-current readings are synthetic, and no sensor hardware is involved.",
            icon="⚠️",
        )
    else:
        st.info(
            "Your readings are analyzed as uploaded. The detector assumes lamps burn from about 19:00 to 06:30; "
            "device locations are placeholders at real 311 locations because the file has no Calgary coordinates."
        )


def _simulated_inputs():
    with st.expander("Simulation settings"):
        a, b, c, d = st.columns(4)
        n_poles = a.slider("Poles", 30, 200, 150, step=10, key="sensor-poles")
        days = b.slider("Days", 14, 56, 56, step=7, key="sensor-days")
        start = c.date_input("Start date", pd.Timestamp("2026-07-01"), key="sensor-start").isoformat()
        seed = int(d.number_input("Random seed", 0, 9999, 42, key="sensor-seed"))
    return cached_simulation(start, days, n_poles, seed)


def _upload_inputs():
    file = st.file_uploader(
        "Time-series CSV (one row per reading)", type=["csv"], key="sensor-file", help="At most about 200 MB."
    )
    if file is None:
        st.info(
            "Choose a CSV with a timestamp column, a numeric current or power column, and optionally a device ID column."
        )
        return None
    data = file.getvalue()
    try:
        head = pd.read_csv(io.BytesIO(data), nrows=500)
    except (ValueError, pd.errors.ParserError) as exc:
        st.error(f"That file could not be read as a CSV: {exc}")
        return None
    columns = [str(c) for c in head.columns]
    a, b, c = st.columns(3)
    ts_col = a.selectbox(
        "Timestamp column", columns, index=_guess(columns, ("time", "date")), key="sensor-ts"
    )
    value_col = b.selectbox(
        "Current or power column",
        columns,
        index=_guess(columns, ("amp", "current", "power", "watt", "kw", "value"), 1),
        key="sensor-value",
    )
    id_options = ["(single device)"] + columns
    id_guess = _guess(columns, ("id", "device", "pole", "sensor", "lamp", "light"), -1)
    id_default = (
        0
        if not any(
            w in columns[id_guess].lower() for w in ("id", "device", "pole", "sensor", "lamp", "light")
        )
        else id_guess + 1
    )
    id_choice = c.selectbox("Device ID column", id_options, index=id_default, key="sensor-id")
    id_col = None if id_choice == "(single device)" else id_choice
    try:
        return cached_upload(data, ts_col, id_col, value_col)
    except ValueError as exc:
        st.error(str(exc))
        return None


def _pole_status(poles: pd.DataFrame, alarms: pd.DataFrame, events: pd.DataFrame | None) -> pd.DataFrame:
    pts = poles.copy()
    alarmed = set(alarms["pole_id"])
    if events is None:
        pts["status"] = ["alarm" if p in alarmed else "no alarm" for p in pts["pole_id"]]
        pts["tip"] = (
            pts["pole_id"]
            .map(alarms.drop_duplicates("pole_id").set_index("pole_id")["kind"].map(sensors.FAULT_LABELS))
            .fillna("OK")
        )
    else:
        caught = set(events.loc[events["detected_at"].notna(), "pole_id"])
        faulty = dict(zip(events["pole_id"], events["fault_kind"], strict=False))
        status = []
        for p in pts["pole_id"]:
            if p in caught:
                status.append("fault caught")
            elif p in faulty:
                status.append("fault missed")
            elif p in alarmed:
                status.append("false alarm")
            else:
                status.append("healthy")
        pts["status"] = status
        pts["tip"] = pts["pole_id"].map(lambda p: sensors.FAULT_LABELS.get(faulty.get(p), "OK"))
    pts["color"] = pts["status"].map(COLORS)
    return pts


def _map(pts: pd.DataFrame) -> None:
    st.pydeck_chart(
        pdk.Deck(
            map_style=None,
            initial_view_state=pdk.ViewState(
                latitude=float(pts["latitude"].mean()), longitude=float(pts["longitude"].mean()), zoom=10.2
            ),
            layers=[
                pdk.Layer(
                    "ScatterplotLayer",
                    pts,
                    get_position="[longitude, latitude]",
                    get_fill_color="color",
                    get_radius=170,
                    pickable=True,
                )
            ],
            tooltip={"text": "{pole_id}\n{tip} ({status})"},
        )
    )
    legend = sorted(set(pts["status"]))
    st.caption(" · ".join(legend))


def _pole_chart(readings: pd.DataFrame, alarms: pd.DataFrame, events: pd.DataFrame | None) -> None:
    alarmed = list(dict.fromkeys(alarms["pole_id"]))
    others = [p for p in readings["pole_id"].unique() if p not in set(alarmed)][:5]
    choices = alarmed + others
    if not choices:
        return
    label = {a.pole_id: sensors.FAULT_LABELS[a.kind] for a in alarms.drop_duplicates("pole_id").itertuples()}
    pole_id = st.selectbox(
        "Look at one pole",
        choices,
        format_func=lambda p: f"{p} · {label.get(p, 'no alarm')}",
        key="sensor-pole",
    )
    series = readings[readings["pole_id"] == pole_id].set_index("ts")["amps"].sort_index()
    mine = alarms[alarms["pole_id"] == pole_id]
    if mine.empty:
        window = series.iloc[: 96 * 4]
        st.write("No alarm on this pole: the lamp draws about the same current every night and none by day.")
    else:
        when = mine["detected_at"].min()
        window = series[when - pd.Timedelta(days=2) : when + pd.Timedelta(days=3)]
        text = f"First alarm: **{sensors.FAULT_LABELS[mine.iloc[0]['kind']]}** at **{when:%b %d %H:%M}**."
        if events is not None and pole_id in set(events["pole_id"]):
            row = events[events["pole_id"] == pole_id].iloc[0]
            text += f" The fault began {row['fault_start']:%b %d %H:%M}; a resident's 311 call was {row['ticket_date']:%b %d}."
        st.write(text)
    st.line_chart(window.rename("Lamp current (A equivalent)"))


def _send(base_url: str, secret: str, reports: list[dict]) -> list[dict]:
    rows = []
    for report in reports:
        payload = {k: report[k] for k in ("phone", "location_text", "description")}
        response = requests.post(
            f"{base_url.rstrip('/')}/report",
            json=payload,
            headers={VOICE_SHARED_SECRET_HEADER: secret},
            timeout=(1, 20),
        )
        if response.status_code == 401:
            raise PermissionError(
                "The API rejected the access key. Run make configure, then restart make api."
            )
        response.raise_for_status()
        body = response.json()
        rows.append(
            {
                "Pole": report["pole_id"],
                "Result": "Merged into an existing light" if body.get("merged") else "New light",
                "Priority": body.get("rank"),
                "Expected fix": body.get("expected_fix_date"),
                "Message": body.get("message"),
            }
        )
    return rows


def _dispatch_panel(
    alarms: pd.DataFrame, poles: pd.DataFrame, simulated: bool, base_url: str, secret: str
) -> None:
    st.subheader("Report to dispatch")
    st.caption(
        "Each alarm becomes a report in the live queue, ranked and planned like a resident's call. "
        "Switch the Dispatch workspace to Live dispatch to see it. Run make reset afterward to clear test reports."
    )
    if alarms.empty:
        st.info("No alarms to send.")
        return
    sent = st.session_state.setdefault("sensor_sent", set())
    reports = [r for r in sensors.alarm_reports(alarms.sort_values("detected_at"), poles, simulated)]
    pending = [r for r in reports if r["pole_id"] not in sent]
    if not pending:
        st.success("Every alarm has been sent.")
        return
    count = st.number_input(
        "How many alarms to send",
        1,
        min(MAX_SEND, len(pending)),
        min(3, len(pending)),
        key="sensor-count",
        help=f"Sent in time order, at most {MAX_SEND} at once. {len(pending)} alarms are waiting.",
    )
    if st.button("Send to dispatch", key="sensor-send", type="primary"):
        if not secret:
            st.error("No voice access key is configured. Run make configure, then restart the dashboard.")
            return
        batch = pending[: int(count)]
        try:
            with st.spinner("Sending..."):
                rows = _send(base_url, secret, batch)
        except PermissionError as exc:
            st.error(str(exc))
            return
        except requests.RequestException:
            st.error("Could not reach the dispatch API. Start it with make api, then try again.")
            return
        sent.update(r["pole_id"] for r in batch)
        st.success(f"Sent {len(rows)} alarm(s) to dispatch.")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render_sensors(api_base_url: str, voice_secret: str) -> None:
    source = st.radio(
        "Data source",
        [SIM_SOURCE, UPLOAD_SOURCE],
        horizontal=True,
        key="sensor-source",
        label_visibility="collapsed",
    )
    _source_notice(source)

    events = None
    if source == SIM_SOURCE:
        poles, readings, alarms, events, summary = _simulated_inputs()
        simulated = True
    else:
        result = _upload_inputs()
        if result is None:
            return
        poles, readings, alarms = result
        simulated = False

    if source == SIM_SOURCE:
        if summary["faults_injected"] == 0:
            st.info("No 311 tickets fall in this window. Try the default start date or more days.")
            return
        a, b, c, d = st.columns(4)
        with a:
            _card(
                "Faults injected", str(summary["faults_injected"]), f"across {summary['poles']} poles", True
            )
        with b:
            _card(
                "Caught by sensors",
                f"{summary['recall']:.0%}",
                f"{summary['faults_detected']} faults; {summary['false_alarms']} false alarms",
            )
        with c:
            _card(
                "Detection delay",
                f"{summary['median_detection_delay_h']:.1f} h",
                "median, after the fault starts",
            )
        with d:
            _card(
                "Ahead of the 311 call",
                f"{summary['median_lead_over_311_h']:.0f} h",
                "median lead over the resident",
            )
    else:
        kinds = alarms["kind"].map(sensors.FAULT_LABELS).value_counts()
        a, b, c = st.columns(3)
        with a:
            _card("Devices", str(readings["pole_id"].nunique()), f"{len(readings):,} readings", True)
        with b:
            _card("Alarms", str(len(alarms)), f"on {alarms['pole_id'].nunique()} devices")
        with c:
            _card(
                "Most common fault",
                kinds.index[0] if len(kinds) else "None",
                f"{int(kinds.iloc[0])} alarms" if len(kinds) else "no faults found",
            )

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Fleet map")
        _map(_pole_status(poles, alarms, events))
    with right:
        st.subheader("Alarms by type")
        by_kind = alarms["kind"].map(sensors.FAULT_LABELS).value_counts()
        if by_kind.empty:
            st.info("No faults detected.")
        else:
            st.bar_chart(by_kind)

    _pole_chart(readings, alarms, events)
    _dispatch_panel(alarms, poles, simulated, api_base_url, voice_secret)

    with st.expander("All alarms"):
        table = alarms.merge(poles[["pole_id", "comm_name"]], on="pole_id", how="left")
        table["kind"] = table["kind"].map(sensors.FAULT_LABELS)
        st.dataframe(
            table.rename(
                columns={
                    "pole_id": "Pole",
                    "kind": "Fault",
                    "detected_at": "Detected",
                    "comm_name": "Community",
                }
            ),
            hide_index=True,
            width="stretch",
        )
