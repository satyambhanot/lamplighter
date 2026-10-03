"""Load and clean the Calgary 311 street-light tickets."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import DAMAGE_SERVICE_NAME, SCHOOLS_CSV, TICKETS_CSV, TRANSIT_STOPS_CSV

DATE_COLUMNS = ["requested_date", "updated_date", "closed_date"]


def load_tickets(path: Path = TICKETS_CSV) -> pd.DataFrame:
    """Load, parse, and clean the raw 311 tickets.

    Parses date columns, drops rows without coordinates, adds an
    ``is_damage`` column (True for "Streetlight Damage" tickets), and
    keeps Duplicate-status rows flagged (``is_duplicate``) rather than
    dropping them.

    Args:
        path: Path to the 311 tickets CSV.

    Returns:
        A cleaned DataFrame, one row per raw ticket.
    """
    df = pd.read_csv(path, dtype={"service_request_id": str, "comm_name": str, "address": str})

    for col in DATE_COLUMNS:
        df[col] = pd.to_datetime(df[col], format="%m/%d/%Y %I:%M:%S %p")

    df = df.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)

    df["is_damage"] = df["service_name"] == DAMAGE_SERVICE_NAME
    df["is_duplicate"] = df["status_description"].str.startswith("Duplicate")

    return df


def load_layers() -> dict[str, pd.DataFrame]:
    """Load the school/transit layers fetched by
    scripts/fetch_open_data.py. A missing file means "no nearby
    schools/transit" rather than an error — engine.features handles an
    absent key by treating every light as not-nearby.
    """
    layers: dict[str, pd.DataFrame] = {}
    if SCHOOLS_CSV.exists():
        layers["schools"] = pd.read_csv(SCHOOLS_CSV)
    if TRANSIT_STOPS_CSV.exists():
        layers["transit"] = pd.read_csv(TRANSIT_STOPS_CSV)
    return layers
