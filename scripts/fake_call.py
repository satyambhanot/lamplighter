"""Replay a sample call against the local API, so the full report flow
can be tested without ElevenLabs.

Run with: python -m scripts.fake_call
Implemented in Phase 6/7.
"""

from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    """POST a sample report to the local API and log the response."""
    raise NotImplementedError("Phase 6")


if __name__ == "__main__":
    main()
