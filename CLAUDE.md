# Project: Lamplighter (Team NO Dark Night)

## What this is

A 48-hour project for the IEEE YP Industry Hackathon (Calgary, Oct 2-4,
2026), Case 6: Street-Light Outage Dispatch. Submissions close Sunday
Oct 4, 12:00 PM MDT.

User: City of Calgary street lighting dispatch. Goal: fewer dark nights
per crew-hour.

The software decides which reported street lights a crew fixes each week,
beats an oldest-first (FIFO) baseline, improves itself by tuning its own
weights, and rebuilds the plan when crew capacity drops 20%. Residents can
call an ElevenLabs voice agent to report a light or check its status, and
the call updates the ranked queue live.

## Judging (what matters)

- 30% autonomous reasoning: show baseline vs version 1 vs self-tuned
  result, from data.
- 20% real problem, 20% working software + architecture diagram,
  15% commercialization, 15% pitch.
- The live demo must produce real output on screen.

## Architecture: a modular monolith

This is the team's locked-in architecture. Treat this file as the source
of truth; if anyone wants to change a decision below, raise it with the
group first — don't just change it in code.

One Python codebase, one repo, two running processes (the API and the
dashboard), and a pure engine package at the center. The engine does all
the thinking and knows nothing about the web or the database. The API,
dashboard, and command-line scripts are thin shells around it.

Why: five people, 36 hours, one laptop on stage. Microservices, queues, or
cloud hosting would add failure points without adding judging points.

### Decision log

| Area | Decision | Why |
|---|---|---|
| Language | Python 3.11, pip and venv | Everyone knows it; no new tooling |
| Engine | pandas, numpy, scikit-learn `BallTree` (haversine) | Fast radius searches for duplicates, schools, transit |
| API | FastAPI with Pydantic schemas | Typed contracts, auto docs at `/docs` |
| Database | SQLite via stdlib `sqlite3`, WAL mode, no ORM | Zero setup; the API is the only writer |
| Dashboard | Streamlit, pydeck map, `st.fragment(run_every=3)` for live refresh | Fastest path to a live map with no extra packages |
| Charts | matplotlib PNGs in `results/` | Reproducible and easy to put in slides |
| Tuning | Random search, 200 trials, seed 42 | Simple, explainable, deterministic. Optuna is a stretch goal |
| Voice | ElevenLabs agent with two webhook tools | ElevenLabs owns speech; we own logic |
| Tunnel | ngrok to the local API | One command, works on venue Wi-Fi |
| Geocoding | Demo address list first, Nominatim second, cached | Demo never depends on an outside service |
| Dispatcher note | Anthropic API, with a template fallback | Works even with no key or no internet |
| Quality | ruff for lint and format, pytest | One fast tool, a few targeted tests |
| Tasks | Makefile | Everyone runs the same commands |
| Demo clock | Frozen at the demo date | Same dates and ranks every run |

### Repo layout

```text
lamplighter/
├── config.py          all constants and assumptions
├── Makefile
├── engine/            pure logic, no web or database code
│   ├── data.py        load and clean tickets
│   ├── geo.py         haversine, BallTree helpers
│   ├── features.py    school, transit, calls, cluster
│   ├── score.py       score() and reasons()
│   ├── plan.py        plan_week(), routing
│   ├── simulate.py    weekly replay, metrics
│   ├── tune.py        random search
│   ├── note.py        dispatcher note
│   ├── live.py        the only engine entry point the API calls
│   └── run_all.py     regenerates results/
├── api/
│   ├── main.py        routes only
│   ├── service.py     report, merge, re-rank logic
│   ├── db.py          SQL queries
│   ├── schemas.py     Pydantic models
│   ├── geocode.py
│   └── seed.py        builds demo state
├── dashboard/app.py
├── voice/             prompt, tools, setup, transcript
├── scripts/           fetch_open_data.py, fake_call.py
├── data/              seed CSV; raw/ is gitignored
├── results/
├── tests/
└── docs/              DESIGN.md, DEMO_SCRIPT.md
```

### Engine decisions

**Unit of work:** a "light" is one or more reports within 150 m of each
other while still unfixed. Its ID is the first ticket's ID.

**Simulation clock:** planning is weekly and dark nights are counted
daily. Every Monday, the planner builds the week from the queue as of
Sunday night. The crew works the route over five days, each with one
fifth of the weekly budget, and a light's fix date is the day the crew
reaches it. A light reported midweek waits for the next Monday.

**Routing:** nearest neighbour from the depot. The planner walks the
policy's ranked list and adds each light if the route still fits the
budget.

**Metrics:** risk-weighted dark nights (main), total dark nights, fixes
per crew-hour, median days dark, and lights still dark at the end.

**Policies:** FIFO, version 1 (hand-set weights, `DEFAULT_POLICY_WEIGHTS`
in `config.py`), and tuned. Damage-first is a stretch fourth policy. Age
in the score is measured in weeks so all weights sit on a similar scale.
Tuning draws each policy weight uniformly from 0 to 2 (`WEIGHT_MAX` in
`engine/tune.py`).

| Setting | Value |
|---|---|
| Duplicate radius | 150 m |
| School radius | 200 m |
| Transit radius | 100 m |
| Cluster radius | 500 m |
| Repair time | 30 minutes |
| Travel speed | 30 km/h |
| Depot | Average location of all tickets: 51.04062, -114.05793 (Phase 1) |
| Weekly crew minutes | 840 (14 crew-hours/week); validated against Phase 2 routing, see note below |
| Sensitivity runs | 70%, 85%, 100% of that budget |
| Risk weight per dark night | 1, plus 1 if damage, 1 if near a school, 0.5 if near transit, 0.25 per extra call (max 1) |
| Tuning window | March 23 to June 30 |
| Test window | July 1 to August 27 |
| Demo date | Monday, August 24 |

Risk weights define the city's cost of a dark night. They are fixed and
never tuned. Only the policy weights are tuned.

**Weekly crew minutes, validated (Phase 2):** the original Phase 1
framing ("85% of average weekly arrivals") assumed 32.9 raw tickets/week
as the arrival rate and ignored travel time. Real routing shows that's
wrong on both counts: duplicate merging (within DUPLICATE_RADIUS_M of a
still-unfixed light) means many calls are repeats about an already-
queued problem, so the real rate of *new* lights is closer to ~22/week
— and that rate itself falls as the backlog shrinks. At 840 minutes,
FIFO's real (travel-inclusive) throughput averages ~20 fixes/week:
a mild, shrinking but non-trivial backlog (29 lights still dark at the
end of the full replay) — exactly the realistic backlog this project
calls for. Tested budgets up to 1350 minutes barely move throughput
(the duplicate-merge dynamic caps it), so 840 stays.

### Data model

```sql
lights(id PK, lat, lon, comm_name, is_damage, first_reported,
       call_count, status, fixed_at,
       score, rank, expected_fix_date, reasons)
calls(id PK, light_id, phone_hash, channel, location_text,
      description, created_at)
events(id PK, at, type, light_id, message)
geocode_cache(query PK, lat, lon, source)
```

The database stores facts and decisions; the engine owns the features.
`lights` holds facts about each light (location, type, dates, call count,
status) and the engine's outputs (score, rank, expected fix date,
reasons). It never stores derived features such as `near_school`,
`near_transit`, `age_days`, or `neighbours_dark`: `build_features()`
recomputes them on every re-rank. A new feature built from existing
facts plus a layer needs no schema change; a new raw input does.

`status` is open, fixed, or hazard. `channel` is voice, fake, or seed.
Phone numbers are stored only as salted hashes, with the salt in `.env`.

### API contract

```text
POST /report   {phone, location_text, description}
            -> {ticket_id, merged, hazard, needs_clarification,
                rank, old_rank, expected_fix_date, message}
GET  /status?phone=      -> {ticket_id, rank, expected_fix_date, status}
GET  /queue              -> [{ticket_id, lat, lon, rank, score, reasons,
                              expected_fix_date, comm_name, call_count}]
GET  /plan?budget_pct=&policy=
                         -> {budget_pct, policy, lights_planned,
                             minutes_used, skipped_count, note,
                             queue: [QueueItem]}
GET  /events?since=      -> [{at, type, light_id, message}]
POST /fixed/{ticket_id}
POST /demo/reset
GET  /health
```

If an address can't be found, `/report` returns `needs_clarification:
true` instead of an error, so the agent can ask for the nearest
intersection. Voice tool calls (`/report`, `/status`) must send a shared
secret header (`X-Lamplighter-Voice-Secret`); the API rejects calls
without it.

`/plan` is read-only: a what-if re-plan of the current queue for the
dashboard slider, including the dispatcher note. `policy` is fifo, v1,
or tuned. Event `type` is new, merged, rerank, hazard, fixed, or reset,
and `message` is human-readable, like "Call merged, light moved from #12
to #4."

The live demo clock is `DEMO_DATE`: it is "today" for scoring,
`first_reported` on new calls, and fix dates. Event `at` timestamps use
the real wall clock so `/events?since=` works.

### Voice agent decisions

- Built on the ElevenLabs agent platform with two tools: `report_light`
  and `check_status`.
- The demo uses a browser test call, not a phone number.
- Replies are two sentences at most, calls are kept under two minutes,
  and dates are said as "the week of."
- The agent always reads the address back and always asks about downed
  poles or exposed wires before filing.

### Dashboard layout

- **Top row:** three cards showing FIFO vs tuned risk-weighted dark
  nights, percent improvement, and fixes per crew-hour.
- **Middle:** the map on the left (top 10 lights highlighted), the live
  activity log on the right.
- **Bottom:** this week's list and the dispatcher note.
- **Sidebar:** policy picker and crew budget slider, both calling
  `/plan`.

## How one call flows end to end

1. A resident calls. The ElevenLabs agent handles the speech, asks for
   the nearest address, reads it back, and asks if the pole is down.
2. The agent calls the `report_light` tool, which hits `POST /report` on
   the laptop through ngrok.
3. The API checks for hazards, geocodes the address, and looks for an
   unfixed light within 150 m. It either merges the call (call count goes
   up) or creates a new light.
4. The API calls the engine to re-score the open queue with the tuned
   weights, projects fix dates from crew capacity, saves the new ranks,
   and writes an event like "Call merged, light moved from #12 to #4."
5. The agent tells the caller their rank and expected fix date.
6. The dashboard polls the API every few seconds, so the map and
   activity log update on screen while the call is still happening.

## Staff engineer decisions

- **One engine, used everywhere.** `engine/` is pure Python with no web
  or database code. The offline replay, the live API, and the dashboard
  all call the same `score()` function. If the API had its own scoring
  copy, the live demo and the results slide could disagree, and that's
  the bug that sinks a Q&A.
- **Offline and online are separate on purpose.** Tuning runs before the
  demo and writes `results/weights.json`. The live API only reads it.
  Nothing slow or random happens on stage.
- **Only the API writes to the database.** The dashboard reads through
  the API. This avoids SQLite lock errors and gives everyone one contract
  to code against.
- **ElevenLabs owns all the audio.** The backend is plain HTTP and never
  touches speech. That cuts the hardest part of voice out of scope.
- **The activity log is a feature, not debugging.** Showing "merged,
  re-ranked, #12 to #4" live is the clearest proof of autonomous
  reasoning, which is 30% of the score.
- **Hazards are checked twice.** The agent's prompt asks about downed
  poles, and the API also scans the text. Safety shouldn't depend on one
  layer.
- **Hash phone numbers.** Store a salted hash and compare against it for
  status lookups. It works the same and gives a clean privacy answer.

## Engine contracts (agree before anyone codes)

```text
engine/
  load_tickets() -> DataFrame
  build_features(lights, layers, as_of) -> DataFrame
  score(features, weights) -> Series
  plan_week(queue, order, budget_min) -> list[light_id]
  simulate(tickets, policy, budget_min) -> RunResult
  project_fix_dates(queue, weights, budget_min) -> {light_id: date}

engine/live.py  (the only module the API imports from engine/)
  load_tuned_weights() -> dict
      results/weights.json, else config.DEFAULT_POLICY_WEIGHTS
  load_live_layers() -> dict
      school and transit layers, loaded once at API startup
  rerank(lights, layers, weights, budget_min, as_of) -> DataFrame
      in:  index = light id; columns latitude, longitude, comm_name,
           is_damage (bool), first_reported (Timestamp), call_count (int)
      out: same index, sorted by rank, plus near_school, near_transit,
           age_days, neighbours_dark, score, rank (1 = fixed next),
           reasons, expected_fix_date ("YYYY-MM-DD", or None if more
           than 12 weeks out)
  what_if(lights, layers, policy, budget_pct, as_of) -> dict
      policy in {fifo, v1, tuned}; returns {planned: DataFrame (rerank
      columns, visit order), skipped: DataFrame, minutes_used: float,
      note: str}
  demo_queue(as_of) -> DataFrame
      open lights at as_of from the tuned-policy replay, same columns
      as rerank's input
```

The database uses `lat`/`lon` and the engine uses `latitude`/`longitude`.
One adapter in `api/service.py` renames them; the engine never sees
`lat`/`lon`, and the API never copies scoring logic.

The `reasons` field (like "damage ticket, near a school, 3 calls") lets
the dashboard and the voice agent explain every rank.

## Build order: thin slice first

- **First hour:** agree on the contracts above. The API returns fake data
  and the dashboard draws a fake queue.
- **By Saturday noon:** one thin path works end to end using only FIFO:
  `fake_call.py` hits `/report`, the light shows up on the map. Then
  point the ElevenLabs agent at it.
- **Saturday afternoon:** deepen each layer: real scoring, school and
  transit data, tuning, crew cut, dispatcher note.
- **Saturday 9 PM:** feature freeze.

A working thin slice early means there is always something to demo, and
every later hour just makes it better.

## How the team works

**Commands everyone uses:**

```text
make setup     create venv, install requirements
make results   python -m engine.run_all
make api       uvicorn api.main:app --port 8000
make dash      streamlit run dashboard/app.py
make tunnel    ngrok http 8000
make test      pytest -q
make reset     restore demo state
```

**Roles (five people, one owner per file):**

| Role | Owns |
|---|---|
| Engine lead | `engine/` (including `live.py`), `results/`, non-raw `data/`, engine and tuning tests, `ANTHROPIC_MODEL` in `config.py` |
| Backend lead | `api/` except `geocode.py`, API tests |
| Voice lead | `voice/`, `api/geocode.py`, `scripts/fake_call.py`, `DEMO_ADDRESSES` in `config.py` |
| Dashboard lead | `dashboard/` |
| Pitch lead | `docs/` (design doc, demo script, architecture diagram, slides), `README.md` |

Need a change in a file you don't own? Ask its owner.

**Rules:**

- `main` must always run. Each person works on a branch named after
  themselves.
- Merge at least every three hours with small pull requests and a quick
  review from one teammate.
- A piece is done when it runs from a fresh clone with `make`, has a test
  or a demo command, and is mentioned in the README.

**Checkpoints (Saturday, October 3, then Sunday):**

| Time | Must be true |
|---|---|
| Sat 10:00 | Contracts merged; API and dashboard run on fake data |
| Sat 13:00 | Thin slice works end to end with FIFO; a fake call appears on the map; the voice agent reaches the API |
| Sat 18:00 | Scoring, tuning, crew cut, dispatcher note, and activity log all working |
| Sat 21:00 | Feature freeze; record the backup demo video |
| Sun 10:30 | Submitted. The hard deadline is noon |

## Risk register

| Risk | Fallback |
|---|---|
| Venue Wi-Fi or ngrok fails | Run `fake_call.py` live and show the recorded call |
| An address can't be geocoded | Demo address list, then ask for an intersection |
| Tuned weights don't beat version 1 on the test window | Report it honestly; the gain over FIFO is still the story |
| Merge conflicts | Folder ownership and frequent small merges |
| LLM call fails | Template note fills in automatically |

The deciding question for any disagreement: does it make the demo more
reliable or the result more convincing? If not, keep the decision as
written.

**Deliberately not building:** login, a real phone number, cloud
hosting, websockets, or microservices.

## Production story (for the scalability slide)

A nightly job pulls new tickets from the 311 open data feed, the offline
layer runs on Databricks over the full multi-year history, weights are
re-tuned weekly, and the API runs in the City's cloud behind a real phone
number and single sign-on for dispatchers. (Databricks is a sponsor, so
this line lands well.)

## Data

`data/street_lights_311.csv`: 774 Calgary 311 tickets, Mar 23 to Aug 27,
2026, filtered from the full City of Calgary 311 export (`data/raw/`,
gitignored, 1M+ rows of every service type) by
`scripts/prepare_seed_data.py`. Columns: service_request_id,
requested_date, updated_date, closed_date, status_description,
service_name, comm_name, address, longitude, latitude.

Known facts (measured from the actual seed data — the open-data feed
updates continuously, so exact counts will drift if re-pulled):
- `address` is empty for every row. Use latitude and longitude.
- No missing coordinates.
- `service_name` is "Roads - Streetlight Maintenance" (589) or
  "Roads - Streetlight Damage" (185).
- Status: 762 Closed, 9 Duplicate (Closed), 2 Open, 1 Duplicate (Open).
- Tickets per week over the window: mean 32.9, min 0, max 74 (22 weeks).
- Most tickets close the same day they open, so `closed_date` likely
  means "handed off", not "fixed". Never use `closed_date` as a repair
  date.
- The organizers' starter ranks all tickets, including closed ones. We
  replace it with a historical replay.

Licence: Open Government Licence - City of Calgary. Cite it.

## Coding standards

- Python 3.11. Type hints everywhere. Google-style docstrings.
- Use logging, not print (except for CLI result tables).
- Constants come from `config.py`. No magic numbers in logic.
- Small functions with plain names. pandas + numpy first. No heavy
  frameworks.
- Never commit secrets. Keys live in `.env` (gitignored) and are listed
  in `.env.example`.
- Never invent data, results, or dataset IDs. If a download fails, say
  so and fall back gracefully.

## Working style

- Before coding a phase, show a short plan (files and functions) and
  wait for sign-off.
- After coding, run it and show the real output.
- Commit after each working step with a clear message.
- Claude must never appear as a contributor, co-author, or author on
  anything in this repo: no `Co-Authored-By` trailers, no commits
  authored as Claude, no PRs/issues opened under a Claude identity.
  Commits are authored by the human teammate who asked for them, full
  stop.
