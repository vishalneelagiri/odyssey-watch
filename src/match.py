"""Selection logic. Pure functions over data — no network, no HTML."""
from collections import defaultdict
from datetime import date, timedelta

from src import config
from src.models import Seat, SeatPair, Showtime


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
