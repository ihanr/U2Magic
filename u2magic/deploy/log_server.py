from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import base64
import hashlib
import hmac
import json
import os
import subprocess


BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "logs" / "u2magic.log"
HOST = "0.0.0.0"
PORT = 18081
AUTH_USERNAME = os.environ.get("U2MAGIC_WEB_USERNAME", "")
AUTH_PASSWORD = os.environ.get("U2MAGIC_WEB_PASSWORD", "")
AUTH_COOKIE = hashlib.sha256(
    f"{AUTH_USERNAME}:{AUTH_PASSWORD}".encode("utf-8")
).hexdigest()


def tail_lines(path: Path, max_lines: int) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as f:
        f.seek(0, 2)
        end = f.tell()
        block_size = 8192
        data = b""
        lines_found = 0
        pos = end
        while pos > 0 and lines_found <= max_lines:
            read_size = min(block_size, pos)
            pos -= read_size
            f.seek(pos)
            chunk = f.read(read_size)
            data = chunk + data
            lines_found = data.count(b"\n")
    lines = data.splitlines()[-max_lines:]
    return b"\n".join(lines).decode("utf-8", errors="replace")


def docker_logs(max_lines: int) -> str:
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(max_lines), "u2magic"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return result.stdout
    except Exception as exc:
        return f"Failed to read docker logs: {exc}"


class Handler(BaseHTTPRequestHandler):
    def allowed_origin(self) -> str:
        origin = self.headers.get("Origin", "")
        if not origin:
            return ""
        parsed_origin = urlparse(origin)
        request_host = self.headers.get("Host", "").split(":", 1)[0]
        if (
            parsed_origin.scheme == "http"
            and parsed_origin.hostname == request_host
            and parsed_origin.port == 18080
        ):
            return origin
        return ""

    def is_authenticated(self) -> bool:
        if not AUTH_USERNAME or not AUTH_PASSWORD:
            return True

        authorization = self.headers.get("Authorization", "")
        if authorization.startswith("Basic "):
            try:
                decoded = base64.b64decode(authorization[6:]).decode("utf-8")
                if hmac.compare_digest(
                    decoded, f"{AUTH_USERNAME}:{AUTH_PASSWORD}"
                ):
                    return True
            except (ValueError, UnicodeDecodeError):
                pass

        cookies = self.headers.get("Cookie", "")
        for item in cookies.split(";"):
            name, separator, value = item.strip().partition("=")
            if (
                separator
                and name == "U2MAGIC_AUTH"
                and hmac.compare_digest(value, AUTH_COOKIE)
            ):
                return True
        return False

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        origin = self.allowed_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        origin = self.allowed_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization")
            self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:
        if not self.is_authenticated():
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="U2Magic Logs"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_json(200, {"ok": True})
            return
        if parsed.path != "/logs":
            self.send_json(404, {"error": "not found"})
            return
        query = parse_qs(parsed.query)
        try:
            lines = int(query.get("lines", ["500"])[0])
        except ValueError:
            lines = 500
        lines = max(50, min(lines, 3000))
        text = tail_lines(LOG_FILE, lines)
        source = str(LOG_FILE)
        if not text.strip():
            text = docker_logs(lines)
            source = "docker logs u2magic"
        self.send_json(200, {"path": source, "lines": lines, "text": text})

    def log_message(self, fmt: str, *args) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Serving {LOG_FILE} at http://{HOST}:{PORT}/logs")
    server.serve_forever()
