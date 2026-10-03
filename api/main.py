"""FastAPI routes only — all logic lives in api/service.py.

Run with: uvicorn api.main:app --port 8000 --reload
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from fastapi import Depends, FastAPI, Header, HTTPException

from api import db, seed, service
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    conn = db.get_connection()
    try:
        yield conn
    finally:
        conn.close()


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    db.init_db()
    with _connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM lights").fetchone()
        if row["n"] == 0:
            logger.info("Empty database — seeding demo state")
            seed.build_demo_state(conn)
    yield


app = FastAPI(title="Lamplighter API", lifespan=_lifespan)


def get_db() -> Iterator[sqlite3.Connection]:
    with _connection() as conn:
        yield conn


def require_voice_secret(secret: str | None = Header(default=None, alias=VOICE_SHARED_SECRET_HEADER)) -> None:
    """Voice tool calls must send the shared secret header."""
    expected = os.environ.get("VOICE_SHARED_SECRET")
    if not expected or secret != expected:
        raise HTTPException(status_code=401, detail="missing or invalid voice secret")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/report", response_model=ReportResponse, dependencies=[Depends(require_voice_secret)])
def report(req: ReportRequest, conn: sqlite3.Connection = Depends(get_db)) -> ReportResponse:
    return service.report_light(conn, req.phone, req.location_text, req.description)


@app.get("/status", response_model=StatusResponse, dependencies=[Depends(require_voice_secret)])
def status(phone: str, conn: sqlite3.Connection = Depends(get_db)) -> StatusResponse:
    result = service.check_status(conn, phone)
    if result is None:
        raise HTTPException(status_code=404, detail="no ticket found for this phone number")
    return result


@app.get("/queue", response_model=list[QueueItem])
def queue(conn: sqlite3.Connection = Depends(get_db)) -> list[QueueItem]:
    return service.get_queue(conn)


@app.get("/plan", response_model=PlanResponse)
def plan(budget_pct: float = 1.0, policy: str = "tuned", conn: sqlite3.Connection = Depends(get_db)) -> PlanResponse:
    try:
        return service.build_plan(conn, budget_pct, policy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/events", response_model=list[EventItem])
def events(since: str = "1970-01-01T00:00:00", conn: sqlite3.Connection = Depends(get_db)) -> list[EventItem]:
    return service.get_events(conn, since)


@app.post("/fixed/{ticket_id}", response_model=FixedResponse)
def fixed(ticket_id: str, conn: sqlite3.Connection = Depends(get_db)) -> FixedResponse:
    try:
        return service.mark_fixed(conn, ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/demo/reset")
def demo_reset(conn: sqlite3.Connection = Depends(get_db)) -> dict[str, str]:
    seed.build_demo_state(conn)
    return {"status": "reset"}
