"""Weekly plan construction: nearest-neighbour routing from the depot.

Implemented in Phase 2.
"""

from __future__ import annotations

import pandas as pd


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
    raise NotImplementedError("Phase 2")
