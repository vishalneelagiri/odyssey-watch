"""HTML to dataclasses. Pure functions — no network, no I/O."""
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from src import config
from src.models import Seat, Showtime


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
