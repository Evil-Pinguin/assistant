# -*- coding: utf-8 -*-
"""Центр активности AURA: журнал действий + отмена (undo)."""
import datetime
import threading
from collections import deque


class Activity:
    """Потокобезопасный журнал. Каждая запись может иметь функцию отмены."""

    def __init__(self, emit=None, limit=300):
        self.emit = emit or (lambda *a, **k: None)
        self._entries = deque(maxlen=limit)
        self._lock = threading.RLock()

    def add(self, desc: str, kind: str = "action", undo=None, icon: str = ""):
        entry = {
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "desc": desc,
            "kind": kind,
            "icon": icon,
            "undo": undo,
        }
        with self._lock:
            self._entries.appendleft(entry)
        self.emit("activity", time=entry["time"], desc=desc, icon=icon,
                  has_undo=callable(undo))
        return entry

    def snapshot(self, limit=100):
        with self._lock:
            return [{k: v for k, v in e.items() if k != "undo"}
                    for e in list(self._entries)[:limit]]

    def undo_last(self):
        """Отменить последнее отменяемое действие. Возвращает описание или None."""
        with self._lock:
            while self._entries:
                entry = self._entries[0]
                undo = entry.get("undo")
                if callable(undo):
                    self._entries.popleft()
                    try:
                        undo()
                    except Exception as exc:
                        self.emit("log", level="error",
                                  msg=f"Не удалось отменить «{entry['desc']}»: {exc}")
                        return None
                    self.emit("log", level="system",
                              msg=f"↶ Отменено: {entry['desc']}")
                    return entry["desc"]
                self._entries.popleft()  # неотменяемое — пропускаем
        return None

    def clear(self):
        with self._lock:
            self._entries.clear()
