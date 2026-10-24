"""Konuşma var mı kararı: sabit RMS eşiği ya da gürültü tabanına göre uyarlanan eşik.

Sabit eşik müzik ya da oyun sesinin altında konuşmada işe yaramıyor: arka plan hep
eşiğin üstünde kaldığı için "sessizlik" hiç oluşmuyor, cümleler ancak max_segment_sec
dolunca zorla bölünüyordu. Uyarlanan kapı ses bandındaki enerjiye ve son birkaç
saniyenin taban seviyesine bakıyor; cümle aralarındaki "sadece müzik" anlarını
sessizlik sayabiliyor.
"""
from __future__ import annotations

import collections

import numpy as np

from .config import AppConfig


class RmsGate:
    """Eski davranış: ham RMS kullanıcının eşiğini geçiyor mu."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def is_voice(self, mono: np.ndarray, level: float, in_speech: bool) -> bool:
        return level >= self._config.silence_threshold


class AdaptiveGate:
    """Bant enerjisi + kayan gürültü tabanı + histerezis.

    Başlamak için taban seviyenin START_RATIO katı, sürmek için CONTINUE_RATIO katı
    gerekiyor; kelime aralarındaki kısa düşüşler cümleyi kesmesin. Taban, son
    WINDOW_SEC saniyedeki bant seviyelerinin alt yüzdeliği: arka plan müziği
    sürekli olduğu için oraya oturuyor, konuşma tepeleri onu yukarı çekmiyor.
    Kullanıcının eşiğinin yarısı alt sınır; gerçek sessizlikte hassasiyet eskisi gibi.
    """

    BAND_LOW_HZ = 150.0
    BAND_HIGH_HZ = 4500.0
    WINDOW_SEC = 10.0
    FLOOR_PERCENTILE = 15
    START_RATIO = 1.8
    CONTINUE_RATIO = 1.3

    def __init__(self, config: AppConfig, rate: int, block_sec: float = 1024 / 48000) -> None:
        self._config = config
        self._rate = rate
        self._levels: collections.deque[float] = collections.deque(maxlen=max(10, int(self.WINDOW_SEC / block_sec)))
        self._mask_cache: dict[int, np.ndarray] = {}
        self.floor = 0.0

    def band_level(self, mono: np.ndarray) -> float:
        n = mono.size
        if n < 8:
            return 0.0
        mask = self._mask_cache.get(n)
        if mask is None:
            freqs = np.fft.rfftfreq(n, 1.0 / self._rate)
            mask = self._mask_cache[n] = (freqs >= self.BAND_LOW_HZ) & (freqs <= self.BAND_HIGH_HZ)
        spectrum = np.fft.rfft(mono)
        # Parseval: bant içindeki enerjiyi zaman alanındaki RMS ölçeğine çeviriyor
        return float(np.sqrt(2.0 * np.sum(np.abs(spectrum[mask]) ** 2)) / n)

    def threshold(self, in_speech: bool) -> float:
        minimum = self._config.silence_threshold * 0.5
        ratio = self.CONTINUE_RATIO if in_speech else self.START_RATIO
        return max(minimum, self.floor * ratio)

    def is_voice(self, mono: np.ndarray, level: float, in_speech: bool) -> bool:
        band = self.band_level(mono)
        self._levels.append(band)
        if len(self._levels) >= 10:
            self.floor = float(np.percentile(self._levels, self.FLOOR_PERCENTILE))
        return band >= self.threshold(in_speech)


def create_gate(config: AppConfig, rate: int):
    return AdaptiveGate(config, rate) if config.gate_mode == "auto" else RmsGate(config)
