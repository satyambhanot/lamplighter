# data/

Committed, derived data — small enough to check in, and committing it
means a fresh clone gets identical numbers without re-fetching anything.

- `street_lights_311.csv`: 774 Calgary 311 street-light tickets, Mar 23
  to Aug 27, 2026. Filtered from the full City of Calgary 311 export
  (`raw/`, gitignored, 1M+ rows of every service type) by
  `scripts/prepare_seed_data.py`.
- `schools.csv`: 506 Calgary school locations.
- `transit_stops.csv`: 6,213 active Calgary Transit stops.

Both layers are downloaded from data.calgary.ca's Socrata API by
`python -m scripts.fetch_open_data` (dataset ids verified against the
live API, not guessed — see `config.SCHOOLS_DATASET_URL` /
`TRANSIT_STOPS_DATASET_URL`). Re-run that script to refresh them; the
city's open-data feed updates continuously, so counts may drift slightly
from a fresh pull.

Licence: Open Government Licence — City of Calgary.

`raw/` is gitignored (the 270MB full 311 export doesn't belong in git)
and only needed to regenerate `street_lights_311.csv` via
`python -m scripts.prepare_seed_data`.
