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
