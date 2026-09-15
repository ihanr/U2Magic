from main import filter_allowed


def test_only_exact_category_and_allowed_tracker_are_selected():
    rows = [
        {"category": "U2", "tracker": "https://u2.dmhy.org/a"},
        {"category": "U2", "tracker": "https://other.example/a"},
        {"category": "Other", "tracker": "https://u2.dmhy.org/a"},
    ]
    assert filter_allowed(rows, {"u2.dmhy.org"}) == [rows[0]]
