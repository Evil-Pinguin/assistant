# -*- coding: utf-8 -*-
"""Плагины AURA: папка plugins/*.py с функцией register(api).

api-объект даёт плагину:
  api.say(text)              — озвучить
  api.log(msg, level=...)    — в журнал
  api.add_skill(name, patterns, handler) — своя встроенная команда
  api.add_action(type, fn)   — новый тип действия
  api.config, api.memory     — доступ к подсистемам
"""
import importlib.util
import os

from .config import PLUGINS_DIR


class AuraAPI:
    def __init__(self, brain):
        self.brain = brain
        self.config = brain.config
        self.memory = brain.memory

    def say(self, text):
        self.brain.say(text)

    def log(self, msg, level="system"):
        self.brain._log(msg, level=level)

    def add_skill(self, name, patterns, handler):
        from .skills.builtins import Skill
        self.brain.skills.append(Skill(name, patterns, handler))

    def add_action(self, action_type, fn):
        from .skills import actions as A
        A.register_action(action_type, fn)


def load_plugins(brain) -> list:
    """Загрузить все плагины. Возвращает список имён."""
    api = AuraAPI(brain)
    loaded = []
    if not os.path.isdir(PLUGINS_DIR):
        return loaded
    for fname in sorted(os.listdir(PLUGINS_DIR)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        path = os.path.join(PLUGINS_DIR, fname)
        try:
            spec = importlib.util.spec_from_file_location(f"aura_plugin_{fname[:-3]}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "register"):
                module.register(api)
                loaded.append(fname[:-3])
        except Exception as exc:
            brain._log(f"Плагин {fname} не загрузился: {exc}", level="error")
    if loaded:
        brain._log(f"Плагины загружены: {', '.join(loaded)}")
    return loaded
