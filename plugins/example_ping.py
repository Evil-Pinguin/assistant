# -*- coding: utf-8 -*-
"""Пример плагина AURA.

AURA вызывает register(api) при старте. Так можно добавить:
  - свои команды (api.add_skill)
  - новые типы действий (api.add_action)
  - просто говорить и писать в журнал.
"""


def register(api):
    def h_ping(t, m, ctx):
        try:
            import time as _t
            import requests
            t0 = _t.time()
            requests.get("https://1.1.1.1", timeout=5)
            ms = round((_t.time() - t0) * 1000)
            return f"Интернет на связи, отклик {ms} мс."
        except Exception:
            return "Интернета нет. Как я тогда отвечаю? Магия."

    api.add_skill("ping", [r"(пинг|проверь интернет|есть ли интернет|сеть есть)"], h_ping)
    api.log("Плагин ping загружен: скажите «пинг».")
