"""Çeviri sonuçları için iş parçacığı güvenli, sınırlı LRU önbellek."""

from __future__ import annotations

import threading
import unicodedata
from collections import OrderedDict
from typing import Optional


def normalize(text: str) -> str:
    # Büyük/küçük harf ve noktalama bilerek korunuyor: çeviriyi değiştirebiliyorlar.
    return unicodedata.normalize("NFC", " ".join(text.split()))


class LruCache:
    def __init__(self, max_entries: int) -> None:
        self._max = max_entries
        self._items: OrderedDict[tuple, str] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: tuple) -> Optional[str]:
        with self._lock:
            value = self._items.get(key)
            if value is None:
                self.misses += 1
                return None
            self._items.move_to_end(key)
            self.hits += 1
            return value

    def put(self, key: tuple, value: str) -> None:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self._max:
                self._items.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
