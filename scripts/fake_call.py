"""Replay a sample call against the local API, so the full report flow
can be tested without ElevenLabs.

Run with: python -m scripts.fake_call (after `make configure` and `make api`).
"""

from __future__ import annotations

import logging
import os

import requests
from dotenv import load_dotenv

from config import ROOT_DIR, VOICE_SHARED_SECRET_HEADER

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    """POST a sample report to the local API, then check its status."""
    load_dotenv(ROOT_DIR / ".env")
    secret = os.environ.get("VOICE_SHARED_SECRET")
    if not secret:
        raise RuntimeError("Run `make configure` before the sample call.")
    headers = {VOICE_SHARED_SECRET_HEADER: secret}
    api_base_url = os.environ.get("LAMPLIGHTER_API_URL", "http://localhost:8000").rstrip("/")

    payload = {
        "phone": "+14035550199",
        "location_text": "City Hall",
        "description": "The streetlight outside has been flickering and is now completely out.",
    }
    report = requests.post(f"{api_base_url}/report", json=payload, headers=headers, timeout=10)
    report.raise_for_status()
    logger.info("Report response: %s", report.json())

    status = requests.get(
        f"{api_base_url}/status", params={"phone": payload["phone"]}, headers=headers, timeout=10
    )
    status.raise_for_status()
    logger.info("Status: %s", status.json())


if __name__ == "__main__":
    main()
