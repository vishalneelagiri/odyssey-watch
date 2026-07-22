import json

from src.state import load_state, new_pairs, save_state


def test_load_returns_none_when_file_missing(tmp_path):
    assert load_state(str(tmp_path / "nope.json")) is None


def test_save_then_load_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    data = {"601707": ["H:12-11", "G:5-4"]}
    save_state(path, data)
    assert load_state(path) == data


def test_saved_file_is_readable_json(tmp_path):
    path = str(tmp_path / "state.json")
    save_state(path, {"1": ["A:1-2"]})
    assert json.loads((tmp_path / "state.json").read_text()) == {"1": ["A:1-2"]}


def test_new_pair_in_known_showtime_is_reported():
    previous = {"601707": ["H:12-11"]}
    current = {"601707": ["H:12-11", "G:5-4"]}
    assert new_pairs(previous, current) == {"601707": ["G:5-4"]}


def test_pair_present_in_both_scans_is_not_reported():
    previous = {"601707": ["H:12-11"]}
    current = {"601707": ["H:12-11"]}
    assert new_pairs(previous, current) == {}


def test_pair_in_newly_seen_showtime_is_reported():
    assert new_pairs({}, {"999": ["K:3-2"]}) == {"999": ["K:3-2"]}


def test_disappeared_pair_is_not_reported():
    assert new_pairs({"1": ["H:12-11"]}, {"1": []}) == {}


def test_repurchased_then_rereleased_pair_alerts_again():
    # The behaviour a permanent already-alerted set would wrongly suppress.
    first = new_pairs({}, {"1": ["H:12-11"]})
    assert first == {"1": ["H:12-11"]}
    gone = new_pairs({"1": ["H:12-11"]}, {"1": []})
    assert gone == {}
    back = new_pairs({"1": []}, {"1": ["H:12-11"]})
    assert back == {"1": ["H:12-11"]}


def test_showtime_absent_from_current_is_dropped():
    # Past showtimes vanish rather than accumulating.
    assert new_pairs({"old": ["H:1-2"]}, {"new": []}) == {}


def test_new_pairs_output_is_sorted_for_stable_emails():
    result = new_pairs({}, {"1": ["K:3-2", "G:5-4", "H:12-11"]})
    assert result["1"] == ["G:5-4", "H:12-11", "K:3-2"]
