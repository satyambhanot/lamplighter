"""Export real engine scenarios for the dashboard without running an API.

Run with ``python -m scripts.build_dashboard_preview``. The dashboard
reads this artifact and never imports the engine or writes to the database.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os

import pandas as pd

from config import DEMO_DATE, SCHOOLS_CSV, TICKETS_CSV, TRANSIT_STOPS_CSV, WEIGHTS_JSON
from dashboard.data import BUDGET_OPTIONS, POLICY_LABELS, PREVIEW_PATH, DispatchView
from engine.live import demo_queue, load_live_layers, what_if


def _items(frame: pd.DataFrame) -> list[dict]:
    return [
        {
            "ticket_id": str(light_id),
            "lat": float(row.latitude),
            "lon": float(row.longitude),
            "rank": int(row["rank"]),
            "score": float(row.score),
            "reasons": str(row.reasons),
            "comm_name": str(row.comm_name),
            "call_count": int(row.call_count),
            "is_damage": bool(row.is_damage),
            "first_reported": row.first_reported.isoformat(),
            "age_days": max(0, int(row.age_days)),
            "near_school": bool(row.near_school),
            "near_transit": bool(row.near_transit),
            "neighbours_dark": int(row.neighbours_dark),
            "expected_fix_date": row.expected_fix_date,
        }
        for light_id, row in frame.iterrows()
    ]


def main() -> None:
    # Exports must be deterministic and must never call a paid note service.
    os.environ.pop("ANTHROPIC_API_KEY", None)
    lights = demo_queue(DEMO_DATE)
    layers = load_live_layers()
    scenarios = {}
    for policy in POLICY_LABELS:
        for budget in BUDGET_OPTIONS:
            result = what_if(lights, layers, policy, budget / 100, pd.Timestamp(DEMO_DATE), use_llm=False)
            planned, skipped = result["planned"], result["skipped"]
            view = DispatchView.model_validate(
                {
                    "queue": _items(pd.concat([planned, skipped]).sort_values("rank")),
                    "plan": {
                        "policy": policy,
                        "budget_pct": budget / 100,
                        "lights_planned": len(planned),
                        "minutes_used": result["minutes_used"],
                        "skipped_count": len(skipped),
                        "queue": _items(planned),
                        "note": result["note"],
                    },
                    "events": [],
                }
            )
            scenarios[f"{policy}:{budget}"] = view.model_dump(mode="json")
        print(f"Exported {policy}: {len(BUDGET_OPTIONS)} capacity scenarios", flush=True)
    with TICKETS_CSV.open(newline="") as handle:
        originals = {row["service_request_id"]: row for row in csv.DictReader(handle)}
    history = {
        str(lid): {
            "ticket_id": str(lid),
            "complete": False,
            "history": [
                {
                    "at": row.first_reported.isoformat(),
                    "channel": "seed",
                    "description": originals.get(str(lid), {}).get("service_name", "Historical 311 report"),
                    "location_text": originals.get(str(lid), {}).get("address", ""),
                }
            ],
        }
        for lid, row in lights.iterrows()
    }
    payload = {
        "as_of": DEMO_DATE,
        "source": "Historical replay of Calgary 311 reports; simulated repairs, not live field status.",
        "input_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (TICKETS_CSV, SCHOOLS_CSV, TRANSIT_STOPS_CSV, WEIGHTS_JSON)
            if path.exists()
        },
        "scenarios": scenarios,
        "history": history,
    }
    temp = PREVIEW_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    temp.replace(PREVIEW_PATH)
    print(f"Wrote {len(lights)} lights and {len(scenarios)} scenarios to {PREVIEW_PATH}")


if __name__ == "__main__":
    main()
