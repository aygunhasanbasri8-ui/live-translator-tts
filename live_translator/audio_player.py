"""Dublaj sesini çalan oynatıcılar. pygame varsa o, yoksa Windows MCI."""
from __future__ import annotations

import ctypes
import itertools
import sys
import threading
import time
from typing import Optional, Protocol

from .log import LOGGER

try:
    import pygame  # type: ignore
except Exception:  # pragma: no cover - opsiyonel
    pygame = None


class IAudioPlayer(Protocol):
    def play_blocking(self, path: str) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


class PygameAudioPlayer:
    def __init__(self) -> None:
        pygame.mixer.init()
        self._lock = threading.Lock()

    def play_blocking(self, path: str) -> None:
        with self._lock:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.02)
        with self._lock:
            pygame.mixer.music.unload()

    def stop(self) -> None:
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    def close(self) -> None:
        try:
            pygame.mixer.quit()
        except Exception:
            pass


class MciAudioPlayer:
    """winmm.dll üzerinden mp3 çalar. Ek bağımlılık istemediği için pygame
    wheel'i olmayan Python sürümlerinde (3.13+) yedek olarak duruyor."""

    def __init__(self) -> None:
        self._winmm = ctypes.windll.winmm
        self._alias_seq = itertools.count(1)
        self._current_alias: Optional[str] = None
        self._lock = threading.Lock()

    def _mci(self, command: str) -> int:
        buf = ctypes.create_unicode_buffer(256)
        return self._winmm.mciSendStringW(command, buf, 254, None)

    def play_blocking(self, path: str) -> None:
        alias = f"ltts{next(self._alias_seq)}"
        # mp3'ü 'mpegvideo' sürücüsü açıyor; o olmazsa türü Windows'a bırakıyoruz
        if self._mci(f'open "{path}" type mpegvideo alias {alias}') != 0:
            if self._mci(f'open "{path}" alias {alias}') != 0:
                raise RuntimeError("MCI ses dosyasını açamadı")
        with self._lock:
            self._current_alias = alias
        try:
            self._mci(f"play {alias} wait")
        finally:
            with self._lock:
                self._current_alias = None
            self._mci(f"close {alias}")

    def stop(self) -> None:
        with self._lock:
            alias = self._current_alias
        if alias:
            try:
                self._mci(f"stop {alias}")
            except Exception:
                pass

    def close(self) -> None:
        self.stop()


class NullAudioPlayer:
    def play_blocking(self, path: str) -> None:
        LOGGER.warning("Kullanılabilir ses oynatıcı yok, dublaj atlandı.")

    def stop(self) -> None: ...
    def close(self) -> None: ...


def create_audio_player() -> IAudioPlayer:
    if pygame is not None:
        try:
            player = PygameAudioPlayer()
            LOGGER.info("Ses oynatıcı: pygame.mixer")
            return player
        except Exception as exc:
            LOGGER.warning("pygame.mixer başlatılamadı (%s), MCI'ya geçiliyor.", exc)
    if sys.platform == "win32":
        try:
            player = MciAudioPlayer()
            LOGGER.info("Ses oynatıcı: Windows MCI (winmm)")
            return player
        except Exception as exc:
            LOGGER.warning("MCI başlatılamadı: %s", exc)
    LOGGER.error("Ses oynatıcı bulunamadı; dublaj devre dışı.")
    return NullAudioPlayer()
