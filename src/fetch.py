"""The only network code in the project."""
import time

import requests

from src import config


def get(url: str, params: dict[str, str] | None = None) -> str:
    """Fetch a page with a browser User-Agent, retrying transient failures.

    Sleeps REQUEST_DELAY_S after every request. A scan makes roughly 25-35
    requests; spacing them keeps the load trivial for Cinemark and keeps us
    well clear of rate limiting.
    """
    headers = {"User-Agent": config.USER_AGENT}
    last_error: Exception | None = None

    for attempt in range(config.MAX_RETRIES):
        try:
            response = requests.get(
                url, params=params, headers=headers, timeout=config.REQUEST_TIMEOUT_S
            )
            response.raise_for_status()
            time.sleep(config.REQUEST_DELAY_S)
            return response.text
        except Exception as error:  # noqa: BLE001 — retry any transport failure
            last_error = error
            time.sleep(config.REQUEST_DELAY_S * (attempt + 1))

    if last_error is None:
        raise RuntimeError(
            f"Fetch failed: MAX_RETRIES is {config.MAX_RETRIES} (no attempts made)"
        )
    raise last_error
