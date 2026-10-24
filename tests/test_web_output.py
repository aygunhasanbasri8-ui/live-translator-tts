import http.client
import json

import pytest

from live_translator.web_output import WebOutputServer


@pytest.fixture
def server():
    s = WebOutputServer(0, "gizli-anahtar")
    s.start()
    yield s
    s.stop()


def _get(server, path, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", path, headers=headers or {})
    return conn, conn.getresponse()


def test_requires_token_and_local_origin(server):
    assert _get(server, "/overlay")[1].status == 403
    assert _get(server, "/overlay?token=yanlis")[1].status == 403
    assert _get(server, "/events?token=gizli-anahtar", {"Origin": "https://kotu.example"})[1].status == 403
    assert _get(server, "/baska?token=gizli-anahtar")[1].status == 404

    conn, resp = _get(server, "/overlay?token=gizli-anahtar")
    assert resp.status == 200 and b"EventSource" in resp.read()


def _next_event(resp):
    while True:
        line = resp.fp.readline().decode("utf-8").strip()
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])


def test_stream_replays_last_line_then_follows(server):
    server.publish({"kind": "line", "original": "Hello", "translated": "Merhaba"})
    conn, resp = _get(server, "/events?token=gizli-anahtar", {"Origin": f"http://127.0.0.1:{server.port}"})
    assert resp.status == 200
    assert _next_event(resp)["translated"] == "Merhaba"

    server.publish({"kind": "line", "original": "Bye", "translated": "Hoşça kal"})
    assert _next_event(resp)["translated"] == "Hoşça kal"
    conn.close()
