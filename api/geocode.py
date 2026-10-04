"""Demo locations, local cache, then a bounded Calgary geocoder."""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
import time

import requests

from api import db
from config import DEMO_ADDRESSES, NOMINATIM_RATE_LIMIT_SECONDS, NOMINATIM_USER_AGENT

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_last_request = 0.0


# Callers say "near City Hall" or "outside the school"; the place is what follows.
_LEADING_PHRASES = re.compile(
    r"^(?:(?:right |just )?(?:near|nearby|outside(?: of)?|in front of|across from|beside|next to|"
    r"close to|by|at|on|behind|opposite)\s+)?(?:the\s+)?"
)


def normalize_location(location_text: str) -> str:
    """Lowercase, collapse spaces and drop a leading "near", "outside the", etc."""
    query = " ".join(location_text.casefold().split()).rstrip(".")
    return _LEADING_PHRASES.sub("", query, count=1) or query


def _in_city(lat: float, lon: float) -> bool:
    return 50.85 <= lat <= 51.25 and -114.35 <= lon <= -113.85


def _demo_address(query: str) -> tuple[float, float] | None:
    """Exact demo-address match, else the longest demo name inside the query.

    Callers rarely say only the name: "Khalsa School on Conrich Road" or
    "King George School by the field" should still resolve.
    """
    if query in DEMO_ADDRESSES:
        return DEMO_ADDRESSES[query]
    for name in sorted(DEMO_ADDRESSES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", query):
            return DEMO_ADDRESSES[name]
    return None


def geocode(conn: sqlite3.Connection, location_text: str) -> tuple[float, float] | None:
    query = normalize_location(location_text)
    demo = _demo_address(query)
    if demo:
        return demo
    coordinates = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", query)
    if coordinates:
        lat, lon = map(float, coordinates.groups())
        return (lat, lon) if _in_city(lat, lon) else None
    cached = db.get_geocode_cache(conn, query)
    if cached:
        return cached["lat"], cached["lon"]
    result = _geocode_nominatim(query)
    if result:
        db.set_geocode_cache(conn, query, *result, "nominatim")
    return result


def _geocode_nominatim(location_text: str) -> tuple[float, float] | None:
    global _last_request
    with _lock:
        wait = max(0, NOMINATIM_RATE_LIMIT_SECONDS - (time.monotonic() - _last_request))
        if wait:
            time.sleep(wait)
        _last_request = time.monotonic()
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": location_text + ", Calgary, Alberta",
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "ca",
                    "bounded": 1,
                    "viewbox": "-114.35,51.25,-113.85,50.85",
                },
                headers={"User-Agent": NOMINATIM_USER_AGENT},
                timeout=3,
            )
            response.raise_for_status()
            rows = response.json()
            if not rows:
                return None
            lat, lon = float(rows[0]["lat"]), float(rows[0]["lon"])
            return (lat, lon) if _in_city(lat, lon) else None
        except (requests.RequestException, ValueError, TypeError, KeyError, IndexError):
            logger.warning("Geocoding is unavailable; requesting a clearer location")
            return None
