from main import announce_values, filter_allowed, host_counts, load_state, release_state, run_once, save_state
from pathlib import Path


def test_only_exact_category_and_allowed_tracker_are_selected():
    rows = [
        {"category": "U2", "tracker": "https://u2.dmhy.org/a"},
        {"category": "U2", "tracker": "https://other.example/a"},
        {"category": "Other", "tracker": "https://u2.dmhy.org/a"},
    ]
    assert filter_allowed(rows, {"u2.dmhy.org"}) == [rows[0]]


def test_host_counts_reports_u2_category_tracker_hosts():
    rows = [{"category": "U2", "tracker": "https://u2.dmhy.org/a"},
            {"category": "U2", "tracker": "https://u2.dmhy.org/b"},
            {"category": "U2", "tracker": "https://other.example/a"}]
    assert host_counts(rows) == {"other.example": 1, "u2.dmhy.org": 2}


def test_announce_values_reads_each_u2_torrent():
    class Client:
        def next_announce(self, torrent_hash, tracker): return 900
    rows = [{"hash": "a", "category": "U2", "tracker": "https://u2.dmhy.org/a"}]
    assert announce_values(Client(), rows) == {"a": 900}


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


def test_run_once_writes_only_allowed_u2_and_records_ownership(tmp_path):
    class Client:
        name = "DE2"
        def __init__(self): self.calls = []
        def list_u2_torrents(self):
            return [{"hash": "a", "category": "U2", "tracker": "https://u2.dmhy.org/a",
                     "uploaded": 0, "up_limit": -1, "next_announce": 1800}]
        def next_announce(self, torrent_hash, tracker): return 1800
        def set_upload_limit(self, torrent_hash, limit_bps): self.calls.append((torrent_hash, limit_bps))
    client = Client()
    state = run_once([client], {"allowed_tracker_hosts": ["u2.dmhy.org"]}, {}, dry_run=False)
    assert client.calls == [("a", 45 * 1024 * 1024)]
    assert state["DE2/a"]["owned"] is True
