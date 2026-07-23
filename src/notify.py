"""Compose and deliver the alert email."""
import smtplib
import ssl
from email.message import EmailMessage

from src import config
from src.models import Alert


def format_email(alerts: list[Alert]) -> tuple[str, str]:
    """Build one consolidated message covering every newly-opened pair.

    One email per scan, not one per pair — a burst of released seats should
    arrive as a single readable message.
    """
    if not alerts:
        raise ValueError("no alerts to format")

    total_pairs = sum(len(alert.pairs) for alert in alerts)
    first = alerts[0].showtime.starts_at.strftime("%a %b ") + str(
        alerts[0].showtime.starts_at.day
    )

    if len(alerts) == 1:
        subject = (
            f"Odyssey 70mm: {total_pairs} seat pair"
            f"{'s' if total_pairs != 1 else ''} open "
            f"{first} {alerts[0].showtime.display_time}"
        )
    else:
        subject = (
            f"Odyssey 70mm: {total_pairs} seat pairs open across "
            f"{len(alerts)} showtimes from {first}"
        )

    lines = ["Newly available adjacent seats in the back rows (F-K):", ""]
    for alert in alerts:
        showtime = alert.showtime
        stamp = showtime.starts_at.strftime("%a %b %d, %I:%M %p").replace(" 0", " ")
        lines.append(f"{stamp}")
        for pair in alert.pairs:
            lines.append(f"    Row {pair.row}, seats {pair.seat_a} and {pair.seat_b}")
        lines.append(f"    Book: {showtime.seatmap_url}")
        lines.append("")

    lines.append("These go fast. Seats are not held for you.")
    return subject, "\n".join(lines)


def format_confirmation(listed: int, checked: int) -> tuple[str, str]:
    """Build the one-time "watcher is live" confirmation email.

    Sent on the very first run to prove the email delivery path actually
    works, long before the first real seat alert. Deliberately does not
    start like an alert subject, so it can never be mistaken for one.
    """
    subject = "Odyssey 70mm watcher is live"
    body = (
        "The Odyssey 70mm watcher is now running.\n\n"
        "It is watching for two adjacent available seats in the back rows "
        "for The Odyssey in IMAX 70mm.\n\n"
        f"This first scan listed {listed} showtime{'s' if listed != 1 else ''} "
        f"and is checking {checked} of them.\n\n"
        "It will email again only when a qualifying pair opens — silence "
        "means nothing has opened yet."
    )
    return subject, body


def send_email(subject: str, body: str, password: str) -> None:
    """Send via Gmail SMTP over implicit SSL."""
    if not password:
        raise ValueError("missing Gmail app password")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.EMAIL_FROM
    message["To"] = config.EMAIL_TO
    message.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=context) as server:
        server.login(config.EMAIL_FROM, password)
        server.send_message(message)
