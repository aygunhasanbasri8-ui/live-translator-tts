"""Kesinleşmiş altyazıların dökümü; SRT ya da düz metin olarak kaydedilebiliyor."""
from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class TranscriptLine:
    start: float        # duvar saati (time.time())
    end: float
    original: str
    translated: str


def srt_timestamp(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


class Transcript:
    # Saatlerce açık kalırsa bellek şişmesin; kabaca birkaç saatlik konuşma
    MAX_LINES = 5000

    def __init__(self) -> None:
        self._lines: list[TranscriptLine] = []
        self._lock = threading.Lock()

    def add(self, start: float, end: float, original: str, translated: str) -> None:
        with self._lock:
            self._lines.append(TranscriptLine(start, end, original, translated))
            if len(self._lines) > self.MAX_LINES:
                del self._lines[0]

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._lines)

    def to_srt(self, field: str = "translated") -> str:
        """Zamanlar ilk satıra göre; videoyu baştan izlerken kabaca hizalı olur."""
        with self._lock:
            lines = list(self._lines)
        if not lines:
            return ""
        origin = lines[0].start
        blocks = []
        for index, line in enumerate(lines, 1):
            text = line.original if field == "original" else line.translated
            if field == "both":
                text = f"{line.original}\n{line.translated}"
            start = line.start - origin
            # Paralel işlenip sıralı yayınlandığı için bitiş bir sonrakinin
            # başlangıcını geçebiliyor; çakışan SRT'yi bazı oynatıcılar atlıyor.
            end = max(start + 0.5, line.end - origin)
            if index < len(lines):
                end = min(end, max(start + 0.1, lines[index].start - origin))
            blocks.append(f"{index}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{text}\n")
        return "\n".join(blocks)

    def to_text(self) -> str:
        with self._lock:
            lines = list(self._lines)
        if not lines:
            return ""
        origin = lines[0].start
        out = []
        for line in lines:
            stamp = srt_timestamp(line.start - origin).split(",")[0]
            out.append(f"[{stamp}] {line.original}\n           {line.translated}")
        return "\n".join(out) + "\n"
