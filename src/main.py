"""Orchestrates one scan."""
import os
from datetime import date, datetime, timedelta

from src import config, fetch, match, notify, parse, state
from src.models import Alert, Showtime


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
    showtimes = []
    for offset in range(config.WINDOW_DAYS + 1):
        day = today + timedelta(days=offset)
        html = fetch.get(config.LISTING_URL, {"showDate": day.isoformat()})
        showtimes.extend(parse.parse_showtimes(html))

    if not showtimes:
        raise RuntimeError(
            "no IMAX 70mm showtimes parsed across the entire window — "
            "markup has probably changed"
        )

    # Tier 2: seat maps only for bookable showtimes inside the hours.
    # Dedupe across dates: late-night showings are listed on the previous day's
    # page as well as their own (a 1:00am show on the 22nd appears on the 21st),
    # so the same showtime_id can arrive from two different listing fetches.
    wanted_by_id: dict[int, Showtime] = {}
    for showtime in showtimes:
        if match.showtime_in_window(showtime, today):
            wanted_by_id[showtime.showtime_id] = showtime
    wanted = list(wanted_by_id.values())
    print(f"{len(showtimes)} showtimes listed, {len(wanted)} worth checking")

    current: dict[str, list[str]] = {}
    pairs_by_showtime: dict[str, tuple] = {}
    showtime_by_id = {}

    for showtime in wanted:
        seats = parse.parse_seats(fetch.get(showtime.seatmap_url))
        pairs = match.find_pairs(seats)
        key = str(showtime.showtime_id)
        current[key] = [pair.key for pair in pairs]
        pairs_by_showtime[key] = tuple(pairs)
        showtime_by_id[key] = showtime

    previous = state.load_state(state_path)
    first_run = previous is None

    fresh = state.new_pairs(previous or {}, current)
    state.save_state(state_path, current)

    if first_run:
        print("first run — state seeded, no email sent")
        return 0

    if not fresh:
        print("no newly-opened pairs")
        return 0

    alerts = []
    for key, new_keys in fresh.items():
        pairs = tuple(p for p in pairs_by_showtime[key] if p.key in set(new_keys))
        alerts.append(Alert(showtime=showtime_by_id[key], pairs=pairs))
    alerts.sort(key=lambda a: a.showtime.starts_at)

    subject, body = notify.format_email(alerts)
    notify.send_email(subject, body, password)
    total = sum(len(a.pairs) for a in alerts)
    print(f"emailed {total} newly-opened pairs across {len(alerts)} showtimes")
    return total


if __name__ == "__main__":
    run(os.environ.get("GMAIL_APP_PASSWORD", ""))
