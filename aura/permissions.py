# -*- coding: utf-8 -*-
"""Система разрешений AURA: SAFE / NORMAL / GOD MODE + переопределения.

gate(категория) -> "allow" | "confirm" | "deny"
Категории: app_launch, app_close, browser_open, browser_forms, browser_purchase,
           files_read, files_modify, files_delete, shell, python,
           system_volume, system_brightness, power, ai_actions
"""
import threading

CATEGORIES = [
    ("app_launch", "Запуск приложений"),
    ("app_close", "Закрытие приложений"),
    ("browser_open", "Открытие сайтов"),
    ("browser_forms", "Заполнение форм"),
    ("browser_purchase", "Покупки / отправка"),
    ("files_read", "Чтение файлов"),
    ("files_modify", "Изменение файлов"),
    ("files_delete", "Удаление файлов"),
    ("shell", "Команды системы"),
    ("python", "Запуск Python-кода"),
    ("system_volume", "Громкость"),
    ("system_brightness", "Яркость"),
    ("power", "Выключение / перезагрузка"),
    ("ai_actions", "Действия через ИИ"),
]

LEVELS = {
    "safe": {
        "app_launch": "allow", "app_close": "allow", "browser_open": "allow",
        "browser_forms": "deny", "browser_purchase": "deny",
        "files_read": "allow", "files_modify": "confirm", "files_delete": "deny",
        "shell": "deny", "python": "deny", "system_volume": "allow",
        "system_brightness": "allow", "power": "deny", "ai_actions": "deny",
    },
    "normal": {
        "app_launch": "allow", "app_close": "allow", "browser_open": "allow",
        "browser_forms": "confirm", "browser_purchase": "deny",
        "files_read": "allow", "files_modify": "allow", "files_delete": "confirm",
        "shell": "confirm", "python": "confirm", "system_volume": "allow",
        "system_brightness": "allow", "power": "confirm", "ai_actions": "confirm",
    },
    "god": {cat: "allow" for cat, _ in CATEGORIES},
}

LEVEL_TITLES = {"safe": "SAFE — безопасный", "normal": "NORMAL — обычный",
                "god": "GOD MODE — полный контроль"}


class Permissions:
    def __init__(self, config):
        self.config = config
        self._lock = threading.RLock()

    @property
    def level(self) -> str:
        lvl = self.config.get("permission_level", "normal")
        return lvl if lvl in LEVELS else "normal"

    def set_level(self, level: str):
        if level in LEVELS:
            self.config.set("permission_level", level)
            self.config.set("perm_overrides", {})
            self.config.save()

    def gate(self, category: str) -> str:
        with self._lock:
            overrides = self.config.get("perm_overrides") or {}
            if category in overrides:
                return overrides[category]
            return LEVELS[self.level].get(category, "deny")

    def set_override(self, category: str, mode: str):
        if category not in LEVELS["normal"] or mode not in ("allow", "confirm", "deny"):
            return
        with self._lock:
            overrides = dict(self.config.get("perm_overrides") or {})
            overrides[category] = mode
            self.config.set("perm_overrides", overrides)
            self.config.save()

    def overrides(self) -> dict:
        return dict(self.config.get("perm_overrides") or {})
