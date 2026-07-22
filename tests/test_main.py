import json
from datetime import date
from pathlib import Path

import pytest

from src import main

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


def make_available(html, seat_id):
    """Flip one seat button (by its `id`) from unavailable to available."""
    return html.replace(
        f'<button available="False" class="seatUnavailable seatBlock" id="{seat_id}"',
        f'<button available="True" class="seatAvailable seatBlock" id="{seat_id}"',
        1,
    )


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
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)
    path = str(tmp_path / "state.json")

    main.run("pw", state_path=path, today=date(2026, 8, 5))

    assert sent == []
    assert Path(path).exists()


def test_no_email_when_nothing_new(fake_site, monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(main.notify, "send_email", lambda *a: sent.append(a))
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)
    path = str(tmp_path / "state.json")

    main.run("pw", state_path=path, today=date(2026, 8, 5))
    main.run("pw", state_path=path, today=date(2026, 8, 5))

    assert sent == []


def test_emails_when_a_new_pair_appears(monkeypatch, tmp_path):
    path = str(tmp_path / "state.json")
    sent = []
    monkeypatch.setattr(main.notify, "send_email", lambda *a: sent.append(a))
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)

    # First scan: everything sold out.
    monkeypatch.setattr(
        main.fetch,
        "get",
        lambda url, params=None: load("seatmap_604612_nearly_sold_out.html")
        if "TicketSeatMap" in url
        else load("listing_2026-08-05.html"),
    )
    main.run("pw", state_path=path, today=date(2026, 8, 5))
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
    count = main.run("pw", state_path=path, today=date(2026, 8, 5))

    assert count > 0
    assert len(sent) == 1


def test_raises_when_every_date_parses_zero_showtimes(monkeypatch, tmp_path):
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)
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


def test_first_run_with_qualifying_pairs_sends_no_email(monkeypatch, tmp_path):
    # Row F is phys_row 6 and is in GOOD_ROWS: row6col12/row6col13 (seats F15,
    # F14) become an adjacent qualifying pair once available. If the
    # first-run guard is removed, this would email on the very first scan.
    path = str(tmp_path / "state.json")
    sent = []
    monkeypatch.setattr(main.notify, "send_email", lambda *a: sent.append(a))
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)

    seatmap = make_available(
        make_available(load("seatmap_604612_nearly_sold_out.html"), "row6col12"),
        "row6col13",
    )
    monkeypatch.setattr(
        main.fetch,
        "get",
        lambda url, params=None: seatmap
        if "TicketSeatMap" in url
        else load("listing_2026-08-05.html"),
    )

    main.run("pw", state_path=path, today=date(2026, 8, 5))

    assert sent == []
    assert Path(path).exists()
    saved = json.loads(Path(path).read_text())
    assert any(saved.values()), "the qualifying pair should still be in the saved state"


def test_only_newly_opened_pairs_are_emailed(monkeypatch, tmp_path):
    # Scan 1 has pair A (row F) open, scan 2 has both A and B (row G) open.
    # Only B is newly-opened and only B should be emailed.
    path = str(tmp_path / "state.json")
    sent = []
    monkeypatch.setattr(
        main.notify, "send_email", lambda subject, body, pw: sent.append((subject, body))
    )
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)

    base = load("seatmap_604612_nearly_sold_out.html")
    pair_a_only = make_available(make_available(base, "row6col12"), "row6col13")
    pair_a_and_b = make_available(make_available(pair_a_only, "row7col12"), "row7col13")

    monkeypatch.setattr(
        main.fetch,
        "get",
        lambda url, params=None: pair_a_only
        if "TicketSeatMap" in url
        else load("listing_2026-08-05.html"),
    )
    main.run("pw", state_path=path, today=date(2026, 8, 5))
    assert sent == []

    monkeypatch.setattr(
        main.fetch,
        "get",
        lambda url, params=None: pair_a_and_b
        if "TicketSeatMap" in url
        else load("listing_2026-08-05.html"),
    )
    main.run("pw", state_path=path, today=date(2026, 8, 5))

    assert len(sent) == 1
    subject, body = sent[0]
    assert "Row G" in body
    assert "Row F" not in body


def test_alerts_sorted_by_starts_at(monkeypatch, tmp_path):
    # Two showtimes both get new pairs on scan 2. The listing deliberately
    # lists the 7:00pm showtime before the 12:00pm one, so only an explicit
    # sort by starts_at (not parse/insertion order) puts 12:00pm first.
    path = str(tmp_path / "state.json")
    sent = []
    monkeypatch.setattr(
        main.notify, "send_email", lambda subject, body, pw: sent.append((subject, body))
    )
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)

    listing_html = """
    <html><body>
    <div class="showtime" data-print-type-name="Imax 70mm">
      <a class="showtime-link"
         href="/TicketSeatMap/?TheaterId=276&ShowtimeId=900002&CinemarkMovieId=104867&Showtime=2026-08-05T19:00:00">
        7:00pm
      </a>
    </div>
    <div class="showtime" data-print-type-name="Imax 70mm">
      <a class="showtime-link"
         href="/TicketSeatMap/?TheaterId=276&ShowtimeId=900001&CinemarkMovieId=104867&Showtime=2026-08-05T12:00:00">
        12:00pm
      </a>
    </div>
    </body></html>
    """

    base = load("seatmap_604612_nearly_sold_out.html")
    pair_state = make_available(make_available(base, "row6col12"), "row6col13")

    monkeypatch.setattr(
        main.fetch,
        "get",
        lambda url, params=None: base if "TicketSeatMap" in url else listing_html,
    )
    main.run("pw", state_path=path, today=date(2026, 8, 5))
    assert sent == []

    monkeypatch.setattr(
        main.fetch,
        "get",
        lambda url, params=None: pair_state if "TicketSeatMap" in url else listing_html,
    )
    main.run("pw", state_path=path, today=date(2026, 8, 5))

    assert len(sent) == 1
    subject, body = sent[0]
    assert body.index("12:00 PM") < body.index("7:00 PM")
