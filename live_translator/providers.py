"""Ücretsiz uçlar için sırayla denenen sağlayıcılar ve geri çekilme.

Google'ın ücretsiz STT/çeviri uçları sık istekte 429 dönüp IP'yi bir süre
engelliyor. Hata alan sağlayıcıya her segmentte yeniden gitmek engeli
uzatıyor, o yüzden bir süre hiç gitmiyor ve varsa sıradakine geçiyoruz."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Sequence


class ServiceUnavailable(RuntimeError):
    """Hiçbir sağlayıcı sonuç veremedi (hepsi beklemede ya da hata verdi)."""


class Cooldown:
    """Art arda her geçici hatada bekleme iki katına çıkar, ilk başarıda sıfırlanır."""

    def __init__(self, base_sec: float = 4.0, max_sec: float = 60.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._base = base_sec
        self._max = max_sec
        self._clock = clock
        self._failures = 0
        self._until = 0.0
        self._lock = threading.Lock()

    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self._until - self._clock())

    def active(self) -> bool:
        return self.remaining() > 0.0

    def failed(self) -> float:
        with self._lock:
            delay = min(self._max, self._base * (2 ** self._failures))
            self._failures += 1
            self._until = self._clock() + delay
            return delay

    def succeeded(self) -> None:
        with self._lock:
            self._failures = 0
            self._until = 0.0


@dataclass
class Provider:
    name: str
    call: Callable[..., str]
    # Kısmi sonuçlar saniyede bir geliyor; kotası dar yedekleri onlarla harcamıyoruz.
    finals_only: bool = False
    cooldown: Cooldown = field(default_factory=Cooldown)


def call_first_available(providers: Sequence[Provider], args: tuple, is_final: bool,
                         is_transient: Callable[[Exception], bool]) -> str:
    """Sağlayıcıları sırayla dener. Geçici hata (ağ, 429) sağlayıcıyı bir süre
    devre dışı bırakır; kalıcı hata yalnızca o isteği bir sonrakine devreder."""
    problems = []
    for provider in providers:
        if provider.finals_only and not is_final:
            continue
        wait = provider.cooldown.remaining()
        if wait > 0:
            problems.append(f"{provider.name} {wait:.0f} sn beklemede")
            continue
        try:
            result = provider.call(*args)
        except Exception as exc:
            if is_transient(exc):
                delay = provider.cooldown.failed()
                problems.append(f"{provider.name}: {exc} ({delay:.0f} sn ara)")
            else:
                problems.append(f"{provider.name}: {exc}")
            continue
        provider.cooldown.succeeded()
        return result
    raise ServiceUnavailable("; ".join(problems) or "uygun sağlayıcı yok")
