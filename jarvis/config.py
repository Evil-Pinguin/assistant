# -*- coding: utf-8 -*-
"""Конфигурация ассистента: загрузка/сохранение data/settings.json."""
import copy
import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
COMMANDS_FILE = os.path.join(DATA_DIR, "custom_commands.json")
LOG_FILE = os.path.join(DATA_DIR, "jarvis.log")

DEFAULTS = {
    # --- Голос и слух ---
    "language": "ru-RU",            # язык распознавания речи
    "wake_word": "джарвис",         # кодовое слово
    "require_wake_word": True,      # ждать кодовое слово перед командой
    "mic_enabled": True,            # слушать микрофон при старте
    "tts_enabled": True,            # озвучивать ответы
    "tts_rate": 175,                # скорость речи (слов в минуту)
    "tts_volume": 1.0,              # громкость речи 0.0–1.0
    "tts_voice_id": "",             # ID голоса (пусто = по умолчанию)
    "stt_engine": "google",         # "google" (онлайн) или "vosk" (офлайн)
    "vosk_model_path": "",          # путь к модели vosk для офлайн-режима
    # --- Персонализация ---
    "user_name": "",                # как ассистент называет пользователя
    "city": "Москва",               # город по умолчанию для погоды
    "confirm_power": True,          # подтверждать выключение/перезагрузку
    "music_url": "https://music.youtube.com",  # что открывать на «включи музыку»
    "screenshots_dir": "",          # куда сохранять скриншоты (пусто = авто)
    # --- ИИ ---
    "ai_enabled": False,            # отвечать через ИИ, если команда не распознана
    "ai_base_url": "https://api.openai.com/v1",
    "ai_api_key": "",
    "ai_model": "gpt-4o-mini",
    "ai_allow_actions": False,      # разрешить ИИ выполнять действия на ПК
    "ai_history_limit": 8,          # сколько реплик помнить
}


class Config:
    """Потокобезопасное хранилище настроек с сохранением в JSON."""

    def __init__(self, path: str = SETTINGS_FILE):
        self.path = path
        self._lock = threading.RLock()
        self._data = copy.deepcopy(DEFAULTS)
        self.load()

    # -- Работа с файлом -------------------------------------------------
    def load(self):
        with self._lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        stored = json.load(f)
                    if isinstance(stored, dict):
                        merged = copy.deepcopy(DEFAULTS)
                        merged.update({k: v for k, v in stored.items()})
                        self._data = merged
                except (OSError, json.JSONDecodeError) as exc:
                    print(f"[config] Не удалось прочитать настройки: {exc}")

    def save(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    # -- Доступ -----------------------------------------------------------
    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value):
        with self._lock:
            self._data[key] = value

    def update(self, values: dict):
        with self._lock:
            self._data.update(values)

    def as_dict(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._data)

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)
