"""Weekly plan construction: nearest-neighbour routing from the depot."""

from __future__ import annotations

import pandas as pd

from config import DEPOT_LAT, DEPOT_LON, REPAIR_MINUTES, TRAVEL_SPEED_KMH
from engine.geo import haversine_m


def _nn_tour(coords: list[tuple[float, float]]) -> tuple[float, list[int]]:
    """Nearest-neighbour tour from the depot through coords and back.

    Returns (total minutes, visit order as indices into ``coords``).
    """
    if not coords:
        return 0.0, []

    remaining = list(enumerate(coords))
    visit_order: list[int] = []
    total_km = 0.0
    current = (DEPOT_LAT, DEPOT_LON)

    while remaining:
        nearest_pos = min(
            range(len(remaining)),
            key=lambda i: haversine_m(current[0], current[1], *remaining[i][1]),
        )
        idx, coord = remaining.pop(nearest_pos)
        total_km += haversine_m(current[0], current[1], *coord) / 1000
        current = coord
        visit_order.append(idx)

    total_km += haversine_m(current[0], current[1], DEPOT_LAT, DEPOT_LON) / 1000
    travel_minutes = total_km / TRAVEL_SPEED_KMH * 60
    repair_minutes = REPAIR_MINUTES * len(coords)
    return travel_minutes + repair_minutes, visit_order


def _coords_for(queue: pd.DataFrame, light_ids: list[str]) -> list[tuple[float, float]]:
    return [(queue.loc[i, "latitude"], queue.loc[i, "longitude"]) for i in light_ids]


def route_minutes(queue: pd.DataFrame, light_ids: list[str]) -> float:
    """Total minutes (repair + nearest-neighbour travel from the depot
    and back) to visit this set of lights.
    """
    minutes, _ = _nn_tour(_coords_for(queue, light_ids))
    return minutes


def plan_week(queue: pd.DataFrame, order: list[str], budget_min: int) -> list[str]:
    """Build this week's fix list by walking the policy's ranked order.

    Walks ``order`` and adds each light id if a nearest-neighbour route
    from DEPOT through all chosen lights and back still fits
    ``budget_min``. Route time is REPAIR_MINUTES per light plus travel
    minutes (haversine distance / TRAVEL_SPEED_KMH). Lights that don't
    fit are skipped, not deferred within the same week.

    Args:
        queue: Open lights with coordinates, indexed by light id.
        order: Light ids in the policy's ranked order (best first).
        budget_min: Total crew minutes available this week.

    Returns:
        Light ids selected for this week's route, in visit order.
    """
    selected: list[str] = []
    for light_id in order:
        if light_id not in queue.index:
            continue
        candidate = selected + [light_id]
        if route_minutes(queue, candidate) <= budget_min:
            selected = candidate

    _, visit_order = _nn_tour(_coords_for(queue, selected))
    return [selected[i] for i in visit_order]
