"""Build the demo database state: replay history up to config.DEMO_DATE
so the queue looks like a realistic mid-run snapshot.

Used at startup and by POST /demo/reset.
"""

from __future__ import annotations

import json
import logging
import sqlite3

import pandas as pd

from api import db
from config import DEFAULT_POLICY_WEIGHTS, DEMO_DATE, WEEKLY_CREW_MINUTES, WEIGHTS_JSON
from engine.data import load_layers, load_tickets
from engine.features import build_features
from engine.score import make_score_policy
from engine.score import reasons as compute_reasons
from engine.score import score as compute_score
from engine.simulate import project_fix_dates, simulate

logger = logging.getLogger(__name__)


def build_demo_state(conn: sqlite3.Connection) -> None:
    """Clear and repopulate lights/calls/events from the historical
    replay as of config.DEMO_DATE, using the tuned policy and weights
    from results/weights.json.

    Only the ``lights`` table is populated — seeded lights have no real
    caller phone numbers to attach as ``calls`` rows, and the activity
    log (``events``) is meant for live demo-time activity, not the
    entire historical backlog.
    """
    db.clear_demo_state(conn)

    tickets = load_tickets()
    layers = load_layers()
    if WEIGHTS_JSON.exists():
        weights = json.loads(WEIGHTS_JSON.read_text())
    else:
        logger.warning("%s not found; seeding with DEFAULT_POLICY_WEIGHTS (run `make results` to tune)", WEIGHTS_JSON)
        weights = dict(DEFAULT_POLICY_WEIGHTS)

    policy = make_score_policy(layers, weights)
    result = simulate(tickets, policy, WEEKLY_CREW_MINUTES, snapshot_at=DEMO_DATE)
    snapshot = result.snapshot_queue

    if snapshot is None or snapshot.empty:
        logger.warning("No snapshot queue captured at %s; demo state will be empty", DEMO_DATE)
        conn.commit()
        return

    as_of = pd.Timestamp(DEMO_DATE)
    features = build_features(snapshot, layers, as_of)
    features["score"] = compute_score(features, weights)
    features["reasons"] = compute_reasons(features, weights)
    features = features.sort_values("score", ascending=False)
    features["rank"] = range(1, len(features) + 1)

    fix_dates = project_fix_dates(features, weights, WEEKLY_CREW_MINUTES)

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
                "expected_fix_date": fix_dates.get(light_id),
                "reasons": row["reasons"],
            },
        )

    conn.commit()
    logger.info("Seeded demo state: %d open lights as of %s", len(features), DEMO_DATE)
