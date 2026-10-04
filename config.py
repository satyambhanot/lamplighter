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
# Committed (not data/raw/, which is gitignored) so a fresh clone gets the
# same school/transit layers, and therefore the same scores, without
# re-running scripts/fetch_open_data.py.
SCHOOLS_CSV = DATA_DIR / "schools.csv"
TRANSIT_STOPS_CSV = DATA_DIR / "transit_stops.csv"

# Full City of Calgary 311 export, manually downloaded into data/raw/
# (gitignored — 1M+ rows, every service type). scripts/prepare_seed_data.py
# filters this down to TICKETS_CSV.
RAW_311_CSV = RAW_DATA_DIR / "311_Service_Requests_-_Current_Year.csv"

# data.calgary.ca Socrata API (SODA) endpoints, verified directly against
# the live API in Phase 3 — not guessed. scripts/fetch_open_data.py
# downloads these into SCHOOLS_CSV / TRANSIT_STOPS_CSV.
SCHOOLS_DATASET_URL = "https://data.calgary.ca/resource/fd9t-tdn2.json"  # "Schools", 506 rows
TRANSIT_STOPS_DATASET_URL = "https://data.calgary.ca/resource/muzh-c9qc.json"  # "Calgary Transit Stops"

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

# DEPOT is the average location of all tickets. Computed once in Phase 1
# from the 774-ticket seed data and frozen here as a stated assumption.
DEPOT_LAT: float = 51.04062
DEPOT_LON: float = -114.05793

# Weekly crew time budget in minutes, validated against Phase 2's real
# routing (not just REPAIR_MINUTES). Raw ticket arrivals average
# 32.9/week, but duplicate merging (within DUPLICATE_RADIUS_M of a still-
# unfixed light) means many of those are repeat calls about an already-
# queued problem — the real rate of *new* lights is closer to ~22/week,
# and that rate itself falls as the backlog shrinks (a fixed light's
# location can generate a fresh light again). At 840 minutes, FIFO
# averages ~20 fixes/week against that real rate: a mild, shrinking but
# non-trivial backlog (29 lights still dark at the end of the full
# replay) — the realistic backlog the architecture calls for. Raising
# the budget well past this (tested up to 1350 min) barely moves
# throughput, so 840 is kept rather than over-provisioning for a ceiling
# the duplicate-merge dynamic won't let FIFO reach anyway.
WEEKLY_CREW_MINUTES: int = 840

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

# --- 311 source data ----------------------------------------------------------

# service_name values that count as a street light ticket. "Damage" tickets
# get RISK_WEIGHT_DAMAGE; everything else is routine "Maintenance".
STREETLIGHT_SERVICE_NAMES = (
    "Roads - Streetlight Maintenance",
    "Roads - Streetlight Damage",
)
DAMAGE_SERVICE_NAME = "Roads - Streetlight Damage"

# --- External services --------------------------------------------------------

NOMINATIM_USER_AGENT = "lamplighter-hackathon/1.0 (satyambhanot15@gmail.com)"
NOMINATIM_RATE_LIMIT_SECONDS = 1.0
ANTHROPIC_MODEL = "claude-sonnet-5-5"  # Sonnet 5.5 — "claude-sonnet-5" (no minor) isn't a real model id

# Demo addresses tried before Nominatim, so the demo never depends on an
# outside service. Filled in as the team picks real demo call locations.
DEMO_ADDRESSES: dict[str, tuple[float, float]] = {}

# --- Voice / API security ------------------------------------------------------

VOICE_SHARED_SECRET_HEADER = "X-Lamplighter-Voice-Secret"
