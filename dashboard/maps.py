"""Selectable map layers and stable ticket identities for the dispatch workspace."""

from __future__ import annotations

import pandas as pd
import pydeck as pdk

from config import DEPOT_LAT, DEPOT_LON, SCHOOLS_CSV, TRANSIT_STOPS_CSV
from dashboard.data import DispatchView, capacity_impact


def ticket_from_selection(state: dict) -> str | None:
    for objects in state.get("selection", {}).get("objects", {}).values():
        for item in objects:
            if item.get("ticket_id"):
                return str(item["ticket_id"])
    return None


def reference_layers() -> dict[str, list[dict]]:
    result = {}
    for name, path, label in (("schools", SCHOOLS_CSV, "name"), ("transit", TRANSIT_STOPS_CSV, "stop_name")):
        if path.exists():
            frame = pd.read_csv(path).dropna(subset=["latitude", "longitude"])
            result[name] = [
                {
                    "lat": float(row.latitude),
                    "lon": float(row.longitude),
                    "display": str(getattr(row, label, name.title())),
                    "dispatch": name.title(),
                    "ticket_id": "",
                }
                for row in frame.itertuples()
            ]
    return result


def build_map(
    view: DispatchView,
    selected: str,
    community: str,
    flags: dict[str, bool],
    references: dict[str, list[dict]],
    focus: bool = False,
) -> pdk.Deck:
    route = {item.ticket_id: i + 1 for i, item in enumerate(view.plan.queue)}
    removed = {item.ticket_id for item in capacity_impact(view)["removed"]}
    points = []
    for item in view.queue:
        if community != "All communities" and item.comm_name != community:
            continue
        planned = item.ticket_id in route
        if not flags.get("planned", True) and planned or not flags.get("waiting", True) and not planned:
            continue
        color = (
            [30, 128, 131, 255]
            if item.ticket_id == selected
            else [187, 90, 68, 230]
            if item.ticket_id in removed
            else [190, 128, 36, 255]
            if planned
            else [113, 132, 150, 190]
        )
        points.append(
            {
                "lat": item.lat,
                "lon": item.lon,
                "display": item.comm_name.title(),
                "ticket_id": item.ticket_id,
                "dispatch": f"Route stop {route[item.ticket_id]}" if planned else "Waiting backlog",
                "label": str(route[item.ticket_id]) if planned else "",
                "color": color,
                "size": 11 if planned or item.ticket_id == selected else 6,
            }
        )
    layers = []
    for name, color in (("schools", [113, 99, 151, 190]), ("transit", [86, 134, 168, 170])):
        if flags.get(name) and references.get(name):
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    id=name,
                    data=references[name],
                    get_position="[lon,lat]",
                    get_fill_color=color,
                    get_radius=25,
                    radius_min_pixels=3,
                    pickable=True,
                )
            )
    # Filtering pins must not redraw artificial shortcuts through hidden stops.
    route_items = view.plan.queue
    if flags.get("route", True) and flags.get("planned", True) and route_items:
        path = (
            [[DEPOT_LON, DEPOT_LAT]]
            + [[item.lon, item.lat] for item in route_items]
            + [[DEPOT_LON, DEPOT_LAT]]
        )
        layers.append(
            pdk.Layer(
                "PathLayer",
                id="route-order",
                data=[{"path": path}],
                get_path="path",
                get_color=[150, 166, 180, 160],
                get_width=2,
                width_units=pdk.types.String("pixels"),
                pickable=False,
            )
        )
    layers.extend(
        [
            pdk.Layer(
                "ScatterplotLayer",
                id="lights",
                data=points,
                get_position="[lon,lat]",
                get_fill_color="color",
                get_radius="size",
                radius_units=pdk.types.String("pixels"),
                stroked=True,
                get_line_color=[255, 255, 255],
                line_width_min_pixels=2,
                pickable=True,
            ),
            pdk.Layer(
                "TextLayer",
                id="stop-labels",
                data=[point for point in points if point["label"]],
                get_position="[lon,lat]",
                get_text="label",
                get_size=11,
                get_color=[255, 255, 255],
                get_text_anchor=pdk.types.String("middle"),
                get_alignment_baseline=pdk.types.String("center"),
                character_set=pdk.types.String("0123456789"),
                pickable=True,
            ),
            pdk.Layer(
                "ScatterplotLayer",
                id="depot",
                data=[
                    {
                        "lat": DEPOT_LAT,
                        "lon": DEPOT_LON,
                        "display": "Crew depot",
                        "dispatch": "Route origin",
                        "ticket_id": "",
                    }
                ],
                get_position="[lon,lat]",
                get_fill_color=[28, 43, 58],
                get_radius=7,
                radius_units=pdk.types.String("pixels"),
                stroked=True,
                get_line_color=[255, 255, 255],
                line_width_min_pixels=2,
                pickable=True,
            ),
        ]
    )
    selected_item = next((item for item in view.queue if item.ticket_id == selected), None)
    if selected_item and focus:
        lat, lon, zoom = selected_item.lat, selected_item.lon, 13
    elif points:
        lat = (min(p["lat"] for p in points) + max(p["lat"] for p in points)) / 2
        lon = (min(p["lon"] for p in points) + max(p["lon"] for p in points)) / 2
        zoom = 9.1 if community == "All communities" else 12
    else:
        lat, lon, zoom = DEPOT_LAT, DEPOT_LON, 9.1
    return pdk.Deck(
        layers=layers,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=zoom),
        tooltip={
            "text": "{display}\n{ticket_id}\n{dispatch}",
            "style": {"backgroundColor": "#1c2b3a", "color": "white", "fontSize": "12px"},
        },
    )
