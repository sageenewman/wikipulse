from ingestion.resume import pick_latest


def test_no_messages_means_start_from_now() -> None:
    assert pick_latest([]) == ""


def test_newest_message_wins_across_partitions() -> None:
    tails = [(1000, "pos-old"), (3000, "pos-newest"), (2000, "pos-middle")]
    assert pick_latest(tails) == "pos-newest"


def test_messages_without_a_position_are_ignored() -> None:
    """A newer message with no header must not erase an older, usable position."""
    assert pick_latest([(1000, "pos-1"), (2000, "")]) == "pos-1"
    assert pick_latest([(2000, "")]) == ""
