Lamplighter — senior engineering review, October 3, 2026

Scope: the current working tree, including engine, API, dashboard, scripts,
voice assets, configuration, tests, documentation, and saved result metadata.
Application code and the live database were not modified for this review.
Behavioral probes used synthetic inputs, mocked external services, and temporary
SQLite databases. The existing uncommitted work was preserved.

The architecture is suitable for this project. Keep the modular monolith,
SQLite, shared scoring functions, and the Streamlit dashboard. The next work
should strengthen domain rules and reproducibility before adding more features.
Splitting files alone would leave the most important defects intact.

Validation update before commit: **76 tests passed**. Ruff lint and formatting
checks pass. The full-run reporting window now includes the final week's workdays,
so the conservation test passes; the original finding is retained below as a
record of the defect and its acceptance criteria.

Evaluator changes arrived during the review. I rechecked the final source rather
than repeating the previous audit: school/transit risk now reaches the metric,
and later reports no longer retroactively increase earlier risk in the checked
midnight-date cases. A one-day school example now produces 2.0 weighted days;
a later damage report leaves a prior two-day school-risk window at 4.0.
The other findings below apply after those improvements.

**Prioritized correctness findings**

1. **Resolved — Full-run metrics disagreed about the simulation horizon.**
   Location: `engine/simulate.py:337`, `:374`, `:411`, `:418`.

   The replay scheduled the final Monday's repairs across that whole week, while
   the default reporting window stopped on Monday. The conservation test found
   463 total repairs versus 448 attributed to communities. The default window
   now includes the final Friday, and the test passes.

   Refactor: define one explicit replay end and one reporting interval, with a
   consistent endpoint convention. Derive totals, community counts, exposure,
   and crew time from the same recorded events. If backlog is deliberately a
   whole-run measure, name it accordingly in both the contract and display.
   Acceptance: totals equal their community breakdown; appending observations
   after a reporting cutoff does not change metrics before that cutoff.

2. **P1 — A scheduled light is removed before its repair actually occurs.**
   Location: `engine/simulate.py:299`, `:321`.

   Every selected light is popped from the open queue on Monday, even when its
   assigned repair date is Friday. A repeat report received on Tuesday is merged
   the following Monday, after the original light has already disappeared.
   Reproduction: five Sunday outages plus a Tuesday repeat at the Friday stop
   produce six repairs; `REPEAT` appears as a separate job in the next snapshot.
   Policies therefore change the number of apparent jobs through event ordering,
   in addition to changing which jobs are prioritized.

   Refactor: keep weekly planning, but process report arrivals and repair
   completions in chronological order. Track scheduled and resolved states
   separately; only completion removes a light from duplicate matching.
   Acceptance: repeats before completion merge; reports after completion create
   a new outage according to the declared recurrence rule.

3. **P1 — Replanning can spend the same weekly capacity again.**
   Location: `api/service.py:135`, `:167`, `:205`; `engine/live.py:144`.

   Each proposal receives the full weekly budget. Completed repairs leave the
   queue without creating a record of consumed capacity. A later confirmation
   supersedes the old plan and accepts another full-budget proposal on the same
   frozen Monday. In an isolated 420-minute-week fixture, twelve completed
   repairs consumed at least 360 minutes of repair time; the API then confirmed
   another 398.09-minute proposal for the same week. Travel already performed
   would increase the overspend further.

   Refactor: introduce a planning period with total, consumed, committed, and
   available minutes. Define what replacing a plan releases and what completed
   work permanently consumes. Store completion effort or a declared estimate
   and enforce the period budget in the confirmation transaction.
   Acceptance: repeated confirm/repair/replan cycles cannot exceed that period's
   budget, and a new period explicitly restores capacity.

4. **P1 — Confirmation does not guarantee the plan that was reviewed.**
   Location: `api/service.py:46`, `:157`, `:180`; `engine/live.py:143`;
   `engine/run_all.py:149`.

   Database revisions protect queue changes, but policy weights are reread from
   a file during each what-if calculation. Updating weights between review and
   confirmation changes the recomputed plan without changing the reviewed
   revision. In a synthetic test, all thirteen reviewed visits were replaced by
   thirteen different visits and confirmation still succeeded. There is also a
   split source of truth: persisted ranks use startup-cached weights, while
   dashboard plans use freshly loaded weights. The candidate and baseline can
   likewise observe different weight files despite sharing a SQLite snapshot.

   Refactor: use an immutable planning context containing policy version,
   validated weights, layer versions, assumptions, and clock. Bind confirmation
   to a candidate ID or content hash covering this context and the queue revision.
   Publish artifacts atomically; install a new version through one controlled
   path. Acceptance: either the exact reviewed membership is confirmed or the
   request receives a conflict requiring a new review.

5. **P1 — Hazard reports have no durable dispatcher workflow.**
   Location: `api/service.py:294`, `:314`; `api/db.py:117`;
   `dashboard/app.py:157`, `:522`.

   A recognized hazard is stored with `status='hazard'`. The queue query returns
   only `open` lights; ticket inspection is populated from that queue, and repair
   recording requires a confirmed ordinary route. The API says the report is
   flagged for urgent review, but the dashboard offers only a recent activity
   message, with no hazard inbox, acknowledgement, escalation record, or
   resolution path. After subsequent activity, it becomes even less discoverable.
   A sparking-pole probe confirmed that the hazard was stored but absent from
   both queue and plan.

   Refactor: add a persistent hazard worklist with explicit triage states and
   dispatcher actions. Keeping hazards out of routine routes is appropriate;
   that separation needs a complete operational path of its own.
   Acceptance: hazards remain visible until explicitly resolved or handed off,
   and the handoff/result is recorded.

6. **P2 — Retrying report delivery changes priority and invalidates plans.**
   Location: `api/schemas.py:13`; `api/service.py:279`, `:301`, `:317`.

   `/report` has no idempotency identifier. Sending the same successful request
   again inserts another call, increments `call_count`, advances the revision,
   and invalidates the confirmed plan. A duplicate delivery probe produced two
   calls and revision 2. Geographic merging is not delivery deduplication:
   genuine additional calls should count, while retrying one delivery should not.

   Refactor: accept a stable upstream report/tool-call ID, enforce uniqueness in
   SQLite, and persist the corresponding response in the same transaction.
   Reject reuse of an ID with a different payload. Apply this to hazard reports
   as well, where retries currently create separate hazard records.

7. **P2 — Damage and hazard classification are conflated.**
   Location: `api/service.py:269`, `:301`, `:312`.

   New reports set `is_damage` from the hazard flag alone. Routine physical
   damage therefore enters as non-damage, and merging an additional report only
   increments the count. A report saying "Lamp housing is damaged and broken"
   was stored with `is_damage=0`. Keyword matching also classified "The pole is
   down" as non-hazard and "There are no exposed wires" as a hazard.

   Refactor: represent confirmed hazard answers and ordinary damage as distinct
   report facts, collected through the reporting contract. Define escalation
   conservatively and preserve the reported evidence for review. Merge ordinary
   damage into the existing light independently of the report count. Add table-
   driven cases for affirmative, negative, ambiguous, and repeated reports.

8. **P2 — Repair dates ignore the stated daily crew limit.**
   Location: `engine/simulate.py:164`, `:491`; `CLAUDE.md:97`.

   `_assign_workdays()` spreads stops by count, rather than travel and repair
   duration. At the supported 50% setting, a 420-minute week implies 84 minutes
   per day. Twelve stops are split into 3/2/3/2/2 repairs: two days already need
   90 repair minutes before any travel. A separate 60-minute-week fixture also
   assigns a 30-minute repair to a day with only twelve available minutes.

   Refactor: choose and document daily working time, carryover, and depot-return
   assumptions; then share a duration-aware schedule between replay and date
   projection. Until then, present capacity and dates as weekly approximations
   rather than a feasible day-by-day schedule.

9. **P2 — The engine does not handle valid boundary cases consistently.**
   Location: `engine/simulate.py:114`, `:121`, `:288`.

   Empty replay input raises `AttributeError: 'float' object has no attribute
   'normalize'`, even though other engine entry points handle empty queues.
   Separately, interval risk accounting floors each subinterval to whole days.
   Splitting a two-day outage with a repeat report at noon produced only one
   total dark day. The committed 774-ticket dataset uses midnight dates, so the
   latter is a future-input compatibility problem rather than a demonstrated
   error in that particular dataset.

   Refactor: validate input schema and timestamps at the engine boundary, define
   the empty result, and decide whether dark nights mean nightly observations
   or continuous exposure. Use that definition consistently instead of rounding
   every history segment independently.

10. **P2 — Caller lookup needs canonicalization and privacy-safe transport.**
    Location: `api/service.py:259`, `:354`; `api/main.py:149`.

    Removing punctuation does not normalize country codes. `403-555-0100` and
    `+1 403-555-0100` produce different hashes, so a resident can fail to retrieve
    their report when the voice provider changes formatting. The GET status
    contract also places the raw number in the query string. The installed
    Uvicorn access-log path formatter retains that query string; database
    hashing does not protect those logs.

    Refactor: normalize to one documented phone format before hashing, and use
    a lookup transport/logging policy that excludes raw phone numbers. Test both
    lookup equivalence and access-log redaction with synthetic numbers.

11. **P2 — Geocoding treats any in-city first result as a precise location.**
    Location: `api/geocode.py:50`, `:64`.

    The response's precision/type is ignored. A mocked result explicitly typed
    as the city boundary of Calgary was accepted as a light coordinate. A broad
    or ambiguous description can therefore create or merge a report at a city
    or area centroid. A successful HTTP response is not proof of a usable street
    location. `DEMO_ADDRESSES` is also empty, so normal address lookup lacks the
    intended deterministic demo fallback.

    Refactor: return a structured location result with precision, candidate
    description, and clarification requirement; validate address/intersection
    suitability and confirm the location before using it for duplicate matching.
    Test broad results, empty responses, timeouts, malformed payloads, and cache hits.

**Product limitations and reproducibility**

- The frozen demo clock is intentional and visible. However, a newly reported
  light receives `first_reported=DEMO_DATE` and is excluded from that Monday's
  plan. There is no advance-period action, so that new light can never become
  eligible through normal live-demo actions. Decide how to demonstrate the full
  new-report-to-repair cycle; an explicit simulation clock/period transition
  would also support the capacity ledger.
- `voice/tools.json` has no tools; the prompt/setup/transcript are placeholders,
  and `scripts/fake_call.py` raises `NotImplementedError`. These are unfinished
  integration work, separate from code cleanup. The external voice flow has not
  been validated in this review.
- The saved tuning log contains three trials, while configuration declares 200.
  Saved weights and summaries lack a run manifest tying them to code, inputs,
  metric definition, and effective trial count. Preview input hashes currently
  match the files on disk, but the manifest does not identify the engine version.
  The existing improvement figures cannot validate the corrected evaluator.
- Missing school/transit files become absent features; invalid CSV coordinates,
  dates, or weight files have no comprehensive boundary validation. Make degraded
  input explicit in the UI/API and artifact manifest, rather than silently
  treating an unavailable layer as evidence that no lights are near it.
- `requirements.txt` specifies lower bounds only; there is no checked-in lockfile
  or CI workflow. The current test run uses the isolated Python 3.13 environment,
  while the architecture document specifies 3.11. Choose a supported runtime and
  make clean-install/test/browser checks reproducible on it.
- `docs/AGENT_PROMPTS.md` still describes API/dashboard code as stubs and promotes
  the old 22.2% result. `CLAUDE.md` retains an obsolete dashboard layout, and
  `docs/DESIGN.md` is a placeholder. Update implementation guidance alongside
  contracts so the next contributor does not reintroduce old assumptions.

**Refactoring sequence**

| Order | Area | Concrete change | Purpose |
|---|---|---|---|
| 1 | `engine/simulate.py` | Extract chronological replay, duration-aware scheduling, and pure metric aggregation; keep one declared period boundary | Fix duplicate timing and feasible repair dates while preserving metric conservation |
| 2 | `api/service.py`, `api/db.py` | Introduce a planning-period ledger and explicit plan/visit transitions | Enforce capacity across repeated confirmations and completed work |
| 3 | `engine/live.py`, API planning | Inject one validated, versioned planning context; confirm immutable candidates | Prevent policy drift and make reviewed decisions reproducible |
| 4 | Reporting/geocoding | Separate ingestion, delivery deduplication, location resolution, damage facts, and hazard triage | Keep input handling from silently changing priority or losing urgent work |
| 5 | API contracts and dashboard data | Share strict wire models and one engine-to-contract serializer; retain presentation-specific view models separately | Eliminate drift among `api/schemas.py`, `dashboard/data.py`, and preview export adapters |
| 6 | `dashboard/app.py` | Extract session-state transitions, API client, plan review, ticket details, and queue components | Make polling, review invalidation, selection, and feedback testable without rendering the whole app |
| 7 | Storage/runtime | Move remaining SQL behind focused repository functions; add schema versions and injectable DB/settings/clock | Make upgrades and startup tests safe without hardcoding the real demo database |
| 8 | Build/results/docs | Pin the runtime/dependencies; add CI and a small checked-in browser smoke suite; publish versioned artifacts atomically | Make a fresh checkout reproduce the reviewed behavior and evidence |

The dashboard currently contains 539 lines of rendering, callbacks, mutation
handling, and global session state in one entry point. Its HTTP and schema code
is combined in `dashboard/data.py`; reporting and plan operations share the
368-line API service. The reason to split these files is to isolate their
invariants and tests, not to hit an arbitrary line limit. Keep the existing
`dashboard/maps.py` extraction and data validation.

A few smaller presentation corrections should accompany that work: `reasons()`
accepts weights but does not use them, so "Why this light ranks here" currently
shows general facts even for FIFO or zero-weight features. Display actual policy
contributions separately from ticket facts. Also normalize the date when calling
it a repair *week*, and keep completed confirmed visits inspectable instead of
clearing selection when their ID is no longer in the open queue.

Planning calculations currently run inside read/write transactions, and every
poll recalculates the scenario and often the baseline. One isolated 198-light
scenario took about 0.63 seconds here, which does not justify a wholesale
performance rewrite. After adding model versions, cache by queue revision and
planning context, reuse immutable spatial indexes, and shorten write transactions
with a final revision check. Measure latency before adopting a more complex planner.

**What is working well**

- SQLite WAL, parameterized SQL, immediate write transactions, and revision checks
  give a sound basis for consistent updates.
- Confirmation and repair retries are covered, as are stale writes, competing
  confirmations, rollback after scoring failure, and preserving a completed queue
  across startup.
- The dashboard validates response membership/counts/capacity, keeps stale views
  scoped to the chosen scenario, and disables mutations on disconnected views.
- Map identities use ticket IDs, routes distinguish visit order from priority,
  and capacity comparison checks actual membership rather than only totals.
- Preview mode is visibly separate, evaluation results are labeled provisional,
  HTML interpolation is escaped, and CSV exports neutralize formula prefixes.
- Seeded tuning and separate policy/risk weights are useful foundations once the
  replay and artifact provenance are correct.

**Tests worth adding as part of the fixes**

Use small synthetic fixtures with exact expected outcomes for the findings above:
period capacity across multiple plans; policy changes between review and confirm;
repeated report delivery; hazard lifecycle; pre/post-completion repeats; daily
schedule limits; full-run/window conservation; empty replay; and non-midnight
report history. Add startup and migration tests against a temporary DB; current
API endpoint tests override the connection and intentionally skip lifespan.

Keep network access disabled by default in tests. `engine.live.what_if()` still
defaults to LLM notes, and several live-engine tests use that default; importing
`api.main` loads `.env`. A developer's configured key could therefore turn unit
tests into external service calls. Inject a deterministic note provider and test
external integrations explicitly. Keep browser selection and confirmation smoke
checks in the repository; the previous manual browser scripts live under `/tmp`.

Reviewed source fingerprints (SHA-256 prefixes):

| File | Fingerprint |
|---|---|
| `engine/simulate.py` | `38e9f8e423a519d6` |
| `engine/live.py` | `1b74e537f15c9257` |
| `engine/tune.py` | `e217e127a5a6fda2` |
| `engine/run_all.py` | `e56db20ede1e73ae` |
| `api/service.py` | `fe1475281f47b775` |
| `dashboard/app.py` | `3305c9a9e3f2d8e7` |
| `tests/test_simulate.py` | `a5e42afc173453ed` |
