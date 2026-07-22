# odyssey-watch

Watches Cinemark Seven Bridges (Woodridge, IL) for 2 adjacent available seats
to *The Odyssey* in IMAX 70mm, and emails when a pair opens.

## What it looks for

- Format: `Imax 70mm`, Auditorium 17
- Rows F–K (the back half — the screen renders above row A), any column
- Exactly 2 adjacent seats, judged by physical grid column so aisles never
  count as adjacent
- Showtimes starting 11:00–19:00 Central, any day, today through +21 days
- Wheelchair and companion spaces are excluded

## How it works

Two-tier polling every 10 minutes:

1. One listing request per date (22 total) finds which IMAX 70mm showtimes
   exist and which are bookable. Sold-out and past showtimes cost nothing more.
2. Seat maps are fetched only for bookable showtimes inside the hours —
   typically 3–10 requests.

`state.json` holds the previous scan's pairs. An email fires for pairs present
now but absent then, so a seat that is bought and later re-released alerts
again. The first run seeds state without emailing.

Schedules vary by day and are read per-date; newly released weeks appear on
their own with no code change.

## Configuration

Everything tunable lives in `src/config.py` — rows, columns, hours, window
length, cadence. Change `GOOD_ROWS` or `MIN_COL`/`MAX_COL` to widen or narrow
the zone.

## Tests

    pip install -r requirements.txt pytest
    python -m pytest

Parser tests run against real HTML captured 2026-07-21 in `tests/fixtures/`.
Both seat map fixtures legitimately contain zero qualifying pairs — the film is
sold out — so positive matching is tested against synthetic seat data.

## Known limitations

- GitHub Actions cron is best-effort and can lag 10–30 minutes or skip runs.
- Cinemark could change their markup. Parsers raise rather than silently
  reporting "no seats", so a failed run is visible in the Actions tab.
- The scanner never buys, holds, or reserves anything.
