"""Boundary tests for dispatch data, disconnected services, and exports."""

from __future__ import annotations

import csv
import io
import json

import pytest
import requests
from pydantic import ValidationError

from dashboard import data


def _item(ticket_id: str = "A", **changes) -> dict:
    return {
        "ticket_id": ticket_id,
        "lat": 51.04,
        "lon": -114.05,
        "rank": 1,
        "score": 2.0,
        "reasons": "damage ticket",
        "comm_name": "BELTLINE",
        "call_count": 2,
        **changes,
    }


def _view() -> dict:
    return {
        "queue": [_item(), _item("B", rank=2)],
        "plan": {
            "policy": "tuned",
            "budget_pct": 1.0,
            "lights_planned": 1,
            "minutes_used": 45,
            "skipped_count": 1,
            "note": "One visit planned.",
            "queue": [_item()],
        },
    }


@pytest.mark.parametrize(
    "changes", [{"lat": float("nan")}, {"lon": 181}, {"score": float("inf")}, {"call_count": 0}]
)
def test_bad_queue_values_are_rejected(changes) -> None:
    with pytest.raises(ValidationError):
        data.QueueItem.model_validate(_item(**changes))


def test_duplicate_queue_and_unrelated_plan_are_rejected() -> None:
    payload = _view()
    payload["queue"] = [_item(), _item()]
    with pytest.raises(ValidationError, match="duplicate"):
        data.DispatchView.model_validate(payload)
    payload = _view()
    payload["plan"]["queue"] = [_item("missing")]
    with pytest.raises(ValidationError, match="different snapshots"):
        data.DispatchView.model_validate(payload)


def test_plan_cannot_overrun_budget_or_misreport_count() -> None:
    payload = _view()
    payload["plan"]["minutes_used"] = 841
    with pytest.raises(ValidationError, match="capacity"):
        data.DispatchView.model_validate(payload)
    payload = _view()
    payload["plan"]["lights_planned"] = 4
    with pytest.raises(ValidationError, match="count"):
        data.DispatchView.model_validate(payload)


def test_empty_live_queue_is_valid() -> None:
    payload = _view()
    payload["queue"] = []
    payload["plan"].update(queue=[], lights_planned=0, skipped_count=0, minutes_used=0)
    assert data.DispatchView.model_validate(payload).queue == []


def test_timeout_becomes_actionable_error(monkeypatch) -> None:
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == (0.8, 3.0)
        raise requests.Timeout()

    monkeypatch.setattr(data.requests, "get", timeout)
    with pytest.raises(data.DataUnavailable, match="Historical preview"):
        data.fetch_live("http://local", "tuned", 100)


def test_html_error_page_is_not_a_dispatch_plan(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("not JSON")

    monkeypatch.setattr(data.requests, "get", lambda *args, **kwargs: Response())
    with pytest.raises(data.DataUnavailable):
        data.fetch_live("http://local", "tuned", 100)


def test_events_failure_does_not_hide_a_valid_queue(monkeypatch) -> None:
    payload = _view()
    payload.update(revision=1, baseline=payload["plan"], events="invalid events")

    def get(base_url, endpoint, **params):
        assert params["headers"] == {"X-Lamplighter-Dispatcher-Secret": "dispatcher-test"}
        return payload

    monkeypatch.setattr(data, "_get", get)
    view = data.fetch_live("http://local", "tuned", 100, "dispatcher-test")
    assert len(view.queue) == 2
    assert not view.events_available


def test_service_must_return_requested_policy(monkeypatch) -> None:
    payload = _view()
    monkeypatch.setattr(data, "_get", lambda base, endpoint, **params: payload)
    with pytest.raises(data.DataUnavailable):
        data.fetch_live("http://local", "fifo", 100)


def test_preview_missing_or_corrupt_is_actionable(tmp_path) -> None:
    path = tmp_path / "preview.json"
    for contents in (None, "{", json.dumps({"scenarios": {}})):
        if contents is not None:
            path.write_text(contents)
        with pytest.raises(data.DataUnavailable, match="make preview"):
            data.load_preview("tuned", 100, path)


def test_queue_search_and_route_order() -> None:
    payload = _view()
    payload["plan"]["queue"][0]["rank"] = 2
    view = data.DispatchView.model_validate(payload)
    rows = data.queue_rows(view, search="beltline")
    assert rows[0]["Route stop"] == 1
    assert rows[0]["Priority"] == 2
    assert rows[1]["Priority"] == 2  # Every queue item belongs to the selected scenario.
    assert data.queue_rows(view, search="absent") == []


def test_csv_export_neutralizes_formulas_and_preserves_quotes() -> None:
    rows = data.queue_rows(data.DispatchView.model_validate(_view()))
    rows[0]["Dispatch reason"] = '=HYPERLINK("https://example.com")'
    rows[0]["Community"] = 'A, "B"'
    parsed = list(csv.DictReader(io.StringIO(data.export_csv(rows))))
    assert parsed[0]["Dispatch reason"].startswith("'=HYPERLINK")
    assert parsed[0]["Community"] == 'A, "B"'


def test_every_saved_preview_scenario_is_consistent() -> None:
    for policy in data.POLICY_LABELS:
        for budget in data.BUDGET_OPTIONS:
            view = data.load_preview(policy, budget)
            assert len(view.queue) == view.plan.lights_planned + view.plan.skipped_count


def test_capacity_compares_membership_even_when_total_count_is_unchanged():
    payload = _view()
    payload["baseline"] = dict(payload["plan"])
    payload["plan"] = dict(payload["plan"], budget_pct=0.8, minutes_used=40, queue=[_item("B", rank=2)])
    view = data.DispatchView.model_validate(payload)
    impact = data.capacity_impact(view)
    assert [item.ticket_id for item in impact["removed"]] == ["A"]
    assert [item.ticket_id for item in impact["added"]] == ["B"]
    assert impact["unchanged"] == 0
    assert impact["minutes_delta"] == -5
    assert impact["communities"][0]["Visits removed"] == 1
    assert impact["communities"][0]["Visits added"] == 1


def test_inconsistent_baseline_is_rejected():
    payload = _view()
    payload["baseline"] = dict(payload["plan"], policy="fifo")
    with pytest.raises(ValidationError, match="same policy"):
        data.DispatchView.model_validate(payload)


def test_map_selection_uses_ticket_identity_not_point_index():
    from dashboard.maps import ticket_from_selection

    assert (
        ticket_from_selection(
            {"selection": {"objects": {"depot": [{"ticket_id": ""}], "lights": [{"ticket_id": "B"}]}}}
        )
        == "B"
    )
    assert ticket_from_selection({"selection": {"indices": {"lights": [2]}}}) is None
