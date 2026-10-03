"""Replay a sample call against the local API, so the full report flow
can be tested without ElevenLabs.

Run with: python -m scripts.fake_call  (needs `make api` running and
VOICE_SHARED_SECRET set the same in both places).
"""

from __future__ import annotations

import logging
import os

import requests

from config import VOICE_SHARED_SECRET_HEADER

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000"


def main() -> None:
    """POST a sample report to the local API, then check its status."""
    headers = {VOICE_SHARED_SECRET_HEADER: os.environ.get("VOICE_SHARED_SECRET", "")}

    payload = {
        "phone": "+14035550199",
        "location_text": "City Hall",
        "description": "The streetlight outside has been flickering and is now completely out.",
    }
    logger.info("POST /report %s", payload)
    report = requests.post(f"{API_BASE_URL}/report", json=payload, headers=headers, timeout=10)
    report.raise_for_status()
    logger.info("Response: %s", report.json())

    status = requests.get(f"{API_BASE_URL}/status", params={"phone": payload["phone"]}, headers=headers, timeout=10)
    status.raise_for_status()
    logger.info("Status: %s", status.json())


if __name__ == "__main__":
    main()
