"""Validate live responses and saved previews before presenting dispatch data."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

import requests
from pydantic import BaseModel, ConfigDict, Field, model_validator

from config import DEMO_DATE, ROOT_DIR, SUMMARY_CSV, WEEKLY_CREW_MINUTES

PREVIEW_PATH = ROOT_DIR / "dashboard" / "preview.json"
POLICY_LABELS = {"tuned": "Tuned priority", "v1": "Balanced priority", "fifo": "Oldest first"}
BUDGET_OPTIONS = tuple(range(50, 125, 5))


class DataUnavailable(Exception):
    """A source cannot provide a usable dispatch view."""


class QueueItem(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    ticket_id: str = Field(min_length=1)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    rank: int = Field(ge=1)
    score: float
    reasons: str
    comm_name: str = "Unassigned"
    call_count: int = Field(default=1, ge=1)
    is_damage: bool | None = None
    first_reported: datetime | None = None
    age_days: int | None = None
    near_school: bool | None = None
    near_transit: bool | None = None
    neighbours_dark: int | None = None
    expected_fix_date: str | None = None


class Plan(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    budget_pct: float = Field(gt=0)
    policy: Literal["fifo", "v1", "tuned"]
    candidate_id: str | None = None
    lights_planned: int = Field(ge=0)
    minutes_used: float = Field(ge=0)
    skipped_count: int = Field(ge=0)
    note: str
    queue: list[QueueItem]

    @model_validator(mode="after")
    def check_count(self) -> Plan:
        if self.lights_planned != len(self.queue):
            raise ValueError("planned count does not match route")
        if len({item.ticket_id for item in self.queue}) != len(self.queue):
            raise ValueError("route contains duplicate tickets")
        if self.minutes_used > WEEKLY_CREW_MINUTES * self.budget_pct + 0.01:
            raise ValueError("route exceeds crew capacity")
        return self


class Event(BaseModel):
    id: int | None = None
    at: datetime
    type: str
    light_id: str | None = None
    message: str


class ConfirmedVisit(BaseModel):
    ticket_id: str
    position: int
    status: str
    comm_name: str = "Unassigned"
    fixed_at: datetime | None = None


class ConfirmedPlan(BaseModel):
    id: str
    policy: str
    budget_pct: float
    status: str
    created_at: datetime
    remaining_ids: list[str]
    completed_count: int
    visits: list[ConfirmedVisit] = Field(default_factory=list)


class HazardItem(BaseModel):
    ticket_id: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    first_reported: datetime
    location_text: str
    description: str
    call_count: int = Field(ge=1)


class HistoryItem(BaseModel):
    at: datetime
    channel: str
    description: str
    location_text: str = ""


class TicketHistory(BaseModel):
    ticket_id: str
    history: list[HistoryItem] = Field(default_factory=list)
    complete: bool = False


class DispatchView(BaseModel):
    queue: list[QueueItem]
    plan: Plan
    events: list[Event] = Field(default_factory=list)
    events_available: bool = True
    baseline: Plan | None = None
    revision: int | None = None
    as_of: str = DEMO_DATE
    confirmed_plan: ConfirmedPlan | None = None
    hazards: list[HazardItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_queue(self) -> DispatchView:
        ids = {item.ticket_id for item in self.queue}
        if len(ids) != len(self.queue):
            raise ValueError("queue contains duplicate tickets")
        if not {item.ticket_id for item in self.plan.queue} <= ids:
            raise ValueError("plan and queue are from different snapshots")
        if self.plan.lights_planned + self.plan.skipped_count != len(ids):
            raise ValueError("plan and queue counts do not match")
        if self.baseline is not None:
            if self.baseline.policy != self.plan.policy or self.baseline.budget_pct != 1.0:
                raise ValueError("baseline must use the same policy at full capacity")
            if not {item.ticket_id for item in self.baseline.queue} <= ids:
                raise ValueError("baseline and queue are from different snapshots")
            if self.baseline.lights_planned + self.baseline.skipped_count != len(ids):
                raise ValueError("baseline and queue counts do not match")
        return self


def load_preview(policy: str, budget: int, path: Path = PREVIEW_PATH) -> DispatchView:
    """Load a deterministic engine export; never invent preview records."""
    try:
        payload = json.loads(path.read_text())
        if payload["as_of"] != DEMO_DATE:
            raise ValueError("preview date does not match the planning clock")
        scenario = dict(payload["scenarios"][f"{policy}:{budget}"])
        scenario["baseline"] = payload["scenarios"][f"{policy}:100"]["plan"]
        view = DispatchView.model_validate(scenario)
        if view.plan.policy != policy or abs(view.plan.budget_pct - budget / 100) > 1e-9:
            raise ValueError("preview scenario does not match selection")
        return view
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DataUnavailable("The historical preview is unavailable. Rebuild it with make preview.") from exc


def _get(base_url: str, endpoint: str, *, headers: dict | None = None, **params: object) -> object:
    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/{endpoint}", params=params, headers=headers, timeout=(0.8, 3.0)
        )
        if getattr(response, "status_code", None) == 401:
            raise DataUnavailable("Dispatcher access is unavailable. Run make configure and restart the app.")
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise DataUnavailable(
            "Live dispatch is unavailable. Check the service connection or use Historical preview."
        ) from exc


def fetch_live(base_url: str, policy: str, budget: int, token: str = "") -> DispatchView:
    """Read a single revisioned snapshot so queue, plan, and baseline agree."""
    payload = _get(
        base_url,
        "dispatch",
        headers={"X-Lamplighter-Dispatcher-Secret": token},
        policy=policy,
        budget_pct=budget / 100,
    )
    try:
        if not isinstance(payload, dict):
            raise TypeError("dispatch must be an object")
        payload = dict(payload)
        events = payload.pop("events", [])
        view = DispatchView.model_validate(payload)
        if view.revision is None or view.baseline is None:
            raise ValueError("dispatch requires a revision and baseline")
        if view.plan.policy != policy or abs(view.plan.budget_pct - budget / 100) > 1e-9:
            raise ValueError("service returned a different scenario")
    except (ValueError, TypeError) as exc:
        raise DataUnavailable("The service returned an incomplete or inconsistent dispatch plan.") from exc
    try:
        if not isinstance(events, list):
            raise TypeError("events must be a list")
        # ISO timestamps may be naive demo timestamps or timezone-aware.
        parsed = [Event.model_validate(event) for event in events]
        view.events = sorted(parsed, key=lambda e: e.at.timestamp(), reverse=True)[:8]
    except (DataUnavailable, ValueError, TypeError):
        view.events_available = False
    return view


def fetch_history(base_url: str, ticket_id: str, token: str) -> TicketHistory:
    try:
        from urllib.parse import quote

        payload = _get(
            base_url,
            f"lights/{quote(ticket_id, safe='')}/history",
            headers={"X-Lamplighter-Dispatcher-Secret": token},
        )
        return TicketHistory.model_validate(payload)
    except ValueError as exc:
        raise DataUnavailable("Report history is temporarily unavailable.") from exc


def preview_history(ticket_id: str) -> TicketHistory:
    try:
        payload = json.loads(PREVIEW_PATH.read_text())
        return TicketHistory.model_validate(payload["history"][ticket_id])
    except (OSError, ValueError, KeyError, TypeError):
        return TicketHistory(ticket_id=ticket_id)


def mutate(base_url: str, endpoint: str, token: str, payload: dict) -> dict:
    """Send an authenticated write; surface conflicts without retrying a stale decision."""
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/{endpoint}",
            json=payload,
            headers={"X-Lamplighter-Dispatcher-Secret": token},
            timeout=(0.8, 10),
        )
        if response.status_code == 409:
            raise DataUnavailable(
                response.json().get("detail", "The queue changed. Refresh and review again.")
            )
        if response.status_code == 401:
            raise DataUnavailable("Dispatcher access is unavailable. Check the local access configuration.")
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise DataUnavailable(
            "The change could not be recorded. Refresh to check its status before trying again."
        ) from exc


def capacity_impact(view: DispatchView) -> dict:
    """Compare route membership, not just visit totals; selection can change non-monotonically."""
    baseline = view.baseline or view.plan
    before = {item.ticket_id: item for item in baseline.queue}
    after = {item.ticket_id: item for item in view.plan.queue}
    current = {item.ticket_id: item for item in view.queue}
    removed = [current[lid] for lid in before if lid not in after]
    added = [current[lid] for lid in after if lid not in before]
    communities = {}
    for change, items in (("removed", removed), ("added", added)):
        for item in items:
            counts = communities.setdefault(
                item.comm_name, {"Community": item.comm_name.title(), "Visits removed": 0, "Visits added": 0}
            )
            counts["Visits removed" if change == "removed" else "Visits added"] += 1
    return {
        "removed": removed,
        "added": added,
        "unchanged": len(before.keys() & after.keys()),
        "minutes_delta": view.plan.minutes_used - baseline.minutes_used,
        "communities": list(communities.values()),
    }


def load_evaluation(path: Path = SUMMARY_CSV) -> list[dict[str, str]]:
    """Saved experimental results, presented separately from live metrics."""
    try:
        with path.open(newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def queue_rows(
    view: DispatchView, community: str = "All communities", search: str = "", *, status: str = "all"
) -> list[dict]:
    """Policy ranks come from the selected plan; route position is separate."""
    planned = {item.ticket_id: (position + 1, item) for position, item in enumerate(view.plan.queue)}
    rows = []
    for original in view.queue:
        stop, item = planned.get(original.ticket_id, (None, original))
        if (status == "planned" and stop is None) or (status == "waiting" and stop is not None):
            continue
        if community != "All communities" and item.comm_name != community:
            continue
        if search.casefold() not in f"{item.ticket_id} {item.comm_name} {item.reasons}".casefold():
            continue
        rows.append(
            {
                "Ticket": item.ticket_id,
                "Community": item.comm_name.title(),
                "Priority": item.rank,
                "Route stop": stop,
                "Calls": item.call_count,
                "Dispatch reason": item.reasons,
                "Status": "Planned" if stop else "Waiting",
            }
        )
    return sorted(
        rows, key=lambda row: (row["Route stop"] is None, row["Route stop"] or row["Priority"], row["Ticket"])
    )


def export_csv(rows: list[dict]) -> str:
    """Export displayed records, neutralizing spreadsheet formula inputs."""
    output = io.StringIO()
    fields = ["Ticket", "Community", "Priority", "Route stop", "Calls", "Dispatch reason", "Status"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: "'" + value
                if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
                else value
                for key, value in row.items()
            }
        )
    return output.getvalue()
