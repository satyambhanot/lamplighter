"""Regenerate every file in results/ from scratch.

Run with: python -m engine.run_all
Implemented incrementally — Phase 2 adds the FIFO summary, Phase 3 adds
the v1 comparison, Phase 4 adds tuning/crew-cut/sensitivity outputs.
"""

from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    """Load tickets, run every policy, and write results/* outputs."""
    raise NotImplementedError("Phase 2")


if __name__ == "__main__":
    main()
