# -*- coding: utf-8 -*-
"""Память AURA: предпочтения пользователя и факты (data/memory.json)."""
import json
import os
import threading

from .config import MEMORY_FILE


class Memory:
    def __init__(self, path: str = MEMORY_FILE, emit=None):
        self.path = path
        self.emit = emit or (lambda *a, **k: None)
        self._lock = threading.RLock()
        self.prefs = {}
        self.facts = []
        self.load()

    # ---------- файл ----------
    def load(self):
        with self._lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.prefs = data.get("prefs", {}) or {}
                    self.facts = data.get("facts", []) or []
                except (OSError, json.JSONDecodeError):
                    pass

    def save(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"prefs": self.prefs, "facts": self.facts},
                          f, ensure_ascii=False, indent=2)

    # ---------- предпочтения ----------
    def set_pref(self, key: str, value: str):
        with self._lock:
            self.prefs[key.strip().lower()] = str(value).strip()
            self.save()

    def get_pref(self, key: str, default=""):
        with self._lock:
            return self.prefs.get(key.strip().lower(), default)

    # ---------- факты ----------
    def add_fact(self, text: str):
        text = text.strip()
        if not text:
            return
        with self._lock:
            if text not in self.facts:
                self.facts.append(text)
                self.facts = self.facts[-100:]
                self.save()

    def clear_facts(self):
        with self._lock:
            self.facts = []
            self.save()

    # ---------- для ИИ и команд ----------
    def as_prompt(self) -> str:
        with self._lock:
            lines = []
            if self.prefs:
                kv = "; ".join(f"{k}: {v}" for k, v in sorted(self.prefs.items()))
                lines.append(f"Предпочтения пользователя: {kv}.")
            if self.facts:
                lines.append("Вы запомнили: " + "; ".join(self.facts[-5:]) + ".")
            return "\n".join(lines)

    def summary(self) -> str:
        with self._lock:
            parts = []
            if self.prefs:
                parts.append("Предпочтения: " + "; ".join(
                    f"{k} = {v}" for k, v in sorted(self.prefs.items())))
            else:
                parts.append("Предпочтений пока нет.")
            if self.facts:
                parts.append("Факты:\n" + "\n".join(f"• {x}" for x in self.facts[-15:]))
            else:
                parts.append("Фактов пока нет — скажите «запомни: …».")
            return "\n".join(parts)
