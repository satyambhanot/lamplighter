"""Typed contracts for reporting, planning, and confirmed crew work."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PolicyName = Literal["fifo", "v1", "tuned"]


class ReportRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=40)
    location_text: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=2000)


class ReportResponse(BaseModel):
    ticket_id: str | None = None
    merged: bool = False
    hazard: bool = False
    needs_clarification: bool = False
    rank: int | None = None
    old_rank: int | None = None
    expected_fix_date: str | None = None
    message: str


class StatusResponse(BaseModel):
    ticket_id: str
    rank: int | None = None
    expected_fix_date: str | None = None
    status: str


class QueueItem(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    ticket_id: str
    lat: float
    lon: float
    rank: int
    score: float
    reasons: str
    comm_name: str
    call_count: int
    is_damage: bool
    first_reported: str
    age_days: int
    near_school: bool
    near_transit: bool
    neighbours_dark: int
    expected_fix_date: str | None = None


class PlanResponse(BaseModel):
    budget_pct: float
    policy: PolicyName
    lights_planned: int
    minutes_used: float
    skipped_count: int
    note: str
    queue: list[QueueItem]


class EventItem(BaseModel):
    id: int
    at: str
    type: str
    light_id: str | None = None
    message: str


class ConfirmRequest(BaseModel):
    revision: int = Field(ge=0)
    policy: PolicyName
    budget_pct: float = Field(ge=0.5, le=1.2, allow_inf_nan=False)


class RepairRequest(BaseModel):
    revision: int = Field(ge=0)
    plan_id: str


class ConfirmedVisit(BaseModel):
    ticket_id: str
    position: int
    status: str


class ConfirmedPlan(BaseModel):
    id: str
    policy: PolicyName
    budget_pct: float
    status: str
    created_at: str
    remaining_ids: list[str]
    completed_count: int
    visits: list[ConfirmedVisit] = Field(default_factory=list)


class DispatchResponse(BaseModel):
    revision: int
    as_of: str
    queue: list[QueueItem]
    plan: PlanResponse
    baseline: PlanResponse
    events: list[EventItem]
    confirmed_plan: ConfirmedPlan | None = None


class FixedResponse(BaseModel):
    ticket_id: str
    status: str
    fixed_at: str
    revision: int


class HistoryItem(BaseModel):
    at: str
    channel: str
    description: str
    location_text: str


class HistoryResponse(BaseModel):
    ticket_id: str
    history: list[HistoryItem]
    complete: bool


class HealthResponse(BaseModel):
    status: str
