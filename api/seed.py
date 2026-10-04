"""Build demo state without reseeding a queue whose repairs are complete."""

from __future__ import annotations

import csv
import sqlite3

from api import db, service
from config import DEMO_DATE, TICKETS_CSV
from engine import live


def build_demo_state(conn: sqlite3.Connection) -> None:
    for table in ("plan_visits", "plans", "calls", "events", "lights"):
        conn.execute(f"DELETE FROM {table}")
    lights = live.demo_queue(DEMO_DATE)
    with TICKETS_CSV.open(newline="") as handle:
        original = {row["service_request_id"]: row for row in csv.DictReader(handle)}
    for lid, row in lights.iterrows():
        db.upsert_light(
            conn,
            {
                "id": str(lid),
                "lat": float(row.latitude),
                "lon": float(row.longitude),
                "comm_name": str(row.comm_name),
                "is_damage": int(row.is_damage),
                "first_reported": row.first_reported.isoformat(),
                "call_count": int(row.call_count),
                "status": "open",
            },
        )
        ticket = original.get(str(lid), {})
        db.insert_call(
            conn,
            {
                "light_id": str(lid),
                "phone_hash": "seed",
                "channel": "seed",
                "location_text": ticket.get("address", ""),
                "description": ticket.get("service_name", "Historical 311 report"),
                "created_at": row.first_reported.isoformat(),
            },
        )
    service.rerank_and_save(conn)
    conn.execute("UPDATE dispatch_state SET seeded=1 WHERE id=1")
    db.bump_revision(conn)
    service.log_event(conn, "reset", "Historical demo queue loaded. Repairs in this workspace are simulated.")


def ensure_demo_state(conn: sqlite3.Connection) -> None:
    with db.transaction(conn, write=True):
        if not conn.execute("SELECT seeded FROM dispatch_state WHERE id=1").fetchone()[0]:
            if conn.execute("SELECT count(*) FROM lights").fetchone()[0] == 0:
                build_demo_state(conn)
            else:
                conn.execute("UPDATE dispatch_state SET seeded=1 WHERE id=1")
