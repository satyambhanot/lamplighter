"""Tests for engine.data.load_tickets()."""

from engine.data import load_tickets


def test_load_tickets_shape() -> None:
    df = load_tickets()
    assert len(df) == 774
    assert set(df["service_name"].unique()) == {
        "Roads - Streetlight Maintenance",
        "Roads - Streetlight Damage",
    }


def test_load_tickets_no_missing_coordinates() -> None:
    df = load_tickets()
    assert df["latitude"].notna().all()
    assert df["longitude"].notna().all()


def test_load_tickets_flags() -> None:
    df = load_tickets()
    assert df["is_damage"].sum() == 185
    assert df["is_duplicate"].sum() == 10
