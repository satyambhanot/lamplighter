"""Download Calgary school and transit-stop locations from
data.calgary.ca into data/raw/ (gitignored).

Implemented in Phase 3. If a download fails, log it and continue
without that layer rather than inventing data.
"""

from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def fetch_schools() -> None:
    """Download Calgary school locations to config.SCHOOLS_CSV."""
    raise NotImplementedError("Phase 3")


def fetch_transit_stops() -> None:
    """Download Calgary Transit stop locations to config.TRANSIT_STOPS_CSV."""
    raise NotImplementedError("Phase 3")


def main() -> None:
    fetch_schools()
    fetch_transit_stops()


if __name__ == "__main__":
    main()
