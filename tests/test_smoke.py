"""Smoke test: the project imports cleanly even before the engine is
implemented, so `make test` always has something to run.
"""

import config


def test_config_constants_defined() -> None:
    assert config.DUPLICATE_RADIUS_M == 150
    assert config.TUNING_TRIALS == 200
    assert config.TUNING_SEED == 42
