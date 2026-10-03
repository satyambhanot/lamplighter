"""One-time filter: the full City of Calgary 311 export (data/raw/,
gitignored, 1M+ rows of every service type) down to the street-light
seed CSV the rest of the project reads (data/street_lights_311.csv).

Run with: python -m scripts.prepare_seed_data
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime

from config import RAW_311_CSV, STREETLIGHT_SERVICE_NAMES, TEST_END, TICKETS_CSV, TUNE_START

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "service_request_id",
    "requested_date",
    "updated_date",
    "closed_date",
    "status_description",
    "service_name",
    "comm_name",
    "address",
    "longitude",
    "latitude",
]

RAW_DATE_FORMAT = "%m/%d/%Y %I:%M:%S %p"


def main() -> None:
    """Filter RAW_311_CSV to street-light tickets within [TUNE_START,
    TEST_END] and write TICKETS_CSV with OUTPUT_COLUMNS only.
    """
    window_start = datetime.fromisoformat(TUNE_START)
    window_end = datetime.fromisoformat(TEST_END).replace(hour=23, minute=59, second=59)

    rows_in = 0
    rows_out = 0
    with (
        open(RAW_311_CSV, newline="", encoding="utf-8") as raw_file,
        open(TICKETS_CSV, "w", newline="", encoding="utf-8") as out_file,
    ):
        reader = csv.DictReader(raw_file)
        writer = csv.DictWriter(out_file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        for row in reader:
            rows_in += 1
            if row["service_name"] not in STREETLIGHT_SERVICE_NAMES:
                continue
            requested = datetime.strptime(row["requested_date"], RAW_DATE_FORMAT)
            if not (window_start <= requested <= window_end):
                continue
            writer.writerow({col: row[col] for col in OUTPUT_COLUMNS})
            rows_out += 1

    logger.info("Scanned %d raw rows, wrote %d street-light tickets to %s", rows_in, rows_out, TICKETS_CSV)


if __name__ == "__main__":
    main()
