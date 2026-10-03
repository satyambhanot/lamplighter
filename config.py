"""Project-wide constants and assumptions for Lamplighter.

Every assumption the engine, API, or dashboard relies on lives here.
Nothing in the codebase should hardcode a radius, time budget, or date
window directly — import it from this module instead, and update the
README's Assumptions section if a value here changes.
"""

from __future__ import annotations

from pathlib import Path

# --- Paths ---------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
RESULTS_DIR = ROOT_DIR / "results"

TICKETS_CSV = DATA_DIR / "street_lights_311.csv"
SCHOOLS_CSV = RAW_DATA_DIR / "schools.csv"
TRANSIT_STOPS_CSV = RAW_DATA_DIR / "transit_stops.csv"

WEIGHTS_JSON = RESULTS_DIR / "weights.json"
TUNING_LOG_CSV = RESULTS_DIR / "tuning_log.csv"
SUMMARY_CSV = RESULTS_DIR / "summary.csv"
POLICY_COMPARISON_PNG = RESULTS_DIR / "policy_comparison.png"
CREW_CUT_COMMUNITIES_CSV = RESULTS_DIR / "crew_cut_communities.csv"
SENSITIVITY_PNG = RESULTS_DIR / "sensitivity.png"

DB_PATH = ROOT_DIR / "api" / "lamplighter.db"

# --- Simulation geometry (assumptions; see README) ------------------------

DUPLICATE_RADIUS_M = 150
SCHOOL_RADIUS_M = 200
TRANSIT_RADIUS_M = 100
CLUSTER_RADIUS_M = 500

# --- Crew and routing ------------------------------------------------------

REPAIR_MINUTES = 30
TRAVEL_SPEED_KMH = 30

# DEPOT is the average location of all tickets. It is computed once in
# Phase 1 and then frozen here as a stated assumption.
DEPOT_LAT: float | None = None
DEPOT_LON: float | None = None

# Weekly crew time budget in minutes. Set in Phase 1 so FIFO fixes about
# 85% of average weekly arrivals (a realistic, non-trivial backlog).
WEEKLY_CREW_MINUTES: int | None = None

# Fraction of WEEKLY_CREW_MINUTES used for the sensitivity sweep and the
# crew-cut scenario (crew cut uses the 0.70 entry... see README for which
# exact figure the crew-cut analysis uses).
SENSITIVITY_BUDGET_PCTS = [0.70, 0.85, 1.00]
CREW_CUT_BUDGET_PCT = 0.80

# --- Risk weights -----------------------------------------------------------
# These define the city's cost of a dark night. They are fixed and never
# tuned — only the policy weights below are tuned.

RISK_WEIGHT_BASE = 1.0
RISK_WEIGHT_DAMAGE = 1.0
RISK_WEIGHT_SCHOOL = 1.0
RISK_WEIGHT_TRANSIT = 0.5
RISK_WEIGHT_PER_EXTRA_CALL = 0.25
RISK_WEIGHT_PER_EXTRA_CALL_MAX = 1.0

# --- Policy weights (tuned) --------------------------------------------------
# Starting point for the v1 hand-set policy. age_weeks keeps the age term on
# a similar scale to the other (mostly 0/1) terms. tune.py searches around
# values like these; it never touches the RISK_WEIGHT_* constants above.

DEFAULT_POLICY_WEIGHTS = {
    "w_age": 1.0,
    "w_damage": 1.0,
    "w_school": 1.0,
    "w_transit": 0.5,
    "w_repeat": 0.5,
    "w_cluster": 0.25,
}

TUNING_TRIALS = 200
TUNING_SEED = 42

# --- Time windows ------------------------------------------------------------

TUNE_START = "2026-03-23"
TUNE_END = "2026-06-30"
TEST_START = "2026-07-01"
TEST_END = "2026-08-27"
DEMO_DATE = "2026-08-24"  # Monday

# --- External services --------------------------------------------------------

NOMINATIM_USER_AGENT = "lamplighter-hackathon/1.0 (satyambhanot15@gmail.com)"
NOMINATIM_RATE_LIMIT_SECONDS = 1.0
ANTHROPIC_MODEL = "claude-sonnet-5"

# Demo addresses tried before Nominatim, so the demo never depends on an
# outside service. Filled in as the team picks real demo call locations.
DEMO_ADDRESSES: dict[str, tuple[float, float]] = {}

# --- Voice / API security ------------------------------------------------------

VOICE_SHARED_SECRET_HEADER = "X-Lamplighter-Voice-Secret"
