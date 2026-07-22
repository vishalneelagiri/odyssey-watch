"""Orchestrates one scan."""
import os
from datetime import date, datetime, timedelta

import requests

from src import config, fetch, match, notify, parse, state
from src.models import Alert, SeatPair, Showtime


def run(
    password: str,
    *,
    state_path: str = config.STATE_PATH,
    today: date | None = None,
) -> int:
    """Run one scan. Returns the number of newly-opened pairs found."""
    if today is None:
        today = datetime.now(config.TZ).date()

    # Tier 1: one cheap listing request per date. Schedules vary per day, so
    # every date is read independently rather than assuming a repeating pattern.
    # Each date is isolated: a single Cloudflare interstitial or an empty page
    # for one date must not abort dates already parsed successfully.
    showtimes = []
    listing_failed = False
    for offset in range(config.WINDOW_DAYS + 1):
        day = today + timedelta(days=offset)
        try:
            html = fetch.get(config.LISTING_URL, {"showDate": day.isoformat()})
            showtimes.extend(parse.parse_showtimes(html))
        except (OSError, requests.RequestException, ValueError, KeyError) as exc:
            listing_failed = True
            print(f"WARNING: listing fetch/parse failed for {day.isoformat()}: {exc}")

    if not showtimes:
        raise RuntimeError(
            "no IMAX 70mm showtimes parsed across the entire window — "
            "either the markup has changed or every listing request failed"
        )

    # Tier 2: seat maps only for bookable showtimes inside the hours.
    # Dedupe across dates: the same showtime can legitimately be listed on more
    # than one date's listing page, so without this a scan would fetch and
    # process its seat map twice, wasting a request.
    showtime_by_key: dict[str, Showtime] = {}
    for showtime in showtimes:
        if match.showtime_in_window(showtime, today):
            showtime_by_key[str(showtime.showtime_id)] = showtime
    wanted = list(showtime_by_key.values())
    print(f"{len(showtimes)} showtimes listed, {len(wanted)} worth checking")

    previous = state.load_state(state_path)
    first_run = previous is None

    current: dict[str, list[str]] = {}
    pairs_by_showtime: dict[str, tuple[SeatPair, ...]] = {}
    seatmap_successes = 0

    for showtime in wanted:
        key = str(showtime.showtime_id)
        try:
            seats = parse.parse_seats(fetch.get(showtime.seatmap_url))
        except (OSError, requests.RequestException, ValueError, KeyError) as exc:
            print(
                f"WARNING: seat map fetch/parse failed for showtime {key} "
                f"({showtime.display_time}): {exc}"
            )
            # Carry the previous scan's result forward rather than omitting
            # this showtime: omitting it would drop it from saved state, and
            # the next successful scan would see every one of its pairs as
            # brand new and re-alert spuriously.
            if previous is not None and key in previous:
                current[key] = previous[key]
            continue
        pairs = match.find_pairs(seats)
        current[key] = [pair.key for pair in pairs]
        pairs_by_showtime[key] = tuple(pairs)
        seatmap_successes += 1

    if wanted and seatmap_successes == 0:
        raise RuntimeError(
            f"all {len(wanted)} seat map(s) failed to fetch/parse — "
            "either the markup has changed or every seat-map request failed"
        )

    # A failed tier-1 listing date means any showtime only ever listed on that
    # date is entirely absent from `current`, not merely carried forward with
    # a stale value. Without this, save_state would prune it as if it had
    # genuinely passed, and the next successful scan would see all of its
    # pairs as brand new and re-alert spuriously.
    if listing_failed and previous:
        for key, value in previous.items():
            if key not in current:
                current[key] = value

    if first_run:
        state.save_state(state_path, current)
        print("first run — state seeded, no email sent")
        return 0

    fresh = state.new_pairs(previous or {}, current)

    if not fresh:
        state.save_state(state_path, current)
        print("no newly-opened pairs")
        return 0

    alerts = []
    for key, new_keys in fresh.items():
        new_key_set = set(new_keys)
        pairs = tuple(p for p in pairs_by_showtime[key] if p.key in new_key_set)
        alerts.append(Alert(showtime=showtime_by_key[key], pairs=pairs))
    alerts.sort(key=lambda a: a.showtime.starts_at)

    subject, body = notify.format_email(alerts)
    # State must only advance once the send has actually succeeded: if
    # send_email raises, current must not be saved, so the next scan sees the
    # same newly-opened pairs as still-new and retries the alert rather than
    # silently losing it.
    notify.send_email(subject, body, password)
    state.save_state(state_path, current)
    total = sum(len(a.pairs) for a in alerts)
    print(f"emailed {total} newly-opened pairs across {len(alerts)} showtimes")
    return total


if __name__ == "__main__":
    run(os.environ.get("GMAIL_APP_PASSWORD", ""))
