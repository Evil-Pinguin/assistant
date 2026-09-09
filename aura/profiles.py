# -*- coding: utf-8 -*-
"""Режимы (profiles): готовые сценарии «Работа», «Игры», «Стрим», «Ночь», «Разработка».

Хранятся в data/profiles.json; при первом запуске заполняются встроенными.
Активация: «включи рабочий режим», «режим разработки», по названию или фразе.
"""
import json
import os
import threading

from .config import PROFILES_FILE

BUILTIN_PROFILES = [
    {
        "name": "Работа", "icon": "💻",
        "phrases": ["рабочий режим", "режим работы", "включи работу", "начнём работу"],
        "actions": [
            {"type": "open_app", "target": "code"},
            {"type": "open_url", "target": "https://mail.google.com"},
            {"type": "volume", "target": "30"},
            {"type": "say", "text": "Рабочий режим активирован. Удачной работы!"}
        ],
    },
    {
        "name": "Игры", "icon": "🎮",
        "phrases": ["игровой режим", "режим игр", "пора играть", "включи игры"],
        "actions": [
            {"type": "open_app", "target": "steam"},
            {"type": "open_app", "target": "discord"},
            {"type": "volume", "target": "60"},
            {"type": "say", "text": "Игровой режим активирован. Хорошей игры!"}
        ],
    },
    {
        "name": "Стрим", "icon": "🎥",
        "phrases": ["режим стрима", "начинаю стрим", "стрим режим"],
        "actions": [
            {"type": "open_app", "target": "obs"},
            {"type": "open_app", "target": "discord"},
            {"type": "say", "text": "Стрим режим готов. Удачной трансляции!"}
        ],
    },
    {
        "name": "Ночь", "icon": "🌙",
        "phrases": ["ночной режим", "режим ночи", "пора спать"],
        "actions": [
            {"type": "brightness", "target": "40"},
            {"type": "volume", "target": "20"},
            {"type": "say", "text": "Ночной режим включён. Спокойной ночи!"}
        ],
    },
    {
        "name": "Разработка", "icon": "🚀",
        "phrases": ["режим разработки", "дев режим", "dev environment",
                    "запусти dev environment"],
        "actions": [
            {"type": "open_app", "target": "code"},
            {"type": "open_app", "target": "terminal"},
            {"type": "open_url", "target": "https://github.com"},
            {"type": "say", "text": "Среда разработки готова"}
        ],
    },
]


class Profiles:
    def __init__(self, path: str = PROFILES_FILE, emit=None):
        self.path = path
        self.emit = emit or (lambda *a, **k: None)
        self._lock = threading.RLock()
        self.items = []
        self._ensure()

    def _ensure(self):
        with self._lock:
            if not os.path.exists(self.path):
                self.items = [dict(p) for p in BUILTIN_PROFILES]
                self.save()
            else:
                self.load()

    def load(self):
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.items = [p for p in data.get("profiles", [])
                              if isinstance(p, dict) and p.get("name")]
            except (OSError, json.JSONDecodeError) as exc:
                self.emit("log", level="error", msg=f"Не удалось прочитать режимы: {exc}")
                self.items = [dict(p) for p in BUILTIN_PROFILES]

    def save(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"profiles": self.items}, f, ensure_ascii=False, indent=2)

    def all(self):
        with self._lock:
            return [dict(p) for p in self.items]

    def upsert(self, profile: dict):
        with self._lock:
            name = (profile.get("name") or "").strip()
            for i, p in enumerate(self.items):
                if p.get("name", "").strip() == name:
                    self.items[i] = profile
                    break
            else:
                self.items.append(profile)
            self.save()

    def delete(self, name: str):
        with self._lock:
            self.items = [p for p in self.items if p.get("name", "").strip() != name]
            self.save()

    def match(self, text: str):
        """Найти режим по тексту: «включи рабочий режим», «режим игр», по фразе."""
        t = (text or "").lower().strip()
        if not t:
            return None
        with self._lock:
            for p in self.items:
                name = (p.get("name") or "").lower()
                phrases = [x.lower() for x in p.get("phrases", [])]
                # «режим X», «включи X», точное название, фразы
                if name and (name in t or t in name):
                    return p
                if f"режим {name}" in t or f"режим {name.replace(' ', '')}" in t:
                    return p
                for ph in phrases:
                    if ph and (ph == t or ph in t):
                        return p
        return None
