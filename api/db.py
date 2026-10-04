"""SQLite facts, revisioned dispatch snapshots, and confirmed plans."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from config import DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS lights (
 id TEXT PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL, comm_name TEXT,
 is_damage INTEGER NOT NULL DEFAULT 0, first_reported TEXT NOT NULL,
 call_count INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'open',
 fixed_at TEXT, score REAL, rank INTEGER, expected_fix_date TEXT, reasons TEXT
);
CREATE TABLE IF NOT EXISTS calls (
 id INTEGER PRIMARY KEY AUTOINCREMENT, light_id TEXT NOT NULL REFERENCES lights(id),
 phone_hash TEXT NOT NULL, channel TEXT NOT NULL, location_text TEXT,
 description TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, type TEXT NOT NULL,
 light_id TEXT, message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS geocode_cache (
 query TEXT PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL, source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dispatch_state (
 id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL DEFAULT 0,
 seeded INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO dispatch_state(id) VALUES(1);
CREATE TABLE IF NOT EXISTS plans (
 id TEXT PRIMARY KEY, policy TEXT NOT NULL, budget_pct REAL NOT NULL,
 created_at TEXT NOT NULL, status TEXT NOT NULL, snapshot TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plan_visits (
 plan_id TEXT NOT NULL REFERENCES plans(id), light_id TEXT NOT NULL REFERENCES lights(id),
 position INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 PRIMARY KEY(plan_id, light_id), UNIQUE(plan_id, position)
);
CREATE INDEX IF NOT EXISTS calls_phone ON calls(phone_hash, id);
CREATE INDEX IF NOT EXISTS lights_status ON lights(status);
"""

LIGHT_FIELDS = (
    "id",
    "lat",
    "lon",
    "comm_name",
    "is_damage",
    "first_reported",
    "call_count",
    "status",
    "fixed_at",
    "score",
    "rank",
    "expected_fix_date",
    "reasons",
)


def get_connection(db_path: str = str(DB_PATH)) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = str(DB_PATH)) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection, *, write: bool = False) -> Iterator[None]:
    conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
    try:
        yield
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def revision(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT revision FROM dispatch_state WHERE id=1").fetchone()[0]


def bump_revision(conn: sqlite3.Connection) -> int:
    conn.execute("UPDATE dispatch_state SET revision=revision+1 WHERE id=1")
    return revision(conn)


def get_light(conn: sqlite3.Connection, light_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM lights WHERE id=?", (light_id,)).fetchone()


def upsert_light(conn: sqlite3.Connection, light: dict) -> None:
    fields = [field for field in LIGHT_FIELDS if field in light]
    updates = ", ".join(f"{field}=excluded.{field}" for field in fields if field != "id")
    placeholders = ", ".join("?" for _ in fields)
    conn.execute(
        f"INSERT INTO lights ({', '.join(fields)}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}",
        tuple(light[field] for field in fields),
    )


def get_open_queue(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM lights WHERE status='open' ORDER BY rank, id").fetchall()


def insert_call(conn: sqlite3.Connection, call: dict) -> int:
    fields = ("light_id", "phone_hash", "channel", "location_text", "description", "created_at")
    cursor = conn.execute(
        "INSERT INTO calls(light_id,phone_hash,channel,location_text,description,created_at) "
        "VALUES(?,?,?,?,?,?)",
        tuple(call.get(field) for field in fields),
    )
    return int(cursor.lastrowid)


def insert_event(conn: sqlite3.Connection, event: dict) -> None:
    conn.execute(
        "INSERT INTO events(at,type,light_id,message) VALUES(?,?,?,?)",
        tuple(event.get(field) for field in ("at", "type", "light_id", "message")),
    )


def get_events_since(conn: sqlite3.Connection, since: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM events WHERE at>? ORDER BY id DESC LIMIT 100", (since,)).fetchall()


def get_geocode_cache(conn: sqlite3.Connection, query: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM geocode_cache WHERE query=?", (query,)).fetchone()


def set_geocode_cache(conn: sqlite3.Connection, query: str, lat: float, lon: float, source: str) -> None:
    conn.execute(
        "INSERT INTO geocode_cache(query,lat,lon,source) VALUES(?,?,?,?) "
        "ON CONFLICT(query) DO UPDATE SET lat=excluded.lat,lon=excluded.lon,source=excluded.source",
        (query, lat, lon, source),
    )
