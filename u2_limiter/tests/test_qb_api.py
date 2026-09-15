from qb_api import QbClient


def test_list_uses_exact_u2_category():
    client = QbClient({"name": "DE2", "host": "http://127.0.0.1:1", "username": "", "password": ""})
    assert client.info_path() == "/api/v2/torrents/info?category=U2"


def test_limit_path_is_single_torrent_endpoint():
    client = QbClient({"name": "DE2", "host": "http://127.0.0.1:1", "username": "", "password": ""})
    assert client.limit_path() == "/api/v2/torrents/setUploadLimit"


def test_properties_path_uses_one_torrent_hash_query():
    client = QbClient({"name": "DE2", "host": "http://example.test", "username": "", "password": ""})
    assert client.properties_path("a" * 40) == "/api/v2/torrents/properties?hash=" + "a" * 40


def test_torrent_properties_returns_qb_announce_countdown_and_uploaded(monkeypatch):
    client = QbClient({"name": "DE2", "host": "http://example.test", "username": "", "password": ""})
    monkeypatch.setattr(client, "_request", lambda path, data=None: b'{"reannounce":224,"total_uploaded":123}')
    assert client.torrent_properties("a" * 40) == {"reannounce": 224, "total_uploaded": 123}
