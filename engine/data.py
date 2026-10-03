"""Load and clean the Calgary 311 street-light tickets.

Implemented in Phase 1.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import TICKETS_CSV


def load_tickets(path: Path = TICKETS_CSV) -> pd.DataFrame:
    """Load, parse, and clean the raw 311 tickets.

    Parses date columns, drops rows without coordinates, adds an
    ``is_damage`` column (True for "Streetlight Damage" tickets), and
    keeps Duplicate-status rows flagged rather than dropping them.

    Args:
        path: Path to the 311 tickets CSV.

    Returns:
        A cleaned DataFrame, one row per raw ticket.
    """
    raise NotImplementedError("Phase 1")
