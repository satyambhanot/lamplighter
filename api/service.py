"""Report/merge/re-rank business logic, called by api/main.py routes.

This is the only layer that calls into engine/ from the live API — it
keeps main.py as routing-only. Implemented in Phase 6.
"""

from __future__ import annotations

import sqlite3

from api.schemas import PlanResponse, ReportResponse, StatusResponse

HAZARD_KEYWORDS = (
    "downed pole",
    "down pole",
    "fallen pole",
    "exposed wire",
    "sparking",
    "fire",
)


def check_hazard(description: str) -> bool:
    """Scan free text for hazard keywords (downed pole, exposed wires,
    sparking, fire). The voice agent's prompt also asks about this
    directly — safety is checked twice.
    """
    raise NotImplementedError("Phase 6")


def report_light(conn: sqlite3.Connection, phone: str, location_text: str, description: str) -> ReportResponse:
    """Handle POST /report end to end: hazard check, geocode, dedupe
    merge-or-create, re-score the queue, project fix dates, log an
    event, and build the response.
    """
    raise NotImplementedError("Phase 6")


def check_status(conn: sqlite3.Connection, phone: str) -> StatusResponse | None:
    """Handle GET /status: hash the phone, look up the caller's latest
    ticket. Returns None if no ticket is found for this caller.
    """
    raise NotImplementedError("Phase 6")


def mark_fixed(conn: sqlite3.Connection, ticket_id: str) -> None:
    """Handle POST /fixed/{ticket_id}: set status=fixed, record
    fixed_at, re-rank the remaining queue, and log an event.
    """
    raise NotImplementedError("Phase 6")


def build_plan(conn: sqlite3.Connection, budget_pct: float, policy: str) -> PlanResponse:
    """Handle GET /plan: a what-if re-plan of the current queue at
    budget_pct of WEEKLY_CREW_MINUTES under the named policy, without
    mutating stored state.
    """
    raise NotImplementedError("Phase 6")


def hash_phone(phone: str) -> str:
    """Salt (from .env) + hash a phone number before it touches the DB."""
    raise NotImplementedError("Phase 6")
