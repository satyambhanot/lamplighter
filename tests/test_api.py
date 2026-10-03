"""FastAPI TestClient tests for api/main.py — report, merge, status, hazard.

Each test gets its own temp SQLite file and a fresh startup-triggered
seed (the real historical replay — slow-ish per test, but isolation
matters more than speed here).
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from api import db, main, service

HEADERS = {"X-Lamplighter-Voice-Secret": "test-secret"}


def _test_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_SHARED_SECRET", "test-secret")
    monkeypatch.setenv("PHONE_HASH_SALT", "test-salt")
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "get_connection", lambda *_a, **_k: _test_connection(db_path))
    with TestClient(main.app) as test_client:
        yield test_client


def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_queue_seeded_on_startup(client) -> None:
    response = client.get("/queue")
    assert response.status_code == 200
    items = response.json()
    assert len(items) > 0
    assert all("ticket_id" in item for item in items)


def test_report_requires_voice_secret(client) -> None:
    response = client.post("/report", json={"phone": "+14035550100", "location_text": "City Hall", "description": "light is out"})
    assert response.status_code == 401


def test_report_creates_new_light(client) -> None:
    response = client.post(
        "/report",
        json={"phone": "+14035550100", "location_text": "City Hall", "description": "the light is out"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["merged"] is False
    assert body["hazard"] is False
    assert body["rank"] is not None
    assert body["ticket_id"]


def test_report_merges_nearby_report(client) -> None:
    first = client.post(
        "/report",
        json={"phone": "+14035550100", "location_text": "City Hall", "description": "the light is out"},
        headers=HEADERS,
    ).json()
    second = client.post(
        "/report",
        json={"phone": "+14035550101", "location_text": "City Hall", "description": "same light, still out"},
        headers=HEADERS,
    ).json()

    assert second["merged"] is True
    assert second["ticket_id"] == first["ticket_id"]


def test_report_hazard(client) -> None:
    response = client.post(
        "/report",
        json={"phone": "+14035550102", "location_text": "City Hall", "description": "there is a downed pole with exposed wires"},
        headers=HEADERS,
    )
    body = response.json()
    assert body["hazard"] is True
    assert "911" in body["message"]


def test_report_needs_clarification_on_unresolvable_location(client, monkeypatch) -> None:
    monkeypatch.setattr(service, "geocode", lambda conn, text: None)
    response = client.post(
        "/report",
        json={"phone": "+14035550103", "location_text": "nowhere in particular", "description": "light is out"},
        headers=HEADERS,
    )
    body = response.json()
    assert body["needs_clarification"] is True


def test_mark_fixed_removes_from_queue(client) -> None:
    report = client.post(
        "/report",
        json={"phone": "+14035550104", "location_text": "City Hall", "description": "light out"},
        headers=HEADERS,
    ).json()
    ticket_id = report["ticket_id"]

    response = client.post(f"/fixed/{ticket_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "fixed"

    queue = client.get("/queue").json()
    assert all(item["ticket_id"] != ticket_id for item in queue)


def test_mark_fixed_unknown_ticket_404(client) -> None:
    response = client.post("/fixed/does-not-exist")
    assert response.status_code == 404


def test_demo_reset(client) -> None:
    client.post(
        "/report",
        json={"phone": "+14035550105", "location_text": "City Hall", "description": "light out"},
        headers=HEADERS,
    )
    response = client.post("/demo/reset")
    assert response.status_code == 200
    assert len(client.get("/queue").json()) > 0


def test_plan_endpoint(client) -> None:
    response = client.get("/plan", params={"budget_pct": 0.5, "policy": "tuned"})
    assert response.status_code == 200
    body = response.json()
    assert body["policy"] == "tuned"
    assert body["lights_fixed"] >= 0


def test_plan_invalid_policy(client) -> None:
    response = client.get("/plan", params={"policy": "nonsense"})
    assert response.status_code == 400


def test_status_not_found(client) -> None:
    response = client.get("/status", params={"phone": "+19999999999"}, headers=HEADERS)
    assert response.status_code == 404


def test_status_after_report(client) -> None:
    report = client.post(
        "/report",
        json={"phone": "+14035550106", "location_text": "City Hall", "description": "light out"},
        headers=HEADERS,
    ).json()
    response = client.get("/status", params={"phone": "+14035550106"}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["ticket_id"] == report["ticket_id"]


def test_events_after_report(client) -> None:
    client.post(
        "/report",
        json={"phone": "+14035550107", "location_text": "City Hall", "description": "light out"},
        headers=HEADERS,
    )
    response = client.get("/events")
    assert response.status_code == 200
    assert any(e["type"] == "report" for e in response.json())
