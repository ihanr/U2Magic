from qb_api import QbClient


def test_list_uses_exact_u2_category():
    client = QbClient({"name": "DE2", "host": "http://127.0.0.1:1", "username": "", "password": ""})
    assert client.info_path() == "/api/v2/torrents/info?category=U2"


def test_limit_path_is_single_torrent_endpoint():
    client = QbClient({"name": "DE2", "host": "http://127.0.0.1:1", "username": "", "password": ""})
    assert client.limit_path() == "/api/v2/torrents/setUploadLimit"


def test_next_announce_uses_matching_tracker_detail(monkeypatch):
    client = QbClient({"name": "DE2", "host": "http://example.test", "username": "", "password": ""})
    monkeypatch.setattr(client, "_request", lambda path, data=None: b'[{"url":"https://other.example/a","next_announce":1},{"url":"https://daydream.dmhy.best/a","next_announce":900}]')
    assert client.next_announce("a" * 40, "https://daydream.dmhy.best/a") == 900
