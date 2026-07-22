"""Persistence of the previous scan, so only newly-opened pairs alert."""
import json
import os
import tempfile


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

    Writes are atomic: serializes to a temporary file in the same directory,
    then uses os.replace() to move it into place. This guarantees that if the
    process is killed mid-write, the destination file is never left truncated.
    os.replace() is atomic on both POSIX and Windows, and same-directory
    placement ensures the rename never crosses a filesystem boundary.
    """
    # Determine the directory to place the temporary file in.
    # For bare filenames like "state.json", dirname returns ""; use "." instead.
    directory = os.path.dirname(path) or "."

    # Create temporary file in the same directory as the destination.
    # This ensures os.replace() won't need to cross a filesystem boundary.
    try:
        fd, temp_path = tempfile.mkstemp(dir=directory, text=True)
        try:
            # Write to the temporary file descriptor.
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(current, handle, indent=2, sort_keys=True)
                handle.write("\n")
            # Atomically move temp file to destination.
            os.replace(temp_path, path)
        except Exception:
            # Clean up temp file if serialization failed.
            try:
                os.close(fd)
            except Exception:
                pass
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            raise
    except Exception:
        raise


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
