"""Tests for engine.live — the only engine module api/ is allowed to
import from.
"""

import pandas as pd
import pytest

from config import DEFAULT_POLICY_WEIGHTS, DEMO_DATE, WEEKLY_CREW_MINUTES
from engine.live import LIVE_POLICIES, RERANK_OUTPUT_COLUMNS, demo_queue, load_tuned_weights, rerank, what_if


def _lights() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "latitude": [51.0, 51.001, 51.1],
            "longitude": [-114.0, -114.001, -114.2],
            "comm_name": ["A", "A", "B"],
            "is_damage": [True, False, False],
            "first_reported": [
                pd.Timestamp("2026-08-01"),
                pd.Timestamp("2026-08-10"),
                pd.Timestamp("2026-07-01"),
            ],
            "call_count": [1, 1, 3],
        },
        index=["L1", "L2", "L3"],
    )


def test_load_tuned_weights_shape() -> None:
    weights = load_tuned_weights()
    assert set(weights.keys()) == set(DEFAULT_POLICY_WEIGHTS.keys())


def test_rerank_empty_in_empty_out() -> None:
    empty = pd.DataFrame(
        columns=["latitude", "longitude", "comm_name", "is_damage", "first_reported", "call_count"]
    )
    result = rerank(empty, {}, DEFAULT_POLICY_WEIGHTS, WEEKLY_CREW_MINUTES, pd.Timestamp(DEMO_DATE))
    assert result.empty


def test_rerank_adds_expected_columns_and_sorts_by_rank() -> None:
    result = rerank(_lights(), {}, DEFAULT_POLICY_WEIGHTS, WEEKLY_CREW_MINUTES, pd.Timestamp(DEMO_DATE))
    for col in RERANK_OUTPUT_COLUMNS:
        assert col in result.columns
    assert list(result["rank"]) == sorted(result["rank"])
    assert result["rank"].tolist() == [1, 2, 3]


def test_rerank_damage_ticket_ranks_first_among_same_age() -> None:
    lights = pd.DataFrame(
        {
            "latitude": [51.0, 51.001],
            "longitude": [-114.0, -114.001],
            "comm_name": ["A", "A"],
            "is_damage": [False, True],
            "first_reported": [pd.Timestamp("2026-08-01")] * 2,
            "call_count": [1, 1],
        },
        index=["L1", "L2"],
    )
    result = rerank(lights, {}, DEFAULT_POLICY_WEIGHTS, WEEKLY_CREW_MINUTES, pd.Timestamp(DEMO_DATE))
    assert result.loc["L2", "rank"] < result.loc["L1", "rank"]


@pytest.mark.parametrize("policy", LIVE_POLICIES)
def test_what_if_every_policy(policy) -> None:
    result = what_if(_lights(), {}, policy, 1.0, pd.Timestamp(DEMO_DATE))
    assert set(result.keys()) == {"planned", "skipped", "minutes_used", "note"}
    assert len(result["planned"]) + len(result["skipped"]) == 3
    assert isinstance(result["note"], str)
    assert result["note"]


def test_what_if_fifo_ranks_oldest_first() -> None:
    # planned's row order is plan_week()'s nearest-neighbour visit order,
    # not priority order — check `rank` (the actual FIFO decision) instead.
    result = what_if(_lights(), {}, "fifo", 1.0, pd.Timestamp(DEMO_DATE))
    planned = result["planned"]
    assert planned.loc["L3", "rank"] == 1  # 2026-07-01, oldest


def test_what_if_invalid_policy_raises() -> None:
    with pytest.raises(ValueError, match="unknown policy"):
        what_if(_lights(), {}, "nonsense", 1.0, pd.Timestamp(DEMO_DATE))


def test_what_if_crew_cut_budget_reduces_minutes() -> None:
    full = what_if(_lights(), {}, "tuned", 1.0, pd.Timestamp(DEMO_DATE))
    cut = what_if(_lights(), {}, "tuned", 0.5, pd.Timestamp(DEMO_DATE))
    assert cut["minutes_used"] <= full["minutes_used"]


def test_demo_queue_shape() -> None:
    queue = demo_queue(DEMO_DATE)
    assert not queue.empty
    for col in ["latitude", "longitude", "comm_name", "is_damage", "first_reported", "call_count"]:
        assert col in queue.columns
    # a realistic mid-replay snapshot, not build_open_queue()'s ~198-light cold start
    assert len(queue) < 100


def test_projection_uses_snapshot_clock_and_defers_monday_reports():
    from engine.simulate import project_fix_dates

    lights = _lights().iloc[:2].copy()
    lights["rank"] = [1, 2]
    lights.loc["L2", "first_reported"] = pd.Timestamp("2026-09-07")
    dates = project_fix_dates(lights, DEFAULT_POLICY_WEIGHTS, 840, as_of=pd.Timestamp("2026-09-07"))
    assert "2026-09-07" <= dates["L1"] < "2026-09-14"
    assert dates["L2"] >= "2026-09-14"


def test_current_plan_and_projection_agree_for_new_monday_reports():
    lights = _lights().iloc[:2].copy()
    lights.loc["L2", "first_reported"] = pd.Timestamp(DEMO_DATE)
    result = what_if(lights, {}, "fifo", 1, pd.Timestamp(DEMO_DATE), use_llm=False)
    assert "L2" not in result["planned"].index
    assert result["skipped"].loc["L2", "expected_fix_date"] >= "2026-08-31"
