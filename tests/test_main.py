import json
from datetime import date, timedelta
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
    # No password (the dry-run path used before the Gmail secret exists):
    # seed silently, send nothing.
    sent = []
    monkeypatch.setattr(main.notify, "send_email", lambda *a: sent.append(a))
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)
    path = str(tmp_path / "state.json")

    main.run("", state_path=path, today=date(2026, 8, 5))

    assert sent == []
    assert Path(path).exists()


def test_first_run_with_password_sends_confirmation_email(fake_site, monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(
        main.notify, "send_email", lambda subject, body, pw: sent.append((subject, body, pw))
    )
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)
    path = str(tmp_path / "state.json")

    main.run("pw", state_path=path, today=date(2026, 8, 5))

    assert len(sent) == 1
    subject, body, pw = sent[0]
    assert "live" in subject.lower()
    assert not subject.startswith("Odyssey 70mm:")
    assert pw == "pw"
    assert Path(path).exists()


def test_first_run_with_empty_password_sends_nothing(fake_site, monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(main.notify, "send_email", lambda *a: sent.append(a))
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)
    path = str(tmp_path / "state.json")

    main.run("", state_path=path, today=date(2026, 8, 5))

    assert sent == []
    assert Path(path).exists()


def test_first_run_confirmation_send_failure_does_not_save_state(
    fake_site, monkeypatch, tmp_path
):
    def boom(*a):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr(main.notify, "send_email", boom)
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)
    path = str(tmp_path / "state.json")

    with pytest.raises(RuntimeError, match="smtp exploded"):
        main.run("pw", state_path=path, today=date(2026, 8, 5))

    assert not Path(path).exists()


def test_steady_state_run_sends_no_confirmation(fake_site, monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(
        main.notify, "send_email", lambda subject, body, pw: sent.append((subject, body, pw))
    )
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)
    path = str(tmp_path / "state.json")

    main.run("pw", state_path=path, today=date(2026, 8, 5))
    assert len(sent) == 1  # the confirmation from the first run
    sent.clear()

    main.run("pw", state_path=path, today=date(2026, 8, 5))
    assert sent == []


def test_no_email_when_nothing_new(fake_site, monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(main.notify, "send_email", lambda *a: sent.append(a))
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)
    path = str(tmp_path / "state.json")

    main.run("pw", state_path=path, today=date(2026, 8, 5))
    sent.clear()  # discard the first-run confirmation; this test is about steady-state
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
    assert len(sent) == 1  # the first-run confirmation
    sent.clear()

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
    # The same showtime_id can legitimately be returned by more than one
    # date's listing page, so the same showtime_id arrives twice. It must not
    # be fetched twice.
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

    # Only the first-run confirmation goes out — never an alert built from
    # the qualifying pair itself.
    assert len(sent) == 1
    assert "Row F" not in str(sent[0])
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
    assert len(sent) == 1  # the first-run confirmation
    sent.clear()

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


def _listing_with_showtimes(entries):
    """Build a minimal listing page with one <div class="showtime"> per entry.

    Each entry is (showtime_id, iso_date, hhmm_24h, display_text).
    """
    divs = []
    for showtime_id, iso_date, hhmm, display in entries:
        divs.append(f"""
        <div class="showtime" data-print-type-name="Imax 70mm">
          <a class="showtime-link"
             href="/TicketSeatMap/?TheaterId=276&ShowtimeId={showtime_id}&CinemarkMovieId=104867&Showtime={iso_date}T{hhmm}:00">
            {display}
          </a>
        </div>
        """)
    return "<html><body>" + "".join(divs) + "</body></html>"


def test_failed_send_does_not_advance_state(monkeypatch, tmp_path):
    # Reverting the fix (saving state before sending, or removing the
    # try/except that lets send failures propagate) would make this test
    # pass a state file that has already advanced past the pre-send contents.
    path = str(tmp_path / "state.json")
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)

    base = load("seatmap_604612_nearly_sold_out.html")
    listing = load("listing_2026-08-05.html")
    monkeypatch.setattr(
        main.fetch,
        "get",
        lambda url, params=None: base if "TicketSeatMap" in url else listing,
    )
    monkeypatch.setattr(main.notify, "send_email", lambda *a: None)

    # First run: sold out, seeds state.
    main.run("pw", state_path=path, today=date(2026, 8, 5))
    pre_send_contents = Path(path).read_text()

    # Second run: a pair opens, so send_email would be invoked — but it raises.
    injected = make_available(make_available(base, "row6col12"), "row6col13")
    monkeypatch.setattr(
        main.fetch,
        "get",
        lambda url, params=None: injected if "TicketSeatMap" in url else listing,
    )

    def boom(*a):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr(main.notify, "send_email", boom)

    with pytest.raises(RuntimeError, match="smtp exploded"):
        main.run("pw", state_path=path, today=date(2026, 8, 5))

    assert Path(path).read_text() == pre_send_contents


def test_one_failing_listing_date_does_not_abort_scan(monkeypatch, tmp_path):
    # Reverting tier-1's per-date try/except would let the Aug 5 failure
    # propagate out of run() instead of being isolated.
    path = str(tmp_path / "s.json")
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 1)  # scans Aug 5 and Aug 6
    monkeypatch.setattr(main.notify, "send_email", lambda *a: None)

    aug6_listing = _listing_with_showtimes(
        [(900001, "2026-08-06", "12:00", "12:00pm")]
    )
    seatmap = load("seatmap_604612_nearly_sold_out.html")

    def fake_get(url, params=None):
        if "TicketSeatMap" in url:
            return seatmap
        if params and params.get("showDate") == "2026-08-05":
            raise ValueError("markup changed for this date")
        return aug6_listing

    monkeypatch.setattr(main.fetch, "get", fake_get)

    main.run("pw", state_path=path, today=date(2026, 8, 5))

    assert Path(path).exists()
    saved = json.loads(Path(path).read_text())
    assert "900001" in saved


def test_one_failing_seatmap_carries_previous_entry_forward(monkeypatch, tmp_path):
    # Reverting the tier-2 carry-forward (dropping the failed key instead of
    # re-using `previous[key]`) would make the entry vanish from saved state.
    path = str(tmp_path / "s.json")
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)
    monkeypatch.setattr(main.notify, "send_email", lambda *a: None)

    listing = _listing_with_showtimes(
        [
            (900001, "2026-08-05", "11:30", "11:30am"),
            (900002, "2026-08-05", "15:15", "3:15pm"),
        ]
    )
    sold_out = load("seatmap_604612_nearly_sold_out.html")
    open_pair = make_available(
        make_available(sold_out, "row6col12"), "row6col13"
    )

    def fake_get_run1(url, params=None):
        if "ShowtimeId=900001" in url:
            return open_pair
        if "TicketSeatMap" in url:
            return sold_out
        return listing

    monkeypatch.setattr(main.fetch, "get", fake_get_run1)
    main.run("pw", state_path=path, today=date(2026, 8, 5))

    saved_run1 = json.loads(Path(path).read_text())
    assert saved_run1["900001"], "showtime 900001 should have a qualifying pair"

    def fake_get_run2(url, params=None):
        if "ShowtimeId=900001" in url:
            raise ValueError("seat map markup changed")
        if "TicketSeatMap" in url:
            return sold_out
        return listing

    monkeypatch.setattr(main.fetch, "get", fake_get_run2)
    main.run("pw", state_path=path, today=date(2026, 8, 5))

    saved_run2 = json.loads(Path(path).read_text())
    assert saved_run2["900001"] == saved_run1["900001"]


def test_total_tier2_failure_raises(monkeypatch, tmp_path):
    # Without the F1 guard, a total seat-map wipeout returns 0 silently.
    path = str(tmp_path / "s.json")
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 0)

    listing = _listing_with_showtimes(
        [(900001, "2026-08-05", "11:30", "11:30am")]
    )

    def fake_get(url, params=None):
        if "TicketSeatMap" in url:
            raise ValueError("seat map markup changed")
        return listing

    monkeypatch.setattr(main.fetch, "get", fake_get)

    with pytest.raises(RuntimeError, match="seat map"):
        main.run("pw", state_path=path, today=date(2026, 8, 5))


def test_tier1_partial_failure_does_not_prune_unseen_showtimes(monkeypatch, tmp_path):
    # Reverting the F3 carry-forward would let save_state prune showtime
    # 900001 the moment its only listing date fails to fetch/parse.
    path = str(tmp_path / "s.json")
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 1)  # scans Aug 5 and Aug 6
    monkeypatch.setattr(main.notify, "send_email", lambda *a: None)

    aug5_listing = _listing_with_showtimes(
        [(900001, "2026-08-05", "12:00", "12:00pm")]
    )
    aug6_listing = _listing_with_showtimes(
        [(900002, "2026-08-06", "12:00", "12:00pm")]
    )
    seatmap = load("seatmap_604612_nearly_sold_out.html")

    def fake_get_run1(url, params=None):
        if "TicketSeatMap" in url:
            return seatmap
        if params and params.get("showDate") == "2026-08-05":
            return aug5_listing
        return aug6_listing

    monkeypatch.setattr(main.fetch, "get", fake_get_run1)
    main.run("pw", state_path=path, today=date(2026, 8, 5))

    saved_run1 = json.loads(Path(path).read_text())
    assert "900001" in saved_run1

    def fake_get_run2(url, params=None):
        if "TicketSeatMap" in url:
            return seatmap
        if params and params.get("showDate") == "2026-08-05":
            raise ValueError("markup changed for Aug 5")
        return aug6_listing

    monkeypatch.setattr(main.fetch, "get", fake_get_run2)
    main.run("pw", state_path=path, today=date(2026, 8, 5))

    saved_run2 = json.loads(Path(path).read_text())
    assert "900001" in saved_run2
    assert saved_run2["900001"] == saved_run1["900001"]


def test_include_far_false_skips_far_seatmaps(monkeypatch, tmp_path):
    # Reverting the near/far split (fetching every wanted showtime
    # unconditionally) would make seatmap_calls include the far showtime too.
    path = str(tmp_path / "s.json")
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 10)
    monkeypatch.setattr(main.notify, "send_email", lambda *a: None)

    near_date = date(2026, 8, 5) + timedelta(days=2)   # within NEAR_WINDOW_DAYS
    far_date = date(2026, 8, 5) + timedelta(days=10)   # beyond NEAR_WINDOW_DAYS

    listings_by_date = {
        "2026-08-05": _listing_with_showtimes(
            [(900001, near_date.isoformat(), "12:00", "12:00pm")]
        ),
        far_date.isoformat(): _listing_with_showtimes(
            [(900002, far_date.isoformat(), "12:00", "12:00pm")]
        ),
    }
    seatmap = load("seatmap_604612_nearly_sold_out.html")
    seatmap_calls = []

    def fake_get(url, params=None):
        if "TicketSeatMap" in url:
            seatmap_calls.append(url)
            return seatmap
        show_date = params.get("showDate") if params else None
        return listings_by_date.get(show_date, "<html></html>")

    monkeypatch.setattr(main.fetch, "get", fake_get)

    # Not a first run: the first-run guard forces a complete scan regardless
    # of include_far (see the far-seed fix), so seed empty state up front to
    # actually exercise the near/far tiering split this test targets.
    main.state.save_state(path, {})

    main.run("pw", state_path=path, today=date(2026, 8, 5), include_far=False)

    assert any("ShowtimeId=900001" in u for u in seatmap_calls)
    assert not any("ShowtimeId=900002" in u for u in seatmap_calls)


def test_skipped_far_showtime_carries_previous_state_forward(monkeypatch, tmp_path):
    # If the skip path stopped carrying `previous[key]` forward, the far
    # showtime would vanish from saved state instead of persisting.
    path = str(tmp_path / "s.json")
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 10)
    monkeypatch.setattr(main.notify, "send_email", lambda *a: None)

    far_date = date(2026, 8, 5) + timedelta(days=10)
    listing = _listing_with_showtimes(
        [(900002, far_date.isoformat(), "12:00", "12:00pm")]
    )
    sold_out = load("seatmap_604612_nearly_sold_out.html")
    open_pair = make_available(
        make_available(sold_out, "row6col12"), "row6col13"
    )

    # Run 1: include_far=True, showtime 900002 has an open pair, gets seeded.
    monkeypatch.setattr(
        main.fetch,
        "get",
        lambda url, params=None: open_pair if "TicketSeatMap" in url else listing,
    )
    main.run("pw", state_path=path, today=date(2026, 8, 5), include_far=True)
    saved_run1 = json.loads(Path(path).read_text())
    assert saved_run1.get("900002"), "far showtime should be seeded with its pair"

    # Run 2: include_far=False — 900002's seat map must not be fetched at all,
    # and its previous entry must survive unchanged.
    def fake_get_run2(url, params=None):
        if "TicketSeatMap" in url:
            raise AssertionError("far showtime seat map must not be fetched")
        return listing

    monkeypatch.setattr(main.fetch, "get", fake_get_run2)
    main.run("pw", state_path=path, today=date(2026, 8, 5), include_far=False)

    saved_run2 = json.loads(Path(path).read_text())
    assert saved_run2["900002"] == saved_run1["900002"]


def test_all_far_skipped_does_not_trip_total_failure_guard(monkeypatch, tmp_path):
    # Every wanted showtime is far and include_far=False: zero seat maps are
    # attempted, so the total-failure guard must not fire even though zero
    # succeeded. Reverting the "attempted" tracking to the old "wanted"-based
    # check would make this raise RuntimeError.
    path = str(tmp_path / "s.json")
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 10)
    monkeypatch.setattr(main.notify, "send_email", lambda *a: None)

    far_date = date(2026, 8, 5) + timedelta(days=10)
    listing = _listing_with_showtimes(
        [(900002, far_date.isoformat(), "12:00", "12:00pm")]
    )

    def fake_get(url, params=None):
        if "TicketSeatMap" in url:
            raise AssertionError("far showtime seat map must not be fetched")
        return listing

    monkeypatch.setattr(main.fetch, "get", fake_get)

    # Not a first run: the first-run guard forces a complete scan regardless
    # of include_far, so seed empty state up front to actually exercise the
    # all-far-skipped guard this test targets.
    main.state.save_state(path, {})

    result = main.run(
        "pw", state_path=path, today=date(2026, 8, 5), include_far=False
    )
    assert result == 0
    assert Path(path).exists()


def test_include_far_true_default_fetches_everything(monkeypatch, tmp_path):
    # Regression guard: tiering must be off by default. Both near and far
    # showtimes get their seat maps fetched when include_far isn't passed.
    path = str(tmp_path / "s.json")
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 10)
    monkeypatch.setattr(main.notify, "send_email", lambda *a: None)

    near_date = date(2026, 8, 5) + timedelta(days=2)
    far_date = date(2026, 8, 5) + timedelta(days=10)

    listings_by_date = {
        "2026-08-05": _listing_with_showtimes(
            [(900001, near_date.isoformat(), "12:00", "12:00pm")]
        ),
        far_date.isoformat(): _listing_with_showtimes(
            [(900002, far_date.isoformat(), "12:00", "12:00pm")]
        ),
    }
    seatmap = load("seatmap_604612_nearly_sold_out.html")
    seatmap_calls = []

    def fake_get(url, params=None):
        if "TicketSeatMap" in url:
            seatmap_calls.append(url)
            return seatmap
        show_date = params.get("showDate") if params else None
        return listings_by_date.get(show_date, "<html></html>")

    monkeypatch.setattr(main.fetch, "get", fake_get)

    main.run("pw", state_path=path, today=date(2026, 8, 5))  # include_far default

    assert any("ShowtimeId=900001" in u for u in seatmap_calls)
    assert any("ShowtimeId=900002" in u for u in seatmap_calls)


def test_first_run_fetches_far_seatmaps_even_when_include_far_false(monkeypatch, tmp_path):
    # A fresh deploy has no state.json, so this is a first run. First runs
    # must be a complete scan regardless of include_far, otherwise the seed
    # is missing far-window keys entirely and the next include_far=True run
    # treats every one of them as brand new.
    path = str(tmp_path / "s.json")
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 10)
    monkeypatch.setattr(main.notify, "send_email", lambda *a: None)

    near_date = date(2026, 8, 5) + timedelta(days=2)   # within NEAR_WINDOW_DAYS
    far_date = date(2026, 8, 5) + timedelta(days=10)   # beyond NEAR_WINDOW_DAYS

    listings_by_date = {
        "2026-08-05": _listing_with_showtimes(
            [(900001, near_date.isoformat(), "12:00", "12:00pm")]
        ),
        far_date.isoformat(): _listing_with_showtimes(
            [(900002, far_date.isoformat(), "12:00", "12:00pm")]
        ),
    }
    seatmap = load("seatmap_604612_nearly_sold_out.html")
    seatmap_calls = []

    def fake_get(url, params=None):
        if "TicketSeatMap" in url:
            seatmap_calls.append(url)
            return seatmap
        show_date = params.get("showDate") if params else None
        return listings_by_date.get(show_date, "<html></html>")

    monkeypatch.setattr(main.fetch, "get", fake_get)

    main.run("pw", state_path=path, today=date(2026, 8, 5), include_far=False)

    assert any("ShowtimeId=900001" in u for u in seatmap_calls)
    assert any("ShowtimeId=900002" in u for u in seatmap_calls), (
        "far showtime seat map must be fetched on the first run even with "
        "include_far=False"
    )
    saved = json.loads(Path(path).read_text())
    assert "900001" in saved
    assert "900002" in saved, "far showtime key must be present in the seeded state"


def test_first_run_backlog_not_dumped_on_first_hourly_scan(monkeypatch, tmp_path):
    # End-to-end regression for the reported bug: a first run under a */10
    # schedule (include_far=False) against seat maps that already have open
    # far-window pairs must seed those far keys and send no email. The next
    # include_far=True run against the same availability must also send no
    # email, since nothing is actually new — proving the far-window backlog
    # is not dumped into a single alert.
    path = str(tmp_path / "s.json")
    sent = []
    monkeypatch.setattr(main.config, "WINDOW_DAYS", 10)
    monkeypatch.setattr(main.notify, "send_email", lambda *a: sent.append(a))

    near_date = date(2026, 8, 5) + timedelta(days=2)
    far_date = date(2026, 8, 5) + timedelta(days=10)

    listings_by_date = {
        "2026-08-05": _listing_with_showtimes(
            [(900001, near_date.isoformat(), "12:00", "12:00pm")]
        ),
        far_date.isoformat(): _listing_with_showtimes(
            [(900002, far_date.isoformat(), "12:00", "12:00pm")]
        ),
    }
    # The far showtime's seat map has an open qualifying pair (row6col12/13)
    # already available — this is the "backlog" that must not be dumped.
    open_pair = make_available(
        make_available(load("seatmap_604612_nearly_sold_out.html"), "row6col12"),
        "row6col13",
    )

    def fake_get(url, params=None):
        if "TicketSeatMap" in url:
            return open_pair
        show_date = params.get("showDate") if params else None
        return listings_by_date.get(show_date, "<html></html>")

    monkeypatch.setattr(main.fetch, "get", fake_get)

    # First run: */10 schedule, include_far=False. This is the first run
    # (no state.json yet), so it must still cover far dates and seed them.
    main.run("pw", state_path=path, today=date(2026, 8, 5), include_far=False)
    assert len(sent) == 1  # the first-run confirmation, never an alert
    sent.clear()
    saved_run1 = json.loads(Path(path).read_text())
    assert saved_run1.get("900002"), "far showtime's open pair must be seeded"

    # Second run: the hourly schedule fires with include_far=True against the
    # same unchanged availability. Nothing is new, so no email.
    main.run("pw", state_path=path, today=date(2026, 8, 5), include_far=True)
    assert sent == []


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
    assert len(sent) == 1  # the first-run confirmation
    sent.clear()

    monkeypatch.setattr(
        main.fetch,
        "get",
        lambda url, params=None: pair_state if "TicketSeatMap" in url else listing_html,
    )
    main.run("pw", state_path=path, today=date(2026, 8, 5))

    assert len(sent) == 1
    subject, body = sent[0]
    assert body.index("12:00 PM") < body.index("7:00 PM")
