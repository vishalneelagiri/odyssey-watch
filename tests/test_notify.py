from datetime import datetime

import pytest

from src import config
from src.models import Alert, SeatPair, Showtime
from src.notify import format_confirmation, format_email, send_email


def make_alert(hour=15, minute=15, pairs=(("H", "12", "11"),)):
    showtime = Showtime(
        state="bookable",
        display_time=f"{hour if hour <= 12 else hour - 12}:{minute:02d}pm",
        showtime_id=601707,
        movie_id=104867,
        starts_at=datetime(2026, 8, 5, hour, minute, tzinfo=config.TZ),
        seatmap_url="https://www.cinemark.com/TicketSeatMap/?ShowtimeId=601707",
    )
    return Alert(
        showtime=showtime,
        pairs=tuple(SeatPair(row=r, phys_row=6, seat_a=a, seat_b=b) for r, a, b in pairs),
    )


def test_subject_names_seat_count_and_showtime():
    subject, _ = format_email([make_alert()])
    assert "Odyssey" in subject
    assert "70mm" in subject
    assert "Wed Aug 5" in subject


def test_subject_summarises_when_multiple_showtimes():
    subject, _ = format_email([make_alert(), make_alert(hour=19, minute=0)])
    assert "2 showtimes" in subject


def test_body_lists_row_seats_and_booking_link():
    _, body = format_email([make_alert()])
    assert "Row H" in body
    assert "12" in body and "11" in body
    assert "https://www.cinemark.com/TicketSeatMap/?ShowtimeId=601707" in body


def test_body_lists_every_pair():
    alert = make_alert(pairs=(("H", "12", "11"), ("K", "3", "2")))
    _, body = format_email([alert])
    assert "Row H" in body
    assert "Row K" in body


def test_format_email_rejects_empty_alerts():
    with pytest.raises(ValueError, match="no alerts"):
        format_email([])


def test_send_email_uses_ssl_and_logs_in(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, context=None):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, user, password):
            sent["user"] = user
            sent["password"] = password

        def send_message(self, message):
            sent["subject"] = message["Subject"]
            sent["to"] = message["To"]

    monkeypatch.setattr("src.notify.smtplib.SMTP_SSL", FakeSMTP)
    send_email("subject line", "body text", "app-password")

    assert sent["host"] == config.SMTP_HOST
    assert sent["port"] == config.SMTP_PORT
    assert sent["password"] == "app-password"
    assert sent["to"] == config.EMAIL_TO
    assert sent["subject"] == "subject line"


def test_send_email_rejects_empty_password():
    with pytest.raises(ValueError, match="password"):
        send_email("s", "b", "")


def test_confirmation_subject_signals_live_not_alert():
    subject, _ = format_confirmation(5, 3)
    assert "live" in subject.lower()
    alert_subject, _ = format_email([make_alert()])
    assert subject != alert_subject
    assert not subject.startswith("Odyssey 70mm:")


def test_confirmation_body_mentions_counts():
    _, body = format_confirmation(5, 3)
    assert "5" in body
    assert "3" in body
