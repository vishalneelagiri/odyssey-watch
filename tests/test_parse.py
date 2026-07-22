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
