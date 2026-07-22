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
