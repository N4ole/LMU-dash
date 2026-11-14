"""Tests de sécurité du serveur HTTP (vrai serveur sur un port libre, données de démo)."""

import http.client
import json
import os
import threading
from http.server import ThreadingHTTPServer

import pytest

import server
from readers import DemoReader
from shared import Shared
from store import Profiles, Settings
from updates import UpdateCheck
from version import VERSION


@pytest.fixture
def live(tmp_path, monkeypatch):
    profiles = Profiles(str(tmp_path / "data"))
    settings = Settings(os.path.join(profiles.path(), "settings.json"))
    engine = server.Engine(DemoReader(settings), settings, str(tmp_path / "data"), profiles)
    monkeypatch.setattr(server, "ENGINE", engine)
    monkeypatch.setattr(server, "SETTINGS", settings)
    monkeypatch.setattr(server, "SHARED", Shared("N4ole/lmu-dash", engine.tracks, enabled=False))
    monkeypatch.setattr(server, "UPDATES", UpdateCheck("N4ole/lmu-dash", enabled=False))
    monkeypatch.setattr(server, "ALLOWED_HOSTS", server.LOCAL_HOSTS)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    yield {"port": srv.server_address[1], "tmp": tmp_path, "settings": settings, "profiles": profiles}
    srv.shutdown()
    srv.server_close()


def request(live, method, path, body=None, headers=None, raw_body=None):
    conn = http.client.HTTPConnection("127.0.0.1", live["port"], timeout=5)
    h = {"Host": f"localhost:{live['port']}"}
    data = raw_body
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    for k, v in h.items():
        if v is not None:
            conn.putheader(k, v)
    if data is not None and "Content-Length" not in h:
        conn.putheader("Content-Length", str(len(data)))
    conn.endheaders()
    if data:
        conn.send(data)
    r = conn.getresponse()
    out = r.status, r.read(), dict(r.getheaders())
    conn.close()
    return out


# ---------------------------------------------------------------- GET


def test_index_and_version(live):
    status, body, headers = request(live, "GET", "/")
    assert status == 200 and b"LMU" in body
    assert headers["X-Content-Type-Options"] == "nosniff"
    status, body, _ = request(live, "GET", "/api/version")
    assert status == 200 and json.loads(body)["version"] == VERSION


@pytest.mark.parametrize(
    "path",
    [
        "/../server.py",
        "/../../server.py",
        "/..%2fserver.py",
        "/%2e%2e/server.py",
        "/%2e%2e%2f%2e%2e%2fserver.py",
        "/..\\server.py",
        "/web/../server.py",
        "//server.py",
        "/./../store.py",
    ],
)
def test_path_traversal(live, path):
    status, body, _ = request(live, "GET", path)
    assert status in (301, 404)  # 301 : renvoi vers « / » quand le segment douteux est ignoré
    assert b"def main" not in body and b"import" not in body


def test_no_directory_listing(live, tmp_path, monkeypatch):
    web = tmp_path / "web"
    (web / "sub").mkdir(parents=True)
    (web / "sub" / "secret.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(server, "WEB_DIR", str(web))
    status, body, _ = request(live, "GET", "/sub/")
    assert status == 404 and b"secret.txt" not in body


# ---------------------------------------------------------------- Host (DNS rebinding)


@pytest.mark.parametrize("host", ["localhost", "localhost:8765", "127.0.0.1:8765", "[::1]:8765", "LOCALHOST"])
def test_local_hosts_allowed(live, host):
    assert request(live, "GET", "/api/settings", headers={"Host": host})[0] == 200


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8765", "127.0.0.1.nip.io", "localhost.evil.example"])
def test_foreign_host_rejected(live, host):
    status, body, _ = request(live, "GET", "/api/settings", headers={"Host": host})
    assert status == 403 and b"pitLoss" not in body


def test_foreign_host_allowed_when_listening_on_network(live, monkeypatch):
    monkeypatch.setattr(server, "ALLOWED_HOSTS", None)  # --host 0.0.0.0
    assert request(live, "GET", "/api/settings", headers={"Host": "192.168.1.20:8765"})[0] == 200


@pytest.mark.parametrize(
    "value,expected",
    [("LocalHost:8765", "localhost"), ("[::1]:8765", "[::1]"), ("[::1]", "[::1]"), ("localhost.", "localhost")],
)
def test_host_name(value, expected):
    assert server.host_name(value) == expected


# ---------------------------------------------------------------- POST


def test_post_json_updates_settings(live):
    status, body, _ = request(live, "POST", "/api/settings", body={"pitLoss": 42})
    assert status == 200 and json.loads(body)["pitLoss"] == 42.0


def test_post_same_origin_allowed(live):
    origin = f"http://localhost:{live['port']}"
    assert request(live, "POST", "/api/settings", body={"pitLoss": 41}, headers={"Origin": origin})[0] == 200


@pytest.mark.parametrize("origin", ["http://evil.example", "null", "http://localhost:1"])
def test_post_cross_origin_rejected(live, origin):
    status, _, _ = request(live, "POST", "/api/settings", body={"pitLoss": 11}, headers={"Origin": origin})
    assert status == 403
    assert live["settings"].get()["pitLoss"] == 60.0


@pytest.mark.parametrize("ctype", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data", None])
def test_post_requires_json_content_type(live, ctype):
    status, _, _ = request(live, "POST", "/api/settings", raw_body=b'{"pitLoss": 11}', headers={"Content-Type": ctype})
    assert status == 415
    assert live["settings"].get()["pitLoss"] == 60.0


def test_post_body_too_large(live):
    big = b'{"x":"' + b"a" * (server.MAX_BODY + 10) + b'"}'
    status, _, _ = request(live, "POST", "/api/settings", raw_body=big, headers={"Content-Type": "application/json"})
    assert status == 413


@pytest.mark.parametrize("length", ["-1", "abc"])
def test_post_bad_content_length_does_not_hang(live, length):
    status, _, _ = request(
        live,
        "POST",
        "/api/settings",
        raw_body=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": length},
    )
    assert status == 400


def test_post_chunked_rejected(live):
    status, _, _ = request(
        live,
        "POST",
        "/api/settings",
        raw_body=b"2\r\n{}\r\n0\r\n\r\n",
        headers={"Content-Type": "application/json", "Transfer-Encoding": "chunked", "Content-Length": None},
    )
    assert status == 411


@pytest.mark.parametrize("raw", [b"not json", b"[1, 2]", b'"x"', b"\xff\xfe"])
def test_post_invalid_json(live, raw):
    status, _, _ = request(live, "POST", "/api/settings", raw_body=raw, headers={"Content-Type": "application/json"})
    assert status == 400


def test_post_unknown_endpoint(live):
    assert request(live, "POST", "/api/nope", body={})[0] == 404


@pytest.mark.parametrize("name", ["../../evil", "..", "..\\..\\evil", "/tmp/x"])
def test_profile_names_stay_in_data_dir(live, name):
    status, body, _ = request(live, "POST", "/api/profiles", body={"action": "create", "name": name})
    assert status == 200
    profiles_dir = os.path.realpath(live["tmp"] / "data" / "profiles")
    for entry in os.listdir(profiles_dir):
        assert os.path.isdir(os.path.join(profiles_dir, entry))
    assert sorted(os.listdir(live["tmp"])) == ["data"]  # rien créé à côté du dossier de données
    assert sorted(os.listdir(live["tmp"] / "data")) == ["profiles", "profiles.json", "tracks"]


def test_profile_delete_cannot_escape(live):
    outside = live["tmp"] / "keep"
    outside.mkdir()
    status, body, _ = request(live, "POST", "/api/profiles", body={"action": "delete", "name": "../../keep"})
    assert json.loads(body)["ok"] is False
    assert outside.exists()


# ---------------------------------------------------------------- SSE


def test_stream_limit(live, monkeypatch):
    monkeypatch.setattr(server, "MAX_STREAMS", 0)
    status, _, _ = request(live, "GET", "/stream")
    assert status == 503
