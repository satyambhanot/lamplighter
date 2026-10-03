"""SQLite access. WAL mode, no ORM — the API is the only writer.

Schema matches CLAUDE.md's "Data model" section exactly.
"""

from __future__ import annotations

import sqlite3

from config import DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS lights (
    id              TEXT PRIMARY KEY,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    comm_name       TEXT,
    is_damage       INTEGER NOT NULL DEFAULT 0,
    first_reported  TEXT NOT NULL,
    call_count      INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'open',  -- open | fixed | hazard
    fixed_at        TEXT,
    near_school     INTEGER NOT NULL DEFAULT 0,
    near_transit    INTEGER NOT NULL DEFAULT 0,
    score           REAL,
    rank            INTEGER,
    expected_fix_date TEXT,
    reasons         TEXT
);

CREATE TABLE IF NOT EXISTS calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    light_id        TEXT NOT NULL REFERENCES lights(id),
    phone_hash      TEXT NOT NULL,
    channel         TEXT NOT NULL,  -- voice | fake | seed
    location_text   TEXT,
    description     TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    at              TEXT NOT NULL,
    type            TEXT NOT NULL,
    light_id        TEXT,
    message         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS geocode_cache (
    query           TEXT PRIMARY KEY,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    source          TEXT NOT NULL  -- demo | nominatim
);
"""


def get_connection(db_path: str = str(DB_PATH)) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = str(DB_PATH)) -> None:
    """Create all tables if they don't already exist."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def get_light(conn: sqlite3.Connection, light_id: str) -> sqlite3.Row | None:
    """Fetch one light by id, or None if it doesn't exist."""
    raise NotImplementedError("Phase 6")


def upsert_light(conn: sqlite3.Connection, light: dict) -> None:
    """Insert a new light or update an existing one in place."""
    raise NotImplementedError("Phase 6")


def get_open_queue(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all open lights ordered by rank."""
    raise NotImplementedError("Phase 6")


def insert_call(conn: sqlite3.Connection, call: dict) -> int:
    """Record a call against a light; returns the new call row id."""
    raise NotImplementedError("Phase 6")


def insert_event(conn: sqlite3.Connection, event: dict) -> None:
    """Append one activity-log event."""
    raise NotImplementedError("Phase 6")


def get_events_since(conn: sqlite3.Connection, since: str) -> list[sqlite3.Row]:
    """Return events with ``at`` after the given ISO timestamp."""
    raise NotImplementedError("Phase 6")


def get_geocode_cache(conn: sqlite3.Connection, query: str) -> sqlite3.Row | None:
    """Look up a previously geocoded query string."""
    raise NotImplementedError("Phase 6")


def set_geocode_cache(conn: sqlite3.Connection, query: str, lat: float, lon: float, source: str) -> None:
    """Cache a geocoding result."""
    raise NotImplementedError("Phase 6")
