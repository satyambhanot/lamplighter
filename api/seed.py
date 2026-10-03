"""Build the demo database state: replay history up to config.DEMO_DATE
so the queue looks like a realistic mid-run snapshot.

Used at startup and by POST /demo/reset. Implemented in Phase 6.
"""

from __future__ import annotations

import sqlite3


def build_demo_state(conn: sqlite3.Connection) -> None:
    """Clear and repopulate lights/calls/events from the historical
    replay as of config.DEMO_DATE, using the tuned policy and weights
    from results/weights.json.
    """
    raise NotImplementedError("Phase 6")
