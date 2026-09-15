from main import filter_allowed, load_state, release_state, save_state
from pathlib import Path


def test_only_exact_category_and_allowed_tracker_are_selected():
    rows = [
        {"category": "U2", "tracker": "https://u2.dmhy.org/a"},
        {"category": "U2", "tracker": "https://other.example/a"},
        {"category": "Other", "tracker": "https://u2.dmhy.org/a"},
    ]
    assert filter_allowed(rows, {"u2.dmhy.org"}) == [rows[0]]


def test_state_round_trip_is_atomic(tmp_path):
    path = tmp_path / "state.json"
    save_state(path, {"DE2/a": {"owned": True, "original_limit_bps": -1}})
    assert load_state(path) == {"DE2/a": {"owned": True, "original_limit_bps": -1}}
    assert not Path(str(path) + ".tmp").exists()


def test_release_restores_only_owned_records():
    class Client:
        def __init__(self): self.calls = []
        def set_upload_limit(self, torrent_hash, limit_bps): self.calls.append((torrent_hash, limit_bps))
    client = Client()
    records = {"DE2/a": {"node": "DE2", "hash": "a", "owned": True, "original_limit_bps": 9},
               "DE2/b": {"node": "DE2", "hash": "b", "owned": False, "original_limit_bps": 8}}
    assert release_state({"DE2": client}, records) == {"DE2/b": records["DE2/b"]}
    assert client.calls == [("a", 9)]
