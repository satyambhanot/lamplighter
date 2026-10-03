"""Pydantic request/response models — the typed contract between the
API, the dashboard, and the voice agent tools.

See CLAUDE.md's "API contract" section for the source-of-truth shapes.
"""

from __future__ import annotations

from pydantic import BaseModel


class ReportRequest(BaseModel):
    phone: str
    location_text: str
    description: str


class ReportResponse(BaseModel):
    ticket_id: str
    merged: bool
    hazard: bool
    needs_clarification: bool
    rank: int | None = None
    old_rank: int | None = None
    expected_fix_date: str | None = None
    message: str


class StatusResponse(BaseModel):
    ticket_id: str
    rank: int
    expected_fix_date: str
    status: str


class QueueItem(BaseModel):
    ticket_id: str
    lat: float
    lon: float
    rank: int
    score: float
    reasons: str


class PlanResponse(BaseModel):
    budget_pct: float
    policy: str
    lights_fixed: int
    risk_weighted_dark_nights: float
    fixes_per_crew_hour: float
    queue: list[QueueItem]


class EventItem(BaseModel):
    at: str
    type: str
    light_id: str | None = None
    message: str


class FixedResponse(BaseModel):
    ticket_id: str
    status: str
    fixed_at: str


class HealthResponse(BaseModel):
    status: str
