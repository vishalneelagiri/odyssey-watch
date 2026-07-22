from datetime import datetime
from pathlib import Path

import pytest

from src import config
from src.parse import parse_seats, parse_showtimes

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
