# Odyssey IMAX 70mm Seat Watcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poll Cinemark Seven Bridges every 10 minutes for 2 adjacent available seats in the back rows of Auditorium 17 for *The Odyssey* in IMAX 70mm, and email when a qualifying pair opens.

**Architecture:** Two-tier polling. Tier 1 fetches one listing page per date across a 21-day window to discover which IMAX 70mm showtimes exist and which are bookable. Tier 2 fetches seat maps only for bookable showtimes that pass the time filter. Parsing and matching are pure functions tested against real captured HTML; state is a committed `state.json` diffed against the previous scan so cancellations re-alert.

**Tech Stack:** Python 3.11, `requests`, `beautifulsoup4`, `pytest`, GitHub Actions, Gmail SMTP.

**Spec:** `docs/superpowers/specs/2026-07-21-odyssey-70mm-seat-watcher-design.md`

## Global Constraints

- Python 3.11+ (`zoneinfo` from stdlib, PEP 604 `X | None` unions).
- All datetimes tz-aware in `America/Chicago`. Never use naive `datetime.now()` — runners are UTC.
- **BeautifulSoup lowercases attribute names.** Read `seattype`, not `seatType`; `showtimeid`, not `showtimeId`. Reading camelCase returns `None` and silently yields zero seats.
- Never hardcode `CinemarkMovieId`. Filter on the format label `Imax 70mm`.
- Never hardcode showtime clock times or counts. Schedules vary per day and are read per-date.
- Every HTTP request sends the browser `User-Agent` from `config.USER_AGENT` and sleeps `config.REQUEST_DELAY_S` between requests.
- Parser failures must be loud. Zero showtimes across *all* dates raises; it must never be reported as "no seats found".
- No purchasing, holding, or checkout. Observe and notify only.
- Secrets never in code. `GMAIL_APP_PASSWORD` comes from the environment.

**Verified constants** (confirmed live 2026-07-21, do not re-derive):

| | |
|---|---|
| `TheaterId` | `276` |
| Listing URL | `https://www.cinemark.com/theatres/il-woodridge/cinemark-seven-bridges-and-imax?showDate=YYYY-MM-DD` |
| Seat map URL | `https://www.cinemark.com/TicketSeatMap/?TheaterId=276&ShowtimeId=<id>&CinemarkMovieId=<id>&Showtime=<iso>` |
| Format label | `Imax 70mm` |
| Grid | 27 columns, rows `A B C D E E F G H J K` (letter `I` skipped, `E` appears twice) |
| Screen | rendered above row A; A is front, K is back |

---

## File Structure

| File | Responsibility |
|---|---|
| `src/config.py` | All tunable constants. No logic. |
| `src/models.py` | `Seat`, `Showtime`, `SeatPair`, `Alert` dataclasses. No logic. |
| `src/parse.py` | HTML → dataclasses. Pure. |
| `src/match.py` | Seats → qualifying pairs; showtime window filter. Pure. |
| `src/state.py` | Load / save / diff `state.json`. |
| `src/notify.py` | Compose and send email. |
| `src/fetch.py` | HTTP with UA, retries, delay. The only network code. |
| `src/main.py` | Orchestration. |
| `tests/test_parse.py` | Parser tests against real fixtures. |
| `tests/test_match.py` | Matcher tests against synthetic data. |
| `tests/test_state.py` | State diff tests. |
| `tests/test_notify.py` | Email formatting + send with mocked SMTP. |
| `.github/workflows/connectivity-check.yml` | Task 1 risk retirement. Manual trigger. |
| `.github/workflows/watch.yml` | Production scheduled scan. |

Fixtures already committed in `tests/fixtures/`:

| Fixture | Contents |
|---|---|
| `seatmap_604612_nearly_sold_out.html` | 241 cells, 227 regular seats, 0 available regular, 4 available `wheelchair` |
| `seatmap_601707_has_availability.html` | 19 available regular seats, all rows A/B; rows F–K empty |
| `listing_today_with_soldout.html` | 6 IMAX 70mm: 1 bookable, 1 `soldOut`, 4 `past` |
| `listing_2026-08-05.html` | 5 bookable IMAX 70mm: 7:45am, 11:30am, 3:15pm, 7:00pm, 10:45pm |

---

### Task 1: Scaffolding and Cloudflare risk retirement

**This task must complete before any other.** All successful requests during discovery came from a residential IP. GitHub Actions runs on Azure ranges, and the site sits behind Cloudflare. If a runner is blocked, the hosting decision changes and later work is wasted.

**Files:**
- Create: `requirements.txt`, `.gitignore`, `pytest.ini`, `src/__init__.py`, `tests/__init__.py`
- Create: `.github/workflows/connectivity-check.yml`

- [ ] **Step 1: Create `requirements.txt`**

```
requests==2.31.0
beautifulsoup4==4.12.2
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
```

- [ ] **Step 3: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
pythonpath = .
```

- [ ] **Step 4: Create empty package markers**

```bash
touch src/__init__.py tests/__init__.py
```

- [ ] **Step 5: Create `.github/workflows/connectivity-check.yml`**

```yaml
name: connectivity-check

on:
  workflow_dispatch:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - name: Fetch Cinemark listing from runner
        run: |
          UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
          code=$(curl -s -o /tmp/out.html -w "%{http_code}" -A "$UA" --max-time 30 \
            "https://www.cinemark.com/theatres/il-woodridge/cinemark-seven-bridges-and-imax?showDate=2026-08-05")
          echo "HTTP status: $code"
          echo "Bytes: $(wc -c < /tmp/out.html)"
          echo "IMAX 70mm blocks found: $(grep -c 'data-print-type-name="Imax 70mm"' /tmp/out.html || true)"
          head -c 400 /tmp/out.html
          test "$code" = "200"
```

- [ ] **Step 6: Commit and push**

```bash
git add requirements.txt .gitignore pytest.ini src/__init__.py tests/__init__.py .github/workflows/connectivity-check.yml
git commit -m "chore: scaffolding and runner connectivity check"
git push
```

- [ ] **Step 7: Run the workflow and read the result**

Run it from the GitHub Actions tab (`Run workflow`), or:

```bash
gh workflow run connectivity-check.yml
sleep 45 && gh run list --workflow=connectivity-check.yml --limit 1
gh run view --log | tail -30
```

**Expected on success:** `HTTP status: 200`, bytes > 300000, `IMAX 70mm blocks found:` a nonzero number.

**STOP AND DECIDE:**
- `200` with nonzero IMAX blocks → the architecture holds. Proceed to Task 2.
- `403`, `503`, or an HTML challenge page → GitHub Actions is blocked. **Stop and report to the user.** Fall back to launchd on the Mac (same `src/` code, different scheduler), accepting the gap while the machine sleeps. Do not continue building against GHA.
- `200` but zero IMAX blocks → markup changed since capture. Stop and re-inspect before writing parsers.

---

### Task 2: Config and models

**Files:**
- Create: `src/config.py`, `src/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `config` constants used by every later task. `Seat`, `Showtime`, `SeatPair`, `Alert` dataclasses. `SeatPair.key` is the string identity used by `state.py` for diffing.

- [ ] **Step 1: Write `src/config.py`**

```python
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
```

- [ ] **Step 2: Write `src/models.py`**

```python
"""Plain data carried between parsing, matching, and notification."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Seat:
    """One grid cell that is an actual seat button."""
    row: str          # row letter, e.g. "H"
    number: str       # printed seat number, e.g. "12"
    phys_row: int     # grid row index — the real row identity ("E" appears twice)
    phys_col: int     # grid column index 0..26; aisles consume indices
    seat_type: str    # "seat" | "wheelchair" | "companion"
    available: bool


@dataclass(frozen=True)
class Showtime:
    """A listed showtime. Only bookable ones carry an id and a seat map URL."""
    state: str                      # "bookable" | "sold_out" | "past"
    display_time: str               # as printed, e.g. "3:15pm"
    showtime_id: int | None = None
    movie_id: int | None = None
    starts_at: datetime | None = None   # tz-aware America/Chicago
    seatmap_url: str | None = None


@dataclass(frozen=True)
class SeatPair:
    """Two adjacent qualifying seats in the same physical row."""
    row: str
    phys_row: int
    seat_a: str
    seat_b: str

    @property
    def key(self) -> str:
        """Stable identity used for state diffing."""
        return f"{self.row}:{self.seat_a}-{self.seat_b}"


@dataclass(frozen=True)
class Alert:
    """A showtime plus the newly-opened pairs found for it."""
    showtime: Showtime
    pairs: tuple[SeatPair, ...]
```

- [ ] **Step 3: Write the test**

```python
from src.models import SeatPair


def test_seat_pair_key_is_stable_and_readable():
    pair = SeatPair(row="H", phys_row=6, seat_a="12", seat_b="11")
    assert pair.key == "H:12-11"


def test_seat_pairs_with_same_key_are_equal():
    a = SeatPair(row="H", phys_row=6, seat_a="12", seat_b="11")
    b = SeatPair(row="H", phys_row=6, seat_a="12", seat_b="11")
    assert a == b
    assert len({a, b}) == 1
```

- [ ] **Step 4: Run the test**

Run: `python -m pytest tests/test_models.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/config.py src/models.py tests/test_models.py
git commit -m "feat: add config constants and data models"
```

---

### Task 3: Seat map parser

**Files:**
- Create: `src/parse.py`
- Test: `tests/test_parse.py`

**Interfaces:**
- Consumes: `models.Seat`
- Produces: `parse_seats(html: str) -> list[Seat]`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

import pytest

from src.parse import parse_seats

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


@pytest.fixture
def sold_out_seats():
    return parse_seats(load("seatmap_604612_nearly_sold_out.html"))


@pytest.fixture
def available_seats():
    return parse_seats(load("seatmap_601707_has_availability.html"))


def test_parses_every_seat_button(sold_out_seats):
    # 241 grid cells are seat buttons; blanks are <input> and excluded.
    assert len(sold_out_seats) == 241


def test_reads_lowercased_seattype_attribute(sold_out_seats):
    # bs4 lowercases attrs. If this returns 0, the parser read "seatType".
    regular = [s for s in sold_out_seats if s.seat_type == "seat"]
    assert len(regular) == 227


def test_this_showtime_has_no_available_regular_seats(sold_out_seats):
    # The only 4 open cells are wheelchair spaces.
    assert [s for s in sold_out_seats if s.seat_type == "seat" and s.available] == []


def test_available_cells_are_all_wheelchair(sold_out_seats):
    open_cells = [s for s in sold_out_seats if s.available]
    assert len(open_cells) == 4
    assert {s.seat_type for s in open_cells} == {"wheelchair"}


def test_distinguishes_the_two_rows_lettered_e(sold_out_seats):
    # Row letter is not unique; phys_row is. The blank spacer row contributes
    # no seat buttons, so exactly one phys_row carries letter "E".
    e_rows = {s.phys_row for s in sold_out_seats if s.row == "E"}
    assert len(e_rows) == 1


def test_grid_is_27_columns_contiguous(sold_out_seats):
    assert min(s.phys_col for s in sold_out_seats) == 0
    assert max(s.phys_col for s in sold_out_seats) == 26


def test_parses_availability_in_second_fixture(available_seats):
    open_regular = [s for s in available_seats if s.seat_type == "seat" and s.available]
    assert len(open_regular) == 19
    # All availability is in the front rows.
    assert {s.row for s in open_regular} == {"A", "B"}


def test_raises_on_html_with_no_seats():
    with pytest.raises(ValueError, match="no seat buttons"):
        parse_seats("<html><body>nothing here</body></html>")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_parse.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.parse'`

- [ ] **Step 3: Write the implementation**

```python
"""HTML to dataclasses. Pure functions — no network, no I/O."""
from bs4 import BeautifulSoup

from src.models import Seat


def parse_seats(html: str) -> list[Seat]:
    """Extract every seat button from a TicketSeatMap page.

    Grid cells that are not seats render as <input class="seatBlank"> and are
    skipped — but they occupy column indices, which is what makes physical-column
    adjacency correctly refuse to pair seats across an aisle.

    Note bs4 lowercases attribute names: the markup says seatType, we read
    seattype. Reading the camelCase name returns None and yields zero seats.
    """
    soup = BeautifulSoup(html, "html.parser")
    buttons = soup.select("button.seatBlock")
    if not buttons:
        raise ValueError("no seat buttons found in seat map HTML")

    seats: list[Seat] = []
    for button in buttons:
        info = button.get("info", "")
        parts = info.split(",")
        if len(parts) < 4:
            continue
        row, number, phys_row, phys_col = parts[0], parts[1], parts[2], parts[3]
        seats.append(
            Seat(
                row=row,
                number=number,
                phys_row=int(phys_row),
                phys_col=int(phys_col),
                seat_type=button.get("seattype", ""),
                available=button.get("available") == "True",
            )
        )
    return seats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_parse.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/parse.py tests/test_parse.py
git commit -m "feat: parse seat maps into Seat records"
```

---

### Task 4: Listing parser

**Files:**
- Modify: `src/parse.py`
- Modify: `tests/test_parse.py`

**Interfaces:**
- Consumes: `models.Showtime`, `config.FORMAT_LABEL`, `config.TZ`, `config.SITE_ROOT`
- Produces: `parse_showtimes(html: str) -> list[Showtime]`

- [ ] **Step 1: Write the failing test (append to `tests/test_parse.py`)**

```python
from datetime import datetime

from src.parse import parse_showtimes


@pytest.fixture
def aug5():
    return parse_showtimes(load("listing_2026-08-05.html"))


@pytest.fixture
def today_listing():
    return parse_showtimes(load("listing_today_with_soldout.html"))


def test_only_imax_70mm_showtimes_are_returned(aug5):
    # The page carries 29 showtime divs across all formats; 5 are IMAX 70mm.
    assert len(aug5) == 5


def test_bookable_showtimes_carry_id_and_url(aug5):
    for showtime in aug5:
        assert showtime.state == "bookable"
        assert showtime.showtime_id is not None
        assert showtime.seatmap_url.startswith("https://www.cinemark.com/TicketSeatMap/")


def test_start_times_are_timezone_aware_central(aug5):
    at_3pm = next(s for s in aug5 if s.showtime_id == 601707)
    assert at_3pm.starts_at == datetime(2026, 8, 5, 15, 15, tzinfo=config.TZ)
    assert at_3pm.display_time == "3:15pm"


def test_recognises_sold_out_and_past_states(today_listing):
    states = sorted(s.state for s in today_listing)
    assert states == ["bookable", "past", "past", "past", "past", "sold_out"]


def test_non_bookable_showtimes_have_no_id(today_listing):
    for showtime in today_listing:
        if showtime.state != "bookable":
            assert showtime.showtime_id is None
            assert showtime.seatmap_url is None


def test_schedules_differ_between_dates(aug5, today_listing):
    # Pins the requirement that schedules are read per-date, never assumed
    # uniform. Aug 5 has 5 showtimes; the captured today-listing has 6.
    assert len(aug5) != len(today_listing)


def test_bookable_showtimes_are_deduplicated_by_id(aug5):
    ids = [s.showtime_id for s in aug5]
    assert len(ids) == len(set(ids))


def test_raises_when_no_showtime_blocks_at_all():
    with pytest.raises(ValueError, match="no showtime blocks"):
        parse_showtimes("<html><body>nothing</body></html>")
```

Add `from src import config` to the imports at the top of the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_parse.py -v -k showtime`
Expected: FAIL with `ImportError: cannot import name 'parse_showtimes'`

- [ ] **Step 3: Write the implementation (append to `src/parse.py`)**

```python
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse

from src import config
from src.models import Showtime


def parse_showtimes(html: str) -> list[Showtime]:
    """Extract IMAX 70mm showtimes and their booking state from a listing page.

    Three states are rendered differently:
      bookable  -> <a class="showtime-link" href="/TicketSeatMap/?...">
      sold out  -> <p class="off soldOut">
      past      -> <p class="off past">

    Only bookable showtimes carry a ShowtimeId and a full ISO start time. That
    is fine: the system never acts on sold-out or past showtimes, and the moment
    one becomes bookable it gains an id. They are returned only so callers can
    sanity-check that parsing worked.
    """
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.find_all("div", class_="showtime")
    if not blocks:
        raise ValueError("no showtime blocks found in listing HTML")

    showtimes: list[Showtime] = []
    seen_ids: set[int] = set()

    for block in blocks:
        if block.get("data-print-type-name") != config.FORMAT_LABEL:
            continue

        link = block.find("a", class_="showtime-link")
        if link is not None:
            query = parse_qs(urlparse(link["href"]).query)
            showtime_id = int(query["ShowtimeId"][0])
            if showtime_id in seen_ids:
                continue
            seen_ids.add(showtime_id)
            naive = datetime.fromisoformat(query["Showtime"][0])
            showtimes.append(
                Showtime(
                    state="bookable",
                    display_time=link.get_text(strip=True),
                    showtime_id=showtime_id,
                    movie_id=int(query["CinemarkMovieId"][0]),
                    starts_at=naive.replace(tzinfo=config.TZ),
                    seatmap_url=urljoin(config.SITE_ROOT, link["href"]),
                )
            )
            continue

        sold_out = block.find("p", class_="soldOut")
        if sold_out is not None:
            showtimes.append(
                Showtime(state="sold_out", display_time=sold_out.get_text(strip=True))
            )
            continue

        past = block.find("p", class_="past")
        if past is not None:
            showtimes.append(
                Showtime(state="past", display_time=past.get_text(strip=True))
            )

    return showtimes
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_parse.py -v`
Expected: 16 passed.

- [ ] **Step 5: Commit**

```bash
git add src/parse.py tests/test_parse.py
git commit -m "feat: parse listing pages into Showtime records"
```

---

### Task 5: Seat pair matcher

**Files:**
- Create: `src/match.py`
- Test: `tests/test_match.py`

**Interfaces:**
- Consumes: `models.Seat`, `models.SeatPair`, `config.GOOD_ROWS`, `config.MIN_COL`, `config.MAX_COL`, `config.BOOKABLE_SEAT_TYPE`
- Produces: `find_pairs(seats: list[Seat]) -> list[SeatPair]`

Tests use synthetic `Seat` lists rather than HTML. Both real fixtures legitimately contain zero qualifying pairs — this release is sold out — so positive cases must be constructed.

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from src.match import find_pairs
from src.models import Seat
from src.parse import parse_seats

FIXTURES = Path(__file__).parent / "fixtures"


def seat(row, number, phys_row, phys_col, *, available=True, seat_type="seat"):
    return Seat(
        row=row,
        number=number,
        phys_row=phys_row,
        phys_col=phys_col,
        seat_type=seat_type,
        available=available,
    )


def test_finds_adjacent_pair_in_back_row():
    seats = [seat("H", "12", 6, 12), seat("H", "11", 6, 13)]
    pairs = find_pairs(seats)
    assert len(pairs) == 1
    assert pairs[0].row == "H"
    assert {pairs[0].seat_a, pairs[0].seat_b} == {"12", "11"}


def test_finds_pair_at_far_edge_of_back_row():
    # No column restriction: an edge pair still qualifies.
    seats = [seat("K", "27", 10, 0), seat("K", "26", 10, 1)]
    assert len(find_pairs(seats)) == 1


def test_ignores_front_rows():
    seats = [seat("A", "12", 0, 12), seat("A", "11", 0, 13)]
    assert find_pairs(seats) == []


def test_ignores_seats_split_by_an_aisle():
    # Columns 12 and 14 are not adjacent; column 13 is a blank the parser drops.
    seats = [seat("H", "12", 6, 12), seat("H", "10", 6, 14)]
    assert find_pairs(seats) == []


def test_ignores_lone_available_seat():
    seats = [seat("H", "12", 6, 12)]
    assert find_pairs(seats) == []


def test_ignores_unavailable_neighbour():
    seats = [seat("H", "12", 6, 12), seat("H", "11", 6, 13, available=False)]
    assert find_pairs(seats) == []


def test_ignores_wheelchair_and_companion_seats():
    seats = [
        seat("K", "26", 10, 1, seat_type="wheelchair"),
        seat("K", "25", 10, 2, seat_type="companion"),
    ]
    assert find_pairs(seats) == []


def test_does_not_pair_across_different_physical_rows():
    # Both lettered "E" but different grid rows — must not pair.
    seats = [seat("E", "12", 4, 12), seat("E", "11", 5, 13)]
    assert find_pairs(seats) == []


def test_three_in_a_row_yields_two_overlapping_pairs():
    seats = [seat("G", "14", 5, 10), seat("G", "13", 5, 11), seat("G", "12", 5, 12)]
    assert len(find_pairs(seats)) == 2


def test_real_fixtures_yield_no_pairs():
    # Accurate: rows F-K are entirely sold out in both captures. A matcher that
    # finds a pair here is wrong.
    for name in (
        "seatmap_604612_nearly_sold_out.html",
        "seatmap_601707_has_availability.html",
    ):
        html = (FIXTURES / name).read_text(encoding="utf-8", errors="replace")
        assert find_pairs(parse_seats(html)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_match.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.match'`

- [ ] **Step 3: Write the implementation**

```python
"""Selection logic. Pure functions over data — no network, no HTML."""
from collections import defaultdict

from src import config
from src.models import Seat, SeatPair


def _qualifies(seat: Seat) -> bool:
    return (
        seat.available
        and seat.seat_type == config.BOOKABLE_SEAT_TYPE
        and seat.row in config.GOOD_ROWS
        and config.MIN_COL <= seat.phys_col <= config.MAX_COL
    )


def find_pairs(seats: list[Seat]) -> list[SeatPair]:
    """Return every pair of adjacent qualifying seats.

    Adjacency is by physical grid column within the same physical row. Because
    aisles and gaps render as blank cells that still consume column indices,
    two seats straddling an aisle differ by more than 1 and are never paired.

    Grouping is by phys_row, not row letter: the letter "E" is used by two
    different grid rows.
    """
    by_row: dict[int, list[Seat]] = defaultdict(list)
    for seat in seats:
        if _qualifies(seat):
            by_row[seat.phys_row].append(seat)

    pairs: list[SeatPair] = []
    for row_seats in by_row.values():
        ordered = sorted(row_seats, key=lambda s: s.phys_col)
        for left, right in zip(ordered, ordered[1:]):
            if right.phys_col - left.phys_col == 1:
                pairs.append(
                    SeatPair(
                        row=left.row,
                        phys_row=left.phys_row,
                        seat_a=left.number,
                        seat_b=right.number,
                    )
                )
    return pairs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_match.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/match.py tests/test_match.py
git commit -m "feat: match adjacent available seats in back rows"
```

---

### Task 6: Showtime window filter

**Files:**
- Modify: `src/match.py`
- Modify: `tests/test_match.py`

**Interfaces:**
- Consumes: `models.Showtime`, `config.EARLIEST_START`, `config.LATEST_START`, `config.WINDOW_DAYS`, `config.TZ`
- Produces: `showtime_in_window(showtime: Showtime, today: date) -> bool`

- [ ] **Step 1: Write the failing test (append to `tests/test_match.py`)**

```python
from datetime import date, datetime

from src import config
from src.match import showtime_in_window
from src.models import Showtime
from src.parse import parse_showtimes


def showtime_at(year, month, day, hour, minute, state="bookable"):
    return Showtime(
        state=state,
        display_time="x",
        showtime_id=1,
        movie_id=1,
        starts_at=datetime(year, month, day, hour, minute, tzinfo=config.TZ),
        seatmap_url="https://example.test/",
    )


TODAY = date(2026, 8, 1)


def test_accepts_showtime_inside_hours():
    assert showtime_in_window(showtime_at(2026, 8, 5, 15, 15), TODAY)


def test_accepts_exactly_11am_lower_boundary():
    assert showtime_in_window(showtime_at(2026, 8, 5, 11, 0), TODAY)


def test_accepts_exactly_7pm_upper_boundary():
    assert showtime_in_window(showtime_at(2026, 8, 5, 19, 0), TODAY)


def test_rejects_early_morning_showtime():
    assert not showtime_in_window(showtime_at(2026, 8, 5, 7, 45), TODAY)


def test_rejects_late_night_showtime():
    assert not showtime_in_window(showtime_at(2026, 8, 5, 22, 45), TODAY)


def test_rejects_after_midnight_showtime():
    # The 2:40am case that motivates timezone-aware handling.
    assert not showtime_in_window(showtime_at(2026, 8, 5, 2, 40), TODAY)


def test_rejects_date_before_today():
    assert not showtime_in_window(showtime_at(2026, 7, 31, 15, 0), TODAY)


def test_accepts_last_day_of_window():
    last_day = date(2026, 8, 1 + config.WINDOW_DAYS)
    showtime = showtime_at(last_day.year, last_day.month, last_day.day, 15, 0)
    assert showtime_in_window(showtime, TODAY)


def test_rejects_day_after_window_ends():
    past_end = date(2026, 8, 1 + config.WINDOW_DAYS + 1)
    showtime = showtime_at(past_end.year, past_end.month, past_end.day, 15, 0)
    assert not showtime_in_window(showtime, TODAY)


def test_rejects_non_bookable_showtime():
    assert not showtime_in_window(Showtime(state="sold_out", display_time="10:50pm"), TODAY)


def test_filters_real_listing_to_three_showtimes():
    # Aug 5 lists 7:45am, 11:30am, 3:15pm, 7:00pm, 10:45pm.
    # Exactly the middle three survive: 7:00pm is the inclusive upper boundary.
    # Sorted because DOM order is not guaranteed chronological — late-night
    # showings render in a separate showtimeMovieTimes--lateNight subtree.
    html = (FIXTURES / "listing_2026-08-05.html").read_text(encoding="utf-8", errors="replace")
    kept = [s for s in parse_showtimes(html) if showtime_in_window(s, date(2026, 8, 1))]
    assert sorted(s.display_time for s in kept) == sorted(["11:30am", "3:15pm", "7:00pm"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_match.py -v -k window`
Expected: FAIL with `ImportError: cannot import name 'showtime_in_window'`

- [ ] **Step 3: Write the implementation (append to `src/match.py`)**

```python
from datetime import date, timedelta

from src.models import Showtime


def showtime_in_window(showtime: Showtime, today: date) -> bool:
    """True if this showtime is worth fetching a seat map for.

    Applies to each showtime's own start time. Nothing about the schedule is
    assumed: the daily lineup varies (2 showtimes on one date, 5 on another),
    so a day whose only showings fall outside the hours simply contributes
    nothing rather than being special-cased.

    `today` is passed in rather than read from the clock so the filter stays
    a pure function and the date boundary is testable.
    """
    if showtime.state != "bookable" or showtime.starts_at is None:
        return False

    local = showtime.starts_at.astimezone(config.TZ)
    if not (config.EARLIEST_START <= local.time() <= config.LATEST_START):
        return False

    return today <= local.date() <= today + timedelta(days=config.WINDOW_DAYS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_match.py -v`
Expected: 21 passed.

- [ ] **Step 5: Commit**

```bash
git add src/match.py tests/test_match.py
git commit -m "feat: filter showtimes by hours and date window"
```

---

### Task 7: State store

**Files:**
- Create: `src/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: nothing from earlier tasks beyond `SeatPair.key` strings
- Produces:
  - `load_state(path: str) -> dict[str, list[str]] | None` — `None` when the file does not exist (first run)
  - `save_state(path: str, current: dict[str, list[str]]) -> None`
  - `new_pairs(previous: dict[str, list[str]], current: dict[str, list[str]]) -> dict[str, list[str]]`

State maps `str(showtime_id)` to the list of `SeatPair.key` values seen in that scan. Pruning is implicit: `current` only contains showtimes seen this scan, so past showtimes disappear when it is written.

- [ ] **Step 1: Write the failing test**

```python
import json

from src.state import load_state, new_pairs, save_state


def test_load_returns_none_when_file_missing(tmp_path):
    assert load_state(str(tmp_path / "nope.json")) is None


def test_save_then_load_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    data = {"601707": ["H:12-11", "G:5-4"]}
    save_state(path, data)
    assert load_state(path) == data


def test_saved_file_is_readable_json(tmp_path):
    path = str(tmp_path / "state.json")
    save_state(path, {"1": ["A:1-2"]})
    assert json.loads((tmp_path / "state.json").read_text()) == {"1": ["A:1-2"]}


def test_new_pair_in_known_showtime_is_reported():
    previous = {"601707": ["H:12-11"]}
    current = {"601707": ["H:12-11", "G:5-4"]}
    assert new_pairs(previous, current) == {"601707": ["G:5-4"]}


def test_pair_present_in_both_scans_is_not_reported():
    previous = {"601707": ["H:12-11"]}
    current = {"601707": ["H:12-11"]}
    assert new_pairs(previous, current) == {}


def test_pair_in_newly_seen_showtime_is_reported():
    assert new_pairs({}, {"999": ["K:3-2"]}) == {"999": ["K:3-2"]}


def test_disappeared_pair_is_not_reported():
    assert new_pairs({"1": ["H:12-11"]}, {"1": []}) == {}


def test_repurchased_then_rereleased_pair_alerts_again():
    # The behaviour a permanent already-alerted set would wrongly suppress.
    first = new_pairs({}, {"1": ["H:12-11"]})
    assert first == {"1": ["H:12-11"]}
    gone = new_pairs({"1": ["H:12-11"]}, {"1": []})
    assert gone == {}
    back = new_pairs({"1": []}, {"1": ["H:12-11"]})
    assert back == {"1": ["H:12-11"]}


def test_showtime_absent_from_current_is_dropped():
    # Past showtimes vanish rather than accumulating.
    assert new_pairs({"old": ["H:1-2"]}, {"new": []}) == {}


def test_new_pairs_output_is_sorted_for_stable_emails():
    result = new_pairs({}, {"1": ["K:3-2", "G:5-4", "H:12-11"]})
    assert result["1"] == ["G:5-4", "H:12-11", "K:3-2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.state'`

- [ ] **Step 3: Write the implementation**

```python
"""Persistence of the previous scan, so only newly-opened pairs alert."""
import json
import os


def load_state(path: str) -> dict[str, list[str]] | None:
    """Return the previous scan's pairs, or None if this is the first run.

    None and {} mean different things. None means no state file exists and the
    caller must seed without emailing. {} means a scan ran and found nothing.
    """
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_state(path: str, current: dict[str, list[str]]) -> None:
    """Overwrite state with this scan's results.

    Showtimes absent from `current` are dropped, which prunes past showtimes
    without a separate pass.
    """
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(current, handle, indent=2, sort_keys=True)
        handle.write("\n")


def new_pairs(
    previous: dict[str, list[str]], current: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Pairs available now that were not available in the previous scan.

    Diffing against the previous scan rather than keeping a permanent
    already-alerted set is deliberate. This is a cancellation watcher: a pair
    that opens, is bought, and re-opens days later is exactly the event worth
    knowing about, and a permanent set would suppress it forever.
    """
    result: dict[str, list[str]] = {}
    for showtime_id, keys in current.items():
        seen_before = set(previous.get(showtime_id, []))
        fresh = sorted(set(keys) - seen_before)
        if fresh:
            result[showtime_id] = fresh
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_state.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/state.py tests/test_state.py
git commit -m "feat: persist and diff scan state"
```

---

### Task 8: Email notification

**Files:**
- Create: `src/notify.py`
- Test: `tests/test_notify.py`

**Interfaces:**
- Consumes: `models.Alert`, `models.SeatPair`, `models.Showtime`, `config` SMTP constants
- Produces:
  - `format_email(alerts: list[Alert]) -> tuple[str, str]` — `(subject, body)`
  - `send_email(subject: str, body: str, password: str) -> None`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime

import pytest

from src import config
from src.models import Alert, SeatPair, Showtime
from src.notify import format_email, send_email


def make_alert(hour=15, minute=15, pairs=(("H", "12", "11"),)):
    showtime = Showtime(
        state="bookable",
        display_time=f"{hour if hour <= 12 else hour - 12}:{minute:02d}pm",
        showtime_id=601707,
        movie_id=104867,
        starts_at=datetime(2026, 8, 5, hour, minute, tzinfo=config.TZ),
        seatmap_url="https://www.cinemark.com/TicketSeatMap/?ShowtimeId=601707",
    )
    return Alert(
        showtime=showtime,
        pairs=tuple(SeatPair(row=r, phys_row=6, seat_a=a, seat_b=b) for r, a, b in pairs),
    )


def test_subject_names_seat_count_and_showtime():
    subject, _ = format_email([make_alert()])
    assert "Odyssey" in subject
    assert "70mm" in subject
    assert "Wed Aug 5" in subject


def test_subject_summarises_when_multiple_showtimes():
    subject, _ = format_email([make_alert(), make_alert(hour=19, minute=0)])
    assert "2 showtimes" in subject


def test_body_lists_row_seats_and_booking_link():
    _, body = format_email([make_alert()])
    assert "Row H" in body
    assert "12" in body and "11" in body
    assert "https://www.cinemark.com/TicketSeatMap/?ShowtimeId=601707" in body


def test_body_lists_every_pair():
    alert = make_alert(pairs=(("H", "12", "11"), ("K", "3", "2")))
    _, body = format_email([alert])
    assert "Row H" in body
    assert "Row K" in body


def test_format_email_rejects_empty_alerts():
    with pytest.raises(ValueError, match="no alerts"):
        format_email([])


def test_send_email_uses_ssl_and_logs_in(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, context=None):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, user, password):
            sent["user"] = user
            sent["password"] = password

        def send_message(self, message):
            sent["subject"] = message["Subject"]
            sent["to"] = message["To"]

    monkeypatch.setattr("src.notify.smtplib.SMTP_SSL", FakeSMTP)
    send_email("subject line", "body text", "app-password")

    assert sent["host"] == config.SMTP_HOST
    assert sent["port"] == config.SMTP_PORT
    assert sent["password"] == "app-password"
    assert sent["to"] == config.EMAIL_TO
    assert sent["subject"] == "subject line"


def test_send_email_rejects_empty_password():
    with pytest.raises(ValueError, match="password"):
        send_email("s", "b", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_notify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.notify'`

- [ ] **Step 3: Write the implementation**

```python
"""Compose and deliver the alert email."""
import smtplib
import ssl
from email.message import EmailMessage

from src import config
from src.models import Alert


def format_email(alerts: list[Alert]) -> tuple[str, str]:
    """Build one consolidated message covering every newly-opened pair.

    One email per scan, not one per pair — a burst of released seats should
    arrive as a single readable message.
    """
    if not alerts:
        raise ValueError("no alerts to format")

    total_pairs = sum(len(alert.pairs) for alert in alerts)
    first = alerts[0].showtime.starts_at.strftime("%a %b ") + str(
        alerts[0].showtime.starts_at.day
    )

    if len(alerts) == 1:
        subject = (
            f"Odyssey 70mm: {total_pairs} seat pair"
            f"{'s' if total_pairs != 1 else ''} open "
            f"{first} {alerts[0].showtime.display_time}"
        )
    else:
        subject = (
            f"Odyssey 70mm: {total_pairs} seat pairs open across "
            f"{len(alerts)} showtimes from {first}"
        )

    lines = ["Newly available adjacent seats in the back rows (F-K):", ""]
    for alert in alerts:
        showtime = alert.showtime
        stamp = showtime.starts_at.strftime("%a %b %d, %I:%M %p").replace(" 0", " ")
        lines.append(f"{stamp}")
        for pair in alert.pairs:
            lines.append(f"    Row {pair.row}, seats {pair.seat_a} and {pair.seat_b}")
        lines.append(f"    Book: {showtime.seatmap_url}")
        lines.append("")

    lines.append("These go fast. Seats are not held for you.")
    return subject, "\n".join(lines)


def send_email(subject: str, body: str, password: str) -> None:
    """Send via Gmail SMTP over implicit SSL."""
    if not password:
        raise ValueError("missing Gmail app password")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.EMAIL_FROM
    message["To"] = config.EMAIL_TO
    message.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=context) as server:
        server.login(config.EMAIL_FROM, password)
        server.send_message(message)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_notify.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/notify.py tests/test_notify.py
git commit -m "feat: compose and send alert email"
```

---

### Task 9: HTTP fetch layer

**Files:**
- Create: `src/fetch.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Consumes: `config.USER_AGENT`, `config.REQUEST_DELAY_S`, `config.REQUEST_TIMEOUT_S`, `config.MAX_RETRIES`
- Produces: `get(url: str, params: dict[str, str] | None = None) -> str`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from src import config, fetch


class FakeResponse:
    def __init__(self, status_code=200, text="<html></html>"):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_sends_browser_user_agent(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["headers"] = headers
        captured["url"] = url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    fetch.get("https://example.test/page")

    assert captured["headers"]["User-Agent"] == config.USER_AGENT
    assert captured["timeout"] == config.REQUEST_TIMEOUT_S


def test_passes_query_params(monkeypatch):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    fetch.get("https://example.test/", {"showDate": "2026-08-05"})
    assert captured["params"] == {"showDate": "2026-08-05"}


def test_sleeps_between_requests(monkeypatch):
    slept = []
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: FakeResponse())
    monkeypatch.setattr(fetch.time, "sleep", lambda s: slept.append(s))

    fetch.get("https://example.test/")
    assert slept == [config.REQUEST_DELAY_S]


def test_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def flaky(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("boom")
        return FakeResponse(text="<html>ok</html>")

    monkeypatch.setattr(fetch.requests, "get", flaky)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    assert fetch.get("https://example.test/") == "<html>ok</html>"
    assert calls["n"] == 3


def test_raises_after_max_retries(monkeypatch):
    def always_fails(url, params=None, headers=None, timeout=None):
        raise ConnectionError("boom")

    monkeypatch.setattr(fetch.requests, "get", always_fails)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    with pytest.raises(ConnectionError):
        fetch.get("https://example.test/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.fetch'`

- [ ] **Step 3: Write the implementation**

```python
"""The only network code in the project."""
import time

import requests

from src import config


def get(url: str, params: dict[str, str] | None = None) -> str:
    """Fetch a page with a browser User-Agent, retrying transient failures.

    Sleeps REQUEST_DELAY_S after every request. A scan makes roughly 25-35
    requests; spacing them keeps the load trivial for Cinemark and keeps us
    well clear of rate limiting.
    """
    headers = {"User-Agent": config.USER_AGENT}
    last_error: Exception | None = None

    for attempt in range(config.MAX_RETRIES):
        try:
            response = requests.get(
                url, params=params, headers=headers, timeout=config.REQUEST_TIMEOUT_S
            )
            response.raise_for_status()
            time.sleep(config.REQUEST_DELAY_S)
            return response.text
        except Exception as error:  # noqa: BLE001 — retry any transport failure
            last_error = error
            time.sleep(config.REQUEST_DELAY_S * (attempt + 1))

    raise last_error
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/fetch.py tests/test_fetch.py
git commit -m "feat: add HTTP fetch layer with retries and delay"
```

---

### Task 10: Orchestration

**Files:**
- Create: `src/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: everything above
- Produces: `run(password: str, *, state_path: str = config.STATE_PATH, today: date | None = None) -> int` returning the number of newly-opened pairs

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from pathlib import Path

import pytest

from src import main

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


@pytest.fixture
def fake_site(monkeypatch):
    """Serve the Aug 5 listing for every date, and a sold-out seat map."""
    def fake_get(url, params=None):
        if "TicketSeatMap" in url:
            return load("seatmap_604612_nearly_sold_out.html")
        return load("listing_2026-08-05.html")

    monkeypatch.setattr(main.fetch, "get", fake_get)


def test_first_run_seeds_state_without_emailing(fake_site, monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(main.notify, "send_email", lambda *a: sent.append(a))
    path = str(tmp_path / "state.json")

    main.run("pw", state_path=path, today=date(2026, 8, 1))

    assert sent == []
    assert Path(path).exists()


def test_no_email_when_nothing_new(fake_site, monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(main.notify, "send_email", lambda *a: sent.append(a))
    path = str(tmp_path / "state.json")

    main.run("pw", state_path=path, today=date(2026, 8, 1))
    main.run("pw", state_path=path, today=date(2026, 8, 1))

    assert sent == []


def test_emails_when_a_new_pair_appears(monkeypatch, tmp_path):
    path = str(tmp_path / "state.json")
    sent = []
    monkeypatch.setattr(main.notify, "send_email", lambda *a: sent.append(a))

    # First scan: everything sold out.
    monkeypatch.setattr(
        main.fetch,
        "get",
        lambda url, params=None: load("seatmap_604612_nearly_sold_out.html")
        if "TicketSeatMap" in url
        else load("listing_2026-08-05.html"),
    )
    main.run("pw", state_path=path, today=date(2026, 8, 1))
    assert sent == []

    # Second scan: inject two adjacent available seats into row H.
    injected = load("seatmap_604612_nearly_sold_out.html").replace(
        '<button available="False" class="seatUnavailable seatBlock" id="row6col12"',
        '<button available="True" class="seatAvailable seatBlock" id="row6col12"',
        1,
    ).replace(
        '<button available="False" class="seatUnavailable seatBlock" id="row6col13"',
        '<button available="True" class="seatAvailable seatBlock" id="row6col13"',
        1,
    )
    monkeypatch.setattr(
        main.fetch,
        "get",
        lambda url, params=None: injected
        if "TicketSeatMap" in url
        else load("listing_2026-08-05.html"),
    )
    count = main.run("pw", state_path=path, today=date(2026, 8, 1))

    assert count > 0
    assert len(sent) == 1


def test_raises_when_every_date_parses_zero_showtimes(monkeypatch, tmp_path):
    monkeypatch.setattr(
        main.fetch, "get", lambda url, params=None: "<html><div class='showtime'></div></html>"
    )
    with pytest.raises(RuntimeError, match="no IMAX 70mm showtimes"):
        main.run("pw", state_path=str(tmp_path / "s.json"), today=date(2026, 8, 1))


def test_only_fetches_seat_maps_for_qualifying_showtimes(monkeypatch, tmp_path):
    seatmap_calls = []

    def fake_get(url, params=None):
        if "TicketSeatMap" in url:
            seatmap_calls.append(url)
            return load("seatmap_604612_nearly_sold_out.html")
        return load("listing_2026-08-05.html")

    monkeypatch.setattr(main.fetch, "get", fake_get)
    monkeypatch.setattr(main.notify, "send_email", lambda *a: None)
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)

    # today must be Aug 5 itself: with WINDOW_DAYS=0 the window is a single day,
    # and the stub always serves the Aug 5 listing.
    main.run("pw", state_path=str(tmp_path / "s.json"), today=date(2026, 8, 5))

    # Aug 5 lists 5 showtimes; only 11:30am, 3:15pm and 7:00pm qualify.
    assert len(seatmap_calls) == 3


def test_same_showtime_listed_on_two_dates_is_fetched_once(monkeypatch, tmp_path):
    # Late-night showings appear on the previous day's listing as well as their
    # own, so the same showtime_id arrives twice. It must not be fetched twice.
    seatmap_calls = []

    def fake_get(url, params=None):
        if "TicketSeatMap" in url:
            seatmap_calls.append(url)
            return load("seatmap_604612_nearly_sold_out.html")
        return load("listing_2026-08-05.html")

    monkeypatch.setattr(main.fetch, "get", fake_get)
    monkeypatch.setattr(main.notify, "send_email", lambda *a: None)
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 3)

    main.run("pw", state_path=str(tmp_path / "s.json"), today=date(2026, 8, 5))

    # 4 listing fetches all return the same 5 showtimes; still only 3 seat maps.
    assert len(seatmap_calls) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.main'`

- [ ] **Step 3: Write the implementation**

```python
"""Orchestrates one scan."""
import os
import sys
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
    sys.exit(0 if run(os.environ.get("GMAIL_APP_PASSWORD", "")) >= 0 else 1)
```

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest -v`
Expected: all tests pass — 67 total (2 models, 16 parse, 21 match, 10 state, 7 notify, 5 fetch, 6 main).

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: orchestrate two-tier scan with state diffing"
```

---

### Task 11: Production workflow and documentation

**Files:**
- Create: `.github/workflows/watch.yml`, `README.md`
- Delete: `.github/workflows/connectivity-check.yml`

- [ ] **Step 1: Do a real end-to-end dry run locally**

```bash
cd ~/odyssey-watch
GMAIL_APP_PASSWORD="" python -c "
from src import main
print('pairs found:', main.run('', state_path='/tmp/seed.json'))
"
```

Expected: prints the showtime counts, then `first run — state seeded, no email sent`, then `pairs found: 0`. This makes ~25–35 real requests and takes 30–60 seconds. An empty password is safe because a first run never emails.

- [ ] **Step 2: Create the Gmail app password**

Go to https://myaccount.google.com/apppasswords (requires 2FA on the account). Create one named `odyssey-watch`. Copy the 16-character value.

Add it as a repository secret:

```bash
gh secret set GMAIL_APP_PASSWORD
```

Paste the value when prompted.

- [ ] **Step 3: Verify email delivery once, by hand**

```bash
GMAIL_APP_PASSWORD='<the 16 char password>' python -c "
from src import notify
notify.send_email('Odyssey watcher test', 'If you can read this, SMTP works.', __import__('os').environ['GMAIL_APP_PASSWORD'])
print('sent')
"
```

Expected: `sent`, and the message arrives in the inbox. Do not proceed until it does — a watcher that cannot email is useless.

- [ ] **Step 4: Create `.github/workflows/watch.yml`**

```yaml
name: watch

on:
  schedule:
    - cron: "*/10 * * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: watch
  cancel-in-progress: false

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Scan for seats
        env:
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
        run: python -m src.main

      - name: Persist state
        run: |
          if [ -n "$(git status --porcelain state.json)" ]; then
            git config user.name "odyssey-watch"
            git config user.email "actions@github.com"
            git add state.json
            git commit -m "chore: update scan state [skip ci]"
            git push
          else
            echo "state unchanged"
          fi
```

- [ ] **Step 5: Write `README.md`**

```markdown
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
```

- [ ] **Step 6: Remove the connectivity check workflow**

Its purpose is served; the production workflow now exercises the same path.

```bash
git rm .github/workflows/connectivity-check.yml
```

- [ ] **Step 7: Commit and push**

```bash
git add .github/workflows/watch.yml README.md
git commit -m "feat: add scheduled workflow and documentation"
git push
```

- [ ] **Step 8: Trigger one manual run and confirm**

```bash
gh workflow run watch.yml
sleep 90 && gh run list --workflow=watch.yml --limit 1
gh run view --log | tail -40
```

Expected: the log shows the showtime counts and either `first run — state seeded` or `no newly-opened pairs`, and `state.json` is committed to the repo. The schedule takes over from there.

---

## Verification

After Task 11, confirm all of the following before declaring the system live:

- [ ] `python -m pytest` passes with no failures
- [ ] The manual `watch.yml` run finished green
- [ ] `state.json` exists in the repo and contains showtime ids mapped to lists
- [ ] The hand-sent test email arrived
- [ ] A second manual run reports `no newly-opened pairs` rather than re-alerting
