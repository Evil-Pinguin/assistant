# -*- coding: utf-8 -*-
"""Единый источник правды о состоянии AURA (state machine).

IDLE → WAKE → LISTENING → PROCESSING → EXECUTING → VERIFYING → SPEAKING
                                                    ↘ SUCCESS / ERROR ↘ IDLE

UI, аватар, waveform и статус читают состояние отсюда.
Правило: LISTENING показывается только когда микрофон реально слушает.
"""
import threading
import time

STATES = ("idle", "wake", "listening", "processing", "executing",
          "verifying", "speaking", "success", "error", "alert", "sleep", "off")

UI_LABELS = {
    "idle": "READY",
    "wake": "I'M LISTENING",
    "listening": "LISTENING",
    "processing": "PROCESSING",
    "executing": "EXECUTING",
    "verifying": "VERIFYING",
    "speaking": "SPEAKING",
    "success": "COMPLETE ✓",
    "error": "ERROR",
    "alert": "ATTENTION",
    "sleep": "SLEEPING",
    "off": "OFFLINE",
}


class StateMachine:
    def __init__(self, emit):
        self.emit = emit
        self._lock = threading.Lock()
        self._state = "idle"
        self._since = time.time()

    @property
    def state(self):
        with self._lock:
            return self._state

    def set(self, name: str, label: str = ""):
        if name not in STATES:
            return
        with self._lock:
            self._state = name
            self._since = time.time()
        self.emit("state", name=name, label=label or UI_LABELS.get(name, name))

    def age(self) -> float:
        with self._lock:
            return time.time() - self._since

    # удобные проверки
    def is_busy(self) -> bool:
        return self.state in ("processing", "executing", "verifying")

    def snapshot(self) -> dict:
        with self._lock:
            return {"state": self._state, "since": self._since}
