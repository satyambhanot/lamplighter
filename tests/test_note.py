"""Tests for engine.note.dispatcher_note() — template path only (no
ANTHROPIC_API_KEY in the test environment, which is itself the point:
the note must work with no key configured).
"""

import pandas as pd

import engine.note as note_module
from engine.note import dispatcher_note


def _plan() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "is_damage": [True, False, True],
            "near_school": [True, False, False],
            "near_transit": [False, True, False],
            "comm_name": ["BELTLINE", "BELTLINE", "DOVER"],
            "reasons": ["damage ticket, near a school", "near transit", "damage ticket"],
        }
    )


def _skipped() -> pd.DataFrame:
    return pd.DataFrame({"reasons": ["3 calls, 2.1 weeks old"]})


def test_dispatcher_note_mentions_counts(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    note = dispatcher_note(_plan(), _skipped())
    assert "3 lights" in note
    assert "2 damage reports" in note
    assert "1 light didn't fit" in note or "1 light rolled" in note or "didn't fit" in note


def test_dispatcher_note_empty_plan(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    note = dispatcher_note(pd.DataFrame(), pd.DataFrame())
    assert "No lights" in note


def test_dispatcher_note_crew_cut_mentioned(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    note = dispatcher_note(_plan(), _skipped(), crew_cut_pct=0.8)
    assert "80%" in note


def test_dispatcher_note_singular_grammar(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    plan = pd.DataFrame(
        {"is_damage": [True], "near_school": [False], "near_transit": [False], "comm_name": ["DOVER"]}
    )
    note = dispatcher_note(plan, pd.DataFrame())
    assert "1 light." in note
    assert "1 damage report" in note
    assert "reports" not in note


def test_dispatcher_note_falls_back_on_api_error(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")

    def _raise(facts, api_key):
        raise RuntimeError("simulated API failure")

    monkeypatch.setattr(note_module, "_llm_note", _raise)
    note = dispatcher_note(_plan(), _skipped())
    assert "3 lights" in note
