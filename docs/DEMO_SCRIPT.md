# Lamplighter demo script

A 6-minute live demo for the judges, plus a 3-minute short version, setup, fallbacks and Q&A answers. Every number and on-screen message below came from a rehearsal run against a freshly reset demo database on October 3. If yours differ, run `make reset` and check the setup list again.

Judging weights to keep in mind: 30% autonomous reasoning, 20% real problem, 20% working software and architecture, 15% commercialization, 15% pitch.

## Roles

| Role | Does |
|---|---|
| **Presenter** | Talks the whole time; owns the slides and the story |
| **Driver** | Clicks the dashboard on the projector |
| **Caller** | Makes the ElevenLabs browser calls, on a second laptop or the same one with a headset |
| **Backup** | Watches the terminals; runs the fallback commands if anything fails |

## Setup (15 minutes before)

Run each in its own terminal on the demo laptop:

```bash
git pull origin main
```

```bash
make api
```

```bash
make tunnel
```

```bash
make dash
```

Then reset to a clean demo state (needs `make api` running):

```bash
make reset
```

Checklist before you go on:

- [ ] `https://<NGROK_DOMAIN>/health` shows `{"status":"ok"}` in a browser.
- [ ] Dashboard sidebar: Workspace **Dispatch**, Data source **Live dispatch**, Dispatch policy **Tuned priority**, Crew capacity **100%**.
- [ ] The status line says "Live dispatch" with a recent "Last successful update" time.
- [ ] **Recent activity** (bottom of the page) is expanded and shows only "Historical demo queue loaded".
- [ ] In the "This week's work" search box, type `Resident report`. The table should be empty.
- [ ] ElevenLabs is open at Agents, "Lamplighter street light line", with the microphone allowed.
- [ ] Slides open on the title slide; the backup video is ready to play.
- [ ] Laptop on power, notifications off, browser zoom set so the map and the activity panel both fit.

Only run `make voice` if `voice/system_prompt.md` or `voice/tools.json` changed. The tunnel uses the fixed domain, so the agent never needs re-pointing.

## The 6-minute demo

### 0:00 to 0:40, the problem (slides)

> "When a Calgary street light fails, residents call 311. Crews can't fix every pole the same week, so the city fixes the oldest ticket first. That means a dark stretch by a school can wait behind one lamp on a quiet street. Lamplighter decides which lights the crew fixes each week, and proves it beats oldest-first on real Calgary data."

Mention the data honestly: 774 real 311 street-light tickets from March 23 to August 27, 2026. Most tickets close the same day they open, so "closed" can't mean fixed, and we replay the history week by week instead.

### 0:40 to 1:40, the result (Evaluation workspace)

**Driver:** sidebar, Workspace **Evaluation**.

> "We score a dark night by its risk: more for a damage report, a school nearby, a transit stop, or repeat calls. Oldest-first costs 4,018.5 risk-weighted dark nights over July and August. Our hand-set version 1 gets that to 3,357.2. Then the agent tuned its own weights: 200 random trials on March to June, then tested on July and August, which it never saw. Tuned: 3,006.0. That's 25.2% fewer risk-weighted dark nights than oldest-first, with the same crew."

If asked: median days dark fell from 18 to 16.5. It reproduces exactly with `make results` (seed 42).

**Driver:** Workspace back to **Dispatch**. Check Data source is still **Live dispatch**.

### 1:40 to 3:40, a resident calls (the autonomy moment)

> "Now a resident calls. No app, no login: just a phone call to an AI agent."

**Caller, call 1:** start the ElevenLabs test call.

| Agent says | Caller says |
|---|---|
| "Are you reporting a light that's out, or checking on one…?" | "I'm reporting a street light that's out." |
| asks for the location | "It's near King George School." |
| reads it back, asks about a downed pole or wires | "Yes, that's right. The pole is standing, no wires." |
| "…number ten in the repair queue… the week of September first." | "Thank you, bye." |

**Driver:** point at **Recent activity**: "New report entered at priority #10." In "This week's work", search `Resident report` to show the new light, with its reasons ("near a school, near transit"). Click it to show it on the map.

> "That call geocoded the address, checked for hazards, scored the light with the tuned weights and re-ranked the whole queue, all in a third of a second."

**Caller, call 2:** a second neighbour calls about the same light.

| Caller says |
|---|
| "There's a street light out outside King George School." |
| Confirm the location; the pole is standing. |

The agent says the call was added to the existing report and the light moved up. **Driver:** point at Recent activity: **"Call merged; light moved from #10 to #5."**

> "Two calls about the same pole are one light, not two tickets. Repeat calls raise its priority, and the plan updates live. That's the system reasoning, not a script."

### 3:40 to 4:30, the crew gets cut

**Driver:** Crew capacity slider from **100%** to **80%**.

> "Budget cut: the crew loses a fifth of its hours. Lamplighter re-plans instantly."

Point at the top row: **planned visits 21 → 15**, **crew-hours 14.0 → 11.0**, **waiting backlog 14 → 20**. Open **Capacity impact · 80% compared with 100%** to show exactly which lights drop and which communities lose a visit. Read the dispatcher note out loud; it now ends "Crew capacity is set to 80% of the standard week."

**Driver:** slider back to **100%**.

### 4:30 to 4:50, safety (say it; call only if time allows)

> "If a caller says the pole is down or wires are exposed, the agent tells them to stay away and call 911 if anyone is in danger, and the light never enters the routine queue. The API checks the words too, so safety doesn't depend on one layer. Real emergencies, like a crash with someone hurt, get 'hang up and call 911' immediately, and nothing is filed."

Optional live hazard call: "The pole outside City Hall is down and there are exposed wires." Recent activity shows "Report flagged for urgent dispatcher review." and nothing is added to the queue.

### 4:50 to 6:00, architecture and business (slides)

- **Architecture** (`docs/architecture.png`): one Python engine shared by the offline replay, the live API and the dashboard, so the demo and the results slide can never disagree. Only the API writes data; ElevenLabs owns all audio.
- **Commercialization:** the customer is the City's street lighting dispatch; the value is fewer dark nights per crew-hour. The same engine fits other limited-crew queues such as potholes and traffic signals.
- **Production:** a nightly job pulls the 311 open data feed, the offline layer runs on Databricks over the full multi-year history, weights are re-tuned weekly, and the API runs in the City's cloud behind a real phone number with single sign-on.

> "Fewer dark nights per crew-hour. Thank you."

## 3-minute version

Problem (0:30), result in Evaluation (0:40), call 1 and call 2 with the #10 → #5 merge (1:20), 80% crew cut (0:20), one-line close (0:10). Skip the hazard call and the architecture slide.

## If something breaks

| Problem | What the Backup does | What the Presenter says |
|---|---|---|
| ElevenLabs or the tunnel fails | Run the two commands below on the demo laptop; they hit the same `/report` endpoint the agent uses | "Same request the agent sends; here it is directly." |
| Venue Wi-Fi drops | Same commands (they use `localhost`); the map tiles may go blank, the tables still work | Point at the tables and Recent activity |
| The agent mishears the location | Caller says "King George School" again; if it still fails, use the fallback commands | "It asks for an intersection rather than guessing." |
| Dashboard shows "Connection lost" | Check the `make api` terminal; restart it | Keep talking about the result slide |
| Everything fails | Play the backup video | |

Fallback commands for call 1 and call 2 (run from the repo folder):

```bash
set -a; . ./.env; set +a; curl -s -X POST localhost:8000/report -H "X-Lamplighter-Voice-Secret: $VOICE_SHARED_SECRET" -H 'content-type: application/json' -d '{"phone":"+14035550100","location_text":"King George School","description":"The street light is out."}'
```

```bash
set -a; . ./.env; set +a; curl -s -X POST localhost:8000/report -H "X-Lamplighter-Voice-Secret: $VOICE_SHARED_SECRET" -H 'content-type: application/json' -d '{"phone":"+14035550100","location_text":"near King George School","description":"Still dark outside the school."}'
```

The first returns `"rank":10`, the second `"merged":true,"rank":5,"old_rank":10`.

## Between rehearsals

```bash
make reset
```

This clears every voice-filed light, merge, confirmed plan and simulated repair, and reloads the 34-light demo queue. Re-run the setup checklist afterwards. `make reset` needs `make api` running.

## Q&A answers

| Question | Answer |
|---|---|
| What does "closed" mean in the data? | Most tickets close the day they open, so we read it as handed to maintenance, not fixed, and never use it as a repair date. We assume a light stays dark from its first report until our simulated crew fixes it. |
| Isn't the result circular? | The risk score (the city's cost of a dark night) is fixed and never tuned. Only the policy weights are tuned, on March to June, and reported only on unseen July and August. It also holds at 70%, 85% and 100% crew budget. |
| Why random search, not machine learning? | There are no real repair outcomes to learn from. Random search over 6 weights with a fixed seed is simple, explainable and reproducible. |
| Where do 30 minutes and 30 km/h come from? | Stated assumptions in `config.py`, to validate with City crews. The depot is the average ticket location because the real yard isn't public. |
| How much crew time? | 840 minutes a week (14 crew-hours), validated by routing so a real backlog remains. If crews could fix everything, order wouldn't matter. |
| What about privacy? | Phone numbers are stored only as salted hashes and never shown. In this demo the agent never asks for one. |
| What if someone calls about Edmonton? | The agent says the line only covers Calgary and points them to that city's 311. The geocoder also rejects anything outside Calgary. |
| Can I check my report's status? | Yes: "check on my report" calls `/status`. In the demo every call shares one demo number, so it returns the latest report. |
| Is this live City data? | Real City of Calgary 311 reports, with simulated repairs and a planning clock frozen at Monday, August 24, 2026. |
| How would it scale? | Nightly 311 pull, Databricks for the multi-year history, weekly re-tuning, the API in the City's cloud behind a real number and single sign-on. |

## Not in the demo

The dispatcher plan workflow (Review this plan, Confirm plan, Mark repaired) works but takes too long on stage. Show it only if a judge asks: Review this plan, tick "I reviewed the visit order and capacity impact", Confirm plan; then select a confirmed light, tick "Crew has completed this repair", Mark repaired. A new report after confirming sends the plan back for review.
