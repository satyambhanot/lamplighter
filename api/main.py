"""FastAPI routes only — all logic lives in api/service.py.

Run with: uvicorn api.main:app --port 8000 --reload
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Depends, FastAPI, Header, HTTPException

from api import db
from api.schemas import (
    EventItem,
    FixedResponse,
    HealthResponse,
    PlanResponse,
    QueueItem,
    ReportRequest,
    ReportResponse,
    StatusResponse,
)
from config import VOICE_SHARED_SECRET_HEADER

app = FastAPI(title="Lamplighter API")


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    conn = db.get_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_db() -> Iterator[sqlite3.Connection]:
    with _connection() as conn:
        yield conn


def require_voice_secret(secret: str | None = Header(default=None, alias=VOICE_SHARED_SECRET_HEADER)) -> None:
    """Voice tool calls must send the shared secret header."""
    expected = os.environ.get("VOICE_SHARED_SECRET")
    if not expected or secret != expected:
        raise HTTPException(status_code=401, detail="missing or invalid voice secret")


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/report", response_model=ReportResponse, dependencies=[Depends(require_voice_secret)])
def report(req: ReportRequest, conn: sqlite3.Connection = Depends(get_db)) -> ReportResponse:
    raise NotImplementedError("Phase 6")


@app.get("/status", response_model=StatusResponse, dependencies=[Depends(require_voice_secret)])
def status(phone: str, conn: sqlite3.Connection = Depends(get_db)) -> StatusResponse:
    raise NotImplementedError("Phase 6")


@app.get("/queue", response_model=list[QueueItem])
def queue(conn: sqlite3.Connection = Depends(get_db)) -> list[QueueItem]:
    raise NotImplementedError("Phase 6")


@app.get("/plan", response_model=PlanResponse)
def plan(budget_pct: float = 1.0, policy: str = "tuned", conn: sqlite3.Connection = Depends(get_db)) -> PlanResponse:
    raise NotImplementedError("Phase 6")


@app.get("/events", response_model=list[EventItem])
def events(since: str = "1970-01-01T00:00:00", conn: sqlite3.Connection = Depends(get_db)) -> list[EventItem]:
    raise NotImplementedError("Phase 6")


@app.post("/fixed/{ticket_id}", response_model=FixedResponse)
def fixed(ticket_id: str, conn: sqlite3.Connection = Depends(get_db)) -> FixedResponse:
    raise NotImplementedError("Phase 6")


@app.post("/demo/reset")
def demo_reset(conn: sqlite3.Connection = Depends(get_db)) -> dict[str, str]:
    raise NotImplementedError("Phase 6")
