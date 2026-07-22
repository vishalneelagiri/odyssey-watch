"""Persistence of the previous scan, so only newly-opened pairs alert."""
import json
import os


def load_state(path: str) -> dict[str, list[str]] | None:
    """Return the previous scan's pairs, or None if this is the first run.

    None and {} mean different things. None means no state file exists and the
    caller must seed without emailing. {} means a scan ran and found nothing.
    """
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_state(path: str, current: dict[str, list[str]]) -> None:
    """Overwrite state with this scan's results.

    Showtimes absent from `current` are dropped, which prunes past showtimes
    without a separate pass.
    """
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(current, handle, indent=2, sort_keys=True)
        handle.write("\n")


def new_pairs(
    previous: dict[str, list[str]], current: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Pairs available now that were not available in the previous scan.

    Diffing against the previous scan rather than keeping a permanent
    already-alerted set is deliberate. This is a cancellation watcher: a pair
    that opens, is bought, and re-opens days later is exactly the event worth
    knowing about, and a permanent set would suppress it forever.
    """
    result: dict[str, list[str]] = {}
    for showtime_id, keys in current.items():
        seen_before = set(previous.get(showtime_id, []))
        fresh = sorted(set(keys) - seen_before)
        if fresh:
            result[showtime_id] = fresh
    return result
