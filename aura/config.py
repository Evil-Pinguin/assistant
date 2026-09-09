# -*- coding: utf-8 -*-
"""Конфигурация AURA: загрузка/сохранение data/settings.json + пути."""
import copy
import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
COMMANDS_FILE = os.path.join(DATA_DIR, "custom_commands.json")
PROFILES_FILE = os.path.join(DATA_DIR, "profiles.json")
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")
LOG_FILE = os.path.join(DATA_DIR, "aura.log")
PLUGINS_DIR = os.path.join(BASE_DIR, "plugins")

DEFAULTS = {
    # --- персона ---
    "assistant_name": "Аврора",
    "language": "ru-RU",
    "user_name": "",
    "city": "Москва",
    "personality": "friendly",       # professional | friendly | jarvis | anime
    # --- голос и слух ---
    "mic_enabled": True,
    "wake_word": "аврора",
    "require_wake_word": True,
    "tts_enabled": True,
    "tts_rate": 175,
    "tts_volume": 1.0,
    "tts_voice_id": "",
    "stt_engine": "google",          # google | vosk
    "vosk_model_path": "",
    "hotkey_enabled": True,          # Ctrl+Space — push-to-talk
    # --- поведение ---
    "confirm_power": True,
    "sleep_after_min": 10,           # засыпает после N минут бездействия
    "music_url": "https://music.youtube.com",
    "screenshots_dir": "",
    # --- ИИ ---
    "ai_enabled": False,
    "ai_base_url": "https://api.openai.com/v1",
    "ai_api_key": "",
    "ai_model": "gpt-4o-mini",
    "ai_allow_actions": False,       # ИИ может выполнять действия на ПК
    "ai_history_limit": 8,
    "vision_enabled": True,          # анализ скриншотов через ИИ
    "vision_model": "",              # пусто = ai_model
    # --- разрешения ( уровни: safe / normal / god ) ---
    "permission_level": "normal",
    "perm_overrides": {},            # {"shell": "deny", ...}
}


class Config:
    """Потокобезопасное хранилище настроек с сохранением в JSON."""

    def __init__(self, path: str = SETTINGS_FILE):
        self.path = path
        self._lock = threading.RLock()
        self._data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self):
        with self._lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        stored = json.load(f)
                    if isinstance(stored, dict):
                        merged = copy.deepcopy(DEFAULTS)
                        merged.update(stored)
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

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value):
        with self._lock:
            self._data[key] = value

    def as_dict(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._data)

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)
