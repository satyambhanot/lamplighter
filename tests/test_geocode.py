"""Spoken locations resolve to the demo list without a network call."""

import pytest

from api import geocode
from api.geocode import normalize_location


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("King George School", "king george school"),
        ("near King George School", "king george school"),
        ("outside the City Hall.", "city hall"),
        ("right in front of  City Hall", "city hall"),
        ("Centre Street and 16 Avenue NE", "centre street and 16 avenue ne"),
        ("Near", "near"),
    ],
)
def test_normalize_location_drops_leading_phrases(spoken, expected):
    assert normalize_location(spoken) == expected


def test_phrased_demo_address_skips_nominatim(monkeypatch):
    def fail(*args):
        raise AssertionError("Nominatim should not be called for a demo address")

    monkeypatch.setattr(geocode, "_geocode_nominatim", fail)
    assert geocode.geocode(None, "near King George School") == geocode.DEMO_ADDRESSES["king george school"]


@pytest.mark.parametrize(
    ("spoken", "name"),
    [
        ("Khalsa School on Condrich Road and Township Road intersection", "khalsa school"),
        ("near the Khalsa School", "khalsa school"),
        ("King George School by the soccer field", "king george school"),
        ("outside City Hall on Macleod Trail", "city hall"),
    ],
)
def test_demo_name_inside_a_longer_phrase_resolves_offline(monkeypatch, spoken, name):
    def fail(*args):
        raise AssertionError("Nominatim should not be called for a demo address")

    monkeypatch.setattr(geocode, "_geocode_nominatim", fail)
    assert geocode.geocode(None, spoken) == geocode.DEMO_ADDRESSES[name]
