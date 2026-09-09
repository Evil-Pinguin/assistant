# -*- coding: utf-8 -*-
"""Application Resolver: находит приложение по человеческому имени.

Приоритет поиска:
  1. реестр пользователя (data/settings.json → app_registry)
  2. встроенные алиасы (браузер → chrome, код → code…)
  3. PATH (shutil.which)
  4. ярлыки Start Menu / рабочего стола (Windows .lnk)
  5. уже запущенный процесс (psutil) → «уже открыт»

resolve("браузер") → ("chrome", "alias") | ("C:/.../chrome.exe", "path") | None
"""
import difflib
import os
import shutil


# встроенные алиасы: что мог сказать человек → что искать
BUILTIN_ALIASES = {
    "браузер": "chrome", "хром": "chrome", "chrome": "chrome",
    "код": "code", "вс код": "code", "vs code": "code", "визуал студио код": "code",
    "терминал": "terminal", "консоль": "terminal",
    "блокнот": "notepad", "калькулятор": "calc",
    "проводник": "explorer", "файлы": "explorer",
    "диспетчер задач": "taskmgr",
    "крита": "krita", "криту": "krita",
    "блендер": "blender", "блендера": "blender",
    "юнити": "unityhub", "юнити хаб": "unityhub",
    "дискорд": "discord", "спотифай": "spotify",
    "стим": "steam", "обс": "obs",
}

# «фотошопчик» → photoshop и т.п.
SYNONYMS = {
    "фотошоп": "photoshop", "фотошопчик": "photoshop", "фотошопу": "photoshop",
    "фотошопа": "photoshop", "ворд": "winword", "эксель": "excel",
    "почта": "outlook", "телеграм": "telegram", "телегу": "telegram",
    "вацап": "whatsapp", "ватсап": "whatsapp", "хромиум": "chromium",
}

# чем можно заменить то, чего обычно нет в системе
ALTERNATIVES = {
    "photoshop": ["krita", "gimp", "paint"],
    "premiere": ["davinci resolve", "shotcut", "openshot"],
    "winword": ["libreoffice writer", "notepad", "wordpad"],
    "excel": ["libreoffice calc"],
    "outlook": ["thunderbird"],
    "winrar": ["7zip", "7-zip"],
    "itunes": ["spotify"],
}


def suggest(name, config=None, extra=(), installed=None, limit=3):
    """Похожие приложения для «красивой ошибки».

    Порядок: синоним → известные замены → difflib по пулу имён.
    installed(target) -> bool; по умолчанию — resolve().
    """
    key = (name or "").strip().lower()
    if not key:
        return []
    registry = (config.get("app_registry") or {}) if config else {}
    syn = SYNONYMS.get(key)
    cands = []
    if syn:
        cands.append(syn)
        cands += ALTERNATIVES.get(syn, [])
    cands += ALTERNATIVES.get(key, [])
    pool = (list(BUILTIN_ALIASES.keys()) + list(BUILTIN_ALIASES.values())
            + [k.lower() for k in registry] + [v.lower() for v in registry.values()]
            + [e.lower() for e in extra])
    try:
        cands += difflib.get_close_matches(key, sorted(set(pool)),
                                           n=limit * 3, cutoff=0.6)
    except Exception:
        pass
    check = installed or (lambda t: resolve(t, config)[0] is not None)
    seen, out = {key}, []
    for c in cands:
        c = str(c).strip().lower()
        if not c or c in seen:
            continue
        seen.add(c)
        try:
            if check(c):
                out.append(c)
        except Exception:
            pass
        if len(out) >= limit:
            break
    return out


# папки ярлыков Windows
def _shortcut_dirs():
    home = os.path.expanduser("~")
    programdata = os.environ.get("ProgramData", "C:/ProgramData")
    appdata = os.environ.get("AppData", os.path.join(home, "AppData", "Roaming"))
    return [
        os.path.join(programdata, "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(home, "Desktop"),
        os.path.join(home, "Рабочий стол"),
    ]


def _find_shortcut(query, extra_depth=1):
    """Ищет .lnk/.desktop, содержащий query, в меню Пуск и на рабочем столе."""
    q = query.lower()
    best = None
    for root in _shortcut_dirs():
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = dirnames[:extra_depth * 8] if len(dirnames) > 24 else dirnames
            for f in filenames:
                fl = f.lower()
                if fl.endswith((".lnk", ".desktop")) and q in fl:
                    score = 0 if fl.startswith(q) else 1
                    if best is None or score < best[0]:
                        best = (score, os.path.join(dirpath, f))
    return best[1] if best else None


def _running_process(query):
    try:
        import psutil
        q = query.lower()
        for p in psutil.process_iter(["name"]):
            pname = (p.info.get("name") or "").lower()
            if q and q in pname:
                return pname
    except Exception:
        pass
    return None


def resolve(name: str, config=None):
    """Найти приложение. Возвращает (цель, способ) или (None, None)."""
    if not name:
        return None, None
    key = name.strip().lower()
    registry = (config.get("app_registry") or {}) if config else {}
    aliases = dict(BUILTIN_ALIASES)
    aliases.update({k.lower(): v for k, v in registry.items()})

    target = aliases.get(key, key)

    # 1) реестр может хранить готовый путь
    if target in registry and (registry[target] or "").strip():
        return registry[target], "registry"

    # 2) PATH
    which = shutil.which(target)
    if which:
        return which, "path"

    # 3) ярлыки в меню Пуск / на рабочем столе (Windows)
    if os.name == "nt":
        lnk = _find_shortcut(target)
        if lnk:
            return lnk, "shortcut"

    # 4) уже запущено?
    if _running_process(target):
        return target, "running"

    return None, None


def describe_method(method):
    return {"registry": "из реестра приложений", "path": "найдено в системе",
            "shortcut": "найден ярлык", "running": "уже запущено"}.get(method, method or "")
