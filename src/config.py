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

# Rate limiting. Cinemark (Cloudflare) returns 429 after ~11 requests in a
# burst. 429 means "slow down and retry", unlike other 4xx which are fatal.
RATE_LIMIT_COOLDOWN_S = 20.0   # fallback wait on 429 when no Retry-After header
MAX_429_RETRIES = 5            # attempts specifically for 429, separate from MAX_RETRIES

# Tiered scanning. Every scan checks seat maps for showtimes within this many
# days (last-minute cancellations cluster here). Seat maps for dates beyond it
# are checked less often, driven by which cron schedule fired — see watch.yml.
NEAR_WINDOW_DAYS = 7

STATE_PATH = "state.json"

# Email
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
EMAIL_FROM = "you@example.com"
EMAIL_TO = "you@example.com"
