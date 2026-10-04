# Engineering review — October 3, 2026

Scope: all application modules, scripts, tests, configuration, voice assets,
documentation, and the saved results tables in the current working tree.
Existing uncommitted work was included in the review and preserved.

## Implementation update

The six frontend changes are implemented: linked map/queue selection and ticket
inspection; actual route-membership capacity comparisons; separate planned and
waiting tables; numbered map stops and school/transit/visit-order layers;
separate operational and evaluation workspaces; and authenticated review,
confirmation, and repair recording backed by SQLite transactions.

The API now implements its business routes and serves an atomic `/dispatch`
snapshot containing the selected plan, 100% baseline, revision, and activity.
Confirmation persists actual assignments and their original stop numbers.
New reports invalidate confirmed work; stale revisions are rejected. Retried
confirmations/repairs are idempotent, and failures roll back the complete write.
Historical report history is explicitly partial. Local setup generates ignored
access keys without overwriting existing configuration.

Projection dates now use the queue snapshot clock, and Monday arrivals wait for
the following week's route. Estimates remain approximate: daily crew allocation,
historical repeat timing, risk accounting, empty replay behavior, and evaluator
window defects below still need correction. No saved improvement metric has been
regenerated or promoted as validated. ElevenLabs integration remains unfinished.

Validation: **73 tests passed**; repository-wide Ruff lint, formatting checks
for the changed Python files, and `git diff --check` passed. Chrome verified
preview controls, layer toggles, map-pin/queue-row selection, ticket inspection, evaluation navigation,
real API plan confirmation and repair recording, with zero JavaScript errors.
The mobile document width matched its 390px viewport. Screenshots:
[preview](dashboard-preview.png), [live](dashboard-live.png), [mobile](dashboard-mobile.png).
Validation used an isolated temporary environment; the existing `.venv` was
preserved. Browser writes recorded simulated repairs in the ignored local database.

The second-pass observations below describe the state before this implementation;
the API-stub and projection-clock findings are now resolved.

## Second pass: executable checks and frontend work

The second pass re-read the engine, API, dashboard, scripts, contracts,
configuration, tests, voice assets, and saved artifacts. A fresh temporary
environment resolved the import stalls encountered during the first pass.
All 39 original tests passed before the frontend changes. Passing those
tests does not establish simulator correctness: the following targeted
probes reproduced failures outside their coverage.

| Failure case | Expected behavior | Observed behavior |
|---|---|---|
| A July 2 repeat damage report is appended to a June 28 light; both datasets have the same July 13 final ticket, zero repair capacity, and June 28–30 reporting window | Past risk remains 2.0 | Risk changes from 2.0 to 4.5 |
| One light is placed exactly at a school; its repair takes one day | Base plus school risk equals 2.0 | Risk stays 1.0, identical to the no-school run |
| Rerank one light at September 7 | Estimated repair is on or after the planning date | Estimated repair is August 31 |
| Replay an empty ticket frame | Return empty metrics or a deliberate validation error | `AttributeError: 'float' object has no attribute 'normalize'` |
| Five Sunday reports are scheduled Monday–Friday; the Friday light receives a Tuesday repeat | Repeat merges before Friday's repair | `REPEAT` survives as a new job in the following Monday's queue |
| Give a depot repair a 60-minute weekly budget under the documented five-day split | A 30-minute repair cannot fit a 12-minute daily budget | It is assigned to Monday |
| Request operational endpoints with FastAPI TestClient | Readiness reflects usable dispatch operations | `/health` is 200 while `/queue` and `/plan` are 500; unauthenticated `/status` correctly returns 401 |

The midweek duplicate case is a separate replay defect: selected records
are removed from `open_lights` immediately on Monday, before their assigned
repair days. Reports are merged in weekly batches after this removal.
Process arrivals and completions chronologically even when planning stays
weekly; otherwise policies change both repair timing and the number of
synthetic jobs through an incorrect event order.

The frontend has been replaced with a dispatch console: a city map,
policy/capacity controls, planning totals, dispatcher brief, activity panel,
community filter, searchable queue, CSV export, and responsive styling.
The default historical preview contains 34 real-data replay lights and
45 engine-generated scenarios (three policies, 50–120% budgets in 5% steps).
`make preview` rebuilds this artifact with input hashes. The dashboard
reads the artifact; it does not import the engine or touch the database.

Historical preview and live dispatch are explicitly separate. Live mode
reads the business endpoints with timeouts and preserves a clearly marked
last successful view for the same policy/capacity if the connection fails.
It rejects malformed values, duplicate IDs, mismatched counts/membership,
unexpected policy/budget, and over-capacity routes. An event-feed failure
does not hide an otherwise usable queue. CSV exports neutralize spreadsheet
formula prefixes. Raw service text is escaped before HTML rendering.

The saved 22.2% improvement is kept in a collapsed, provisional evaluation
section. It is not used as a headline operational claim. Fix dates are
omitted while projection-clock semantics remain incorrect. The UI distinguishes
priority from route order; it omits waiting-item ranks in scenario views
because the current API contract only supplies scenario ranks for selected
items. A versioned plan snapshot endpoint would remove this limitation and
the possibility of changes between separate queue/plan reads.

Frontend validation adds 19 tests covering malformed data, capacity,
timeouts, invalid JSON, event-feed failure, empty queues, missing previews,
all 45 saved scenarios, search, CSV handling, policy/capacity/reset controls,
disconnected live mode, stale-view isolation, and an empty live queue.
Browser verification covers desktop and a
390px mobile viewport. Screenshots: [desktop](dashboard-preview.png) and
[mobile](dashboard-mobile.png).

Final validation: **58 tests passed in 48.04 seconds** in the temporary
environment. Repository-wide Ruff lint, formatting checks for the changed
Python files, and `git diff --check` passed. Chrome exercised search,
policy selection, capacity, reset, and live-disconnection handling with
zero JavaScript errors or failed requests. The mobile document width
matched its 390px viewport. The project's original environment was not
replaced; the preview server was started from the isolated test environment.

The engine defects below remain open. Completing API business operations,
repairing the event timeline and objective, and regenerating evaluation
artifacts remain higher priorities than adding more frontend features.

## Assessment

The architecture fits a small hackathon team and a local demonstration.
The implemented engine is readable and reusable. The resident-reporting
product is still incomplete, and the evaluation has correctness issues
that must be resolved before presenting its improvements as validated.

Keep the modular monolith, SQLite, shared scorer, and offline tuning.
Prioritize metric correctness and one working report-to-dashboard path.

## Decisions worth keeping

- The engine/API/dashboard boundaries are clear. A shared scorer reduces
  the chance that the live queue and historical experiment diverge.
- Policy weights and risk weights are separate. This is the right
  conceptual distinction between a dispatch strategy and its scorecard,
  although the scorecard implementation needs correction below.
- FIFO provides an understandable baseline. Seeded random search is a
  reasonable optimization method for the available time and data.
- Geographic searches use haversine BallTree queries, with radii and
  assumptions centralized in configuration.
- Routing accounts for repair time, travel, and a depot return instead
  of estimating capacity from repair counts alone.
- SQLite WAL mode and foreign keys are enabled. One database writer and
  parameterized queries are sensible implementation constraints.
- The note generator has a deterministic template fallback, tests
  explicitly isolate environment variables, and tuning tests now write
  into temporary directories.
- The documentation explicitly questions whether source `closed_date`
  means repaired. Avoiding that unsupported inference is good judgment.

## Blockers and correctness findings

### 1. School and transit risk are absent from replay metrics

`engine/simulate.py:253` and `:260` evaluate raw stored light records.
Those records never acquire `near_school` or `near_transit`.
`risk_weight()` defaults both absent fields to false. Features computed
inside `make_score_policy()` are temporary and do not update those records.

Consequently, schools/transit influence dispatch selection but contribute
nothing to the risk-weighted dark-night objective, including tuning.

Correction: give the evaluator an explicit layer context and compute
geographic risk for every light, independently of its policy. Verify a
hand-calculated school/transit example under FIFO and scored policies.
Regenerate weights and all published metrics after this change.

### 2. Future reports can change the training objective

`_merge_or_create()` changes damage and repeat-call facts.
`simulate()` replays the full history, then multiplies every historical
dark day by the light's final risk weight. Applying `window=` only clips
days; it does not clip the facts used to value those days.

A June light receiving a July damage report before its next Monday plan
can therefore receive a damage surcharge on June days. This defeats the
intended chronological holdout for the tuning objective.

Correction: accumulate risk using facts known on each day, or integrate
over dated fact-change intervals. Training must stop at the training
boundary. Add a test that appending post-training reports cannot change
the training objective for fixed weights.

### 3. Reporting periods are inconsistent

`engine/simulate.py:273` calculates median wait over all fixed lights;
`:279` filters fix counts to the requested window; `:282` includes crew
hours only when the week's Monday lies within that window; `:296` reports
the backlog after the full replay.

For the July 1 boundary, fixes on July 1–3 from the June 29 route can be
counted without that route's crew hours. At the other boundary, a Monday
within the window contributes its entire route time even if some repairs
occur after the window. The replay processes the final week's repairs
through Friday but calls that Monday its run end.

Correction: define one observation cutoff and explicit interval semantics,
record daily work, and align counts, hours, wait statistics, and backlog.
Do not infer midnight interval semantics from inclusive date labels.

### 4. The live product remains scaffolded

All business routes in `api/main.py`, service operations, database CRUD,
geocoding, demo seeding, and `scripts/fake_call.py` raise
`NotImplementedError`. The dashboard now supports the historical preview
and a defensive live client described above. Voice tools are empty; setup/transcript and submission documents
are placeholders. `/health` returning `ok` establishes process liveness,
not operational readiness.

Correction: finish a thin path first: report, persist, rank, read queue,
show queue and event. Add merging, status, hazards, and reset with tests
against a temporary database. Connect voice after the HTTP flow works.

### 5. Implemented schemas disagree with the agreed contracts

`api/schemas.py:36` omits queue fix dates, community, and call count.
`:45` models historical metrics instead of the agreed plan fields
`lights_planned`, `minutes_used`, `skipped_count`, and `note`.
Status requires rank and date even though fixed/hazard or beyond-horizon
items may have neither. Clarification responses need an explicit decision
about whether a ticket ID exists before a ticket is created.
`api/db.py` also retains derived school/transit columns, contrary to the
documented schema decision.

Correction: settle and test these contracts before separate frontend,
backend, and voice implementations grow around different shapes.
Existing databases require a migration or an intentional demo rebuild;
editing `CREATE TABLE IF NOT EXISTS` alone will not alter their tables.

## Important modeling and reliability work

### Scheduling and dates

`_assign_workdays()` splits repairs by count, not consumed minutes.
It does not enforce one fifth of capacity per day or account for daily
depot trips. The weekly tour can fit while a particular day does not.
Keep a simplified model only if the documentation calls it an approximation;
otherwise use a daily planner and share it with projections.

`project_fix_dates()` ignores the caller's `as_of` and always begins one
week after `DEMO_DATE`. Thus generalized live calls can return dates before
their scoring date. Also, `what_if()` selects this week's route while its
dates start next week. Specify which week is being planned, pass the clock
explicitly, and share eligibility rules for existing backlog and new calls.

Rank expresses dispatch priority; nearest-neighbour routing determines
visit order. Rank 1 does not guarantee the first repair. The current FIFO
live test expects the first route item to be the oldest, which contradicts
the planner's return contract. Check FIFO ranks separately from route order.

### Evaluation assumptions

The 150 m merge heuristic can combine different physical lights. Because
only unfixed records merge, policies also create different work units from
the same report stream. Faster repair can turn a later repeat into a new
job. This makes repair-count comparisons policy-dependent. Prefer asset
IDs when available; meanwhile disclose the approximation and show merge
radius sensitivity. Define the risk objective as a modeled proxy, without
claiming measured public-safety improvement.

The chosen budget was inspected using full-history outcomes. Document it
as an exploratory assumption and avoid describing the full experiment as
completely untouched holdout validation. Compare tuned against v1 as well
as FIFO, keep v1 as a candidate, and later assess multiple chronological
windows before enabling automated retuning.

### Reproducibility

At review time, `engine/live.py`, its tests, and the school/transit CSVs
are untracked. A fresh clone cannot reproduce the current working tree.
The saved tuning log has three trials, while configuration and docs claim
200. `requirements.txt` contains lower bounds without a lock or fixed
Python runtime, so installations can resolve differently.

Correction: include intended assets in the reviewed change, regenerate
results after correctness fixes, and save a manifest with input hashes,
code version, layers, windows, seed, budgets, and objective definition.
Pin the demo environment. Generate artifacts in staging and replace the
result set together so a failed run cannot leave mixed generations.

### External calls and data degradation

`dispatcher_note()` performs a synchronous external call when a key is
present, with no explicit application timeout/retry budget or caching.
Exception fallback handles failure after the call finishes; it does not
ensure a responsive dashboard. Bound latency and cache by plan facts;
use the template immediately for the demonstration if needed.

Missing layers silently become false proximity flags. That is convenient
for a demo but changes the model without making the degradation visible.
Validate required columns, finite coordinates, unique IDs, timestamps,
weight keys/values, and positive finite budgets at boundaries. Display
layer availability and reject incomplete evaluation inputs. Downloads
should validate and write atomically before replacing known-good files.

### API safety and consistency before connecting ngrok

The voice secret fails closed, which is good. However, planned fixed/reset
routes currently have no authentication dependencies. The tunnel exposes
the whole API, so protect mutations without adding a full login product.
Use a single transaction for merge/create, call insertion, reranking,
and events; serialize competing writers where needed. Webhook retries
need idempotency to avoid inflating call counts. Load and validate secrets
explicitly: installing python-dotenv does not load `.env` automatically.
Use a monotonic event ID cursor rather than timestamp-only polling to
avoid skipping events sharing a timestamp.

## Verification priorities

The suite mainly establishes plausible outputs and imports. Missing tests
cover evaluator arithmetic, temporal isolation, workday feasibility,
reporting boundaries, projection clocks, and API transactions. The test
named `test_fifo_simulate_conserves_lights` only compares two fix counts;
it does not verify conservation of created, merged, fixed, and open work.

Ruff lint passed during review. Format checking failed: 12 files would be
reformatted. There is no checked-in CI workflow. Add a minimal test/lint
gate and an HTTP smoke test; broader tooling can wait.

The first-pass pytest run did not reach test output during that review.
A separate 15-second import diagnostic stalled in NumPy dependency-file
loading (`importlib.get_data`) while importing pandas. Runtime probes also
did not finish. The second-pass environment and executable checks supersede
that limitation; their observations are recorded above. Both environments
use Python 3.13, whereas the documented target is Python 3.11. Saved
evaluation artifacts were not regenerated because the objective still
needs correction.

## Recommended order

1. Correct the risk evaluator and chronological boundaries, with tiny
   independently calculated regression examples.
2. Align API/schema/engine contracts and the meaning of dates and ranks.
3. Finish one report-to-dashboard flow with temporary-database tests.
4. Add merge, hazard, status, reset, retry handling, and tunnel protection.
5. Regenerate traceable results and finish setup, voice, and demo docs.
6. Rehearse from a fresh checkout with external services unavailable.

Defer cloud infrastructure, microservices, an ORM migration, and a more
complex optimizer until correctness and the complete user flow are proven.
