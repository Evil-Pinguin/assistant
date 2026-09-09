# -*- coding: utf-8 -*-
"""Пользовательские команды из data/custom_commands.json.

Формат:
{
  "commands": [
    {
      "name": "Рабочая папка",
      "phrases": ["открой рабочую папку", "рабочая папка"],
      "actions": [
        {"type": "open_app", "target": "~"},
        {"type": "say", "text": "Открываю рабочую папку"}
      ]
    }
  ]
}

Действия: open_url, open_app, shell, type_text, press, volume, say, wait.
Можно задать "pattern" (регулярное выражение) вместо phrases — для продвинутых.
"""
import difflib
import json
import os
import re
import threading

from ..config import COMMANDS_FILE


class CustomCommands:
    def __init__(self, path: str = COMMANDS_FILE, emit=None):
        self.path = path
        self.emit = emit or (lambda *a, **k: None)
        self._lock = threading.RLock()
        self.commands = []
        self.load()

    # ---------- файл ----------
    def load(self):
        with self._lock:
            if not os.path.exists(self.path):
                self.commands = []
                return
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.commands = [c for c in data.get("commands", [])
                                 if isinstance(c, dict) and c.get("actions")]
            except (OSError, json.JSONDecodeError) as exc:
                self.emit("log", level="error",
                          msg=f"Не удалось прочитать {os.path.basename(self.path)}: {exc}")
                self.commands = []

    def save(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"commands": self.commands}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        self.emit("log", level="system", msg="Свои команды сохранены.")

    # ---------- CRUD для GUI ----------
    def upsert(self, command: dict):
        """Добавить или обновить команду по имени."""
        with self._lock:
            name = (command.get("name") or "").strip()
            for i, existing in enumerate(self.commands):
                if (existing.get("name") or "").strip() == name:
                    self.commands[i] = command
                    break
            else:
                self.commands.append(command)
            self.save()

    def delete(self, name: str):
        with self._lock:
            self.commands = [c for c in self.commands
                             if (c.get("name") or "").strip() != name]
            self.save()

    def get(self, name: str):
        with self._lock:
            for c in self.commands:
                if (c.get("name") or "").strip() == name:
                    return c
        return None

    def names(self):
        with self._lock:
            return [c.get("name", "без имени") for c in self.commands]

    # ---------- сопоставление ----------
    @staticmethod
    def normalize(text: str) -> str:
        text = (text or "").lower().replace("ё", "е")
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()

    def match(self, text: str):
        """Найти команду: точная фраза > начало фразы > нечёткое совпадение > regex.

        Возвращает (команда, ответ_для_озвучки|None) или (None, None).
        """
        norm = self.normalize(text)
        if not norm:
            return None, None
        best, best_score = None, 0.0
        with self._lock:
            for cmd in self.commands:
                # regex-режим для продвинутых
                pattern = cmd.get("pattern")
                if pattern:
                    try:
                        if re.search(pattern, norm):
                            return cmd, cmd.get("reply")
                    except re.error as exc:
                        self.emit("log", level="error",
                                  msg=f"Ошибка в regex команды «{cmd.get('name')}»: {exc}")
                phrases = [self.normalize(p) for p in cmd.get("phrases", []) if p]
                for phrase in phrases:
                    if not phrase:
                        continue
                    if norm == phrase:
                        return cmd, cmd.get("reply")
                    if norm.startswith(phrase) or phrase.startswith(norm):
                        score = 0.9
                    else:
                        score = difflib.SequenceMatcher(None, norm, phrase).ratio()
                    if score > best_score and score >= 0.75:
                        best, best_score = cmd, score
        if best is not None and best_score < 0.9:
            self.emit("log", level="system",
                      msg=f"Схожая команда «{best.get('name')}» (совпадение {best_score:.0%})")
        return best, (best.get("reply") if best else None)
