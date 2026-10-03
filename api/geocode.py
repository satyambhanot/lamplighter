"""Geocoding: demo address list first, Nominatim second, cached.

The demo must never depend on an outside service, so config.DEMO_ADDRESSES
is always checked before any network call. Implemented in Phase 6.
"""

from __future__ import annotations

import sqlite3


def geocode(conn: sqlite3.Connection, location_text: str) -> tuple[float, float] | None:
    """Resolve free-text location to (lat, lon).

    Order: config.DEMO_ADDRESSES exact/fuzzy match -> geocode_cache table
    -> Nominatim (rate-limited to config.NOMINATIM_RATE_LIMIT_SECONDS,
    cached on success).

    Args:
        conn: Open DB connection, used for the geocode cache.
        location_text: Caller-provided address or intersection.

    Returns:
        (lat, lon), or None if nothing could resolve the location — the
        caller should then set needs_clarification=True rather than error.
    """
    raise NotImplementedError("Phase 6")


def _geocode_nominatim(location_text: str) -> tuple[float, float] | None:
    """Call Nominatim directly. Private: always go through geocode()."""
    raise NotImplementedError("Phase 6")
