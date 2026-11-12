"""Serve only bundled viewer assets on loopback. Recording files never enter this server."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import unquote, urlsplit

STATIC = Path(__file__).with_name("static")
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".jsonl": "application/x-ndjson; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
    ".ico": "image/x-icon",
}
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
    "worker-src 'self' blob:; object-src 'none'; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'"
)


class _LoopbackHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer resolves a canonical hostname before listening. This viewer
        # binds only numeric loopback and needs no DNS-dependent server name.
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


def make_server(port: int = 0, *, asset_root: Path | None = None) -> ThreadingHTTPServer:
    root = (asset_root or STATIC).resolve()
    if not (root / "index.html").is_file():
        raise ValueError("Viewer assets are missing. Build the viewer before packaging.")
    assets = {
        "/" + path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
        and path.suffix in CONTENT_TYPES and path.resolve().is_relative_to(root)
    }
    assets["/"] = assets["/index.html"]

    class AssetHandler(BaseHTTPRequestHandler):
        server_version = "AgentFlightRecorder/0.1"
        sys_version = ""

        def log_message(self, _format, *args):
            # No path/query/request logs, including malformed hostile requests.
            pass

        def end_headers(self):
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def _asset(self, head: bool = False):
            port = self.server.server_address[1]
            hosts = self.headers.get_all("Host", [])
            if len(hosts) != 1 or hosts[0] not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
                self.send_error(403, "Host not allowed")
                return
            try:
                parsed = urlsplit(self.path)
                if parsed.scheme or parsed.netloc:
                    raise ValueError()
                path = unquote(parsed.path, errors="strict")
            except (UnicodeError, ValueError):
                self.send_error(400, "Invalid request")
                return
            asset = assets.get(path)
            if asset is None:
                self.send_error(404, "Asset not found")
                return
            try:
                body = asset.read_bytes()
            except OSError:
                self.send_error(404, "Asset not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPES[asset.suffix])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def do_GET(self):
            self._asset()

        def do_HEAD(self):
            self._asset(head=True)

    return _LoopbackHTTPServer(("127.0.0.1", port), AssetHandler)
