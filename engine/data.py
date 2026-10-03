"""Load and clean the Calgary 311 street-light tickets."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import DAMAGE_SERVICE_NAME, TICKETS_CSV

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
