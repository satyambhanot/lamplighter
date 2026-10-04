"""Sensor simulation, fault detection and the Sensors workspace."""

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from api.geocode import geocode
from config import ROOT_DIR
from engine import sensors


def _upload_frame() -> pd.DataFrame:
    """Two lamps for ten days; lamp B dies on the evening of July 5."""
    ts = pd.date_range("2026-07-01", periods=96 * 10, freq="15min")
    night = sensors.is_night(ts)
    rng = np.random.default_rng(1)

    def lamp(dead_from: pd.Timestamp | None = None) -> np.ndarray:
        amps = np.clip(np.where(night, 0.42, 0.0) + rng.normal(0, 0.015, len(ts)), 0, None)
        if dead_from is not None:
            amps[ts >= dead_from] = 0.01
        return amps

    return pd.concat(
        [
            pd.DataFrame({"time": ts, "device": "A", "amps": lamp()}),
            pd.DataFrame({"time": ts, "device": "B", "amps": lamp(pd.Timestamp("2026-07-05 21:00"))}),
        ]
    )


def test_simulation_catches_most_faults_and_is_repeatable() -> None:
    first = sensors.run_simulation(pd.Timestamp("2026-07-01"), 56, 150, 42)
    again = sensors.run_simulation(pd.Timestamp("2026-07-01"), 56, 150, 42)
    summary = first[-1]
    assert summary["faults_injected"] > 50
    assert summary["recall"] >= 0.9
    assert summary["precision"] >= 0.9
    assert summary["median_lead_over_311_h"] > 0
    assert summary == again[-1]


def test_uploaded_series_flags_only_the_dead_lamp() -> None:
    _poles, _readings, alarms = sensors.run_uploaded(_upload_frame(), "time", "device", "amps")
    assert list(alarms["pole_id"]) == ["B"]
    assert alarms.iloc[0]["kind"] == "outage"
    assert alarms.iloc[0]["detected_at"] >= pd.Timestamp("2026-07-05 21:00")


def test_alarm_reports_use_the_report_route_shape_and_geocode() -> None:
    poles, _readings, alarms = sensors.run_uploaded(_upload_frame(), "time", "device", "amps")
    report = sensors.alarm_reports(alarms, poles, simulated=False)[0]
    assert {"phone", "location_text", "description", "pole_id"} <= set(report)
    assert "uploaded" in report["description"]
    assert geocode(None, report["location_text"]) is not None  # "lat, lon" text resolves inside Calgary


def test_sensors_workspace_renders_and_sends_nothing_without_a_click() -> None:
    app = AppTest.from_file(ROOT_DIR / "dashboard/app.py", default_timeout=60).run()
    app.radio(key="workspace").set_value("Sensors").run()
    assert not app.exception
    assert any("Simulation." in item.value for item in app.warning)
    assert any("Faults injected" in item.value for item in app.markdown)
    assert any(button.key == "sensor-send" for button in app.button)
