"""Interactive geographic view of the selected repair queue."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st


def render_map(lights: list[dict[str, Any]], depot: tuple[float, float] | None = None) -> dict | None:
    valid = []
    for item in lights:
        try:
            lat, lon, rank = float(item["lat"]), float(item["lon"]), int(item["rank"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            row = {**item, "lat": lat, "lon": lon, "rank": rank}
            row["_color"] = (
                [239, 68, 68, 220]
                if rank <= 10
                else [245, 158, 11, 210]
                if rank <= 50
                else [250, 204, 21, 200]
            )
            valid.append(row)
        except (KeyError, TypeError, ValueError):
            continue
    if not valid:
        st.info("No mappable open lights are available yet.")
        return None
    # Bound browser work while retaining the full queue in the table.
    data = pd.DataFrame(valid[:200])
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=data,
        get_position="[lon, lat]",
        get_radius=38,
        get_fill_color="_color",
        get_line_color=[255, 255, 255, 220],
        line_width_min_pixels=1,
        radius_min_pixels=5,
        radius_max_pixels=14,
        pickable=True,
        auto_highlight=True,
    )
    layers = [layer]
    if depot:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=pd.DataFrame([{"lat": depot[0], "lon": depot[1]}]),
                get_position="[lon, lat]",
                get_radius=90,
                get_fill_color=[124, 58, 237, 220],
                radius_min_pixels=9,
                radius_max_pixels=14,
                stroked=True,
                get_line_color=[255, 255, 255, 255],
            )
        )
    center_lat = float(data["lat"].median())
    center_lon = float(data["lon"].median())
    deck = pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=10.7, pitch=0),
        tooltip={
            "html": "<b>#{rank} · {ticket_id}</b><br/>Score: {score}<br/>Community: {comm_name}<br/>Reasons: {reasons}<br/>Fix: {expected_fix_date}",
            "style": {"backgroundColor": "#003366", "color": "white", "fontSize": "12px"},
        },
    )
    st.caption("● Top 10 priority  ·  ● Ranks 11–50  ·  ● Remaining queue  ·  Purple marker: assumed depot")
    try:
        result = st.pydeck_chart(
            deck,
            use_container_width=True,
            height=520,
            on_select="rerun",
            selection_mode="single-object",
            key="queue_map",
        )
        selection = getattr(result, "selection", None)
        objs = getattr(selection, "objects", {}) if selection else {}
        if isinstance(selection, dict):
            objs = selection.get("objects", {})
        picks = [item for values in objs.values() for item in values] if isinstance(objs, dict) else []
        return picks[0] if picks else None
    except TypeError:
        st.pydeck_chart(deck, use_container_width=True, height=520, key="queue_map")
        return None
