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
