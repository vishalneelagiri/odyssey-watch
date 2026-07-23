"""The only network code in the project."""
import time

import requests

from src import config


def _retry_after_wait(response) -> float:
    """Seconds to wait before retrying a 429, from Retry-After or a fallback.

    Only the integer-seconds form of Retry-After is handled (that is what
    Cinemark sends when it sends the header at all, which in observation it
    does not). The HTTP-date form is not parsed; anything unparseable falls
    back to config.RATE_LIMIT_COOLDOWN_S.
    """
    value = response.headers.get("Retry-After")
    if value is not None:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            pass
    return config.RATE_LIMIT_COOLDOWN_S


def get(url: str, params: dict[str, str] | None = None) -> str:
    """Fetch a page with a browser User-Agent, retrying transient failures.

    Retried: transport failures (requests.RequestException / OSError, e.g.
    connection resets, DNS failures, timeouts) and 5xx responses — these are
    genuinely transient. 429 is also retried, but on its own separate budget
    (config.MAX_429_RETRIES) with its own cooldown — it means "slow down",
    not "something is broken", so it must not eat into the transport-retry
    budget.

    Fail fast (no retry, no sleep, error raised immediately): 4xx responses
    other than 429 — most importantly 403, the signature of Cloudflare
    blocking this client — and any programming error (AttributeError,
    TypeError, etc.), which is a bug, not a network blip, and must surface
    immediately rather than being disguised as a retryable failure.

    Sleeps REQUEST_DELAY_S after every successful request. A scan makes
    roughly 25-35 requests; spacing them keeps the load trivial for Cinemark
    and keeps us well clear of rate limiting. Between retries, sleeps only
    before a subsequent attempt — never after the final failed attempt.
    """
    headers = {"User-Agent": config.USER_AGENT}
    last_error: Exception | None = None
    transport_attempt = 0
    retry_429_count = 0

    while True:
        try:
            response = requests.get(
                url, params=params, headers=headers, timeout=config.REQUEST_TIMEOUT_S
            )
        except (requests.RequestException, OSError) as error:
            last_error = error
            transport_attempt += 1
            if transport_attempt < config.MAX_RETRIES:
                time.sleep(config.REQUEST_DELAY_S * transport_attempt)
                continue
            break

        status = response.status_code

        if status == 429:
            retry_429_count += 1
            if retry_429_count > config.MAX_429_RETRIES:
                raise requests.HTTPError(
                    f"HTTP 429 (rate limited) from {url} after "
                    f"{config.MAX_429_RETRIES} retries"
                )
            time.sleep(_retry_after_wait(response))
            continue

        if 400 <= status < 500:
            # Client errors other than 429 (notably 403 Cloudflare blocks)
            # are not transient — fail immediately, no retry, no sleep.
            response.raise_for_status()

        if status >= 500:
            last_error = requests.HTTPError(f"HTTP {status} from {url}")
            transport_attempt += 1
            if transport_attempt < config.MAX_RETRIES:
                time.sleep(config.REQUEST_DELAY_S * transport_attempt)
                continue
            break

        time.sleep(config.REQUEST_DELAY_S)
        return response.text

    if last_error is None:
        raise RuntimeError(
            f"Fetch failed: MAX_RETRIES is {config.MAX_RETRIES} (no attempts made)"
        )
    raise last_error
