import copy

from main import dry_run, filter_allowed, host_counts, load_state, release_state, run_once, save_state
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


def test_dry_run_reports_reannounce_without_tracker_query(monkeypatch, capsys):
    class Client:
        def __init__(self, node): pass
        def list_u2_torrents(self):
            return [{"hash": "a", "category": "U2", "tracker": "https://daydream.dmhy.best/private-query"}]
        def torrent_properties(self, torrent_hash):
            return {"reannounce": 224, "total_uploaded": 123}
    monkeypatch.setattr("main.QbClient", Client)
    dry_run({"nodes": [{"name": "DE2"}], "allowed_tracker_hosts": ["daydream.dmhy.best"]})
    output = capsys.readouterr().out
    assert '"reannounce": {"a": 224}' in output
    assert "private-query" not in output
    assert "password" not in output


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
            return [{"hash": "a", "category": "U2", "tracker": "https://daydream.dmhy.best/a",
                     "uploaded": 0, "up_limit": -1}]
        def torrent_properties(self, torrent_hash): return {"reannounce": 1800, "total_uploaded": 0}
        def set_upload_limit(self, torrent_hash, limit_bps): self.calls.append((torrent_hash, limit_bps))
    client = Client()
    state = run_once([client], {"allowed_tracker_hosts": ["daydream.dmhy.best"]}, {}, dry_run=False, now=1000)
    assert client.calls == [("a", 45 * 1024 * 1024)]
    assert state["DE2/a"]["owned"] is True
    assert state["DE2/a"]["previous_reannounce"] == 1800


def test_run_once_does_not_change_limit_when_properties_fail():
    class Client:
        name = "DE2"
        def __init__(self): self.calls = []
        def list_u2_torrents(self):
            return [{"hash": "a", "category": "U2", "tracker": "https://daydream.dmhy.best/a",
                     "uploaded": 0, "up_limit": -1}]
        def torrent_properties(self, torrent_hash): raise OSError("temporary failure")
        def set_upload_limit(self, torrent_hash, limit_bps): self.calls.append((torrent_hash, limit_bps))
    client = Client()
    run_once([client], {"allowed_tracker_hosts": ["daydream.dmhy.best"]}, {}, dry_run=False, now=1000)
    assert client.calls == []


def test_properties_failure_leaves_existing_limit_and_hold_tag_unchanged():
    class Client:
        name = "DE1"
        def __init__(self): self.calls = []
        def list_u2_torrents(self):
            return [{"hash": "a", "category": "U2", "tracker": "https://daydream.dmhy.best/a",
                     "uploaded": 0, "up_limit": 1024, "tags": "U2LimitHoldUntil-9999"}]
        def torrent_properties(self, torrent_hash): raise TimeoutError("qB timeout")
        def set_upload_limit(self, torrent_hash, limit_bps): self.calls.append(("limit", limit_bps))
        def remove_tags(self, torrent_hash, tags): self.calls.append(("remove", tags))
    records = {"DE1/a": {"node": "DE1", "hash": "a", "owned": True,
               "original_limit_bps": 100 * 1024 * 1024, "baseline_uploaded": 0,
               "previous_reannounce": 600, "observed_at": 990, "announce_interval": 1800}}
    client = Client()
    result = run_once([client], {"allowed_tracker_hosts": ["daydream.dmhy.best"]}, records,
                      dry_run=False, now=1000)
    assert client.calls == []
    assert result == records


def test_ownership_is_checkpointed_before_qb_limit_is_changed():
    snapshots = []

    class Client:
        name = "DE2"
        def list_u2_torrents(self):
            return [{"hash": "a", "category": "U2", "tracker": "https://daydream.dmhy.best/a",
                     "uploaded": 0, "up_limit": 100 * 1024 * 1024}]
        def torrent_properties(self, torrent_hash): return {"reannounce": 1800, "total_uploaded": 0}
        def set_upload_limit(self, torrent_hash, limit_bps):
            assert snapshots[-1]["DE2/a"]["original_limit_bps"] == 100 * 1024 * 1024

    run_once([Client()], {"allowed_tracker_hosts": ["daydream.dmhy.best"]}, {}, dry_run=False,
             now=1000, checkpoint=lambda state: snapshots.append(copy.deepcopy(state)))
    assert snapshots


def test_one_failed_node_does_not_stop_the_other_nodes():
    class Broken:
        name = "DE2"
        def list_u2_torrents(self): raise OSError("node unavailable")

    class Healthy:
        name = "UK1"
        def __init__(self): self.calls = []
        def list_u2_torrents(self):
            return [{"hash": "a", "category": "U2", "tracker": "https://daydream.dmhy.best/a",
                     "uploaded": 0, "up_limit": 100 * 1024 * 1024}]
        def torrent_properties(self, torrent_hash): return {"reannounce": 1800, "total_uploaded": 0}
        def set_upload_limit(self, torrent_hash, limit_bps): self.calls.append((torrent_hash, limit_bps))

    healthy = Healthy()
    run_once([Broken(), healthy], {"allowed_tracker_hosts": ["daydream.dmhy.best"]}, {},
             dry_run=False, now=1000)
    assert healthy.calls == [("a", 45 * 1024 * 1024)]


def test_unmanaged_torrent_is_restored_and_hold_tags_are_removed():
    class Client:
        name = "DE1"
        def __init__(self): self.calls = []
        def list_u2_torrents(self):
            return [{"hash": "a", "category": "U2", "tracker": "https://other.example/a",
                     "up_limit": 1024, "tags": "keep,U2LimitHoldUntil-9999"}]
        def set_upload_limit(self, torrent_hash, limit_bps): self.calls.append(("limit", torrent_hash, limit_bps))
        def remove_tags(self, torrent_hash, tags): self.calls.append(("remove", torrent_hash, tags))

    records = {"DE1/a": {"node": "DE1", "hash": "a", "owned": True,
               "original_limit_bps": 100 * 1024 * 1024}}
    client = Client()
    assert run_once([client], {"allowed_tracker_hosts": ["daydream.dmhy.best"]}, records,
                    dry_run=False, now=1000) == {}
    assert client.calls == [("limit", "a", 100 * 1024 * 1024),
                            ("remove", "a", "U2LimitHoldUntil-9999")]


def test_budget_limited_torrent_gets_expiring_hold_tag_before_limit_change():
    class Client:
        name = "DE1"
        def __init__(self): self.calls = []
        def list_u2_torrents(self):
            return [{"hash": "a", "category": "U2", "tracker": "https://daydream.dmhy.best/a",
                     "uploaded": 0, "up_limit": 100 * 1024 * 1024, "tags": "keep,U2LimitHoldUntil-10"}]
        def torrent_properties(self, torrent_hash):
            return {"reannounce": 600, "total_uploaded": 49 * 1024 * 1024 * 1800}
        def add_tags(self, torrent_hash, tags): self.calls.append(("add", torrent_hash, tags))
        def remove_tags(self, torrent_hash, tags): self.calls.append(("remove", torrent_hash, tags))
        def set_upload_limit(self, torrent_hash, limit_bps): self.calls.append(("limit", torrent_hash, limit_bps))
    client = Client()
    records = {"DE1/a": {"node": "DE1", "hash": "a", "owned": True,
               "original_limit_bps": 100 * 1024 * 1024, "baseline_uploaded": 0,
               "previous_reannounce": 1000, "observed_at": 990, "announce_interval": 1800}}
    run_once([client], {"allowed_tracker_hosts": ["daydream.dmhy.best"]}, records, dry_run=False, now=1000)
    assert client.calls[0] == ("add", "a", "U2LimitHoldUntil-1300")
    assert client.calls[1] == ("remove", "a", "U2LimitHoldUntil-10")
    assert client.calls[2][0] == "limit"
