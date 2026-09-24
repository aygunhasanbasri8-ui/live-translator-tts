from __future__ import annotations

import os
import sys
import time
import queue
import ctypes
import asyncio
import logging
import tempfile
import threading
import itertools
import collections
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

_MISSING: list[str] = []

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None
    _MISSING.append("numpy")

try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    from PyQt6.QtCore import Qt, QObject, QThread, pyqtSignal, pyqtSlot, QTimer
except ImportError:  # pragma: no cover
    _MISSING.append("PyQt6")
    QtCore = QtGui = QtWidgets = None  # type: ignore

try:
    import pyaudiowpatch as pyaudio
except ImportError:  # pragma: no cover
    pyaudio = None
    _MISSING.append("PyAudioWPatch")

try:
    import speech_recognition as sr
except ImportError:  # pragma: no cover
    sr = None
    _MISSING.append("SpeechRecognition")

try:
    from deep_translator import GoogleTranslator
except ImportError:  # pragma: no cover
    GoogleTranslator = None
    _MISSING.append("deep-translator")

try:
    import edge_tts
except ImportError:  # pragma: no cover
    edge_tts = None
    _MISSING.append("edge-tts")

if _MISSING:
    msg = (
        "Eksik kütüphaneler tespit edildi: %s\n\n"
        "Kurmak için:\n    pip install %s\n" % (", ".join(_MISSING), " ".join(_MISSING))
    )
    print(msg, file=sys.stderr)
    sys.exit(1)

try:
    import pygame  # type: ignore
except Exception:  # pragma: no cover - opsiyonel
    pygame = None

try:
    import keyboard as kb_lib  # type: ignore
except Exception:  # pragma: no cover - opsiyonel
    kb_lib = None

try:
    from pynput import keyboard as pynput_keyboard  # type: ignore
except Exception:  # pragma: no cover - opsiyonel
    pynput_keyboard = None


LOGGER = logging.getLogger("live_translator")


def _configure_logging() -> None:
    LOGGER.setLevel(logging.INFO)
    if LOGGER.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    LOGGER.addHandler(handler)


@dataclass
class LanguageProfile:
    """Bir dilin STT / çeviri / TTS karşılıklarını tek yerde toplar."""
    label: str          # Arayüzde görünen isim
    stt_code: str       # Google Web Speech dil kodu   (en-US)
    translate_code: str # deep-translator dil kodu     (en)
    voices: tuple[str, ...]  # edge-tts ses isimleri


LANGUAGES: dict[str, LanguageProfile] = {
    "tr": LanguageProfile("Türkçe",        "tr-TR", "tr", ("tr-TR-EmelNeural", "tr-TR-AhmetNeural")),
    "en": LanguageProfile("İngilizce",     "en-US", "en", ("en-US-AriaNeural", "en-US-GuyNeural", "en-GB-SoniaNeural")),
    "de": LanguageProfile("Almanca",       "de-DE", "de", ("de-DE-KatjaNeural", "de-DE-ConradNeural")),
    "fr": LanguageProfile("Fransızca",     "fr-FR", "fr", ("fr-FR-DeniseNeural", "fr-FR-HenriNeural")),
    "es": LanguageProfile("İspanyolca",    "es-ES", "es", ("es-ES-ElviraNeural", "es-ES-AlvaroNeural")),
    "it": LanguageProfile("İtalyanca",     "it-IT", "it", ("it-IT-ElsaNeural", "it-IT-DiegoNeural")),
    "pt": LanguageProfile("Portekizce",    "pt-BR", "pt", ("pt-BR-FranciscaNeural", "pt-BR-AntonioNeural")),
    "ru": LanguageProfile("Rusça",         "ru-RU", "ru", ("ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural")),
    "ar": LanguageProfile("Arapça",        "ar-SA", "ar", ("ar-SA-ZariyahNeural", "ar-SA-HamedNeural")),
    "ja": LanguageProfile("Japonca",       "ja-JP", "ja", ("ja-JP-NanamiNeural", "ja-JP-KeitaNeural")),
    "ko": LanguageProfile("Korece",        "ko-KR", "ko", ("ko-KR-SunHiNeural", "ko-KR-InJoonNeural")),
    "zh-CN": LanguageProfile("Çince (Basit.)", "zh-CN", "zh-CN", ("zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural")),
    "hi": LanguageProfile("Hintçe",        "hi-IN", "hi", ("hi-IN-SwaraNeural", "hi-IN-MadhurNeural")),
    "nl": LanguageProfile("Felemenkçe",    "nl-NL", "nl", ("nl-NL-ColetteNeural", "nl-NL-MaartenNeural")),
    "pl": LanguageProfile("Lehçe",         "pl-PL", "pl", ("pl-PL-ZofiaNeural", "pl-PL-MarekNeural")),
    "sv": LanguageProfile("İsveççe",       "sv-SE", "sv", ("sv-SE-SofieNeural", "sv-SE-MattiasNeural")),
    "uk": LanguageProfile("Ukraynaca",     "uk-UA", "uk", ("uk-UA-PolinaNeural", "uk-UA-OstapNeural")),
    "fa": LanguageProfile("Farsça",        "fa-IR", "fa", ("fa-IR-DilaraNeural", "fa-IR-FaridNeural")),
    "az": LanguageProfile("Azerice",       "az-AZ", "az", ("az-AZ-BanuNeural", "az-AZ-BabekNeural")),
}


@dataclass
class AppConfig:
    """Uygulamanın çalışma anındaki tüm ayarları. Thread'ler bunu okur."""
    source_lang: str = "en"
    target_lang: str = "tr"
    dubbing_enabled: bool = False
    voice: str = "tr-TR-EmelNeural"
    tts_rate: str = "+15%"

    target_sample_rate: int = 16000      # STT'ye giden örnekleme hızı
    silence_threshold: float = 0.010     # RMS eşiği (0.0 - 1.0)
    silence_duration: float = 0.35       # Cümle bitti sayılacak sessizlik (sn)
    min_segment_sec: float = 0.40        # Bundan kısa segmentler atılır
    max_segment_sec: float = 6.0         # Bu süreye ulaşınca zorla gönderilir
    pre_roll_sec: float = 0.30           # Konuşma başlangıcından önce saklanacak tampon

    streaming_enabled: bool = True       # Konuşma sürerken kısmi altyazı akıt
    partial_interval_sec: float = 0.9    # Kısmi sonuç gönderme sıklığı
    partial_min_sec: float = 0.7         # Bundan kısa konuşmada kısmi gönderme

    subtitle_font_size: int = 30
    subtitle_width_pct: int = 80         # Ekran genişliğinin yüzdesi (kenarlara doğru)
    subtitle_bottom_margin: int = 90     # Ekranın altından yükseklik (aşağı/yukarı)
    subtitle_hold_sec: float = 6.0
    show_original: bool = True

    mute_capture_while_dubbing: bool = True
    dubbing_tail_sec: float = 0.45       # Dublaj bittikten sonra sağırlık süresi

    def profile(self, code: str) -> LanguageProfile:
        return LANGUAGES.get(code, LANGUAGES["en"])


class IAudioPlayer(Protocol):
    """Dublaj sesini çalan bileşenin sözleşmesi."""

    def play_blocking(self, path: str) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


class PygameAudioPlayer:
    """pygame.mixer tabanlı oynatıcı (varsa tercih edilir)."""

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
    """
    Windows'un yerleşik MCI (winmm.dll) arayüzü ile mp3 oynatıcı.
    Hiçbir ek bağımlılık gerektirmez; pygame wheel'i olmayan Python
    sürümlerinde (ör. 3.13+) yedek olarak kullanılır.
    """

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
        # 'mpegvideo' sürücüsü Windows'ta mp3 dosyalarını da açar.
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
    """Hiçbir oynatıcı bulunamazsa sessizce devre dışı kalır."""

    def play_blocking(self, path: str) -> None:
        LOGGER.warning("Kullanılabilir ses oynatıcı yok, dublaj atlandı.")

    def stop(self) -> None: ...
    def close(self) -> None: ...


def create_audio_player() -> IAudioPlayer:
    """Ortama göre en uygun oynatıcıyı seçen basit factory."""
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


class AudioMath:
    """Kanal indirgeme / yeniden örnekleme / RMS gibi saf ses matematiği."""

    @staticmethod
    def to_mono(samples: "np.ndarray", channels: int) -> "np.ndarray":
        if channels <= 1:
            return samples
        usable = (len(samples) // channels) * channels
        if usable == 0:
            return samples[:0]
        return samples[:usable].reshape(-1, channels).mean(axis=1)

    @staticmethod
    def resample(samples: "np.ndarray", src_rate: int, dst_rate: int) -> "np.ndarray":
        if src_rate == dst_rate or samples.size == 0:
            return samples
        if src_rate > dst_rate:
            # Basit anti-aliasing: kutu filtresi (moving average)
            factor = int(src_rate // dst_rate)
            if factor > 1:
                kernel = np.ones(factor, dtype=np.float32) / factor
                samples = np.convolve(samples, kernel, mode="same").astype(np.float32)
        new_len = int(round(samples.size * dst_rate / src_rate))
        if new_len <= 1:
            return samples[:0]
        src_idx = np.linspace(0.0, samples.size - 1.0, new_len, dtype=np.float64)
        return np.interp(src_idx, np.arange(samples.size, dtype=np.float64), samples).astype(np.float32)

    @staticmethod
    def rms(samples: "np.ndarray") -> float:
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))

    @staticmethod
    def float_to_pcm16(samples: "np.ndarray") -> bytes:
        clipped = np.clip(samples, -1.0, 1.0)
        return (clipped * 32767.0).astype("<i2").tobytes()


@dataclass
class AudioSegment:
    """
    STT'ye gönderilmeye hazır, 16 kHz mono PCM16 ses parçası.

    is_final=False olanlar KISMİ (partial) sonuçlardır: konuşma daha bitmeden,
    o ana kadar birikmiş sesin anlık görüntüsüdür. Altyazının cümle bitene
    kadar beklemeden akmasını sağlar. Aynı utterance_id'yi paylaşan kısmi
    parçalar birbirinin uzayan hâlidir; sonuncusu is_final=True gelir.
    """
    pcm16: bytes
    sample_rate: int
    duration: float
    is_final: bool = True
    utterance_id: int = 0
    created_at: float = field(default_factory=time.time)


class LoopbackAudioCapturer(QThread):
    """
    Bilgisayarın kendi sesini (System Audio / WASAPI Loopback) sürekli yakalar.
    Sessizlik algılamasıyla (VAD) cümleleri bölüp kuyruğa (queue) atar.
    Mikrofon KULLANMAZ.
    """

    level_changed = pyqtSignal(float)     # 0..1 anlık ses seviyesi (VU meter)
    status_message = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    device_resolved = pyqtSignal(str)

    _FRAMES_PER_BUFFER = 1024

    def __init__(self, config: AppConfig, out_queue: "queue.Queue[AudioSegment]",
                 mute_flag: threading.Event, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._queue = out_queue
        self._mute_flag = mute_flag          # TTS çalarken set edilir (geri besleme koruması)
        self._stop_event = threading.Event()
        self._pa: Optional["pyaudio.PyAudio"] = None
        self._unmute_at = 0.0
        self._last_level_at = 0.0

    LEVEL_EMIT_HZ = 15.0

    def _emit_level(self, level: float) -> None:
        now = time.monotonic()
        if (now - self._last_level_at) < (1.0 / self.LEVEL_EMIT_HZ):
            return
        self._last_level_at = now
        self.level_changed.emit(level)

    def stop(self) -> None:
        self._stop_event.set()

    def _resolve_loopback_device(self, pa: "pyaudio.PyAudio") -> dict:
        """Varsayılan hoparlörün loopback eşleniğini bulur."""
        # 1) PyAudioWPatch'in hazır yardımcısı
        try:
            device = pa.get_default_wasapi_loopback()
            if device:
                return device
        except Exception as exc:
            LOGGER.debug("get_default_wasapi_loopback başarısız: %s", exc)

        # 2) Manuel arama: varsayılan çıkış cihazının adıyla eşleşen loopback
        try:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_out = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
            for device in pa.get_loopback_device_info_generator():
                if default_out["name"] in device["name"]:
                    return device
        except Exception as exc:
            LOGGER.debug("Manuel loopback araması başarısız: %s", exc)

        # 3) Son çare: herhangi bir loopback cihazı
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
        """Önce int16, olmazsa float32 ile stream açmayı dener."""
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
            except Exception as exc:  # format desteklenmiyorsa diğerini dene
                last_error = exc
                LOGGER.debug("Stream açılamadı (format=%s): %s", fmt, exc)
        raise RuntimeError(f"Ses akışı açılamadı: {last_error}")

    def run(self) -> None:  # QThread entry point
        cfg = self._config
        try:
            self._pa = pyaudio.PyAudio()
        except Exception as exc:
            self.error_occurred.emit(f"PyAudio başlatılamadı: {exc}")
            return

        stream = None
        try:
            device = self._resolve_loopback_device(self._pa)
            self.device_resolved.emit(str(device.get("name", "?")))
            stream, fmt, rate, channels = self._open_stream(self._pa, device)
            self.status_message.emit(f"Dinleniyor: {device['name']} ({rate} Hz / {channels} kanal)")

            dtype = np.int16 if fmt == pyaudio.paInt16 else np.float32
            scale = 1.0 / 32768.0 if fmt == pyaudio.paInt16 else 1.0

            # NOT: Tampon NATIVE örnekleme hızında (ör. 48 kHz) tutulur.
            # Yeniden örnekleme yalnızca segment tamamlandığında, tek parça
            # üzerinde yapılır; blok blok yapılsaydı her blok sınırında filtre
            # artefaktı (tıklama) oluşur ve tanıma doğruluğu düşerdi.
            speech_buffer: list["np.ndarray"] = []
            pre_roll: list["np.ndarray"] = []
            pre_roll_max = max(1, int(cfg.pre_roll_sec * rate))
            pre_roll_len = 0
            in_speech = False
            silence_started: Optional[float] = None
            speech_samples = 0
            utterance_id = 0
            last_partial_at = 0.0

            while not self._stop_event.is_set():
                try:
                    available = stream.get_read_available()
                except Exception as exc:
                    LOGGER.warning("Ses akışı sorgulanamadı: %s", exc)
                    time.sleep(0.05)
                    continue

                if available <= 0:
                    # Veri akmıyor = mutlak sessizlik. Elde yarım cümle varsa,
                    # duvar saati üzerinden sessizlik sayacını işlet.
                    now = time.time()
                    if in_speech:
                        if silence_started is None:
                            silence_started = now
                        if (now - silence_started) >= cfg.silence_duration:
                            self._flush(speech_buffer, speech_samples / float(rate), rate,
                                        is_final=True, utterance_id=utterance_id)
                            utterance_id += 1
                            speech_buffer = []
                            speech_samples = 0
                            in_speech = False
                            silence_started = None
                    else:
                        self._emit_level(0.0)
                    time.sleep(0.02)
                    continue

                try:
                    frames = min(available, self._FRAMES_PER_BUFFER)
                    raw = stream.read(frames, exception_on_overflow=False)
                except Exception as exc:
                    LOGGER.warning("Ses okuma hatası: %s", exc)
                    time.sleep(0.05)
                    continue

                block = np.frombuffer(raw, dtype=dtype).astype(np.float32) * scale
                mono = AudioMath.to_mono(block, channels)
                if mono.size == 0:
                    continue

                level = AudioMath.rms(mono)
                self._emit_level(min(level * 8.0, 1.0))

                now = time.time()
                if cfg.mute_capture_while_dubbing:
                    if self._mute_flag.is_set():
                        self._unmute_at = now + cfg.dubbing_tail_sec
                    if now < self._unmute_at:
                        speech_buffer.clear()
                        pre_roll.clear()
                        pre_roll_len = 0
                        in_speech = False
                        silence_started = None
                        speech_samples = 0
                        continue

                is_voice = level >= cfg.silence_threshold

                if not in_speech:
                    # Konuşma öncesi kısa tamponu sakla (kelime başlarını kesmemek için)
                    pre_roll.append(mono)
                    pre_roll_len += mono.size
                    while pre_roll_len > pre_roll_max and len(pre_roll) > 1:
                        pre_roll_len -= pre_roll.pop(0).size
                    if is_voice:
                        in_speech = True
                        silence_started = None
                        speech_buffer = list(pre_roll)
                        speech_samples = pre_roll_len
                        pre_roll = []
                        pre_roll_len = 0
                        last_partial_at = now
                    continue

                speech_buffer.append(mono)
                speech_samples += mono.size

                if is_voice:
                    silence_started = None
                else:
                    if silence_started is None:
                        silence_started = now

                duration = speech_samples / float(rate)
                sentence_ended = silence_started is not None and (now - silence_started) >= cfg.silence_duration
                too_long = duration >= cfg.max_segment_sec

                if sentence_ended or too_long:
                    self._flush(speech_buffer, duration, rate,
                                is_final=True, utterance_id=utterance_id)
                    utterance_id += 1
                    speech_buffer = []
                    speech_samples = 0
                    in_speech = False
                    silence_started = None
                elif (cfg.streaming_enabled
                      and duration >= cfg.partial_min_sec
                      and (now - last_partial_at) >= cfg.partial_interval_sec):
                    # AKICILIK: cümle bitmeden, o ana kadarki sesin anlık
                    # görüntüsünü gönder. Tampon TEMİZLENMEZ; bir sonraki
                    # kısmi sonuç bunun uzamış hâli olur.
                    last_partial_at = now
                    self._flush(speech_buffer, duration, rate,
                                is_final=False, utterance_id=utterance_id)

            # Döngü bitti: elde kalan varsa gönder
            if speech_buffer:
                self._flush(speech_buffer, speech_samples / float(rate), rate,
                            is_final=True, utterance_id=utterance_id)

        except Exception as exc:
            LOGGER.exception("Yakalama döngüsü hatası")
            self.error_occurred.emit(str(exc))
        finally:
            try:
                if stream is not None:
                    stream.stop_stream()
                    stream.close()
            except Exception:
                pass
            try:
                if self._pa is not None:
                    self._pa.terminate()
            except Exception:
                pass
            self._pa = None
            self.status_message.emit("Dinleme durduruldu.")

    def _flush(self, chunks: list["np.ndarray"], duration: float, source_rate: int,
               is_final: bool = True, utterance_id: int = 0) -> None:
        """
        Biriken sesi (native hızda) tek parçaya birleştirir, STT için 16 kHz'e
        indirir ve kuyruğa koyar. Çok kısa segmentler elenir.
        Kısmi (is_final=False) çağrılarda tampon TEMİZLENMEZ - kopyası gönderilir.
        """
        minimum = self._config.min_segment_sec if is_final else self._config.partial_min_sec
        if duration < minimum or not chunks:
            return
        samples = np.concatenate(chunks)
        samples = AudioMath.resample(samples, source_rate, self._config.target_sample_rate)
        if samples.size == 0:
            return
        segment = AudioSegment(
            pcm16=AudioMath.float_to_pcm16(samples),
            sample_rate=self._config.target_sample_rate,
            duration=duration,
            is_final=is_final,
            utterance_id=utterance_id,
        )
        try:
            self._queue.put_nowait(segment)
        except queue.Full:
            # Kuyruk doluysa en eskiyi düşür, yenisini koy (canlılık > bütünlük)
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(segment)
            except queue.Empty:
                pass


class SpeechToTextService:
    """SpeechRecognition (Google Web Speech API) sarmalayıcısı."""

    def __init__(self) -> None:
        self._recognizer = sr.Recognizer()
        self._recognizer.operation_timeout = 12  # ağ takılırsa sonsuz bekleme olmasın
        # SpeechRecognition sürümleri arasında isim değişebiliyor; bir kez çöz.
        self._call = getattr(self._recognizer, "recognize_google", None) \
            or getattr(self._recognizer, "recognize_legacy", None)
        if self._call is None:  # pragma: no cover
            raise RuntimeError("SpeechRecognition sürümünde Google tanıyıcı bulunamadı.")

    def transcribe(self, segment: AudioSegment, language: str) -> str:
        """Boş string = anlaşılamadı. Ağ/servis hataları yukarı fırlatılır."""
        audio = sr.AudioData(segment.pcm16, segment.sample_rate, 2)
        try:
            text = self._call(audio, language=language)
        except sr.UnknownValueError:
            return ""
        return (text or "").strip()


class TranslatorService:
    """deep-translator (GoogleTranslator) sarmalayıcısı + basit LRU cache."""

    _CACHE_LIMIT = 256

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, str], str] = {}
        self._lock = threading.Lock()

    def translate(self, text: str, source: str, target: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        if source == target:
            return text

        key = (text, source, target)
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached

        translated = GoogleTranslator(source=source, target=target).translate(text)
        translated = (translated or "").strip() or text

        with self._lock:
            if len(self._cache) >= self._CACHE_LIMIT:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = translated
        return translated


@dataclass
class TTSRequest:
    text: str
    voice: str
    rate: str
    epoch: int = 0      # bkz. TTSService._epoch


class TTSService:
    """Edge-TTS sentezini ve ses oynatmayı ayrı thread'lerde yönetir."""

    PREFETCH = 3

    def __init__(self, player: IAudioPlayer, speaking_flag: threading.Event,
                 on_error: Optional[Callable[[str], None]] = None) -> None:
        self._player = player
        self._speaking = speaking_flag
        self._on_error = on_error or (lambda _msg: None)

        self._synth_queue: "queue.Queue[Optional[TTSRequest]]" = queue.Queue(maxsize=8)
        self._play_queue: "queue.Queue[Optional[tuple[str, int]]]" = queue.Queue(maxsize=self.PREFETCH)
        self._epoch = 0
        self._epoch_lock = threading.Lock()

        self._synth_thread = threading.Thread(target=self._synth_worker, name="TTSSynth", daemon=True)
        self._play_thread = threading.Thread(target=self._play_worker, name="TTSPlay", daemon=True)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
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
        """Kuyruk doluysa en eski isteği düşürür (canlı yayında gecikme birikmesin)."""
        if not text.strip():
            return
        with self._epoch_lock:
            request = TTSRequest(text=text.strip(), voice=voice, rate=rate, epoch=self._epoch)
        try:
            self._synth_queue.put_nowait(request)
        except queue.Full:
            try:
                self._synth_queue.get_nowait()
                self._synth_queue.put_nowait(request)
                LOGGER.info("TTS kuyruğu doldu, en eski cümle atlandı.")
            except queue.Empty:
                pass

    def clear(self) -> None:
        """Sırayı iptal et. Uçuşta olan sentez de geçersiz kılınır."""
        with self._epoch_lock:
            self._epoch += 1
        for q in (self._synth_queue, self._play_queue):
            while True:
                try:
                    item = q.get_nowait()
                except queue.Empty:
                    break
                if isinstance(item, tuple):
                    self._discard(item[0])
        self._player.stop()
        self._speaking.clear()

    def shutdown(self) -> None:
        self._running.clear()
        self.clear()
        for q in (self._synth_queue, self._play_queue):
            try:
                q.put_nowait(None)  # sentinel
            except queue.Full:
                pass
        for thread in (self._synth_thread, self._play_thread):
            if thread.is_alive():
                thread.join(timeout=4.0)
        self._player.close()

    def _synth_worker(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
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
                    self._loop.run_until_complete(self._synthesize(request, path))
                    if not os.path.exists(path) or os.path.getsize(path) == 0:
                        raise RuntimeError("Edge-TTS boş ses üretti")
                except Exception as exc:
                    LOGGER.warning("TTS sentez hatası: %s", exc)
                    self._on_error(f"TTS hatası: {exc}")
                    self._discard(path)
                    continue

                # Sentez sürerken Durdur'a basılmış olabilir: sonucu çalma.
                if self._is_stale(request.epoch):
                    self._discard(path)
                    continue

                # Oynatma kuyruğu doluysa burada bekleriz: bu, sentezin
                # oynatmadan fazla ilerlemesini engelleyen doğal geri basınçtır.
                while self._running.is_set() and not self._is_stale(request.epoch):
                    try:
                        self._play_queue.put((path, request.epoch), timeout=0.25)
                        break
                    except queue.Full:
                        continue
                else:
                    self._discard(path)
        finally:
            try:
                if self._loop is not None:
                    self._loop.close()
            except Exception:
                pass
            self._loop = None

    async def _synthesize(self, request: TTSRequest, path: str) -> None:
        communicate = edge_tts.Communicate(request.text, request.voice, rate=request.rate)
        await communicate.save(path)

    def _play_worker(self) -> None:
        while self._running.is_set():
            try:
                item = self._play_queue.get(timeout=0.25)
            except queue.Empty:
                # Sıra boşaldı -> artık konuşmuyoruz, mikrofon sağırlığını kaldır
                self._speaking.clear()
                continue
            if item is None:
                break
            path, epoch = item
            if self._is_stale(epoch):        # Durdur'a basılmış: çalma
                self._discard(path)
                self._speaking.clear()
                continue
            try:
                self._speaking.set()      # yakalayıcıya "şu an ben konuşuyorum" de
                self._player.play_blocking(path)
            except Exception as exc:
                LOGGER.warning("TTS oynatma hatası: %s", exc)
                self._on_error(f"Dublaj oynatılamadı: {exc}")
            finally:
                self._discard(path)
                # Sıradaki cümle HAZIRSA bayrağı indirme; böylece cümleler
                # arasında yakalama açılıp kendi dublajımızı duymaz.
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


class PipelineWorker(QThread):
    """Ses segmentlerini arka planda tanır, çevirir ve sırayla yayınlar."""

    subtitle_ready = pyqtSignal(str, str)   # (orijinal, çeviri)
    log_message = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    MAX_WORKERS = 3
    MAX_BACKLOG = 6
    RESULT_TIMEOUT_SEC = 25.0
    DUPLICATE_WINDOW_SEC = 4.0

    def __init__(self, config: AppConfig, in_queue: "queue.Queue[AudioSegment]",
                 stt: SpeechToTextService, translator: TranslatorService,
                 tts: TTSService, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._queue = in_queue
        self._stt = stt
        self._translator = translator
        self._tts = tts
        self._stop_event = threading.Event()
        self._last_text = ""
        self._last_text_at = 0.0
        self._last_partial = ""
        self._pending: "collections.deque[Future]" = collections.deque()
        self._cv = threading.Condition()

    def stop(self) -> None:
        self._stop_event.set()
        with self._cv:
            self._cv.notify_all()

    def run(self) -> None:
        self._stop_event.clear()
        executor = ThreadPoolExecutor(max_workers=self.MAX_WORKERS, thread_name_prefix="stt")
        emitter = threading.Thread(target=self._emit_in_order, name="SubtitleEmitter", daemon=True)
        emitter.start()
        try:
            while not self._stop_event.is_set():
                try:
                    segment = self._queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                # Havuz doluysa segmenti ATMA - geri basınç uygula ve bekle.
                # (Atmak, kullanıcının gördüğü "altyazı bazen gelmiyor"un sebebiydi.)
                with self._cv:
                    while (len(self._pending) >= self.MAX_BACKLOG
                           and not self._stop_event.is_set()):
                        self._cv.wait(0.1)
                if self._stop_event.is_set():
                    break

                future = executor.submit(self._process, segment)
                with self._cv:
                    self._pending.append(future)
                    self.busy_changed.emit(True)
                    self._cv.notify()
        except Exception as exc:  # pipeline asla ölmemeli
            LOGGER.exception("Pipeline üretici hatası")
            self.error_occurred.emit(str(exc))
        finally:
            self._stop_event.set()
            with self._cv:
                self._cv.notify_all()
            emitter.join(timeout=8.0)
            executor.shutdown(wait=False, cancel_futures=True)
            self.busy_changed.emit(False)

    def _process(self, segment: AudioSegment) -> Optional[tuple[str, str, bool]]:
        cfg = self._config
        src_profile = cfg.profile(cfg.source_lang)
        tgt_profile = cfg.profile(cfg.target_lang)

        try:
            original = self._stt.transcribe(segment, src_profile.stt_code)
        except sr.RequestError as exc:
            if segment.is_final:
                self.error_occurred.emit(f"STT servisine ulaşılamadı (internet?): {exc}")
            return None
        except Exception as exc:
            if segment.is_final:
                self.error_occurred.emit(f"STT hatası: {exc}")
            return None

        if not original:
            # Kısmi sonuçların anlaşılamaması normaldir (cümle henüz yarım),
            # kullanıcıyı yormamak için yalnızca kesinleşmiş olanları bildir.
            if segment.is_final:
                self.log_message.emit(f"🔈 ({segment.duration:.1f} sn ses anlaşılamadı)")
            return None

        try:
            translated = self._translator.translate(original, src_profile.translate_code,
                                                    tgt_profile.translate_code)
        except Exception as exc:
            if segment.is_final:
                self.error_occurred.emit(f"Çeviri hatası: {exc}")
            translated = original
        return original, translated, segment.is_final

    def _emit_in_order(self) -> None:
        while True:
            with self._cv:
                while not self._pending and not self._stop_event.is_set():
                    self._cv.wait(0.2)
                if not self._pending:
                    if self._stop_event.is_set():
                        return
                    continue
                future = self._pending[0]

            try:
                result = future.result(timeout=self.RESULT_TIMEOUT_SEC)
            except Exception as exc:
                LOGGER.warning("Segment işlenemedi: %s", exc)
                result = None

            with self._cv:
                if self._pending and self._pending[0] is future:
                    self._pending.popleft()
                if not self._pending:
                    self.busy_changed.emit(False)
                self._cv.notify_all()      # geri basınçta bekleyen üreticiyi uyandır

            if result is not None:
                self._publish(*result)


    def _publish(self, original: str, translated: str, is_final: bool) -> None:
        now = time.time()

        if not is_final:
            # KISMİ: ekrandaki metni tazele, ama günlüğe yazma ve SESLENDİRME.
            # (Yarım cümleyi seslendirmek dublajı berbat ederdi.)
            if original == self._last_partial:
                return
            self._last_partial = original
            self.subtitle_ready.emit(original, translated)
            return

        # Yankı bastırma sıralı yayında yapılır; paralel işçilerde yapılsaydı
        # yarış koşulu oluşurdu.
        if (original.lower() == self._last_text.lower()
                and (now - self._last_text_at) < self.DUPLICATE_WINDOW_SEC):
            self._last_text_at = now
            return
        self._last_text = original
        self._last_text_at = now
        self._last_partial = ""

        self.log_message.emit(f"🎧 {original}")
        self.subtitle_ready.emit(original, translated)
        self.log_message.emit(f"💬 {translated}")

        if self._config.dubbing_enabled and translated:
            self._tts.speak(translated, self._config.voice, self._config.tts_rate)


class SubtitleOverlay(QtWidgets.QWidget):
    """
    Ekranın altında duran, çerçevesiz, yarı saydam ve tıklamaları alttaki
    uygulamaya geçiren (click-through) altyazı şeridi.
    """

    # Windows extended window style sabitleri
    _GWL_EXSTYLE = -20
    _WS_EX_TRANSPARENT = 0x00000020
    _WS_EX_LAYERED = 0x00080000
    _WS_EX_NOACTIVATE = 0x08000000
    _WS_EX_TOOLWINDOW = 0x00000080

    _PAD_H_MAIN, _PAD_V_MAIN, _BORDER_MAIN = 22, 10, 1
    _PAD_H_SUB, _PAD_V_SUB = 16, 4
    _SPACING = 6

    def __init__(self, config: AppConfig) -> None:
        super().__init__(None)
        self._config = config

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._SPACING)

        self._original_label = self._make_label(is_primary=False)
        self._translated_label = self._make_label(is_primary=True)
        layout.addWidget(self._original_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._translated_label, 0, Qt.AlignmentFlag.AlignHCenter)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._clear_text)

        self.apply_style()
        self.reposition()

    def _make_label(self, is_primary: bool) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel("", self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        label.setProperty("primary", is_primary)
        label.setVisible(False)
        return label

    def apply_style(self) -> None:
        size = self._config.subtitle_font_size

        main_font = QtGui.QFont("Segoe UI")
        main_font.setPixelSize(size)
        main_font.setWeight(QtGui.QFont.Weight.DemiBold)
        self._translated_label.setFont(main_font)

        sub_font = QtGui.QFont("Segoe UI")
        sub_font.setPixelSize(max(12, int(size * 0.58)))
        sub_font.setItalic(True)
        self._original_label.setFont(sub_font)

        self._translated_label.setStyleSheet(
            f"""
            QLabel {{
                color: #FFFFFF;
                background-color: rgba(0, 0, 0, 200);
                border: {self._BORDER_MAIN}px solid rgba(255, 255, 255, 45);
                border-radius: 14px;
                padding: {self._PAD_V_MAIN}px {self._PAD_H_MAIN}px;
            }}
            """
        )
        self._original_label.setStyleSheet(
            f"""
            QLabel {{
                color: #B9C4D0;
                background-color: rgba(0, 0, 0, 120);
                border-radius: 10px;
                padding: {self._PAD_V_SUB}px {self._PAD_H_SUB}px;
            }}
            """
        )
        self.reposition()

    def _chrome_width(self, label: QtWidgets.QLabel) -> int:
        """Etiketin metin dışındaki yatay payı (padding + kenarlık)."""
        if label is self._translated_label:
            return 2 * (self._PAD_H_MAIN + self._BORDER_MAIN)
        return 2 * self._PAD_H_SUB

    def enable_click_through(self) -> None:
        """Qt bayrağına ek olarak Win32 seviyesinde de click-through garanti et."""
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            style = get_long(hwnd, self._GWL_EXSTYLE)
            style |= (self._WS_EX_TRANSPARENT | self._WS_EX_LAYERED
                      | self._WS_EX_NOACTIVATE | self._WS_EX_TOOLWINDOW)
            set_long(hwnd, self._GWL_EXSTYLE, style)
        except Exception as exc:
            LOGGER.warning("Click-through ayarlanamadı: %s", exc)

    def reposition(self) -> None:
        """
        Genişliği kullanıcı ayarından, YÜKSEKLİĞİ İÇERİKTEN hesaplar.
        Sabit yükseklik kullanılsaydı 3-4 satırlık uzun çeviriler kırpılır,
        altyazı 'gelmemiş' gibi görünürdü.
        """
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        pct = max(20, min(100, self._config.subtitle_width_pct))
        max_width = min(geo.width(), max(200, int(geo.width() * pct / 100.0)))

        content_width = 0
        height = 0
        shown = 0
        for label in (self._original_label, self._translated_label):
            if not label.isVisible():
                continue
            label.setWordWrap(False)
            natural = label.sizeHint().width()
            label.setWordWrap(True)
            label_width = max(1, min(max_width, natural))
            label.setFixedWidth(label_width)

            needed = label.heightForWidth(label_width)
            if needed <= 0:
                needed = label.sizeHint().height()
            height += needed
            content_width = max(content_width, label_width)
            shown += 1

        if shown == 0:
            content_width = max_width
            height = int(self._config.subtitle_font_size * 1.8)
        else:
            height += self._SPACING * (shown - 1)

        layout = self.layout()
        if layout is not None:
            layout.activate()

        width = min(max_width, max(1, content_width))
        height = min(height, geo.height())

        x = geo.x() + (geo.width() - width) // 2
        y = geo.y() + geo.height() - height - self._config.subtitle_bottom_margin
        self.setGeometry(x, max(geo.y(), y), width, height)

    @pyqtSlot(str, str)
    def show_subtitle(self, original: str, translated: str) -> None:
        try:
            if self._config.show_original and original:
                self._original_label.setText(original)
                self._original_label.setVisible(True)
            else:
                self._original_label.setVisible(False)

            self._translated_label.setText(translated or original)
            self._translated_label.setVisible(bool(translated or original))

            # Metin değişti -> yükseklik yeniden hesaplanmalı
            self.reposition()

            if not self.isVisible():
                self.show()
                self.enable_click_through()
            self._hide_timer.start(int(self._config.subtitle_hold_sec * 1000))
        except Exception as exc:
            LOGGER.warning("Altyazı gösterilemedi: %s", exc)

    def prime(self) -> None:
        """Katmanlı pencereyi ilk kullanımdan önce hazırlar."""
        try:
            self._translated_label.setText(" ")
            self._translated_label.setVisible(True)
            self.reposition()
            self.show()
            QtWidgets.QApplication.processEvents()
        except Exception as exc:
            LOGGER.debug("Overlay ön ısıtma başarısız (önemsiz): %s", exc)
        finally:
            self._hide_timer.stop()
            self._clear_text()
            self.hide()

    def _clear_text(self) -> None:
        self._original_label.setVisible(False)
        self._translated_label.setVisible(False)

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        self.enable_click_through()


class HotkeyManager(QObject):
    """
    Global kısayolları dinler. Öncelik 'keyboard' kütüphanesinde, o yoksa
    'pynput' ile devam eder. Sinyaller Qt'nin queued connection'ı sayesinde
    güvenle ana thread'e taşınır.
    """

    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    toggle_overlay_requested = pyqtSignal()
    status_message = pyqtSignal(str)

    HOTKEY_START = "ctrl+shift+r"
    HOTKEY_STOP = "ctrl+shift+s"
    HOTKEY_TOGGLE = "ctrl+shift+h"

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._backend: Optional[str] = None
        self._pynput_listener = None
        self._handles: list = []

    def install(self) -> None:
        if self._try_keyboard():
            return
        if self._try_pynput():
            return
        self.status_message.emit(
            "⚠ Global kısayollar etkinleştirilemedi (keyboard/pynput yok ya da yetki gerekiyor). "
            "Butonları kullanabilirsiniz."
        )

    def _try_keyboard(self) -> bool:
        if kb_lib is None:
            return False
        try:
            self._handles.append(kb_lib.add_hotkey(self.HOTKEY_START, self.start_requested.emit))
            self._handles.append(kb_lib.add_hotkey(self.HOTKEY_STOP, self.stop_requested.emit))
            self._handles.append(kb_lib.add_hotkey(self.HOTKEY_TOGGLE, self.toggle_overlay_requested.emit))
            self._backend = "keyboard"
            self.status_message.emit("Kısayollar aktif (keyboard): Ctrl+Shift+R / S / H")
            return True
        except Exception as exc:
            LOGGER.warning("keyboard kütüphanesi kısayol kuramadı: %s", exc)
            self._handles.clear()
            return False

    def _try_pynput(self) -> bool:
        if pynput_keyboard is None:
            return False
        try:
            mapping = {
                "<ctrl>+<shift>+r": self.start_requested.emit,
                "<ctrl>+<shift>+s": self.stop_requested.emit,
                "<ctrl>+<shift>+h": self.toggle_overlay_requested.emit,
            }
            self._pynput_listener = pynput_keyboard.GlobalHotKeys(mapping)
            self._pynput_listener.daemon = True
            self._pynput_listener.start()
            self._backend = "pynput"
            self.status_message.emit("Kısayollar aktif (pynput): Ctrl+Shift+R / S / H")
            return True
        except Exception as exc:
            LOGGER.warning("pynput kısayol kuramadı: %s", exc)
            return False

    def uninstall(self) -> None:
        try:
            if self._backend == "keyboard" and kb_lib is not None:
                for handle in self._handles:
                    try:
                        kb_lib.remove_hotkey(handle)
                    except Exception:
                        pass
                self._handles.clear()
            elif self._backend == "pynput" and self._pynput_listener is not None:
                self._pynput_listener.stop()
        except Exception as exc:
            LOGGER.debug("Kısayol kaldırma hatası: %s", exc)


class MainWindow(QtWidgets.QMainWindow):
    """Kontrol paneli. Servisleri kurar, bağlar ve yaşam döngüsünü yönetir."""

    def __init__(self) -> None:
        super().__init__()
        self.config = AppConfig()

        self._audio_queue: "queue.Queue[AudioSegment]" = queue.Queue(maxsize=12)
        self._speaking_flag = threading.Event()
        self._stt = SpeechToTextService()
        self._translator = TranslatorService()
        self._tts = TTSService(create_audio_player(), self._speaking_flag,
                               on_error=lambda m: self._append_log(f"⚠ {m}"))
        self._tts.start()

        self._capturer: Optional[LoopbackAudioCapturer] = None
        self._pipeline: Optional[PipelineWorker] = None
        self._running = False

        self.overlay = SubtitleOverlay(self.config)
        self.hotkeys = HotkeyManager(self)

        self._build_ui()
        self._connect_hotkeys()
        self._sync_config_from_ui()
        # Katmanlı pencere maliyetini açılışta öde (bkz. SubtitleOverlay.prime).
        QTimer.singleShot(60, self.overlay.prime)

    def _build_ui(self) -> None:
        self.setWindowTitle("Canlı Sistem Sesi Çevirmeni — Altyazı + Dublaj")
        self.setMinimumSize(560, 620)

        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        lang_box = QtWidgets.QGroupBox("Diller")
        lang_layout = QtWidgets.QGridLayout(lang_box)

        self.source_combo = QtWidgets.QComboBox()
        self.target_combo = QtWidgets.QComboBox()
        for code, profile in LANGUAGES.items():
            self.source_combo.addItem(profile.label, code)
            self.target_combo.addItem(profile.label, code)
        self.source_combo.setCurrentIndex(self.source_combo.findData("en"))
        self.target_combo.setCurrentIndex(self.target_combo.findData("tr"))

        lang_layout.addWidget(QtWidgets.QLabel("Kaynak dil (videonun dili):"), 0, 0)
        lang_layout.addWidget(self.source_combo, 0, 1)
        lang_layout.addWidget(QtWidgets.QLabel("Hedef dil (çeviri):"), 1, 0)
        lang_layout.addWidget(self.target_combo, 1, 1)
        root.addWidget(lang_box)

        mode_box = QtWidgets.QGroupBox("Mod")
        mode_layout = QtWidgets.QVBoxLayout(mode_box)
        self.radio_subtitle = QtWidgets.QRadioButton("Sadece Altyazı")
        self.radio_dubbing = QtWidgets.QRadioButton("Altyazı + Dublaj (Edge-TTS)")
        self.radio_subtitle.setChecked(True)
        mode_layout.addWidget(self.radio_subtitle)
        mode_layout.addWidget(self.radio_dubbing)

        voice_row = QtWidgets.QHBoxLayout()
        self.voice_combo = QtWidgets.QComboBox()
        self.rate_combo = QtWidgets.QComboBox()
        for rate in ("+0%", "+10%", "+15%", "+25%", "+40%"):
            self.rate_combo.addItem(rate, rate)
        self.rate_combo.setCurrentIndex(2)
        voice_row.addWidget(QtWidgets.QLabel("Ses:"))
        voice_row.addWidget(self.voice_combo, 1)
        voice_row.addWidget(QtWidgets.QLabel("Hız:"))
        voice_row.addWidget(self.rate_combo)
        mode_layout.addLayout(voice_row)

        self.check_show_original = QtWidgets.QCheckBox("Altyazıda orijinal metni de göster")
        self.check_show_original.setChecked(True)
        mode_layout.addWidget(self.check_show_original)

        self.check_streaming = QtWidgets.QCheckBox(
            "Akıcı mod: cümle bitmeden altyazıyı canlı akıt")
        self.check_streaming.setChecked(True)
        self.check_streaming.setToolTip(
            "Açık: konuşma sürerken altyazı ~1 sn'de bir güncellenir (akıcı).\n"
            "Kapalı: yalnızca cümle bitince tek seferde görünür (daha az veri)."
        )
        mode_layout.addWidget(self.check_streaming)
        root.addWidget(mode_box)

        tune_box = QtWidgets.QGroupBox("Hassasiyet ve Görünüm")
        tune_layout = QtWidgets.QGridLayout(tune_box)

        self.threshold_slider = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        # /10000 -> 0.0001 - 0.0500. Varsayılan (0.0100) aralığın alt beşte
        # birindedir; böylece gürültülü içerik için eşik YÜKSELTİLEBİLİR de.
        self.threshold_slider.setRange(1, 500)
        self.threshold_slider.setValue(int(self.config.silence_threshold * 10000))
        self.threshold_slider.setToolTip(
            "Sola: daha hassas (kısık sesleri de yakalar).\n"
            "Sağa: daha seçici (arka plan gürültüsünü eler)."
        )
        self.threshold_value = QtWidgets.QLabel(f"{self.config.silence_threshold:.4f}")

        # Cümle sonu bekleme: gecikmenin doğrudan bileşeni. Küçük değer =
        # daha hızlı altyazı, ama cümleler ortadan bölünebilir.
        self.silence_spin = QtWidgets.QDoubleSpinBox()
        self.silence_spin.setRange(0.15, 1.50)
        self.silence_spin.setSingleStep(0.05)
        self.silence_spin.setDecimals(2)
        self.silence_spin.setSuffix(" sn")
        self.silence_spin.setValue(self.config.silence_duration)
        self.silence_spin.setToolTip(
            "Cümlenin bittiğine karar vermeden önce beklenen sessizlik.\n"
            "Düşürmek altyazıyı hızlandırır; çok düşük olursa cümleler bölünür."
        )

        self.font_spin = QtWidgets.QSpinBox()
        self.font_spin.setRange(14, 96)
        self.font_spin.setValue(self.config.subtitle_font_size)

        self.width_slider = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.width_slider.setRange(20, 100)
        self.width_slider.setValue(self.config.subtitle_width_pct)
        self.width_slider.setToolTip("Altyazı şeridinin ekran genişliğine oranı (kenarlara doğru).")
        self.width_value = QtWidgets.QLabel(f"%{self.config.subtitle_width_pct}")

        self.margin_spin = QtWidgets.QSpinBox()
        self.margin_spin.setRange(0, 2000)      # ekranın en altından en üstüne
        self.margin_spin.setSingleStep(10)
        self.margin_spin.setSuffix(" px")
        self.margin_spin.setValue(self.config.subtitle_bottom_margin)
        self.margin_spin.setToolTip("Ekranın altından yükseklik. Büyüt = altyazı yukarı çıkar.")

        tune_layout.addWidget(QtWidgets.QLabel("Sessizlik eşiği:"), 0, 0)
        tune_layout.addWidget(self.threshold_slider, 0, 1)
        tune_layout.addWidget(self.threshold_value, 0, 2)
        tune_layout.addWidget(QtWidgets.QLabel("Cümle sonu bekleme:"), 1, 0)
        tune_layout.addWidget(self.silence_spin, 1, 1, 1, 2)
        tune_layout.addWidget(QtWidgets.QLabel("Altyazı yazı boyutu:"), 2, 0)
        tune_layout.addWidget(self.font_spin, 2, 1, 1, 2)
        tune_layout.addWidget(QtWidgets.QLabel("Altyazı genişliği:"), 3, 0)
        tune_layout.addWidget(self.width_slider, 3, 1)
        tune_layout.addWidget(self.width_value, 3, 2)
        tune_layout.addWidget(QtWidgets.QLabel("Yükseklik (alttan):"), 4, 0)
        tune_layout.addWidget(self.margin_spin, 4, 1, 1, 2)

        self.level_bar = QtWidgets.QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedHeight(10)
        tune_layout.addWidget(QtWidgets.QLabel("Sistem ses seviyesi:"), 5, 0)
        tune_layout.addWidget(self.level_bar, 5, 1, 1, 2)
        root.addWidget(tune_box)

        button_row = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("▶  Başlat  (Ctrl+Shift+R)")
        self.stop_button = QtWidgets.QPushButton("■  Durdur  (Ctrl+Shift+S)")
        self.stop_button.setEnabled(False)
        self.start_button.setStyleSheet("QPushButton { padding: 10px; font-weight: bold; }")
        self.stop_button.setStyleSheet("QPushButton { padding: 10px; font-weight: bold; }")
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.stop_button)
        root.addLayout(button_row)

        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(400)
        self.log_view.setPlaceholderText("Tanınan ve çevrilen metinler burada görünür...")
        root.addWidget(self.log_view, 1)

        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Hazır.")

        self.start_button.clicked.connect(self.start_translation)
        self.stop_button.clicked.connect(self.stop_translation)
        self.source_combo.currentIndexChanged.connect(self._sync_config_from_ui)
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        self.radio_subtitle.toggled.connect(self._sync_config_from_ui)
        self.radio_dubbing.toggled.connect(self._sync_config_from_ui)
        self.voice_combo.currentIndexChanged.connect(self._sync_config_from_ui)
        self.rate_combo.currentIndexChanged.connect(self._sync_config_from_ui)
        self.check_show_original.toggled.connect(self._sync_config_from_ui)
        self.check_streaming.toggled.connect(self._sync_config_from_ui)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        self.silence_spin.valueChanged.connect(self._on_silence_changed)
        self.font_spin.valueChanged.connect(self._on_appearance_changed)
        self.width_slider.valueChanged.connect(self._on_appearance_changed)
        self.margin_spin.valueChanged.connect(self._on_appearance_changed)

        self._refresh_voices()

    def _connect_hotkeys(self) -> None:
        self.hotkeys.start_requested.connect(self.start_translation)
        self.hotkeys.stop_requested.connect(self.stop_translation)
        self.hotkeys.toggle_overlay_requested.connect(self._toggle_overlay)
        self.hotkeys.status_message.connect(self._append_log)
        self.hotkeys.install()

    def _refresh_voices(self) -> None:
        target = self.target_combo.currentData() or "tr"
        profile = LANGUAGES.get(target, LANGUAGES["tr"])
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        for voice in profile.voices:
            self.voice_combo.addItem(voice, voice)
        self.voice_combo.blockSignals(False)

    def _on_target_changed(self) -> None:
        self._refresh_voices()
        self._sync_config_from_ui()

    def _on_threshold_changed(self, value: int) -> None:
        self.config.silence_threshold = value / 10000.0
        self.threshold_value.setText(f"{self.config.silence_threshold:.4f}")

    def _on_silence_changed(self, value: float) -> None:
        # Yakalayıcı bu değeri her döngüde okur; çalışırken bile anında etki eder.
        self.config.silence_duration = float(value)

    def _on_appearance_changed(self) -> None:
        self.config.subtitle_font_size = self.font_spin.value()
        self.config.subtitle_width_pct = self.width_slider.value()
        self.config.subtitle_bottom_margin = self.margin_spin.value()
        self.width_value.setText(f"%{self.config.subtitle_width_pct}")
        self.overlay.apply_style()
        if not self._running:
            # Ayarın etkisini anında görebilmek için örnek altyazı göster.
            self.overlay.show_subtitle(
                "Preview — original line",
                "Örnek altyazı: konum, genişlik ve boyut böyle görünür.",
            )

    def _sync_config_from_ui(self) -> None:
        self.config.source_lang = self.source_combo.currentData() or "en"
        self.config.target_lang = self.target_combo.currentData() or "tr"
        self.config.dubbing_enabled = self.radio_dubbing.isChecked()
        self.config.voice = self.voice_combo.currentData() or "tr-TR-EmelNeural"
        self.config.tts_rate = self.rate_combo.currentData() or "+15%"
        self.config.show_original = self.check_show_original.isChecked()
        self.config.streaming_enabled = self.check_streaming.isChecked()

    @pyqtSlot()
    def start_translation(self) -> None:
        if self._running:
            return
        if self.config.source_lang == self.config.target_lang:
            self._append_log("⚠ Kaynak ve hedef dil aynı; çeviri yapılmayacak.")

        self._sync_config_from_ui()
        self._drain_queue()
        self._warm_up_services()

        self._pipeline = PipelineWorker(self.config, self._audio_queue, self._stt,
                                        self._translator, self._tts, parent=self)
        self._pipeline.subtitle_ready.connect(self.overlay.show_subtitle)
        self._pipeline.log_message.connect(self._append_log)
        self._pipeline.error_occurred.connect(lambda m: self._append_log(f"⚠ {m}"))
        self._pipeline.start()

        self._capturer = LoopbackAudioCapturer(self.config, self._audio_queue,
                                               self._speaking_flag, parent=self)
        self._capturer.status_message.connect(self._append_log)
        self._capturer.error_occurred.connect(self._on_capture_error)
        self._capturer.level_changed.connect(self._on_level)
        self._capturer.device_resolved.connect(lambda name: self.status_bar.showMessage(f"Kaynak: {name}"))
        self._capturer.start()

        self._running = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.overlay.show()
        self.overlay.show_subtitle("", "🎧 Dinleniyor...")
        self._append_log("▶ Başlatıldı.")

    @pyqtSlot()
    def stop_translation(self) -> None:
        if not self._running:
            return
        self._running = False

        if self._capturer is not None:
            self._capturer.stop()
            if not self._capturer.wait(4000):
                LOGGER.warning("Yakalayıcı thread zamanında kapanmadı.")
            else:
                self._capturer.deleteLater()   # tekrarlı başlat/durdurda birikmesin
            self._capturer = None

        if self._pipeline is not None:
            self._pipeline.stop()
            if not self._pipeline.wait(6000):
                LOGGER.warning("Pipeline thread zamanında kapanmadı.")
            else:
                self._pipeline.deleteLater()
            self._pipeline = None

        self._tts.clear()
        self._drain_queue()

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.level_bar.setValue(0)
        self.overlay.hide()
        self._append_log("■ Durduruldu.")
        self.status_bar.showMessage("Hazır.")

    def _warm_up_services(self) -> None:
        """Çeviri servisinin ağ bağlantısını önceden başlatır."""
        target = self.config.profile(self.config.target_lang).translate_code
        source = self.config.profile(self.config.source_lang).translate_code

        def warm() -> None:
            try:
                self._translator.translate("hello", source, target)
            except Exception as exc:
                LOGGER.debug("Isıtma isteği başarısız (önemsiz): %s", exc)

        threading.Thread(target=warm, name="WarmUp", daemon=True).start()

    def _drain_queue(self) -> None:
        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    @pyqtSlot(float)
    def _on_level(self, level: float) -> None:
        self.level_bar.setValue(int(max(0.0, min(level, 1.0)) * 100))

    @pyqtSlot(str)
    def _on_capture_error(self, message: str) -> None:
        self._append_log(f"⚠ Ses yakalama hatası: {message}")
        QtWidgets.QMessageBox.critical(self, "Ses Yakalama Hatası", message)
        self.stop_translation()

    @pyqtSlot(str)
    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _toggle_overlay(self) -> None:
        self.overlay.setVisible(not self.overlay.isVisible())

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802 (Qt API)
        try:
            self.stop_translation()
            self.hotkeys.uninstall()
            self._tts.shutdown()
            self.overlay.close()
        except Exception as exc:
            LOGGER.warning("Kapanış sırasında hata: %s", exc)
        super().closeEvent(event)


def main() -> int:
    _configure_logging()

    if sys.platform != "win32":
        print("UYARI: WASAPI loopback yakalama yalnızca Windows'ta desteklenir.", file=sys.stderr)

    QtWidgets.QApplication.setApplicationName("Live System Audio Translator")
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
