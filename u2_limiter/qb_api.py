import http.cookiejar
import json
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


class QbClient:
    def __init__(self, node):
        self.node = node
        self.base = node["host"].rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    @staticmethod
    def info_path():
        return "/api/v2/torrents/info?category=U2"

    @staticmethod
    def limit_path():
        return "/api/v2/torrents/setUploadLimit"

    @staticmethod
    def properties_path(torrent_hash):
        return "/api/v2/torrents/properties?" + urlencode({"hash": torrent_hash})

    def _request(self, path, data=None):
        request = Request(self.base + path, data=data)
        with self.opener.open(request, timeout=10) as response:
            return response.read()

    def login(self):
        body = urlencode({"username": self.node["username"], "password": self.node["password"]}).encode()
        self._request("/api/v2/auth/login", body)

    def list_u2_torrents(self):
        try:
            rows = json.loads(self._request(self.info_path()))
        except Exception:
            self.login()
            rows = json.loads(self._request(self.info_path()))
        return [row for row in rows if row.get("category") == "U2"]

    def set_upload_limit(self, torrent_hash, limit_bps):
        data = urlencode({"hashes": torrent_hash, "limit": int(limit_bps)}).encode()
        self._request(self.limit_path(), data)

    def torrent_properties(self, torrent_hash):
        return json.loads(self._request(self.properties_path(torrent_hash)))

    def tracker_host(self, torrent):
        return urlparse(torrent.get("tracker", "")).hostname or ""
