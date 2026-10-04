"""Dispatch writes must preserve revisions, permissions, and repair history."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from api import db, main, seed, service
from config import DEFAULT_POLICY_WEIGHTS

HEADERS = {"X-Lamplighter-Dispatcher-Secret": "dispatch-test"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = str(tmp_path / "dispatch.db")
    db.init_db(path)
    conn = db.get_connection(path)
    with db.transaction(conn, write=True):
        for i in range(3):
            db.upsert_light(
                conn,
                {
                    "id": f"L{i}",
                    "lat": 51.040 + i * 0.002,
                    "lon": -114.06,
                    "comm_name": "BELTLINE",
                    "first_reported": "2026-08-01",
                    "call_count": 1,
                    "status": "open",
                },
            )
        db.insert_call(
            conn,
            {
                "light_id": "L0",
                "phone_hash": "private-hash",
                "channel": "seed",
                "description": "Street light out",
                "created_at": "2026-08-01",
                "location_text": "Calgary",
            },
        )
    conn.close()
    monkeypatch.setenv("DISPATCH_SHARED_SECRET", "dispatch-test")
    monkeypatch.setenv("VOICE_SHARED_SECRET", "voice-test")
    monkeypatch.setenv("PHONE_HASH_SALT", "salt-test")
    monkeypatch.setattr(service, "runtime", lambda: ({}, DEFAULT_POLICY_WEIGHTS))

    def connection():
        conn = db.get_connection(path)
        try:
            yield conn
        finally:
            conn.close()

    main.app.dependency_overrides[main.get_db] = connection
    # Startup seeding is tested separately; avoid writing the real demo database.
    yield TestClient(main.app), path
    main.app.dependency_overrides.clear()


def confirm(client, **changes):
    policy = changes.get("policy", "tuned")
    budget_pct = changes.get("budget_pct", 1.0)
    snapshot = client.get(
        "/dispatch", headers=HEADERS, params={"policy": policy, "budget_pct": budget_pct}
    ).json()
    return client.post(
        "/plans/confirm",
        headers=HEADERS,
        json={
            "revision": snapshot["revision"],
            "policy": policy,
            "budget_pct": budget_pct,
            "candidate_id": snapshot["plan"]["candidate_id"],
            **changes,
        },
    )


def test_snapshot_and_scenario_validation(client):
    client, _ = client
    snapshot = client.get("/dispatch?policy=fifo&budget_pct=0.8", headers=HEADERS).json()
    assert snapshot["plan"]["policy"] == snapshot["baseline"]["policy"] == "fifo"
    assert snapshot["baseline"]["budget_pct"] == 1
    assert snapshot["revision"] == 0
    assert len(snapshot["queue"]) == snapshot["plan"]["lights_planned"] + snapshot["plan"]["skipped_count"]
    for query in ("policy=bad", "budget_pct=0.1", "budget_pct=nan", "budget_pct=1.3"):
        assert client.get("/dispatch?" + query, headers=HEADERS).status_code == 422


def test_writes_and_history_require_dispatcher_access(client):
    client, _ = client
    assert (
        client.post("/plans/confirm", json={"revision": 0, "policy": "tuned", "budget_pct": 1}).status_code
        == 401
    )
    assert client.post("/fixed/L0", json={"revision": 0, "plan_id": "unknown"}).status_code == 401
    assert client.get("/lights/L0/history").status_code == 401
    assert client.get("/dispatch").status_code == 401
    assert client.get("/events").status_code == 401
    assert (
        client.post(
            "/report", json={"phone": "4035550100", "location_text": "here", "description": "out"}
        ).status_code
        == 401
    )


def test_confirm_and_repair_are_idempotent_and_revisioned(client):
    client, path = client
    result = confirm(client)
    assert result.status_code == 200, result.text
    plan = result.json()
    assert confirm(client, revision=0).json()["id"] == plan["id"]
    assert confirm(client, revision=0, policy="fifo").status_code == 409
    ticket = plan["remaining_ids"][0]
    payload = {"revision": 1, "plan_id": plan["id"]}
    repaired = client.post(f"/fixed/{ticket}", headers=HEADERS, json=payload)
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["revision"] == 2
    assert client.post(f"/fixed/{ticket}", headers=HEADERS, json=payload).json() == repaired.json()
    snapshot = client.get("/dispatch", headers=HEADERS).json()
    assert len(snapshot["queue"]) == 2
    assert snapshot["confirmed_plan"]["completed_count"] == 1
    conn = db.get_connection(path)
    assert conn.execute("SELECT count(*) FROM events WHERE type='fixed'").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM plans").fetchone()[0] == 1
    conn.close()
    other = snapshot["confirmed_plan"]["remaining_ids"][0]
    assert client.post(f"/fixed/{other}", headers=HEADERS, json=payload).status_code == 409


def test_cannot_repair_without_a_confirmed_visit(client):
    client, _ = client
    assert (
        client.post("/fixed/L0", headers=HEADERS, json={"revision": 0, "plan_id": "missing"}).status_code
        == 409
    )
    assert (
        client.post("/fixed/unknown", headers=HEADERS, json={"revision": 0, "plan_id": "missing"}).status_code
        == 404
    )
    assert confirm(client, revision=100).status_code == 409
    assert client.get("/dispatch", headers=HEADERS).json()["revision"] == 0


def test_failed_repair_rolls_back_light_visit_and_revision(client, monkeypatch):
    client, _ = client
    plan = confirm(client).json()

    def fail(*args):
        raise RuntimeError("scoring failure")

    monkeypatch.setattr(service, "rerank_and_save", fail)
    with pytest.raises(RuntimeError, match="scoring failure"):
        client.post("/fixed/L0", headers=HEADERS, json={"revision": 1, "plan_id": plan["id"]})
    snapshot = client.get("/dispatch", headers=HEADERS).json()
    assert snapshot["revision"] == 1
    assert len(snapshot["queue"]) == 3
    assert snapshot["confirmed_plan"]["completed_count"] == 0


def test_report_invalidates_confirmed_plan_and_history_hides_phone(client, monkeypatch):
    from api import geocode

    client, _ = client
    plan = confirm(client).json()
    monkeypatch.setattr(geocode, "geocode", lambda *args: (51.040, -114.06))
    result = client.post(
        "/report",
        headers={"X-Lamplighter-Voice-Secret": "voice-test"},
        json={"phone": "4035550100", "location_text": "Calgary", "description": "Light still out"},
    )
    assert result.status_code == 200, result.text
    assert result.json()["merged"]
    snapshot = client.get("/dispatch", headers=HEADERS).json()
    assert snapshot["confirmed_plan"]["status"] == "needs_review"
    assert (
        client.post(
            "/fixed/L0", headers=HEADERS, json={"revision": snapshot["revision"], "plan_id": plan["id"]}
        ).status_code
        == 409
    )
    history = client.get("/lights/L0/history", headers=HEADERS).json()
    assert not history["complete"]
    assert len(history["history"]) == 2
    assert "phone" not in str(history)
    assert "private-hash" not in str(history)


def test_competing_confirmations_cannot_overwrite_reviewed_state(client):
    client, _ = client

    def request(policy):
        return confirm(client, revision=0, policy=policy).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(request, ["fifo", "v1"]))
    assert sorted(statuses) == [200, 409]


def test_confirmation_rejects_a_different_route_at_the_same_revision(client):
    client, _ = client
    snapshot = client.get("/dispatch", headers=HEADERS).json()
    payload = {
        "revision": snapshot["revision"],
        "policy": "tuned",
        "budget_pct": 1.0,
        "candidate_id": "0" * 24,
    }
    assert client.post("/plans/confirm", headers=HEADERS, json=payload).status_code == 409
    assert client.get("/dispatch", headers=HEADERS).json()["confirmed_plan"] is None
    payload["candidate_id"] = snapshot["plan"]["candidate_id"]
    assert client.post("/plans/confirm", headers=HEADERS, json=payload).status_code == 200


def test_hazard_handoff_is_reviewed_authorized_and_idempotent(client, monkeypatch):
    from api import geocode

    client, path = client
    monkeypatch.setattr(geocode, "geocode", lambda *args: (51.05, -114.06))
    report = client.post(
        "/report",
        headers={"X-Lamplighter-Voice-Secret": "voice-test"},
        json={
            "phone": "4035550100",
            "location_text": "Near the library",
            "description": "Exposed wires beside the pole",
        },
    )
    assert report.status_code == 200, report.text
    ticket = report.json()["ticket_id"]
    snapshot = client.get("/dispatch", headers=HEADERS).json()
    assert [item["ticket_id"] for item in snapshot["hazards"]] == [ticket]
    assert ticket not in {item["ticket_id"] for item in snapshot["queue"]}
    endpoint = f"/hazards/{ticket}/handoff"
    payload = {"revision": snapshot["revision"], "note": "Utilities emergency desk, case 1234"}
    assert client.post(endpoint, json=payload).status_code == 401
    assert client.post(endpoint, headers=HEADERS, json={**payload, "revision": 0}).status_code == 409
    assert client.post(endpoint, headers=HEADERS, json={**payload, "note": "  "}).status_code == 422
    result = client.post(endpoint, headers=HEADERS, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "hazard_referred"
    assert client.post(endpoint, headers=HEADERS, json=payload).json() == result.json()
    assert client.get("/dispatch", headers=HEADERS).json()["hazards"] == []
    conn = db.get_connection(path)
    assert conn.execute("SELECT count(*) FROM events WHERE type='hazard_referred'").fetchone()[0] == 1
    conn.close()


def test_completed_queue_is_not_reseeded_on_restart(client, monkeypatch):
    client, path = client
    plan = confirm(client).json()
    for ticket in plan["remaining_ids"]:
        revision = client.get("/dispatch", headers=HEADERS).json()["revision"]
        assert (
            client.post(
                f"/fixed/{ticket}", headers=HEADERS, json={"revision": revision, "plan_id": plan["id"]}
            ).status_code
            == 200
        )
    assert client.get("/dispatch", headers=HEADERS).json()["confirmed_plan"]["status"] == "completed"
    conn = db.get_connection(path)
    with db.transaction(conn, write=True):
        conn.execute("UPDATE dispatch_state SET seeded=1")
    monkeypatch.setattr(seed, "build_demo_state", lambda *args: pytest.fail("must not reseed"))
    seed.ensure_demo_state(conn)
    conn.close()
    assert client.get("/dispatch", headers=HEADERS).json()["queue"] == []
