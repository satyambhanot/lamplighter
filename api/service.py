"""Report/merge/re-rank business logic, called by api/main.py routes.

This is the only layer that calls into engine/ from the live API — it
keeps main.py as routing-only.

The demo clock is frozen at config.DEMO_DATE (see CLAUDE.md): every age
calculation and fix-date projection here uses that date, not real wall
time, so ranks and dates stay identical across runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime
from uuid import uuid4

import pandas as pd

from api import db
from api.geocode import geocode
from api.schemas import EventItem, FixedResponse, PlanResponse, QueueItem, ReportResponse, StatusResponse
from config import (
    DEFAULT_POLICY_WEIGHTS,
    DEMO_DATE,
    DUPLICATE_RADIUS_M,
    WEEKLY_CREW_MINUTES,
    WEIGHTS_JSON,
)
from engine.data import load_layers
from engine.features import build_features
from engine.geo import build_ball_tree, query_radius
from engine.plan import plan_week, route_minutes
from engine.score import reasons as compute_reasons
from engine.score import score as compute_score
from engine.simulate import fifo_policy, project_fix_dates, risk_weight

logger = logging.getLogger(__name__)

HAZARD_KEYWORDS = (
    "downed pole",
    "down pole",
    "fallen pole",
    "exposed wire",
    "sparking",
    "fire",
)

LIGHT_DF_COLUMNS = ["latitude", "longitude", "comm_name", "is_damage", "first_reported", "call_count"]

_layers_cache: dict[str, pd.DataFrame] | None = None
_tuned_weights_cache: dict[str, float] | None = None


def _layers() -> dict[str, pd.DataFrame]:
    """School/transit layers, loaded once per process."""
    global _layers_cache
    if _layers_cache is None:
        _layers_cache = load_layers()
    return _layers_cache


def _tuned_weights() -> dict[str, float]:
    """Tuned policy weights from results/weights.json, loaded once per
    process. Falls back to the v1 hand-set weights if tuning hasn't
    been run yet, so the API still works on a fresh clone.
    """
    global _tuned_weights_cache
    if _tuned_weights_cache is None:
        if WEIGHTS_JSON.exists():
            _tuned_weights_cache = json.loads(WEIGHTS_JSON.read_text())
        else:
            logger.warning("%s not found; falling back to DEFAULT_POLICY_WEIGHTS (run `make results` to tune)", WEIGHTS_JSON)
            _tuned_weights_cache = dict(DEFAULT_POLICY_WEIGHTS)
    return _tuned_weights_cache


def _now_frozen() -> pd.Timestamp:
    """The demo's frozen "today" for scoring/age calculations."""
    return pd.Timestamp(DEMO_DATE)


def check_hazard(description: str) -> bool:
    """Scan free text for hazard keywords (downed pole, exposed wires,
    sparking, fire). The voice agent's prompt also asks about this
    directly — safety is checked twice.
    """
    text = description.lower()
    return any(keyword in text for keyword in HAZARD_KEYWORDS)


def hash_phone(phone: str) -> str:
    """Salt (from .env) + hash a phone number before it touches the DB."""
    salt = os.environ.get("PHONE_HASH_SALT")
    if not salt:
        salt = "lamplighter-dev-insecure-default-salt"
        logger.warning("PHONE_HASH_SALT not set in .env; using an insecure default (local/demo use only)")
    return hashlib.sha256(f"{salt}:{phone.strip()}".encode()).hexdigest()


def _rows_to_queue_df(rows: list[sqlite3.Row]) -> pd.DataFrame:
    """Open-lights DB rows -> the DataFrame shape engine/ functions expect."""
    if not rows:
        return pd.DataFrame(columns=LIGHT_DF_COLUMNS)
    records = {
        row["id"]: {
            "latitude": row["lat"],
            "longitude": row["lon"],
            "comm_name": row["comm_name"],
            "is_damage": bool(row["is_damage"]),
            "first_reported": pd.Timestamp(row["first_reported"]),
            "call_count": row["call_count"],
        }
        for row in rows
    }
    return pd.DataFrame.from_dict(records, orient="index")


def _rescore_and_save(conn: sqlite3.Connection) -> pd.DataFrame:
    """Re-featurize, re-score (tuned weights), re-rank, and re-project
    fix dates for every open light, persisting the result. Called after
    any mutation (new report, merge, fixed) since one light's status can
    change another's neighbours_dark / rank.

    Returns the updated queue (indexed by light id), for callers that
    need to read a specific light's new rank without a second query.
    """
    rows = db.get_open_queue(conn)
    queue = _rows_to_queue_df(rows)
    if queue.empty:
        return queue

    as_of = _now_frozen()
    weights = _tuned_weights()
    features = build_features(queue, _layers(), as_of)
    features["score"] = compute_score(features, weights)
    features["reasons"] = compute_reasons(features, weights)
    features = features.sort_values("score", ascending=False)
    features["rank"] = range(1, len(features) + 1)

    fix_dates = project_fix_dates(features, weights, WEEKLY_CREW_MINUTES)
    features["expected_fix_date"] = [fix_dates.get(light_id) for light_id in features.index]

    for light_id, row in features.iterrows():
        db.upsert_light(
            conn,
            {
                "id": light_id,
                "lat": row["latitude"],
                "lon": row["longitude"],
                "comm_name": row["comm_name"],
                "is_damage": int(row["is_damage"]),
                "first_reported": row["first_reported"].isoformat(),
                "call_count": int(row["call_count"]),
                "status": "open",
                "fixed_at": None,
                "near_school": int(row["near_school"]),
                "near_transit": int(row["near_transit"]),
                "score": float(row["score"]),
                "rank": int(row["rank"]),
                "expected_fix_date": row["expected_fix_date"],
                "reasons": row["reasons"],
            },
        )
    return features


def report_light(conn: sqlite3.Connection, phone: str, location_text: str, description: str) -> ReportResponse:
    """Handle POST /report end to end: hazard check, geocode, dedupe
    merge-or-create, re-score the queue, project fix dates, log an
    event, and build the response.
    """
    now = datetime.now().isoformat()  # naive — must match build_features()'s naive as_of, never tz-aware
    phone_hash = hash_phone(phone)
    hazard = check_hazard(description)

    coords = geocode(conn, location_text)
    if coords is None and not hazard:
        return ReportResponse(
            ticket_id="",
            merged=False,
            hazard=False,
            needs_clarification=True,
            message="I couldn't find that location. What's the nearest cross street or intersection?",
        )
    lat, lon = coords if coords else (0.0, 0.0)

    if hazard:
        light_id = f"hazard-{uuid4().hex[:10]}"
        db.upsert_light(
            conn,
            {
                "id": light_id,
                "lat": lat,
                "lon": lon,
                "comm_name": None,
                "is_damage": 1,
                "first_reported": now,
                "call_count": 1,
                "status": "hazard",
                "fixed_at": None,
                "near_school": 0,
                "near_transit": 0,
                "score": None,
                "rank": None,
                "expected_fix_date": None,
                "reasons": "hazard reported - caller advised to call 911",
            },
        )
        db.insert_call(
            conn,
            {
                "light_id": light_id,
                "phone_hash": phone_hash,
                "channel": "voice",
                "location_text": location_text,
                "description": description,
                "created_at": now,
            },
        )
        db.insert_event(conn, {"at": now, "type": "hazard", "light_id": light_id, "message": f"Hazard reported near {location_text}. Caller advised to call 911."})
        conn.commit()
        return ReportResponse(
            ticket_id=light_id,
            merged=False,
            hazard=True,
            needs_clarification=False,
            message="This sounds like an emergency. Please hang up and call 911 right away.",
        )

    open_rows = db.get_open_queue(conn)
    merge_target: str | None = None
    if open_rows:
        coords_df = pd.DataFrame(
            {"latitude": [r["lat"] for r in open_rows], "longitude": [r["lon"] for r in open_rows]},
            index=[r["id"] for r in open_rows],
        )
        tree = build_ball_tree(coords_df)
        nearby = query_radius(tree, lat, lon, DUPLICATE_RADIUS_M)
        if len(nearby):
            merge_target = coords_df.index[nearby[0]]

    old_rank: int | None = None
    if merge_target is not None:
        light_id = merge_target
        light = db.get_light(conn, light_id)
        old_rank = light["rank"]
        conn.execute("UPDATE lights SET call_count = call_count + 1 WHERE id = ?", (light_id,))
        merged = True
    else:
        light_id = f"L-{uuid4().hex[:10]}"
        merged = False
        db.upsert_light(
            conn,
            {
                "id": light_id,
                "lat": lat,
                "lon": lon,
                "comm_name": None,
                "is_damage": 0,
                "first_reported": now,
                "call_count": 1,
                "status": "open",
                "fixed_at": None,
                "near_school": 0,
                "near_transit": 0,
                "score": None,
                "rank": None,
                "expected_fix_date": None,
                "reasons": None,
            },
        )

    db.insert_call(
        conn,
        {
            "light_id": light_id,
            "phone_hash": phone_hash,
            "channel": "voice",
            "location_text": location_text,
            "description": description,
            "created_at": now,
        },
    )

    updated = _rescore_and_save(conn)
    new_rank = int(updated.loc[light_id, "rank"])
    expected_fix_date = updated.loc[light_id, "expected_fix_date"]

    event_message = f"Call merged, light moved from #{old_rank} to #{new_rank}." if merged else f"New light reported, ranked #{new_rank}."
    db.insert_event(conn, {"at": now, "type": "merge" if merged else "report", "light_id": light_id, "message": event_message})
    conn.commit()

    if merged:
        message = f"Others have reported that light too — it's now ranked number {new_rank}."
    else:
        message = f"Thanks — that's ranked number {new_rank}."
    if expected_fix_date:
        message += f" Expected the week of {expected_fix_date}."

    return ReportResponse(
        ticket_id=light_id,
        merged=merged,
        hazard=False,
        needs_clarification=False,
        rank=new_rank,
        old_rank=old_rank,
        expected_fix_date=expected_fix_date,
        message=message,
    )


def check_status(conn: sqlite3.Connection, phone: str) -> StatusResponse | None:
    """Handle GET /status: hash the phone, look up the caller's latest
    ticket. Returns None if no ticket is found for this caller.
    """
    phone_hash = hash_phone(phone)
    light_id = db.get_latest_call_light_id(conn, phone_hash)
    if light_id is None:
        return None
    light = db.get_light(conn, light_id)
    if light is None:
        return None

    if light["status"] == "fixed":
        return StatusResponse(ticket_id=light_id, rank=0, expected_fix_date=light["fixed_at"] or "", status="fixed")
    if light["status"] == "hazard":
        return StatusResponse(ticket_id=light_id, rank=0, expected_fix_date="", status="hazard")
    return StatusResponse(
        ticket_id=light_id,
        rank=light["rank"] or 0,
        expected_fix_date=light["expected_fix_date"] or "",
        status="open",
    )


def mark_fixed(conn: sqlite3.Connection, ticket_id: str) -> FixedResponse:
    """Handle POST /fixed/{ticket_id}: set status=fixed, record
    fixed_at, re-rank the remaining queue, and log an event.
    """
    light = db.get_light(conn, ticket_id)
    if light is None:
        raise ValueError(f"no such light: {ticket_id}")

    now = datetime.now().isoformat()
    conn.execute("UPDATE lights SET status = 'fixed', fixed_at = ?, rank = NULL WHERE id = ?", (now, ticket_id))
    db.insert_event(conn, {"at": now, "type": "fixed", "light_id": ticket_id, "message": f"Light {ticket_id} marked fixed."})
    _rescore_and_save(conn)
    conn.commit()

    return FixedResponse(ticket_id=ticket_id, status="fixed", fixed_at=now)


def get_queue(conn: sqlite3.Connection) -> list[QueueItem]:
    """Handle GET /queue: the current open queue, ranked, no phone numbers."""
    rows = db.get_open_queue(conn)
    return [
        QueueItem(ticket_id=row["id"], lat=row["lat"], lon=row["lon"], rank=row["rank"] or 0, score=row["score"] or 0.0, reasons=row["reasons"] or "")
        for row in rows
    ]


def get_events(conn: sqlite3.Connection, since: str) -> list[EventItem]:
    """Handle GET /events."""
    rows = db.get_events_since(conn, since)
    return [EventItem(at=row["at"], type=row["type"], light_id=row["light_id"], message=row["message"]) for row in rows]


def build_plan(conn: sqlite3.Connection, budget_pct: float, policy: str) -> PlanResponse:
    """Handle GET /plan: a what-if re-plan of the current queue at
    budget_pct of WEEKLY_CREW_MINUTES under the named policy, without
    mutating stored state.

    risk_weighted_dark_nights here is a live-snapshot metric (today's
    accumulated risk-weighted age across the open queue), not the
    offline replay's cumulative-over-time metric — the two aren't
    directly comparable, but both use the same risk_weight() formula.
    """
    if policy not in ("FIFO", "v1", "tuned"):
        raise ValueError(f"unknown policy: {policy}")

    rows = db.get_open_queue(conn)
    queue = _rows_to_queue_df(rows)
    if queue.empty:
        return PlanResponse(budget_pct=budget_pct, policy=policy, lights_fixed=0, risk_weighted_dark_nights=0.0, fixes_per_crew_hour=0.0, queue=[])

    as_of = _now_frozen()
    features = build_features(queue, _layers(), as_of)

    if policy == "FIFO":
        order = fifo_policy(queue, as_of)
        features["score"] = 0.0
    elif policy == "v1":
        features["score"] = compute_score(features, DEFAULT_POLICY_WEIGHTS)
        order = features.sort_values("score", ascending=False).index.tolist()
    else:  # tuned
        features["score"] = compute_score(features, _tuned_weights())
        order = features.sort_values("score", ascending=False).index.tolist()

    features["reasons"] = compute_reasons(features, DEFAULT_POLICY_WEIGHTS)

    budget_min = round(WEEKLY_CREW_MINUTES * budget_pct)
    selected = plan_week(features, order, budget_min)
    minutes_used = route_minutes(features, selected)

    age_days = (as_of - features["first_reported"]).dt.days.clip(lower=0)
    weights_per_light = features.apply(risk_weight, axis=1)
    risk_weighted_total = float((age_days * weights_per_light).sum())
    fixes_per_crew_hour = len(selected) / (minutes_used / 60) if minutes_used > 0 else 0.0

    queue_items = [
        QueueItem(
            ticket_id=light_id,
            lat=float(features.loc[light_id, "latitude"]),
            lon=float(features.loc[light_id, "longitude"]),
            rank=i,
            score=float(features.loc[light_id, "score"]),
            reasons=str(features.loc[light_id, "reasons"] or ""),
        )
        for i, light_id in enumerate(order, start=1)
    ]

    return PlanResponse(
        budget_pct=budget_pct,
        policy=policy,
        lights_fixed=len(selected),
        risk_weighted_dark_nights=round(risk_weighted_total, 1),
        fixes_per_crew_hour=round(fixes_per_crew_hour, 3),
        queue=queue_items,
    )
