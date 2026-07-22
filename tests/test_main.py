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
