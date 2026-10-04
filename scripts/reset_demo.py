"""Explicitly restore the historical demo using local dispatcher access."""

import os

import requests
from dotenv import load_dotenv

from config import ROOT_DIR


def main() -> None:
    load_dotenv(ROOT_DIR / ".env")
    token = os.environ.get("DISPATCH_SHARED_SECRET")
    if not token:
        raise SystemExit("Run make configure before resetting the demo.")
    response = requests.post(
        os.environ.get("LAMPLIGHTER_API_URL", "http://localhost:8000").rstrip("/") + "/demo/reset",
        headers={"X-Lamplighter-Dispatcher-Secret": token},
        timeout=30,
    )
    response.raise_for_status()
    print("Historical demo restored. Previous simulated repairs and confirmed plans were cleared.")


if __name__ == "__main__":
    main()
