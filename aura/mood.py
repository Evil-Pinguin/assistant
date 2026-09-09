# -*- coding: utf-8 -*-
"""Эмоциональная система AURA: настроение, энергия, внимание.

assistant_state = {
    "mood": "neutral", "energy": 87, "attention": True, "user_activity": "..."
}
Лицо и цвет подсветки меняются автоматически.
"""
import re
import threading
import time

MOOD_EMOJI = {
    "neutral": "😐", "happy": "😊", "curious": "🤔", "sleepy": "😴",
    "annoyed": "😤", "confident": "😎", "concerned": "😨",
}

MOOD_TINT = {  # оттенок свечения лица
    "neutral": None, "happy": (60, 255, 190), "curious": (185, 130, 255),
    "sleepy": (90, 110, 160), "annoyed": (255, 140, 90),
    "confident": (0, 225, 255), "concerned": (255, 150, 70),
}

FRUSTRATION_RE = re.compile(
    r"сломал|не работает|тормозит|завис|бесит|надоело|устал|опять (эт|оно|он|онa)|"
    r"ничего не выходит|блин|чёрт|черт|капец|ужас")


class MoodEngine:
    def __init__(self, config, emit):
        self.config = config
        self.emit = emit
        self._lock = threading.Lock()
        self.mood = "neutral"
        self.energy = 87
        self.attention = True
        self.user_activity = "start"
        self._last_interaction = time.time()
        self._dirty = True

    # ---------- события ----------
    def observe_user(self, text: str) -> bool:
        """Вызывается на каждую реплику. True, если поймали фрустрацию."""
        with self._lock:
            self._last_interaction = time.time()
            self.attention = True
            if self.mood == "sleepy":
                self.mood = "neutral"
                self._dirty = True
        frustrated = bool(text and FRUSTRATION_RE.search(text.lower()))
        if frustrated:
            with self._lock:
                self.mood = "concerned"
                self._dirty = True
        self._push()
        return frustrated

    def on_success(self, count=1):
        with self._lock:
            self.mood = "confident" if self.mood in ("neutral", "confident") else self.mood
            self.energy = max(5, self.energy - count)
            self._dirty = True
        self._push()

    def on_error(self):
        with self._lock:
            self.mood = "concerned"
            self.energy = max(5, self.energy - 3)
            self._dirty = True
        self._push()

    def on_big_success(self):
        with self._lock:
            self.mood = "happy"
            self.energy = max(5, self.energy - 2)
            self._dirty = True
        self._push()

    def tick(self):
        """Плановое обновление: регенерация энергии, засыпание."""
        with self._lock:
            idle_min = (time.time() - self._last_interaction) / 60.0
            self.energy = min(100, self.energy + 0.5)
            limit = max(1, int(self.config.get("sleep_after_min", 10)))
            if idle_min > limit:
                self.attention = False
                if self.mood != "sleepy":
                    self.mood = "sleepy"
                    self._dirty = True
                    self.emit("state", name="sleep", label="Дремлю… зови меня")
        self._push()

    # ---------- наружу ----------
    def state(self) -> dict:
        with self._lock:
            return {"mood": self.mood, "energy": round(self.energy),
                    "attention": self.attention, "user_activity": self.user_activity}

    def _push(self):
        with self._lock:
            dirty = self._dirty
            self._dirty = False
        if dirty:
            self.emit("mood", **self.state())

    def empathy_line(self) -> str:
        lines = [
            "Вижу, всё непросто. Давайте разберёмся вместе.",
            "Похоже, сегодня компьютер решил проверить ваше терпение.",
            "Спокойно, мы это починим.",
            "Знакомое чувство. Что сломалось на этот раз?",
        ]
        import random
        return random.choice(lines)
