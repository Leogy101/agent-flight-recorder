from http.client import HTTPConnection
import socket
from threading import Thread

import pytest

from agent_flight_recorder.server import make_server


@pytest.fixture
def server(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index.html").write_text("<!doctype html><title>Recorder</title>")
    (assets / "third-party-notices.txt").write_text("Bundled license notices")
    (tmp_path / "secret.jsonl").write_text("not for the server")
    (assets / "secret-link.jsonl").symlink_to(tmp_path / "secret.jsonl")
    (assets / "config.env").write_text("SECRET=sentinel")
    server = make_server(0, asset_root=assets)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join()


def request(server, path, method="GET", headers=None):
    client = HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
    client.request(method, path, headers=headers or {})
    response = client.getresponse()
    body = response.read()
    result = response.status, dict(response.getheaders()), body
    client.close()
    return result


def test_only_loopback_assets_with_security_headers(server):
    status, headers, body = request(server, "/")
    assert server.server_address[0] == "127.0.0.1"
    assert status == 200 and b"Recorder" in body
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in headers
    status, headers, body = request(server, "/third-party-notices.txt")
    assert status == 200 and body == b"Bundled license notices"
    assert headers["Content-Type"] == "text/plain; charset=utf-8"


@pytest.mark.parametrize("path", ["/../secret.jsonl", "/%2e%2e/secret.jsonl", "/secret-link.jsonl", "/config.env", "/api/files", "/read?path=/etc/passwd"])
def test_no_filesystem_or_data_api(server, path):
    status, _, body = request(server, path)
    assert status == 404
    assert b"not for the server" not in body and b"sentinel" not in body


def test_host_rebinding_and_write_requests_rejected(server):
    assert request(server, "/", headers={"Host": "evil.example"})[0] == 403
    assert request(server, "/upload", "POST")[0] == 501
    assert request(server, "/", "HEAD")[2] == b""


def test_assets_missing_is_clear(tmp_path):
    with pytest.raises(ValueError, match="assets are missing"):
        make_server(asset_root=tmp_path)


def test_loopback_startup_does_not_resolve_hostnames(tmp_path, monkeypatch):
    def forbidden_lookup(*_args, **_kwargs):
        raise AssertionError("Loopback viewer must not resolve a hostname")

    monkeypatch.setattr(socket, "getfqdn", forbidden_lookup)
    monkeypatch.setattr(socket, "gethostbyaddr", forbidden_lookup)
    (tmp_path / "index.html").write_text("<!doctype html><title>Offline viewer</title>")
    server = make_server(0, asset_root=tmp_path)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert server.server_name == "localhost"
        assert server.server_port == server.server_address[1] > 0
        status, _, body = request(server, "/")
        assert status == 200 and b"Offline viewer" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
