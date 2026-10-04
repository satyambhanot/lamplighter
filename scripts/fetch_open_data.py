"""Download Calgary school and transit-stop locations from
data.calgary.ca into data/ (committed — see config.SCHOOLS_CSV).

Run with: python -m scripts.fetch_open_data

If a download fails, log it and continue without that layer — the rest
of the engine treats a missing layer as "no nearby schools/transit"
rather than erroring.
"""

from __future__ import annotations

import logging

import pandas as pd
import requests

from config import SCHOOLS_CSV, SCHOOLS_DATASET_URL, TRANSIT_STOPS_CSV, TRANSIT_STOPS_DATASET_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _fetch_socrata(url: str, params: dict) -> list[dict]:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_schools() -> None:
    """Download Calgary school locations to config.SCHOOLS_CSV."""
    try:
        rows = _fetch_socrata(SCHOOLS_DATASET_URL, {"$select": "name,point", "$limit": 2000})
    except requests.RequestException:
        logger.exception("Failed to fetch schools dataset; continuing without it")
        return

    records = [
        {
            "name": row["name"],
            "latitude": row["point"]["coordinates"][1],
            "longitude": row["point"]["coordinates"][0],
        }
        for row in rows
        if "point" in row
    ]
    pd.DataFrame(records).to_csv(SCHOOLS_CSV, index=False)
    logger.info("Wrote %d schools to %s", len(records), SCHOOLS_CSV)


def fetch_transit_stops() -> None:
    """Download active Calgary Transit stop locations to
    config.TRANSIT_STOPS_CSV.
    """
    try:
        rows = _fetch_socrata(
            TRANSIT_STOPS_DATASET_URL,
            {"$select": "stop_name,point", "$where": "status='ACTIVE'", "$limit": 10000},
        )
    except requests.RequestException:
        logger.exception("Failed to fetch transit stops dataset; continuing without it")
        return

    records = [
        {
            "stop_name": row["stop_name"],
            "latitude": row["point"]["coordinates"][1],
            "longitude": row["point"]["coordinates"][0],
        }
        for row in rows
        if "point" in row
    ]
    pd.DataFrame(records).to_csv(TRANSIT_STOPS_CSV, index=False)
    logger.info("Wrote %d transit stops to %s", len(records), TRANSIT_STOPS_CSV)


def main() -> None:
    fetch_schools()
    fetch_transit_stops()


if __name__ == "__main__":
    main()
