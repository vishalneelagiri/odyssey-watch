from src.models import SeatPair


def test_seat_pair_key_is_stable_and_readable():
    pair = SeatPair(row="H", phys_row=6, seat_a="12", seat_b="11")
    assert pair.key == "H:12-11"


def test_seat_pairs_with_same_key_are_equal():
    a = SeatPair(row="H", phys_row=6, seat_a="12", seat_b="11")
    b = SeatPair(row="H", phys_row=6, seat_a="12", seat_b="11")
    assert a == b
    assert len({a, b}) == 1
