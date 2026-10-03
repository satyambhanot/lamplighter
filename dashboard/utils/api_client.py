"""Small, timeout-bounded client for the Lamplighter API."""

from __future__ import annotations

import os
from typing import Any

import requests

BASE_URL = os.getenv("LAMPLIGHTER_API_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = (1.5, 4.0)


class APIError(RuntimeError):
    """A user-safe API failure with useful context for the dashboard."""


def _request(method: str, path: str, **kwargs: Any) -> Any:
    try:
        response = requests.request(method, f"{BASE_URL}{path}", timeout=TIMEOUT, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}
    except requests.RequestException as exc:
        detail = ""
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            detail = f" (HTTP {exc.response.status_code})"
        raise APIError(f"API request failed{detail}: {exc}") from exc
    except ValueError as exc:
        raise APIError("API returned invalid JSON") from exc


def get_queue() -> list[dict[str, Any]]:
    data = _request("GET", "/queue")
    if not isinstance(data, list):
        raise APIError("Queue response was not a list")
    return data


def get_health() -> dict[str, Any]:
    data = _request("GET", "/health")
    if not isinstance(data, dict):
        raise APIError("Health response was not an object")
    return data


def get_plan(policy: str, budget_pct: float) -> dict[str, Any]:
    data = _request("GET", "/plan", params={"policy": policy, "budget_pct": budget_pct / 100})
    if not isinstance(data, dict):
        raise APIError("Plan response was not an object")
    return data


def get_events(since: str) -> list[dict[str, Any]]:
    data = _request("GET", "/events", params={"since": since})
    if not isinstance(data, list):
        raise APIError("Events response was not a list")
    return data


def post_demo_reset() -> dict[str, Any]:
    return _request("POST", "/demo/reset")
