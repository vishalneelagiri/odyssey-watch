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
