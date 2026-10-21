"""Edge-TTS ile dublaj.

Sentez ve oynatma ayrı thread'lerde: biri çalarken sıradaki cümleler önden
hazırlanıyor, cümle aralarında boşluk kalmıyor. edge-tts asenkron olduğu için
sentez thread'i kendi event loop'unu açıyor."""
from __future__ import annotations

import asyncio
import itertools
import os
import queue
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import edge_tts

from .audio_player import IAudioPlayer
from .log import LOGGER
from .queues import drain, put_dropping_oldest


@dataclass
class TTSRequest:
    text: str
    voice: str
    rate: str
    epoch: int = 0      # bkz. TTSService._epoch


class TTSService:
    PREFETCH = 3  # sentezlenip çalınmayı bekleyebilecek cümle sayısı

    def __init__(self, player: IAudioPlayer, speaking_flag: threading.Event,
                 on_error: Optional[Callable[[str], None]] = None) -> None:
        self._player = player
        self._speaking = speaking_flag
        self._on_error = on_error or (lambda _msg: None)

        self._synth_queue: "queue.Queue[Optional[TTSRequest]]" = queue.Queue(maxsize=8)
        self._play_queue: "queue.Queue[Optional[tuple[str, int]]]" = queue.Queue(maxsize=self.PREFETCH)
        # Kuyrukları boşaltmak yetmiyor: o an sentezi biten iş sonucunu yine
        # kuyruğa koyar. clear() nesli artırır, eski nesilden gelen her şey atılır.
        self._epoch = 0
        self._epoch_lock = threading.Lock()

        self._synth_thread = threading.Thread(target=self._synth_worker, name="TTSSynth", daemon=True)
        self._play_thread = threading.Thread(target=self._play_worker, name="TTSPlay", daemon=True)
        self._running = threading.Event()
        self._tmp_dir = os.path.join(tempfile.gettempdir(), "live_translator_tts")
        os.makedirs(self._tmp_dir, exist_ok=True)
        self._seq = itertools.count(1)

    def start(self) -> None:
        if not self._synth_thread.is_alive():
            self._running.set()
            self._synth_thread.start()
            self._play_thread.start()

    def speak(self, text: str, voice: str, rate: str) -> None:
        if not text.strip():
            return
        with self._epoch_lock:
            request = TTSRequest(text=text.strip(), voice=voice, rate=rate, epoch=self._epoch)
        if put_dropping_oldest(self._synth_queue, request):
            LOGGER.info("TTS kuyruğu doldu, en eski cümle atlandı.")

    def clear(self) -> None:
        """Bekleyenleri ve o an sentezlenmekte olanı iptal eder."""
        with self._epoch_lock:
            self._epoch += 1
        for q in (self._synth_queue, self._play_queue):
            for item in drain(q):
                if isinstance(item, tuple):
                    self._discard(item[0])
        self._player.stop()
        self._speaking.clear()

    def shutdown(self) -> None:
        self._running.clear()
        self.clear()
        for q in (self._synth_queue, self._play_queue):
            try:
                q.put_nowait(None)
            except queue.Full:
                pass
        for thread in (self._synth_thread, self._play_thread):
            if thread.is_alive():
                thread.join(timeout=4.0)
        self._player.close()

    def _synth_worker(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while self._running.is_set():
                try:
                    request = self._synth_queue.get(timeout=0.25)
                except queue.Empty:
                    continue
                if request is None:
                    break

                path = os.path.join(self._tmp_dir,
                                    f"tts_{next(self._seq)}_{int(time.time()*1000)}.mp3")
                try:
                    loop.run_until_complete(self._synthesize(request, path))
                    if not os.path.exists(path) or os.path.getsize(path) == 0:
                        raise RuntimeError("Edge-TTS boş ses üretti")
                except Exception as exc:
                    LOGGER.warning("TTS sentez hatası: %s", exc)
                    self._on_error(f"TTS hatası: {exc}")
                    self._discard(path)
                    continue

                # sentez sürerken Durdur'a basılmış olabilir
                if self._is_stale(request.epoch):
                    self._discard(path)
                    continue

                # Oynatma kuyruğu doluysa burada bekliyoruz; sentezin
                # oynatmanın çok önüne geçmesini bu engelliyor.
                while self._running.is_set() and not self._is_stale(request.epoch):
                    try:
                        self._play_queue.put((path, request.epoch), timeout=0.25)
                        break
                    except queue.Full:
                        continue
                else:
                    self._discard(path)
        finally:
            loop.close()

    async def _synthesize(self, request: TTSRequest, path: str) -> None:
        communicate = edge_tts.Communicate(request.text, request.voice, rate=request.rate)
        await communicate.save(path)

    def _play_worker(self) -> None:
        while self._running.is_set():
            try:
                item = self._play_queue.get(timeout=0.25)
            except queue.Empty:
                self._speaking.clear()
                continue
            if item is None:
                break
            path, epoch = item
            if self._is_stale(epoch):
                self._discard(path)
                self._speaking.clear()
                continue
            try:
                self._speaking.set()
                self._player.play_blocking(path)
            except Exception as exc:
                LOGGER.warning("TTS oynatma hatası: %s", exc)
                self._on_error(f"Dublaj oynatılamadı: {exc}")
            finally:
                self._discard(path)
                # Sıradaki cümle hazırsa bayrağı indirmiyoruz; yoksa iki cümle
                # arasında yakalama açılıp kendi dublajımızı duyardı.
                if self._play_queue.empty():
                    self._speaking.clear()
        self._speaking.clear()

    def _is_stale(self, epoch: int) -> bool:
        with self._epoch_lock:
            return epoch != self._epoch

    @staticmethod
    def _discard(path: Optional[str]) -> None:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
