"""All tunable constants. No logic lives here."""
from datetime import time
from zoneinfo import ZoneInfo

# Target venue — verified live 2026-07-21
THEATER_ID = 276
LISTING_URL = "https://www.cinemark.com/theatres/il-woodridge/cinemark-seven-bridges-and-imax"
SITE_ROOT = "https://www.cinemark.com"
FORMAT_LABEL = "Imax 70mm"

# Showtimes are Central; CI runners are UTC. Never use naive datetimes.
TZ = ZoneInfo("America/Chicago")

# How far ahead to look. Inclusive of today, so this scans WINDOW_DAYS + 1 dates.
WINDOW_DAYS = 21

# Acceptable showtime start, inclusive on both ends.
EARLIEST_START = time(11, 0)
LATEST_START = time(19, 0)

# Auditorium 17 is a 27-column grid. Row letters skip "I"; "E" appears twice
# (one is an all-blank walkway spacer). Screen is above row A, so F-K is the back.
GOOD_ROWS = frozenset({"F", "G", "H", "J", "K"})

# Full grid width: no column restriction. The back rows are almost always sold
# out, so narrowing the zone would alert on nothing. Tighten here if alerts
# ever become plentiful.
MIN_COL = 0
MAX_COL = 26

# Seat types that are actual bookable seats. Excludes wheelchair and companion.
BOOKABLE_SEAT_TYPE = "seat"

# HTTP politeness
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
REQUEST_DELAY_S = 1.0
REQUEST_TIMEOUT_S = 30
MAX_RETRIES = 3

STATE_PATH = "state.json"

# Email
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
EMAIL_FROM = "you@example.com"
EMAIL_TO = "you@example.com"
