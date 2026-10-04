"""Hazard text check: real hazards are always flagged; denied ones are not."""

import pytest

from api.service import check_hazard


@pytest.mark.parametrize(
    "description",
    [
        "The pole has been knocked down and there are exposed wires on the sidewalk.",
        "There are exposed wires.",
        "Exposed wire hanging from the pole.",
        "The pole is down.",
        "The pole was knocked down by a truck.",
        "Downed pole on the corner.",
        "It is sparking.",
        "The light is on fire.",
        "Something is burning at the base.",
        "No one is hurt, but the wires are exposed.",
        "There are no exposed wires but it is sparking.",
        "No, the pole is down.",
        "Not sure what happened. There are exposed wires.",
        "The light is not working the pole is down.",
        "No one is near the exposed wires yet.",
        "No one hurt and pole down.",
        "There are no sparks and the wires are exposed.",
    ],
)
def test_real_hazards_are_flagged(description):
    assert check_hazard(description)


@pytest.mark.parametrize(
    "description",
    [
        "The street light is out.",
        "Street light is out near King George School, pole is standing, no exposed wires or sparking.",
        "Street light is out near King George School, pole is standing, no exposed wires, no sparking.",
        "The pole is not down and there are no exposed wires.",
        "The pole isn't knocked down.",
        "Without any exposed wires or sparking.",
        "Nothing is sparking or burning.",
        "There aren't any exposed wires.",
    ],
)
def test_denied_hazards_are_not_flagged(description):
    assert not check_hazard(description)
