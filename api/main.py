"""FastAPI transport for revisioned dispatch and confirmed crew work."""

from __future__ import annotations

import hmac
import os
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from api import db, seed, service
from api.schemas import (
    ConfirmedPlan,
    ConfirmRequest,
    DispatchResponse,
    EventItem,
    FixedResponse,
    HealthResponse,
    HistoryResponse,
    PlanResponse,
    QueueItem,
    RepairRequest,
    ReportRequest,
    ReportResponse,
    StatusResponse,
)
from config import ROOT_DIR, VOICE_SHARED_SECRET_HEADER

load_dotenv(ROOT_DIR / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    conn = db.get_connection()
    try:
        service.runtime()
        seed.ensure_demo_state(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="Lamplighter API", lifespan=lifespan)


def get_db() -> Iterator[sqlite3.Connection]:
    conn = db.get_connection()
    try:
        yield conn
    finally:
        conn.close()


def _secret(value: str | None, name: str) -> None:
    expected = os.environ.get(name)
    if not expected or value is None or not hmac.compare_digest(value, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid access key.")


def require_voice_secret(secret: str | None = Header(default=None, alias=VOICE_SHARED_SECRET_HEADER)) -> None:
    _secret(secret, "VOICE_SHARED_SECRET")


def require_dispatch_secret(
    secret: str | None = Header(default=None, alias="X-Lamplighter-Dispatcher-Secret"),
) -> None:
    _secret(secret, "DISPATCH_SHARED_SECRET")


@app.exception_handler(service.Conflict)
async def conflict(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(service.NotFound)
async def not_found(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.get("/health", response_model=HealthResponse)
def health(conn: sqlite3.Connection = Depends(get_db)) -> HealthResponse:
    conn.execute("SELECT revision FROM dispatch_state WHERE id=1").fetchone()
    return HealthResponse(status="ok")


@app.get("/dispatch", response_model=DispatchResponse)
def dispatch(
    policy: Literal["fifo", "v1", "tuned"] = "tuned",
    budget_pct: float = Query(default=1.0, ge=0.5, le=1.2, allow_inf_nan=False),
    conn: sqlite3.Connection = Depends(get_db),
) -> DispatchResponse:
    return service.dispatch_snapshot(conn, policy, budget_pct)


@app.get("/queue", response_model=list[QueueItem])
def queue(conn: sqlite3.Connection = Depends(get_db)) -> list[QueueItem]:
    return service.dispatch_snapshot(conn, "tuned", 1.0).queue


@app.get("/plan", response_model=PlanResponse)
def plan(
    policy: Literal["fifo", "v1", "tuned"] = "tuned",
    budget_pct: float = Query(default=1.0, ge=0.5, le=1.2, allow_inf_nan=False),
    conn: sqlite3.Connection = Depends(get_db),
) -> PlanResponse:
    return service.build_plan(conn, budget_pct, policy)


@app.get("/events", response_model=list[EventItem])
def events(since: str = "1970", conn: sqlite3.Connection = Depends(get_db)) -> list[EventItem]:
    return [EventItem(**dict(row)) for row in db.get_events_since(conn, since)]


@app.get(
    "/lights/{ticket_id}/history",
    response_model=HistoryResponse,
    dependencies=[Depends(require_dispatch_secret)],
)
def history(ticket_id: str, conn: sqlite3.Connection = Depends(get_db)) -> HistoryResponse:
    return service.history(conn, ticket_id)


@app.post("/plans/confirm", response_model=ConfirmedPlan, dependencies=[Depends(require_dispatch_secret)])
def confirm(req: ConfirmRequest, conn: sqlite3.Connection = Depends(get_db)) -> ConfirmedPlan:
    return service.confirm_plan(conn, req)


@app.post("/fixed/{ticket_id}", response_model=FixedResponse, dependencies=[Depends(require_dispatch_secret)])
def fixed(ticket_id: str, req: RepairRequest, conn: sqlite3.Connection = Depends(get_db)) -> FixedResponse:
    return service.mark_fixed(conn, ticket_id, req)


@app.post("/report", response_model=ReportResponse, dependencies=[Depends(require_voice_secret)])
def report(req: ReportRequest, conn: sqlite3.Connection = Depends(get_db)) -> ReportResponse:
    try:
        return service.report_light(conn, req.phone, req.location_text, req.description)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Reporting is not configured.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/status", response_model=StatusResponse, dependencies=[Depends(require_voice_secret)])
def status(phone: str, conn: sqlite3.Connection = Depends(get_db)) -> StatusResponse:
    try:
        result = service.check_status(conn, phone)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Reporting is not configured.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="No report was found for this number.")
    return result


@app.post("/demo/reset", dependencies=[Depends(require_dispatch_secret)])
def reset(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    with db.transaction(conn, write=True):
        seed.build_demo_state(conn)
    return {"status": "reset"}
