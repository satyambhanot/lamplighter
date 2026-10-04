"""Dispatch transactions and adapters to the shared engine."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
from datetime import datetime
from functools import lru_cache
from uuid import uuid4

import pandas as pd

from api import db
from api.schemas import (
    ConfirmedPlan,
    ConfirmedVisit,
    ConfirmRequest,
    DispatchResponse,
    EventItem,
    FixedResponse,
    HistoryItem,
    HistoryResponse,
    PlanResponse,
    QueueItem,
    RepairRequest,
    ReportResponse,
    StatusResponse,
)
from config import DEMO_DATE, DUPLICATE_RADIUS_M, WEEKLY_CREW_MINUTES
from engine import live


class Conflict(Exception):
    """The reviewed state no longer matches the dispatch queue."""


class NotFound(Exception):
    """The requested ticket or confirmed route does not exist."""


@lru_cache(maxsize=1)
def runtime() -> tuple[dict, dict]:
    return live.load_live_layers(), live.load_tuned_weights()


def now() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def log_event(conn: sqlite3.Connection, kind: str, message: str, ticket: str | None = None) -> None:
    db.insert_event(conn, {"at": now(), "type": kind, "light_id": ticket, "message": message})


def _frame(conn: sqlite3.Connection) -> pd.DataFrame:
    rows = [dict(row) for row in db.get_open_queue(conn)]
    if not rows:
        return pd.DataFrame(
            columns=["latitude", "longitude", "comm_name", "is_damage", "first_reported", "call_count"]
        )
    frame = pd.DataFrame(rows).set_index("id").rename(columns={"lat": "latitude", "lon": "longitude"})
    frame["first_reported"] = pd.to_datetime(frame["first_reported"], format="ISO8601")
    frame["is_damage"] = frame["is_damage"].astype(bool)
    frame["comm_name"] = frame["comm_name"].fillna("Unassigned")
    return frame


def items(frame: pd.DataFrame) -> list[QueueItem]:
    return [
        QueueItem(
            ticket_id=str(lid),
            lat=float(row.latitude),
            lon=float(row.longitude),
            comm_name=str(row.comm_name),
            is_damage=bool(row.is_damage),
            first_reported=row.first_reported.isoformat(),
            call_count=int(row.call_count),
            rank=int(row["rank"]),
            score=float(row.score),
            reasons=str(row.reasons),
            age_days=max(0, int(row.age_days)),
            near_school=bool(row.near_school),
            near_transit=bool(row.near_transit),
            neighbours_dark=int(row.neighbours_dark),
            expected_fix_date=row.expected_fix_date,
        )
        for lid, row in frame.iterrows()
    ]


def _scenario(frame: pd.DataFrame, policy: str, budget_pct: float) -> tuple[list[QueueItem], PlanResponse]:
    layers, _ = runtime()
    result = live.what_if(frame, layers, policy, budget_pct, pd.Timestamp(DEMO_DATE), use_llm=False)
    planned, skipped = result["planned"], result["skipped"]
    queue = items(pd.concat([planned, skipped]).sort_values("rank"))
    plan = PlanResponse(
        policy=policy,
        budget_pct=budget_pct,
        lights_planned=len(planned),
        skipped_count=len(skipped),
        minutes_used=result["minutes_used"],
        note=result["note"],
        queue=items(planned),
    )
    return queue, plan


def _confirmed(conn: sqlite3.Connection) -> ConfirmedPlan | None:
    row = conn.execute(
        "SELECT * FROM plans WHERE status IN ('confirmed','needs_review','completed') ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    visits = conn.execute(
        "SELECT light_id,status,position FROM plan_visits WHERE plan_id=? ORDER BY position", (row["id"],)
    ).fetchall()
    return ConfirmedPlan(
        id=row["id"],
        policy=row["policy"],
        budget_pct=row["budget_pct"],
        status=row["status"],
        created_at=row["created_at"],
        remaining_ids=[v["light_id"] for v in visits if v["status"] == "pending"],
        completed_count=sum(v["status"] == "fixed" for v in visits),
        visits=[
            ConfirmedVisit(ticket_id=v["light_id"], position=v["position"], status=v["status"])
            for v in visits
        ],
    )


def dispatch_snapshot(conn: sqlite3.Connection, policy: str, budget_pct: float) -> DispatchResponse:
    # One read transaction covers the candidate, baseline, events, and revision.
    with db.transaction(conn):
        frame = _frame(conn)
        queue, plan = _scenario(frame, policy, budget_pct)
        baseline = plan if budget_pct == 1.0 else _scenario(frame, policy, 1.0)[1]
        events = [EventItem(**dict(row)) for row in db.get_events_since(conn, "1970")[:8]]
        return DispatchResponse(
            revision=db.revision(conn),
            as_of=DEMO_DATE,
            queue=queue,
            plan=plan,
            baseline=baseline,
            events=events,
            confirmed_plan=_confirmed(conn),
        )


def build_plan(conn: sqlite3.Connection, budget_pct: float, policy: str) -> PlanResponse:
    return dispatch_snapshot(conn, policy, budget_pct).plan


def rerank_and_save(conn: sqlite3.Connection) -> None:
    layers, weights = runtime()
    result = live.rerank(_frame(conn), layers, weights, WEEKLY_CREW_MINUTES, pd.Timestamp(DEMO_DATE))
    for item in items(result):
        conn.execute(
            "UPDATE lights SET score=?,rank=?,expected_fix_date=?,reasons=? WHERE id=?",
            (item.score, item.rank, item.expected_fix_date, item.reasons, item.ticket_id),
        )


def confirm_plan(conn: sqlite3.Connection, req: ConfirmRequest) -> ConfirmedPlan:
    with db.transaction(conn, write=True):
        # Retrying an already successful confirmation does not create another plan.
        active = _confirmed(conn)
        if active and active.status == "confirmed":
            raw = conn.execute("SELECT snapshot FROM plans WHERE id=?", (active.id,)).fetchone()[0]
            saved = json.loads(raw)
            if (
                saved["reviewed_revision"] == req.revision
                and active.policy == req.policy
                and active.budget_pct == req.budget_pct
            ):
                return active
        if db.revision(conn) != req.revision:
            raise Conflict("The queue changed. Review the refreshed plan before confirming.")
        _, plan = _scenario(_frame(conn), req.policy, req.budget_pct)
        if not plan.queue:
            raise Conflict("There are no visits to confirm at this capacity.")
        plan_id = "P-" + uuid4().hex[:12]
        conn.execute(
            "UPDATE plans SET status='superseded' WHERE status IN ('confirmed','needs_review','completed')"
        )
        snapshot = plan.model_dump() | {"reviewed_revision": req.revision}
        conn.execute(
            "INSERT INTO plans(id,policy,budget_pct,created_at,status,snapshot) VALUES(?,?,?,?,?,?)",
            (plan_id, req.policy, req.budget_pct, now(), "confirmed", json.dumps(snapshot)),
        )
        conn.executemany(
            "INSERT INTO plan_visits(plan_id,light_id,position) VALUES(?,?,?)",
            [(plan_id, item.ticket_id, i + 1) for i, item in enumerate(plan.queue)],
        )
        db.bump_revision(conn)
        log_event(
            conn, "plan_confirmed", f"Confirmed {len(plan.queue)} visits at {req.budget_pct:.0%} capacity."
        )
        return _confirmed(conn)


def mark_fixed(conn: sqlite3.Connection, ticket_id: str, req: RepairRequest) -> FixedResponse:
    with db.transaction(conn, write=True):
        light = db.get_light(conn, ticket_id)
        if light is None:
            raise NotFound("This light does not exist.")
        visit = conn.execute(
            "SELECT * FROM plan_visits WHERE plan_id=? AND light_id=?", (req.plan_id, ticket_id)
        ).fetchone()
        if light["status"] == "fixed" and visit and visit["status"] == "fixed":
            return FixedResponse(
                ticket_id=ticket_id, status="fixed", fixed_at=light["fixed_at"], revision=db.revision(conn)
            )
        active = _confirmed(conn)
        if not active or active.id != req.plan_id or active.status != "confirmed" or visit is None:
            raise Conflict("Review and confirm a route containing this light before marking it repaired.")
        if db.revision(conn) != req.revision:
            raise Conflict("The queue changed. Refresh before marking this light repaired.")
        conn.execute(
            "UPDATE lights SET status='fixed',fixed_at=?,rank=NULL,score=NULL,expected_fix_date=NULL WHERE id=?",
            (DEMO_DATE, ticket_id),
        )
        conn.execute(
            "UPDATE plan_visits SET status='fixed' WHERE plan_id=? AND light_id=?", (req.plan_id, ticket_id)
        )
        if len(active.remaining_ids) == 1:
            conn.execute("UPDATE plans SET status='completed' WHERE id=?", (req.plan_id,))
        rerank_and_save(conn)
        revision = db.bump_revision(conn)
        log_event(conn, "fixed", f"Repair recorded for {ticket_id}.", ticket_id)
        return FixedResponse(ticket_id=ticket_id, status="fixed", fixed_at=DEMO_DATE, revision=revision)


def history(conn: sqlite3.Connection, ticket_id: str) -> HistoryResponse:
    if db.get_light(conn, ticket_id) is None:
        raise NotFound("This light does not exist.")
    rows = conn.execute(
        "SELECT created_at,channel,description,location_text FROM calls WHERE light_id=? ORDER BY created_at,id",
        (ticket_id,),
    ).fetchall()
    return HistoryResponse(
        ticket_id=ticket_id,
        complete=not any(row["channel"] == "seed" for row in rows),
        history=[
            HistoryItem(
                at=row["created_at"],
                channel=row["channel"],
                description=row["description"] or "",
                location_text=row["location_text"] or "",
            )
            for row in rows
        ],
    )


def hash_phone(phone: str) -> str:
    salt = os.environ.get("PHONE_HASH_SALT")
    if not salt:
        raise RuntimeError("PHONE_HASH_SALT is not configured")
    normalized = re.sub(r"\D", "", phone)
    if not normalized:
        raise ValueError("A phone number is required.")
    return hmac.new(salt.encode(), normalized.encode(), hashlib.sha256).hexdigest()


def check_hazard(description: str) -> bool:
    return bool(
        re.search(
            r"\b(downed pole|fallen pole|down pole|exposed wires?|sparking|on fire|burning)\b",
            description,
            re.IGNORECASE,
        )
    )


def report_light(
    conn: sqlite3.Connection, phone: str, location_text: str, description: str
) -> ReportResponse:
    from api.geocode import geocode

    coords = geocode(conn, location_text)
    conn.commit()  # Geocode cache work happens before the dispatch write transaction.
    hazard = check_hazard(description)
    if coords is None:
        return ReportResponse(
            hazard=hazard,
            needs_clarification=True,
            message="Please provide the nearest intersection or a precise location.",
        )
    with db.transaction(conn, write=True):
        nearby = None if hazard else live.nearest_light(_frame(conn), *coords, DUPLICATE_RADIUS_M)
        old_rank = None
        merged = nearby is not None
        if merged:
            light = db.get_light(conn, nearby)
            lid = light["id"]
            old_rank = light["rank"]
            conn.execute("UPDATE lights SET call_count=call_count+1 WHERE id=?", (lid,))
        else:
            lid = "L-" + uuid4().hex[:12]
            db.upsert_light(
                conn,
                {
                    "id": lid,
                    "lat": coords[0],
                    "lon": coords[1],
                    "comm_name": "Resident report",
                    "first_reported": DEMO_DATE,
                    "is_damage": int(hazard),
                    "call_count": 1,
                    "status": "hazard" if hazard else "open",
                },
            )
        db.insert_call(
            conn,
            {
                "light_id": lid,
                "phone_hash": hash_phone(phone),
                "channel": "voice",
                "location_text": location_text,
                "description": description,
                "created_at": now(),
            },
        )
        rerank_and_save(conn)
        conn.execute("UPDATE plans SET status='needs_review' WHERE status='confirmed'")
        db.bump_revision(conn)
        item = db.get_light(conn, lid)
        kind = "hazard" if hazard else ("merged" if merged else "new")
        message = (
            "Report flagged for urgent dispatcher review."
            if hazard
            else (
                f"Call merged; light moved from #{old_rank} to #{item['rank']}."
                if merged
                else f"New report entered at priority #{item['rank']}."
            )
        )
        log_event(conn, kind, message, lid)
        return ReportResponse(
            ticket_id=lid,
            merged=merged,
            hazard=hazard,
            rank=item["rank"],
            old_rank=old_rank,
            expected_fix_date=item["expected_fix_date"],
            message=message,
        )


def check_status(conn: sqlite3.Connection, phone: str) -> StatusResponse | None:
    row = conn.execute(
        "SELECT lights.* FROM calls JOIN lights ON calls.light_id=lights.id WHERE calls.phone_hash=? ORDER BY calls.id DESC LIMIT 1",
        (hash_phone(phone),),
    ).fetchone()
    return (
        StatusResponse(
            ticket_id=row["id"],
            rank=row["rank"],
            expected_fix_date=row["expected_fix_date"],
            status=row["status"],
        )
        if row
        else None
    )
