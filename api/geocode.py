"""Geocoding: demo address list first, Nominatim second, cached.

The demo must never depend on an outside service, so config.DEMO_ADDRESSES
is always checked before any network call.
"""

from __future__ import annotations

import logging
import sqlite3
import time

import requests

from api import db
from config import DEMO_ADDRESSES, NOMINATIM_RATE_LIMIT_SECONDS, NOMINATIM_USER_AGENT

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_last_nominatim_call: float = 0.0


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
    query = location_text.strip().lower()
    if not query:
        return None

    for key, coords in DEMO_ADDRESSES.items():
        if key in query or query in key:
            return coords

    cached = db.get_geocode_cache(conn, query)
    if cached:
        return (cached["lat"], cached["lon"])

    result = _geocode_nominatim(query)
    if result is not None:
        db.set_geocode_cache(conn, query, result[0], result[1], "nominatim")
    return result


def _geocode_nominatim(location_text: str) -> tuple[float, float] | None:
    """Call Nominatim directly. Private: always go through geocode()."""
    global _last_nominatim_call

    elapsed = time.monotonic() - _last_nominatim_call
    if elapsed < NOMINATIM_RATE_LIMIT_SECONDS:
        time.sleep(NOMINATIM_RATE_LIMIT_SECONDS - elapsed)

    try:
        response = requests.get(
            NOMINATIM_URL,
            params={"q": f"{location_text}, Calgary, Alberta", "format": "json", "limit": 1},
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=5,
        )
        _last_nominatim_call = time.monotonic()
        response.raise_for_status()
        results = response.json()
    except requests.RequestException:
        logger.exception("Nominatim request failed for %r", location_text)
        return None

    if not results:
        return None
    return (float(results[0]["lat"]), float(results[0]["lon"]))
