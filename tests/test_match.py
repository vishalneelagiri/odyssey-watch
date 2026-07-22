from datetime import date, datetime
from pathlib import Path

from src import config
from src.match import find_pairs, showtime_in_window
from src.models import Seat, Showtime
from src.parse import parse_seats, parse_showtimes

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


def test_rejects_bookable_with_no_start_time():
    showtime = Showtime(state="bookable", display_time="x")
    assert not showtime_in_window(showtime, TODAY)


def test_rejects_sold_out_with_valid_start_time():
    showtime = showtime_at(2026, 8, 5, 15, 15, state="sold_out")
    assert not showtime_in_window(showtime, TODAY)


def test_filters_real_listing_to_three_showtimes():
    # Aug 5 lists 7:45am, 11:30am, 3:15pm, 7:00pm, 10:45pm.
    # Exactly the middle three survive: 7:00pm is the inclusive upper boundary.
    # Sorted because DOM order is not guaranteed chronological — late-night
    # showings render in a separate showtimeMovieTimes--lateNight subtree.
    html = (FIXTURES / "listing_2026-08-05.html").read_text(encoding="utf-8", errors="replace")
    kept = [s for s in parse_showtimes(html) if showtime_in_window(s, date(2026, 8, 1))]
    assert sorted(s.display_time for s in kept) == sorted(["11:30am", "3:15pm", "7:00pm"])
