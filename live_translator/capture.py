"""Sistem sesini (mikrofonu değil) WASAPI loopback ile yakalayıp cümlelere böler."""
from __future__ import annotations

import contextlib
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import pyaudiowpatch as pyaudio
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .audio_math import AudioMath
from .config import AppConfig
from .log import LOGGER
from .queues import put_dropping_oldest


@dataclass
class AudioSegment:
    """STT'ye hazır 16 kHz mono PCM16 parça.

    is_final=False olanlar kısmi sonuçtur: konuşma bitmeden o ana kadar
    biriken sesin kopyası, altyazının cümle sonunu beklemeden akması için.
    Aynı utterance_id'li kısmiler birbirinin uzamış hâli, sonuncusu
    is_final=True gelir."""
    pcm16: bytes
    sample_rate: int
    duration: float
    is_final: bool = True
    utterance_id: int = 0
    created_at: float = field(default_factory=time.time)


# (parçalar, süre, kesin mi, utterance_id)
SegmentSink = Callable[[list, float, bool, int], None]


class SpeechSegmenter:
    """Sessizliğe bakarak konuşmayı cümlelere ayırır. Cümle bitince, çok
    uzayınca ya da kısmi sonuç zamanı gelince sink'i çağırır."""

    def __init__(self, config: AppConfig, rate: int, sink: SegmentSink) -> None:
        self._config = config
        self._rate = rate
        self._sink = sink
        self._pre_roll_max = max(1, int(config.pre_roll_sec * rate))
        self._pre_roll: list[np.ndarray] = []
        self._pre_roll_len = 0
        self._buffer: list[np.ndarray] = []
        self._samples = 0
        self._silence_started: Optional[float] = None
        self._utterance_id = 0
        self._last_partial_at = 0.0
        self.in_speech = False

    def feed(self, mono: np.ndarray, level: float, now: float) -> None:
        cfg = self._config
        is_voice = level >= cfg.silence_threshold

        if not self.in_speech:
            self._pre_roll.append(mono)
            self._pre_roll_len += mono.size
            while self._pre_roll_len > self._pre_roll_max and len(self._pre_roll) > 1:
                self._pre_roll_len -= self._pre_roll.pop(0).size
            if is_voice:
                self.in_speech = True
                self._silence_started = None
                self._buffer = list(self._pre_roll)
                self._samples = self._pre_roll_len
                self._pre_roll = []
                self._pre_roll_len = 0
                self._last_partial_at = now
            return

        self._buffer.append(mono)
        self._samples += mono.size
        if is_voice:
            self._silence_started = None
        elif self._silence_started is None:
            self._silence_started = now

        duration = self._duration()
        if self._silence_elapsed(now) or duration >= cfg.max_segment_sec:
            self._end_utterance(duration)
        elif (cfg.streaming_enabled
              and duration >= cfg.partial_min_sec
              and (now - self._last_partial_at) >= cfg.partial_interval_sec):
            # tampon temizlenmiyor, bir sonraki kısmi bunun uzamış hâli olacak
            self._last_partial_at = now
            self._sink(self._buffer, duration, False, self._utterance_id)

    def on_no_data(self, now: float) -> None:
        """Cihaz paket vermiyorsa ortada ses yok demektir; yarım kalan
        cümlenin sessizliğini duvar saatiyle sayıyoruz."""
        if self._silence_started is None:
            self._silence_started = now
        if self._silence_elapsed(now):
            self._end_utterance(self._duration())

    def reset(self) -> None:
        self._buffer = []
        self._samples = 0
        self._pre_roll = []
        self._pre_roll_len = 0
        self._silence_started = None
        self.in_speech = False

    def finish(self) -> None:
        if self._buffer:
            self._sink(self._buffer, self._duration(), True, self._utterance_id)

    def _duration(self) -> float:
        return self._samples / float(self._rate)

    def _silence_elapsed(self, now: float) -> bool:
        return (self._silence_started is not None
                and (now - self._silence_started) >= self._config.silence_duration)

    def _end_utterance(self, duration: float) -> None:
        self._sink(self._buffer, duration, True, self._utterance_id)
        self._utterance_id += 1
        self._buffer = []
        self._samples = 0
        self._silence_started = None
        self.in_speech = False


class LoopbackAudioCapturer(QThread):
    level_changed = pyqtSignal(float)     # 0..1, seviye göstergesi için
    status_message = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    device_resolved = pyqtSignal(str)

    _FRAMES_PER_BUFFER = 1024
    LEVEL_EMIT_HZ = 15.0                  # göstergeye bu kadarı yetiyor, Qt kuyruğu şişmesin
    # Bu kadar süre paket gelmezse cihaz yeniden çözülüyor. Varsayılan çıkış
    # değişince (kulaklık takılınca vb.) eski cihazın loopback'i sessizce
    # susuyor, PortAudio da cihaz listesini ancak yeniden başlatılınca tazeliyor.
    # Uzun duraklamada PortAudio'yu sürekli baştan açmamak için aralık her
    # boş turda ikiye katlanıyor, ses gelince başa dönüyor.
    IDLE_RECHECK_SEC = 3.0
    IDLE_RECHECK_MAX_SEC = 12.0
    MAX_CONSECUTIVE_ERRORS = 20           # ~1 sn; cihaz çıkarılınca akış hep hata veriyor
    RECONNECT_DELAY_SEC = 1.5

    def __init__(self, config: AppConfig, out_queue: "queue.Queue[AudioSegment]",
                 mute_flag: threading.Event, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._queue = out_queue
        self._mute_flag = mute_flag          # dublaj çalarken set edilir
        self._stop_event = threading.Event()
        self._unmute_at = 0.0
        self._last_level_at = 0.0

    def stop(self) -> None:
        self._stop_event.set()

    def _resolve_loopback_device(self, pa: "pyaudio.PyAudio") -> dict:
        """Varsayılan hoparlörün loopback eşleniği; bulunamazsa herhangi biri."""
        try:
            device = pa.get_default_wasapi_loopback()
            if device:
                return device
        except Exception as exc:
            LOGGER.debug("get_default_wasapi_loopback başarısız: %s", exc)

        try:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_out = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
            for device in pa.get_loopback_device_info_generator():
                if default_out["name"] in device["name"]:
                    return device
        except Exception as exc:
            LOGGER.debug("Manuel loopback araması başarısız: %s", exc)

        try:
            for device in pa.get_loopback_device_info_generator():
                return device
        except Exception as exc:
            LOGGER.debug("Loopback listesi alınamadı: %s", exc)

        raise RuntimeError(
            "WASAPI loopback cihazı bulunamadı. Windows Ses ayarlarından bir çıkış "
            "cihazının etkin olduğundan emin olun."
        )

    def _open_stream(self, pa: "pyaudio.PyAudio", device: dict):
        """Bazı sürücüler int16 açmıyor, o zaman float32 deniyoruz."""
        rate = int(device["defaultSampleRate"])
        channels = int(device["maxInputChannels"]) or 2
        last_error: Optional[Exception] = None
        for fmt in (pyaudio.paInt16, pyaudio.paFloat32):
            try:
                stream = pa.open(
                    format=fmt,
                    channels=channels,
                    rate=rate,
                    frames_per_buffer=self._FRAMES_PER_BUFFER,
                    input=True,
                    input_device_index=int(device["index"]),
                )
                return stream, fmt, rate, channels
            except Exception as exc:
                last_error = exc
                LOGGER.debug("Stream açılamadı (format=%s): %s", fmt, exc)
        raise RuntimeError(f"Ses akışı açılamadı: {last_error}")

    def run(self) -> None:
        device_name: Optional[str] = None
        waiting_reported = False
        idle_limit = self.IDLE_RECHECK_SEC
        while not self._stop_event.is_set():
            try:
                pa, device, stream, fmt, rate, channels = self._open_session()
            except Exception as exc:
                if device_name is None:
                    # İlk açılışta cihaz yoksa beklemenin anlamı yok, kullanıcıya söylüyoruz
                    LOGGER.exception("Ses cihazı açılamadı")
                    self.error_occurred.emit(str(exc))
                    break
                LOGGER.warning("Ses cihazı yeniden açılamadı: %s", exc)
                if not waiting_reported:
                    self.status_message.emit("⚠ Ses cihazına ulaşılamıyor, yeniden deneniyor...")
                    waiting_reported = True
                self._stop_event.wait(self.RECONNECT_DELAY_SEC)
                continue

            waiting_reported = False
            name = str(device.get("name", "?"))
            if name != device_name:
                self.device_resolved.emit(name)
                prefix = "Dinleniyor" if device_name is None else "Ses cihazı değişti, dinleniyor"
                self.status_message.emit(f"{prefix}: {name} ({rate} Hz / {channels} kanal)")
                device_name = name

            # Tampon cihazın kendi hızında (ör. 48 kHz) tutulup segment bitince
            # tek seferde 16 kHz'e indiriliyor. Blok blok örneklenseydi her blok
            # sınırında filtre tıklaması oluşur, tanıma kötüleşirdi.
            segmenter = SpeechSegmenter(
                self._config, rate,
                lambda chunks, duration, is_final, uid, r=rate: self._flush(chunks, duration, r, is_final, uid))
            try:
                got_data = self._capture_loop(stream, fmt, channels, segmenter, idle_limit)
                segmenter.finish()
                idle_limit = (self.IDLE_RECHECK_SEC if got_data
                              else min(idle_limit * 2, self.IDLE_RECHECK_MAX_SEC))
            except Exception as exc:
                LOGGER.exception("Yakalama döngüsü hatası")
                self.error_occurred.emit(str(exc))
                break
            finally:
                self._close_session(pa, stream)
        self.status_message.emit("Dinleme durduruldu.")

    def _open_session(self):
        try:
            pa = pyaudio.PyAudio()
        except Exception as exc:
            raise RuntimeError(f"PyAudio başlatılamadı: {exc}") from exc
        try:
            device = self._resolve_loopback_device(pa)
            stream, fmt, rate, channels = self._open_stream(pa, device)
        except Exception:
            with contextlib.suppress(Exception):
                pa.terminate()
            raise
        return pa, device, stream, fmt, rate, channels

    @staticmethod
    def _close_session(pa, stream) -> None:
        with contextlib.suppress(Exception):
            stream.stop_stream()
            stream.close()
        with contextlib.suppress(Exception):
            pa.terminate()

    def _capture_loop(self, stream, fmt: int, channels: int, segmenter: SpeechSegmenter,
                      idle_limit: float) -> bool:
        """Durdurulunca, akış kopunca ya da idle_limit boyunca paket gelmeyince
        döner; son ikisinde run() cihazı baştan çözüp yeniden açıyor. Hiç
        paket okunduysa True."""
        dtype = np.int16 if fmt == pyaudio.paInt16 else np.float32
        scale = 1.0 / 32768.0 if fmt == pyaudio.paInt16 else 1.0
        errors = 0
        got_data = False
        last_data_at = time.monotonic()

        while not self._stop_event.is_set():
            if errors >= self.MAX_CONSECUTIVE_ERRORS:
                LOGGER.warning("Ses akışı art arda hata veriyor, cihaz yeniden açılıyor.")
                return got_data

            # Hiçbir şey çalmıyorken loopback paket üretmiyor ve read() bloklanıyor;
            # önce hazır kare var mı diye bakınca Durdur beklemeden işleniyor.
            try:
                available = stream.get_read_available()
            except Exception as exc:
                errors += 1
                LOGGER.debug("Ses akışı sorgulanamadı: %s", exc)
                time.sleep(0.05)
                continue

            if available <= 0:
                if segmenter.in_speech:
                    segmenter.on_no_data(time.time())
                else:
                    self._emit_level(0.0)
                    if time.monotonic() - last_data_at >= idle_limit:
                        return got_data
                time.sleep(0.02)
                continue

            try:
                raw = stream.read(min(available, self._FRAMES_PER_BUFFER), exception_on_overflow=False)
            except Exception as exc:
                errors += 1
                LOGGER.debug("Ses okuma hatası: %s", exc)
                time.sleep(0.05)
                continue
            errors = 0
            got_data = True
            last_data_at = time.monotonic()

            block = np.frombuffer(raw, dtype=dtype).astype(np.float32) * scale
            mono = AudioMath.to_mono(block, channels)
            if mono.size == 0:
                continue

            level = AudioMath.rms(mono)
            self._emit_level(min(level * 8.0, 1.0))

            now = time.time()
            if self._is_muted(now):
                segmenter.reset()
                continue
            segmenter.feed(mono, level, now)
        return got_data

    def _is_muted(self, now: float) -> bool:
        """Dublaj çalarken ve bittikten kısa süre sonrasına kadar yakalamayı
        sağır tutuyoruz; yoksa kendi dublajımızı yeniden çevirirdik."""
        cfg = self._config
        if not cfg.mute_capture_while_dubbing:
            return False
        if self._mute_flag.is_set():
            self._unmute_at = now + cfg.dubbing_tail_sec
        return now < self._unmute_at

    def _emit_level(self, level: float) -> None:
        now = time.monotonic()
        if (now - self._last_level_at) < (1.0 / self.LEVEL_EMIT_HZ):
            return
        self._last_level_at = now
        self.level_changed.emit(level)

    def _flush(self, chunks: list[np.ndarray], duration: float, source_rate: int,
               is_final: bool = True, utterance_id: int = 0) -> None:
        minimum = self._config.min_segment_sec if is_final else self._config.partial_min_sec
        if duration < minimum or not chunks:
            return
        samples = AudioMath.resample(np.concatenate(chunks), source_rate, self._config.target_sample_rate)
        if samples.size == 0:
            return
        put_dropping_oldest(self._queue, AudioSegment(
            pcm16=AudioMath.float_to_pcm16(samples),
            sample_rate=self._config.target_sample_rate,
            duration=duration,
            is_final=is_final,
            utterance_id=utterance_id,
        ))
