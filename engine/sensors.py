"""Smart-pole sensor readings and fault detection (pure logic, no web or database code).

Two ways to get readings:

* ``run_simulation``: poles sit at real Calgary 311 ticket locations and
  faults start shortly before the real 311 call; the lamp-current readings
  are SYNTHETIC (a simple lamp model plus noise).
* ``run_uploaded``: readings come from a real time-series CSV that the user
  provides; the detector runs on them unchanged. Device locations are
  placeholders taken from real 311 locations, because such files rarely
  carry Calgary coordinates.

``detect`` is a rule-based detector, not a trained model: it looks for an
onset of dark or dim night readings, then classifies it from the readings
that follow. ``alarm_reports`` shapes alarms like resident reports so the
dashboard can send them through the existing ``POST /report`` route.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from config import TICKETS_CSV

# --- Lamp model (assumptions) ------------------------------------------------

READING_MINUTES = 15
NOMINAL_AMPS = 0.42  # about a 100 W LED lamp at 240 V
NOISE_SD = 0.015  # normal measurement noise, amps
DUSK_HOUR = 19.0  # fixed schedule for simplicity (a real system would use sunset)
DAWN_HOUR = 6.5

FAULT_KINDS = ["outage", "flicker", "dim", "stuck_on"]
FAULT_WEIGHTS = [0.55, 0.20, 0.15, 0.10]  # outages dominate real 311 calls
FAULT_LABELS = {
    "outage": "Lamp out",
    "flicker": "Flickering",
    "dim": "Dimming",
    "stuck_on": "On in daytime",
}

# Faults start this long before the real 311 call in the simulation.
FAULT_LEAD_HOURS = (24, 72)

# --- Detector thresholds -------------------------------------------------------

ONSET_WINDOW = 8  # trailing night readings (2 h) examined for an anomaly onset
LOW_FRAC = 0.25  # a reading below 25% of nominal counts as "dark"
ONSET_LOW_SHARE = 0.25  # onset: at least this share of the window is dark ...
DIM_FRAC = 0.80  # ... or the window median sits below 80% of nominal
OUTAGE_SHARE = 0.90  # after onset, >=90% dark readings means outage, else flicker
STUCK_ON_FRAC = 0.50  # daytime current above 50% of nominal ...
STUCK_ON_CONSECUTIVE = 4  # ... for 1 h

# An alarm within this many hours of a simulated fault's start counts as a catch.
MATCH_WINDOW_H = 36

SENSOR_PHONE_PREFIX = "+1999"  # fake caller numbers for sensor reports


@dataclass
class Fault:
    pole_id: str
    kind: str
    start: pd.Timestamp
    ticket_id: str
    ticket_date: pd.Timestamp


# --- Poles ------------------------------------------------------------------------


def _tickets() -> pd.DataFrame:
    df = pd.read_csv(TICKETS_CSV)
    df["requested_date"] = pd.to_datetime(df["requested_date"], format="%m/%d/%Y %I:%M:%S %p")
    df["cell"] = list(zip(df["latitude"].round(4), df["longitude"].round(4)))
    return df.sort_values("requested_date")


def load_poles(start: pd.Timestamp, end: pd.Timestamp, max_poles: int) -> pd.DataFrame:
    """Poles sit at real 311 ticket locations (many tickets share a location).

    A location with a ticket inside [start, end) becomes a faulty pole,
    driven by its first in-window ticket. Remaining locations are healthy
    controls, up to ``max_poles`` in total.
    """
    df = _tickets()
    in_win = df[(df["requested_date"] >= start) & (df["requested_date"] < end)].drop_duplicates("cell")
    rest = df[~df["cell"].isin(in_win["cell"])].drop_duplicates("cell", keep="last")
    controls = rest.head(max(max_poles - len(in_win), 0))
    out = pd.concat([in_win, controls]).head(max_poles).reset_index(drop=True)
    out["pole_id"] = [f"P{i:04d}" for i in out.index]
    return out[["pole_id", "service_request_id", "requested_date", "comm_name", "latitude", "longitude"]]


def assign_locations(device_ids: list[str]) -> pd.DataFrame:
    """Give uploaded devices placeholder locations at real, distinct 311 locations."""
    spots = _tickets().drop_duplicates("cell").reset_index(drop=True)
    if len(device_ids) > len(spots):
        raise ValueError(f"Too many devices ({len(device_ids)}); at most {len(spots)} can be placed.")
    placed = spots.head(len(device_ids)).copy()
    placed["pole_id"] = device_ids
    return placed[["pole_id", "comm_name", "latitude", "longitude"]].reset_index(drop=True)


# --- Readings ---------------------------------------------------------------------


def is_night(ts: pd.DatetimeIndex) -> np.ndarray:
    hour = ts.hour + ts.minute / 60.0
    return np.asarray((hour >= DUSK_HOUR) | (hour < DAWN_HOUR))


def simulate(
    poles: pd.DataFrame, start: pd.Timestamp, days: int, rng: np.random.Generator
) -> tuple[pd.DataFrame, list[Fault]]:
    """Return (readings, injected faults).

    Each pole with a 311 ticket in the window gets one fault that starts
    1-3 days BEFORE that ticket: a sensor can see a failure before a
    neighbour phones it in. Other poles stay healthy as controls.
    """
    ts = pd.date_range(start, periods=days * 24 * 60 // READING_MINUTES, freq=f"{READING_MINUTES}min")
    end = ts[-1]
    night = is_night(ts)
    n = len(ts)

    faults: list[Fault] = []
    amps = np.empty((len(poles), n))
    for i, row in enumerate(poles.itertuples()):
        base = NOMINAL_AMPS * rng.uniform(0.95, 1.05)
        sig = np.clip(np.where(night, base, 0.0) + rng.normal(0, NOISE_SD, n), 0, None)

        lead = pd.Timedelta(hours=float(rng.uniform(*FAULT_LEAD_HOURS)))
        f_start = row.requested_date - lead
        if start <= f_start <= end - pd.Timedelta(hours=MATCH_WINDOW_H // 2):
            kind = str(rng.choice(FAULT_KINDS, p=FAULT_WEIGHTS))
            after = ts >= f_start
            if kind == "outage":
                sig[after] = np.clip(rng.normal(0.01, 0.01, after.sum()), 0, None)
            elif kind == "flicker":
                flick = (rng.random(after.sum()) < 0.4) & night[after]
                seg = sig[after]
                seg[flick] = rng.uniform(0.0, 0.3 * base, flick.sum())
                sig[after] = seg
            elif kind == "dim":
                days_in = (ts[after] - f_start) / pd.Timedelta(days=1)
                sig[after] = sig[after] * (1.0 - 0.45 * np.clip(days_in, 0, 1))
            elif kind == "stuck_on":
                day_after = after & ~night
                sig[day_after] = base + rng.normal(0, NOISE_SD, day_after.sum())
            faults.append(Fault(row.pole_id, kind, f_start, row.service_request_id, row.requested_date))
        amps[i] = sig

    long = pd.DataFrame(
        {
            "pole_id": np.repeat(poles["pole_id"].to_numpy(), n),
            "ts": np.tile(ts.to_numpy(), len(poles)),
            "amps": amps.ravel().round(4),
            "night": np.tile(night, len(poles)),
        }
    )
    return long, faults


def readings_from_frame(raw: pd.DataFrame, ts_col: str, id_col: str | None, value_col: str) -> pd.DataFrame:
    """Turn a user's time-series table into the readings format ``detect`` expects.

    Values are rescaled so a typical lit lamp reads about ``NOMINAL_AMPS``
    (one scale for the whole file, so a dead device stays dead), and each
    device is averaged onto a regular 15-minute grid.
    """
    frame = pd.DataFrame(
        {
            "ts": pd.to_datetime(raw[ts_col], errors="coerce"),
            "pole_id": raw[id_col].astype(str) if id_col else "device-1",
            "value": pd.to_numeric(raw[value_col], errors="coerce"),
        }
    ).dropna()
    if frame.empty:
        raise ValueError("No usable rows: check the timestamp and value columns.")
    if frame["ts"].dt.tz is not None:
        frame["ts"] = frame["ts"].dt.tz_localize(None)

    per_device = []
    for pole_id, group in frame.groupby("pole_id", sort=False):
        series = group.set_index("ts")["value"].sort_index()
        series = series[~series.index.duplicated()].resample(f"{READING_MINUTES}min").mean().dropna()
        if len(series) >= ONSET_WINDOW * 3:
            per_device.append(series.rename(pole_id))
    if not per_device:
        raise ValueError("Each device needs at least a day of readings.")

    scale = float(np.median([s.quantile(0.9) for s in per_device]))
    if scale <= 0:
        raise ValueError("The values are all zero or negative; pick the current or power column.")
    parts = []
    for series in per_device:
        part = (series / scale * NOMINAL_AMPS).rename("amps").reset_index()
        part.insert(0, "pole_id", series.name)
        parts.append(part)
    long = pd.concat(parts, ignore_index=True)
    long["amps"] = long["amps"].round(4)
    long["night"] = is_night(pd.DatetimeIndex(long["ts"]))
    return long[["pole_id", "ts", "amps", "night"]]


# --- Detection --------------------------------------------------------------------


def _first_run(mask: np.ndarray, length: int) -> int | None:
    """Index where the first run of ``length`` consecutive Trues completes."""
    if len(mask) < length:
        return None
    run = np.convolve(mask.astype(int), np.ones(length, dtype=int), mode="valid")
    hits = np.flatnonzero(run == length)
    return int(hits[0] + length - 1) if hits.size else None


def detect(readings: pd.DataFrame) -> pd.DataFrame:
    """Rule-based detector: at most one night alarm and one stuck-on alarm per pole.

    Night faults: find the first point where the trailing window shows an
    anomaly (many dark readings, or a low median), then classify it from
    the NEXT window of readings: mostly dark is an outage, mixed is a
    flicker, steadily low but lit is dim. That costs about 2 h of delay.
    """
    alarms = []
    w = ONSET_WINDOW
    for pole_id, g in readings.groupby("pole_id", sort=False):
        g = g.sort_values("ts")
        ts = g["ts"].to_numpy()
        amps = g["amps"].to_numpy()
        night = g["night"].to_numpy()
        n_idx = np.flatnonzero(night)
        na = amps[n_idx]
        dark = (na < LOW_FRAC * NOMINAL_AMPS).astype(float)

        share = pd.Series(dark).rolling(w).mean().to_numpy()
        med = pd.Series(na).rolling(w).median().to_numpy()
        onset = np.flatnonzero((share >= ONSET_LOW_SHARE) | (med < DIM_FRAC * NOMINAL_AMPS))
        onset = onset[onset + w < len(na)]  # need a full classification window after the onset
        if onset.size:
            t0 = int(onset[0])
            after = dark[t0 + 1 : t0 + 1 + w].mean()
            kind = "outage" if after >= OUTAGE_SHARE else ("flicker" if after >= ONSET_LOW_SHARE else "dim")
            alarms.append({"pole_id": pole_id, "kind": kind, "detected_at": pd.Timestamp(ts[n_idx[t0 + w]])})

        stuck = _first_run(~night & (amps > STUCK_ON_FRAC * NOMINAL_AMPS), STUCK_ON_CONSECUTIVE)
        if stuck is not None:
            alarms.append({"pole_id": pole_id, "kind": "stuck_on", "detected_at": pd.Timestamp(ts[stuck])})
    return pd.DataFrame(alarms, columns=["pole_id", "kind", "detected_at"])


def evaluate(poles: pd.DataFrame, faults: list[Fault], alarms: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Match alarms to simulated faults; report recall, precision and lead over the 311 call."""
    rows = []
    matched = set()
    for f in faults:
        hit = alarms[(alarms["pole_id"] == f.pole_id) & (alarms["kind"] == f.kind)]
        detected_at = None
        if not hit.empty:
            t = hit["detected_at"].min()
            if f.start <= t <= f.start + pd.Timedelta(hours=MATCH_WINDOW_H):
                detected_at = t
                matched.add((f.pole_id, f.kind))
        rows.append(
            {
                "pole_id": f.pole_id,
                "fault_kind": f.kind,
                "fault_start": f.start,
                "detected_at": detected_at,
                "ticket_id": f.ticket_id,
                "ticket_date": f.ticket_date,
                "detection_delay_h": None
                if detected_at is None
                else round((detected_at - f.start).total_seconds() / 3600, 1),
                "lead_over_311_h": None
                if detected_at is None
                else round((f.ticket_date - detected_at).total_seconds() / 3600, 1),
            }
        )
    events = pd.DataFrame(
        rows,
        columns=[
            "pole_id",
            "fault_kind",
            "fault_start",
            "detected_at",
            "ticket_id",
            "ticket_date",
            "detection_delay_h",
            "lead_over_311_h",
        ],
    )
    detected = int(events["detected_at"].notna().sum())
    n_alarms = len(alarms)
    summary = {
        "poles": len(poles),
        "faults_injected": len(faults),
        "faults_detected": detected,
        "recall": round(detected / len(faults), 3) if faults else None,
        "alarms_total": n_alarms,
        "false_alarms": n_alarms - len(matched),
        "precision": round(len(matched) / n_alarms, 3) if n_alarms else None,
        "median_detection_delay_h": float(events["detection_delay_h"].median()) if detected else None,
        "median_lead_over_311_h": float(events["lead_over_311_h"].median()) if detected else None,
        "by_kind": {
            k: {
                "injected": int((events["fault_kind"] == k).sum()),
                "detected": int(((events["fault_kind"] == k) & events["detected_at"].notna()).sum()),
            }
            for k in FAULT_KINDS
        },
    }
    return events, summary


# --- Reporting ------------------------------------------------------------------------


def alarm_reports(alarms: pd.DataFrame, poles: pd.DataFrame, simulated: bool) -> list[dict]:
    """Shape alarms like resident reports for ``POST /report``.

    The location is sent as "lat, lon" text, which the API's geocoder
    accepts inside Calgary. Each pole gets its own fake caller number, so
    two alarms from one pole merge and alarms from different poles do not
    count as one resident.
    """
    located = poles.set_index("pole_id")
    source = "simulated sensor readings" if simulated else "uploaded sensor readings"
    reports = []
    for alarm in alarms.itertuples():
        pole = located.loc[alarm.pole_id]
        digits = re.sub(r"\D", "", str(alarm.pole_id)) or str(abs(hash(alarm.pole_id)) % 10**7)
        reports.append(
            {
                "pole_id": alarm.pole_id,
                "phone": SENSOR_PHONE_PREFIX + digits.zfill(7)[-7:],
                "location_text": f"{pole['latitude']:.5f}, {pole['longitude']:.5f}",
                "description": (
                    f"Sensor alarm from {source}: {FAULT_LABELS[alarm.kind].lower()}, "
                    f"first seen {alarm.detected_at:%Y-%m-%d %H:%M}."
                ),
            }
        )
    return reports


# --- One-call runs ---------------------------------------------------------------------


def run_simulation(start: pd.Timestamp, days: int, n_poles: int, seed: int):
    """Poles at real 311 locations, synthetic readings, detection, scoring."""
    rng = np.random.default_rng(seed)
    poles = load_poles(start, start + pd.Timedelta(days=days), n_poles)
    readings, faults = simulate(poles, start, days, rng)
    alarms = detect(readings)
    events, summary = evaluate(poles, faults, alarms)
    return poles, readings, faults, alarms, events, summary


def run_uploaded(raw: pd.DataFrame, ts_col: str, id_col: str | None, value_col: str):
    """Real time series in, alarms out. There is no ground truth to score against."""
    readings = readings_from_frame(raw, ts_col, id_col, value_col)
    poles = assign_locations(sorted(readings["pole_id"].unique()))
    alarms = detect(readings)
    return poles, readings, alarms
