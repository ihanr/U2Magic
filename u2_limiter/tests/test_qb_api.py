from qb_api import QbClient


def test_list_uses_exact_u2_category():
    client = QbClient({"name": "DE2", "host": "http://127.0.0.1:1", "username": "", "password": ""})
    assert client.info_path() == "/api/v2/torrents/info?category=U2"


def test_limit_path_is_single_torrent_endpoint():
    client = QbClient({"name": "DE2", "host": "http://127.0.0.1:1", "username": "", "password": ""})
    assert client.limit_path() == "/api/v2/torrents/setUploadLimit"
