# Agent prompts (five-person split)

Each teammate starts their own Claude Code session and pastes the
**shared block** followed by **their role block**. The contracts referenced
here are written into CLAUDE.md ("Data model", "API contract", "Engine
contracts", "How the team works").

## Shared block (everyone pastes this first)

```text
You are helping one member of team NO Dark Night build Lamplighter (IEEE YP
Hackathon, Case 6). Five people work in parallel, each in their own Claude
Code session, each owning different files.

Before anything else:
1. `git checkout main && git pull origin main`, then create or update your
   own branch from main (use your teammate-name branch, e.g. `satyam`).
2. Read CLAUDE.md fully. It is the source of truth for architecture, coding
   standards and working style. Follow it exactly, especially:
   - Show a short plan (files + functions) and WAIT for my sign-off before coding.
   - After coding, run it and show real output. Never invent data or results.
   - Commit after each working step. Claude must never appear as author or
     co-author: no Co-Authored-By trailers.
   - Never commit secrets (.env is gitignored).
3. Only edit the files your role owns (see "Roles" in CLAUDE.md). If you
   need a change in someone else's file, stop and tell me what to ask them for.
4. Small PRs to main at least every 3 hours. main must always run.

Current state (Sat Oct 3, evening): engine/, api/ and dashboard/ are built
and merged to main (77 tests pass). results/ has real test-window numbers:
FIFO 4018.5 -> v1 3357.2 -> tuned 3006.0 risk-weighted dark nights (-25.2%).
scripts/fake_call.py works against the live API. The ElevenLabs voice
agent in voice/ also works end to end (see voice/SETUP.md). Still open: the
pitch material in docs/. Read the code before redoing anything in the role tasks
below; many Engine and Backend tasks are already done.

AGREED CONTRACTS (also in CLAUDE.md; code against these and do not change
them without the team):

A. Database: the DB stores facts and engine outputs, never derived features.
   `lights` has no near_school or near_transit columns. Columns: id, lat, lon,
   comm_name, is_damage, first_reported, call_count, status, fixed_at, score,
   rank, expected_fix_date, reasons. calls/events/geocode_cache are unchanged.
   The engine recomputes features on every re-rank.

B. engine/live.py (owned by the Engine lead) is the only engine module the
   API imports:
   - load_tuned_weights() -> dict       # results/weights.json, else config.DEFAULT_POLICY_WEIGHTS
   - load_live_layers() -> dict         # schools/transit layers, loaded once at API startup
   - rerank(lights, layers, weights, budget_min, as_of) -> DataFrame
       in : index = light id; columns latitude, longitude, comm_name,
            is_damage (bool), first_reported (Timestamp), call_count (int)
       out: same index, sorted by rank, adds near_school, near_transit,
            age_days, neighbours_dark, score, rank (1 = fixed next),
            reasons (str), expected_fix_date ("YYYY-MM-DD", or None if more
            than 12 weeks out)
   - what_if(lights, layers, policy, budget_pct, as_of) -> dict
       policy in {"fifo", "v1", "tuned"}; returns {"planned": DataFrame
       (rerank columns, visit order), "skipped": DataFrame, "minutes_used":
       float, "note": str (dispatcher note)}
   - demo_queue(as_of) -> DataFrame     # open lights at that date from the
       tuned-policy replay, same input columns as rerank
   The DB uses lat/lon and the engine uses latitude/longitude. The API does
   the rename in ONE adapter in api/service.py; the engine never sees lat/lon.

C. API contract (CLAUDE.md):
   - GET /queue items: {ticket_id, lat, lon, rank, score, reasons,
     expected_fix_date, comm_name, call_count}
   - GET /plan?budget_pct=&policy= -> {budget_pct, policy, lights_planned,
     minutes_used, skipped_count, note, queue: [QueueItem...]}  (read-only)
   - Event types: new, merged, rerank, hazard, fixed, reset. Messages are
     human-readable, e.g. "Call merged, light moved from #12 to #4."
   - POST /report and GET /status require header X-Lamplighter-Voice-Secret.

D. Demo clock: "today" is config.DEMO_DATE (Mon 2026-08-24) for scoring,
   first_reported and fix dates. Event `at` timestamps use the real wall
   clock so /events?since= works.
```

## 1. Engine lead

```text
ROLE: Engine lead. You own engine/, results/, tests/test_engine*.py and
tests/test_tune.py, data/ (non-raw), plus ANTHROPIC_MODEL in config.py.
Your #1 job is unblocking the Backend lead fast.

Tasks, in order:
1. Within the first ~30 min, commit engine/live.py with every function from
   contract B, with real signatures and docstrings and a quick working
   version (e.g. expected_fix_date = next Monday + 7 days * (rank //
   lights_per_week)). Open a PR right away so the backend can import it.
2. Implement engine.simulate.project_fix_dates() properly: repeatedly call
   plan_week() on the ranked queue, week by week from as_of; each light's
   date is the workday the crew reaches it (reuse _assign_workdays); stop
   after 12 weeks (later lights -> None). Then make live.rerank() use it.
3. live.what_if(): build the order for fifo/v1/tuned, run plan_week at
   budget_pct * WEEKLY_CREW_MINUTES, return planned/skipped/minutes_used,
   and call engine.note.dispatcher_note(planned, skipped, crew_cut_pct).
   planned/skipped must carry the feature columns (note.py reads
   near_school/near_transit).
4. live.demo_queue(as_of): the open queue at as_of from a tuned-policy
   replay (NOT build_open_queue(), which never fixes anything and gives 198
   lights; a realistic mid-replay queue is ~50-90). Add a stop_at/snapshot
   option to simulate() if needed.
5. Bug: tests/test_tune.py calls random_search(n_trials=3), which overwrites
   the real results/tuning_log.csv (the committed file has 3 trials, not
   200). Give random_search a log_path argument (default TUNING_LOG_CSV) and
   use pytest tmp_path in the test.
6. Reproducibility: data/raw/* is gitignored, so a fresh clone has no
   schools/transit layer and gets different numbers. Commit the small
   derived school and transit CSVs under data/ (check the size and cite the
   Open Government Licence - City of Calgary in data/README.md) and point
   config paths at them.
7. ANTHROPIC_MODEL = "claude-sonnet-5" looks invalid. Check the current
   Anthropic model IDs and fix it; a bad ID silently falls back to the
   template note.
8. Rerun `make results`, confirm tuning_log.csv has 200 rows, and report the
   final test-window numbers (they may shift slightly once the layers are
   committed). Tell me the numbers so the Pitch lead can update the slides.
9. Stretch: a damage-first policy in run_all and summary.csv.

Tests: rerank on a 3-light hand-made frame (ranks, dates, reasons present);
project_fix_dates returns Mondays-to-Fridays within the 12-week horizon.
Done = `make test` and `make results` pass from a fresh clone.
```

## 2. Backend lead

```text
ROLE: Backend lead. You own api/ (main.py, service.py, db.py, schemas.py,
seed.py) and tests/test_api*.py. You do NOT own api/geocode.py (Voice lead)
or engine/ (Engine lead). CLAUDE.md already documents the contracts.

Tasks, in order:
1. Contracts PR (first ~30 min, merge fast): update SCHEMA_SQL in db.py
   (drop near_school/near_transit) and schemas.py (QueueItem and
   PlanResponse per contract C). Nothing else in this PR.
2. db.py: implement every stub (get_light, upsert_light, get_open_queue,
   insert_call, insert_event, get_events_since, geocode cache get/set). Plain
   sqlite3, parameterized SQL only.
3. service.py:
   - _to_engine_frame(rows) / back: the single lat/lon <-> latitude/longitude
     adapter.
   - rerank_and_save(conn): load open lights -> engine.live.rerank(...) with
     the tuned weights and layers loaded once at startup -> write score, rank,
     expected_fix_date and reasons back -> return {id: (old_rank, new_rank)}.
   - check_hazard(), hash_phone() (salt from PHONE_HASH_SALT in .env, sha256).
   - report_light(): hazard -> status 'hazard' + hazard event, no queue entry,
     message tells the caller it was escalated. Else geocode via
     api.geocode.geocode(conn, text); None -> needs_clarification=True. Else
     merge with an open light within DUPLICATE_RADIUS_M (call_count +1) or
     create one (id = new ticket id, first_reported = DEMO_DATE), insert the
     call, rerank, log a merged/new + rerank event ("light moved from #12 to
     #4"), and return a spoken-friendly message: max 2 sentences, date as
     "the week of <Mon date>".
   - check_status(), mark_fixed(), build_plan() via engine.live.what_if().
4. main.py: wire all routes; /report and /status require the voice secret.
   Load layers and weights once on startup.
5. seed.py: build_demo_state() clears tables, inserts engine.live.demo_queue
   (DEMO_DATE) as lights (channel 'seed' calls), reranks, logs a reset event.
   Call it on startup if the DB is empty and from POST /demo/reset.
6. If engine/live.py hasn't landed when you need it, write a temporary local
   shim with the same signatures and delete it once the real one merges.
   Don't copy scoring logic into api/.

Coordinate: the Voice lead's scripts/fake_call.py is your end-to-end test.
The thin-slice goal is that fake_call -> /report -> the light shows in
/queue with a rerank event.
Tests (FastAPI TestClient + a temp DB): report creates a light; a second
report 100 m away merges (call_count 2); a missing secret gives 401; a
hazard text never enters the queue.
```

## 3. Voice lead

```text
ROLE: Voice lead. You own voice/ (system_prompt.md, tools.json, SETUP.md,
sample_transcript.md), api/geocode.py, scripts/fake_call.py, and the
DEMO_ADDRESSES dict in config.py (only that dict).

Tasks, in order:
1. scripts/fake_call.py FIRST (the backend's test harness and the stage
   fallback): argparse options --location, --description, --phone,
   --status; POST /report or GET /status on http://localhost:8000 with the
   X-Lamplighter-Voice-Secret header from .env; print the response. Include
   a preset "--demo" call that reliably MERGES with a seeded light (so the
   rank jump shows), plus a hazard preset.
2. DEMO_ADDRESSES: 5-8 real Calgary addresses/intersections, each within
   150 m of a real light in the seed data (use engine.data.load_tickets()
   to pick them; keep lowercase normalized keys). At least one should land
   near a school. Never invent coordinates.
3. api/geocode.py: normalize text -> DEMO_ADDRESSES (exact, then simple
   fuzzy) -> geocode_cache (via api.db functions) -> Nominatim (with
   NOMINATIM_USER_AGENT, rate limited, bounded to Calgary, cached on
   success) -> None. Never raise; a network failure returns None. Tests use
   a mocked Nominatim.
4. ElevenLabs agent (check the CURRENT ElevenLabs Agents docs for the
   webhook/server-tool format; don't guess):
   - voice/system_prompt.md: per CLAUDE.md "Voice agent decisions" (read the
     address back, always ask about downed poles/exposed wires before
     filing, max 2 sentences, under 2 minutes, "the week of"). On
     needs_clarification, ask for the nearest intersection. On hazard, tell
     them to stay away and that it's escalated.
   - voice/tools.json: report_light -> POST /report and check_status -> GET
     /status, both sending the secret header.
   - The browser test call has no caller ID, so the agent must ask for a
     phone number for status lookup. Check whether ElevenLabs exposes a
     caller-ID variable for real phone deployments and note it in SETUP.md.
   - voice/SETUP.md: exact steps (ngrok via `make tunnel`, where to paste the
     URL and secret, how to start a browser test call).
5. Once the backend's /report works: a real browser test call through ngrok.
   Save the transcript to voice/sample_transcript.md and record the call as
   the backup video for the demo.

Until /report exists, test fake_call.py against a 10-line local mock and
don't commit the mock.
```

## 4. Dashboard lead

```text
ROLE: Dashboard lead. You own dashboard/ only. The dashboard never touches
the DB or engine: live data comes from the API over HTTP, and static
headline numbers come from files in results/.

Layout (CLAUDE.md "Dashboard layout"), built for a projector: big fonts,
few colours.
- Top row, 3 cards: FIFO vs tuned risk-weighted dark nights, % improvement,
  fixes per crew-hour (read results/summary.csv; the numbers are real now).
- Middle: pydeck map of Calgary (open lights from GET /queue, top 10
  highlighted and sized by score, tooltip shows rank + reasons + expected
  fix date) | live activity log from GET /events?since= (newest first).
- Bottom: this week's list (rank, community, reasons, expected fix date)
  and the dispatcher note.
- Sidebar: policy picker (fifo/v1/tuned) + crew budget slider (50-120%)
  -> GET /plan; show the planned list, minutes used, skipped count and the
  note from the response. Add a "crew cut 80%" panel from
  results/crew_cut_communities.csv (communities that lose a visit) and show
  results/policy_comparison.png + results/sensitivity.png in an expander.
- Live refresh: st.fragment(run_every=3) around the map + log + list only.

Tasks, in order:
1. Build the whole layout NOW against a small fake-data module
   (dashboard/fake_data.py) shaped exactly like contract C, behind a
   USE_FAKE flag that switches to the real API automatically when
   GET /health fails.
2. A thin API client (dashboard/api_client.py) with timeouts; on errors,
   show a small "API offline" badge, never a stack trace.
3. Switch to the real endpoints as the Backend lead merges them.
4. Demo polish: when a new or merged event arrives, briefly highlight that
   light on the map and the "#12 -> #4" line in the log; this is the
   autonomous-reasoning moment judges watch for.

Done = `make dash` runs with the API off (fake data) and with it on (live),
and a fake_call.py report shows up on screen within ~3 seconds.
```

## 5. Pitch lead

```text
ROLE: Pitch lead. You own docs/ (DESIGN.md, DEMO_SCRIPT.md, architecture
diagram, slides material), README.md, and keeping the design doc in sync.
You write no app code. Pitch, commercialization and the architecture
diagram are ~35% of judging.

Sources: CLAUDE.md, the team design doc
(https://claude.ai/artifact/FbfRfmEWQTaDDNdEbXCXdz), results/ (summary.csv,
policy_comparison.png, sensitivity.png, crew_cut_communities.csv,
weights.json). Use only real numbers from results/; never invent figures.

Tasks, in order:
1. Architecture diagram (docs/architecture.svg or .png + editable source):
   resident -> ElevenLabs -> ngrok -> FastAPI (only DB writer) -> engine
   (pure) <- dashboard via API; offline path: data -> run_all -> tune ->
   results/weights.json -> read by the API. Show the hazard and
   needs_clarification exits.
2. Design-doc fixes (edit the shared doc if your tools can reach it,
   otherwise draft the text in docs/DESIGN.md and tell me):
   - Section 4: lights drops near_school/near_transit; "the database stores
     facts and decisions; the engine owns the features."
   - Section 3: tuning bounds are 0-2 (WEIGHT_MAX), not 0-10; v1 weights =
     config.DEFAULT_POLICY_WEIGHTS; budget = 840 crew-minutes/week
     (validated, see CLAUDE.md), not "85% of arrivals"; features.yaml is a
     stretch goal; data is 774 tickets (762 closed), not 800.
   - Section 10: the five-person role split.
   Then export the final version to docs/DESIGN.md for submission.
3. Slide outline + speaker notes (docs/PITCH.md): problem (FIFO lets a dark
   school zone wait) -> live demo -> results (FIFO 3250.5 -> v1 2870.5 ->
   tuned 2528.2 risk-weighted dark nights on unseen Jul-Aug weeks, -22.2%;
   median days dark 17 -> 13; holds at 70/85/100% budget) -> crew-cut story
   (80% budget: which communities lose a visit) -> "why it's not circular"
   (strategy vs scorecard, held-out weeks) -> commercialization (City of
   Calgary, other limited-crew queues: potholes, signals) -> production
   story (Databricks, nightly 311 pull, weekly re-tune, SSO) -> team. Get
   the final numbers from the Engine lead after they rerun `make results`.
4. docs/DEMO_SCRIPT.md: exact click/talk steps, under 5 minutes, with
   `make reset`, the fake_call.py fallback commands, and who does what.
   Include likely Q&A with answers (what "closed" means, 30 min/30 km/h
   assumptions, depot location, why random search).
5. README: setup, every make command, results table, licence citation.
6. Sat 21:00: run the full rehearsal and record the backup demo video.
```
