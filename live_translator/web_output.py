"""Altyazıyı OBS'e (Browser Source) ya da bir tarayıcı sekmesine veren yerel sunucu.

Yalnızca 127.0.0.1'de dinliyor ve her istek ayarlardaki rastgele belirteci istiyor:
tarayıcıda açık herhangi bir web sayfası localhost'a istek atabildiği için belirteç
olmadan altyazı metni (izlenen içerik) okunabilirdi. Akış tek yönlü (Server-Sent
Events); dışarıdan gelen hiçbir veri işlenmiyor, ek paket de gerekmiyor.
"""
from __future__ import annotations

import json
import queue
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .log import LOGGER

MAX_CLIENTS = 8
CLIENT_QUEUE = 32


def new_token() -> str:
    return secrets.token_urlsafe(16)


class WebOutputServer:
    def __init__(self, port: int, token: str) -> None:
        self.port = port
        self.token = token
        self._clients: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._last: Optional[dict] = None
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        # localhost değil: bazı sistemlerde ::1'e çözülüp dinlemediğimiz adrese gidiyor
        return f"http://127.0.0.1:{self.port}/overlay?token={self.token}"

    def start(self) -> None:
        handler = _make_handler(self)
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="WebOutput", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        with self._lock:
            for q in self._clients:
                _put_dropping_oldest(q, None)
            self._clients.clear()

    def publish(self, event: dict) -> None:
        with self._lock:
            self._last = event
            for q in self._clients:
                _put_dropping_oldest(q, event)

    def _subscribe(self) -> Optional[queue.Queue]:
        with self._lock:
            if len(self._clients) >= MAX_CLIENTS:
                return None
            q: queue.Queue = queue.Queue(CLIENT_QUEUE)
            # Sonradan bağlanan (OBS yeniden açıldı) ekrandaki son satırı hemen görsün
            if self._last is not None:
                q.put(self._last)
            self._clients.append(q)
            return q

    def _unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._clients:
                self._clients.remove(q)


def _put_dropping_oldest(q: queue.Queue, item) -> None:
    # Yavaş bir istemci (donmuş sekme) diğerlerini ve altyazı hattını bekletmesin
    try:
        q.put_nowait(item)
    except queue.Full:
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        q.put_nowait(item)


def _make_handler(server: WebOutputServer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # noqa: N802 - stdlib adı
            LOGGER.debug("web çıktısı: " + fmt, *args)

        def _allowed(self) -> bool:
            query = parse_qs(urlparse(self.path).query)
            if not secrets.compare_digest(query.get("token", [""])[0], server.token):
                return False
            origin = self.headers.get("Origin")
            # OBS'in tarayıcısı bazen Origin göndermiyor; gönderen başka bir siteyse reddediyoruz
            return origin in (None, "null", f"http://127.0.0.1:{server.port}")

        def do_GET(self):  # noqa: N802 - stdlib adı
            path = urlparse(self.path).path
            if path not in ("/overlay", "/events"):
                self.send_error(404)
                return
            if not self._allowed():
                self.send_error(403)
                return
            if path == "/overlay":
                body = OVERLAY_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            self._stream()

        def _stream(self):
            q = server._subscribe()
            if q is None:
                self.send_error(503, "too many clients")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    try:
                        event = q.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        continue
                    if event is None:
                        return
                    data = json.dumps(event, ensure_ascii=False)
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                server._unsubscribe(q)

    return Handler


# Tek dosya, dış kaynak yok. Görünüm URL parametreleriyle: ?size=42&color=%23fff&bg=0.6&show=both&hold=6
OVERLAY_HTML = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><title>Live Translator</title>
<style>
  html, body { margin: 0; background: transparent; overflow: hidden; }
  #box { position: fixed; left: 0; right: 0; bottom: 4%; text-align: center; transition: opacity .4s; }
  .line { display: inline-block; max-width: 92%; padding: .15em .5em; border-radius: .25em;
          font-family: "Segoe UI", system-ui, sans-serif; font-weight: 600; line-height: 1.25; }
  #original { opacity: .8; font-weight: 400; margin-bottom: .2em; }
</style></head>
<body><div id="box">
  <div><span id="original" class="line"></span></div>
  <div><span id="translated" class="line"></span></div>
</div>
<script>
const q = new URLSearchParams(location.search);
const size = Number(q.get("size") || 40), hold = Number(q.get("hold") || 6) * 1000;
const show = q.get("show") || "translated", bg = Number(q.get("bg") ?? 0.55);
const box = document.getElementById("box");
const tr = document.getElementById("translated"), orig = document.getElementById("original");
for (const el of [tr, orig]) {
  el.style.color = q.get("color") || "#fff";
  el.style.background = `rgba(0,0,0,${bg})`;
  el.dir = "auto";
}
tr.style.fontSize = size + "px";
orig.style.fontSize = Math.round(size * 0.65) + "px";
let hideTimer = null;
function render(ev) {
  if (ev.kind === "clear") { box.style.opacity = 0; return; }
  tr.textContent = ev.translated || ev.original || "";
  orig.textContent = show === "both" && ev.translated ? ev.original : "";
  orig.parentElement.hidden = !orig.textContent;
  tr.parentElement.hidden = !tr.textContent;
  box.style.opacity = 1;
  clearTimeout(hideTimer);
  hideTimer = setTimeout(() => { box.style.opacity = 0; }, hold);
}
// EventSource koparsa kendisi yeniden bağlanıyor; sunucu bağlanınca son satırı gönderiyor
const es = new EventSource("/events?token=" + encodeURIComponent(q.get("token") || ""));
es.onmessage = (e) => render(JSON.parse(e.data));
</script></body></html>
"""
