"""Segmentleri paralel tanıyıp çevirir, sonuçları geliş sırasıyla yayınlar."""
from __future__ import annotations

import collections
import queue
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .capture import AudioSegment
from .config import AppConfig
from .log import LOGGER
from .providers import ServiceUnavailable
from .speech import SpeechToTextService, TranslatorService
from .tts import TTSService


class PipelineWorker(QThread):
    subtitle_ready = pyqtSignal(str, str)   # (orijinal, çeviri)
    line_finalized = pyqtSignal(float, float, str, str)  # (başlangıç, bitiş, orijinal, çeviri)
    log_message = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    MAX_WORKERS = 3
    MAX_BACKLOG = 6
    RESULT_TIMEOUT_SEC = 25.0
    DUPLICATE_WINDOW_SEC = 4.0
    # Servis sınırladığında her cümle için aynı uyarıyı basmayalım
    REPORT_INTERVAL_SEC = 15.0

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
        self._last_report_at: dict[str, float] = {}
        self._submitted = 0
        # Bir işçi hep kesin segmentlere boş kalsın; yoksa süren kısmiler
        # bitene kadar cümle sonu altyazısı bekliyor.
        self._partial_slots = threading.Semaphore(self.MAX_WORKERS - 1)
        self._report_lock = threading.Lock()

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

                # Havuz doluysa segmenti atmak yerine bekliyoruz; atınca bazı
                # altyazılar hiç gelmiyordu.
                with self._cv:
                    while (len(self._pending) >= self.MAX_BACKLOG
                           and not self._stop_event.is_set()):
                        self._cv.wait(0.1)
                if self._stop_event.is_set():
                    break

                with self._cv:
                    self._submitted += 1
                    seq = self._submitted
                future = executor.submit(self._process, segment, seq)
                with self._cv:
                    self._pending.append(future)
                    self.busy_changed.emit(True)
                    self._cv.notify()
        except Exception as exc:
            LOGGER.exception("Pipeline üretici hatası")
            self.error_occurred.emit(str(exc))
        finally:
            self._stop_event.set()
            with self._cv:
                self._cv.notify_all()
            emitter.join(timeout=8.0)
            executor.shutdown(wait=False, cancel_futures=True)
            self.busy_changed.emit(False)

    def _is_superseded(self, segment: AudioSegment, seq: int) -> bool:
        """İşlenmeye sıra gelene kadar arkasından yenisi gelmiş kısmi artık
        gösterilmeye değmez. Ağ yavaşken bunları da işlemek işçileri tıkıyor,
        kesin altyazı saniyelerce gecikiyordu. İşlenmeye başlamış kısmiyi ise
        yarıda bırakmıyoruz: tanıma ~1 sn, kısmiler 0.9 sn'de bir geldiği için
        o zaman hiçbir kısmi ekrana çıkamıyordu."""
        return not segment.is_final and seq != self._submitted

    def _process(self, segment: AudioSegment, seq: int) -> Optional[tuple[str, str, AudioSegment]]:
        # Kısmi sonuçların hatası ve anlaşılamaması olağan (cümle yarım),
        # kullanıcıya yalnızca kesinleşmiş segmentlerinkini gösteriyoruz.
        if self._is_superseded(segment, seq):
            return None
        if segment.is_final:
            return self._recognize_and_translate(segment)
        if not self._partial_slots.acquire(blocking=False):
            return None
        try:
            return self._recognize_and_translate(segment)
        finally:
            self._partial_slots.release()

    def _recognize_and_translate(self, segment: AudioSegment) -> Optional[tuple[str, str, AudioSegment]]:
        cfg = self._config
        src_profile = cfg.profile(cfg.source_lang)
        tgt_profile = cfg.profile(cfg.target_lang)

        try:
            original = self._stt.transcribe(segment, src_profile.stt_code, cfg.stt_engine)
        except ServiceUnavailable as exc:
            self._report(segment, "stt", f"Tanıma yapılamadı: {exc}")
            return None
        except Exception as exc:
            self._report(segment, "stt", f"STT hatası: {exc}")
            return None

        if not original:
            if segment.is_final:
                self.log_message.emit(f"🔈 ({segment.duration:.1f} sn ses anlaşılamadı)")
            return None

        try:
            translated = self._translator.translate(original, src_profile.translate_code,
                                                    tgt_profile.translate_code, segment.is_final)
        except Exception as exc:
            if not segment.is_final:
                return None     # çevrilmemiş yarım cümleyi göstermektense bekle
            self._report(segment, "translate", f"Çeviri yapılamadı: {exc}")
            translated = original
        return original, translated, segment

    def _report(self, segment: AudioSegment, kind: str, message: str) -> None:
        if not segment.is_final:
            return
        now = time.monotonic()
        with self._report_lock:
            if now - self._last_report_at.get(kind, -1e9) < self.REPORT_INTERVAL_SEC:
                LOGGER.info("%s", message)
                return
            self._last_report_at[kind] = now
        self.error_occurred.emit(message)

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

    def _publish(self, original: str, translated: str, segment: AudioSegment) -> None:
        now = time.time()

        if not segment.is_final:
            # Kısmi sonuç sadece ekrandaki metni tazeler; günlüğe yazılmaz,
            # yarım cümle seslendirilmez.
            if original == self._last_partial:
                return
            self._last_partial = original
            self.subtitle_ready.emit(original, translated)
            return

        # Yankı bastırma burada, sıralı yayında yapılıyor; paralel işçilerde
        # yapılsa yarış koşulu olurdu.
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
        self.line_finalized.emit(segment.created_at - segment.duration, segment.created_at,
                                 original, translated)

        if self._config.dubbing_enabled and translated:
            self._tts.speak(translated, self._config.voice, self._config.tts_rate,
                            self._config.profile(self._config.target_lang).voices)
