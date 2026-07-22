"""The only network code in the project."""
import time

import requests

from src import config


def get(url: str, params: dict[str, str] | None = None) -> str:
    """Fetch a page with a browser User-Agent, retrying transient failures.

    Retried: transport failures (requests.RequestException / OSError, e.g.
    connection resets, DNS failures, timeouts) and 5xx responses — these are
    genuinely transient.

    Fail fast (no retry, no sleep, error raised immediately): 4xx responses —
    most importantly 403, the signature of Cloudflare blocking this client —
    and any programming error (AttributeError, TypeError, etc.), which is a
    bug, not a network blip, and must surface immediately rather than being
    disguised as a retryable failure.

    Sleeps REQUEST_DELAY_S after every successful request. A scan makes
    roughly 25-35 requests; spacing them keeps the load trivial for Cinemark
    and keeps us well clear of rate limiting. Between retries, sleeps only
    before a subsequent attempt — never after the final failed attempt.
    """
    headers = {"User-Agent": config.USER_AGENT}
    last_error: Exception | None = None

    for attempt in range(config.MAX_RETRIES):
        try:
            response = requests.get(
                url, params=params, headers=headers, timeout=config.REQUEST_TIMEOUT_S
            )
        except (requests.RequestException, OSError) as error:
            last_error = error
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(config.REQUEST_DELAY_S * (attempt + 1))
            continue

        status = response.status_code
        if 400 <= status < 500:
            # Client errors (notably 403 Cloudflare blocks) are not
            # transient — fail immediately, no retry, no sleep.
            response.raise_for_status()

        if status >= 500:
            try:
                response.raise_for_status()
            except Exception as error:  # noqa: BLE001 — 5xx is a genuine transient failure
                last_error = error
                if attempt < config.MAX_RETRIES - 1:
                    time.sleep(config.REQUEST_DELAY_S * (attempt + 1))
                continue

        time.sleep(config.REQUEST_DELAY_S)
        return response.text

    if last_error is None:
        raise RuntimeError(
            f"Fetch failed: MAX_RETRIES is {config.MAX_RETRIES} (no attempts made)"
        )
    raise last_error
