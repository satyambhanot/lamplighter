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
    api_url = os.environ.get("LAMPLIGHTER_API_URL", "http://localhost:8000").rstrip("/")
    try:
        response = requests.post(
            api_url + "/demo/reset",
            headers={"X-Lamplighter-Dispatcher-Secret": token},
            timeout=30,
        )
    except requests.ConnectionError:
        raise SystemExit(f"The API is not running at {api_url}. Start it with make api, then run make reset.")
    if response.status_code == 401:
        raise SystemExit(
            "The API rejected the dispatcher key. Restart make api so it reads the current .env."
        )
    response.raise_for_status()
    print("Historical demo restored. Previous simulated repairs and confirmed plans were cleared.")


if __name__ == "__main__":
    main()
