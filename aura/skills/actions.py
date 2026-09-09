# -*- coding: utf-8 -*-
"""Исполнитель действий AURA (Tool Router).

Каждое действие:
  1) проходит через систему разрешений (allow / confirm / deny);
  2) выполняется;
  3) попадает в Центр активности с функцией отмены, если это возможно.

ИИ не имеет прямого доступа к системе — он предлагает действия блоком,
а выполняет их этот модуль.
"""
import os
import shutil
import subprocess
import time
import webbrowser

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# категория разрешения для каждого типа действия
CATEGORY_OF = {
    "open_url": "browser_open", "url": "browser_open",
    "open_app": "app_launch", "app": "app_launch", "open": "app_launch",
    "open_file": "files_read",
    "close_app": "app_close",
    "shell": "shell", "cmd": "shell",
    "run_python": "python",
    "type_text": None, "type": None,          # автоматизация — всегда разрешена
    "press": None, "hotkey": None,
    "click": None, "mouse_move": None, "scroll": None,
    "volume": "system_volume",
    "brightness": "system_brightness",
    "create_folder": "files_modify",
    "write_file": "files_modify",
    "zip_folder": "files_modify",
    "rename_path": "files_modify",
    "move_path": "files_modify",
    "delete_path": "files_delete",
    "power": "power",
    "say": None, "wait": None,
}


class ActionContext:
    """Всё, что нужно действиям: сказать, лог, конфиг, разрешения, активность."""

    def __init__(self, say, log, config, permissions=None, activity=None):
        self.say = say
        self.log = log
        self.config = config
        self.permissions = permissions
        self.activity = activity


def _expand(p: str) -> str:
    return os.path.expandvars(os.path.expanduser(p or ""))


# --------------------------------------------------------------------------
# обработчики действий
# --------------------------------------------------------------------------
def open_url(target, ctx):
    if not target:
        return "Открыть сайт", None
    if not target.startswith(("http://", "https://", "file://")):
        target = "https://" + target
    webbrowser.open(target)
    return f"Открыт сайт {target}", None


def open_app(target, ctx):
    target = _expand(target)
    if not target:
        return "Пустой запуск", None
    desc = f"Запуск: {os.path.basename(target) or target}"
    try:
        if os.name == "nt":
            try:
                os.startfile(target)  # noqa: App Paths, exe, файлы, папки
            except OSError:
                # имя приложения (krita, unityhub...) — ищем через shell
                subprocess.Popen(["start", "", target], shell=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=CREATE_NO_WINDOW)
            return desc, None
        if os.path.isfile(target) and os.access(target, os.X_OK):
            subprocess.Popen([target], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        elif shutil.which(target):
            subprocess.Popen(shlex_split(target), stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        return desc, None
    except Exception as exc:
        raise RuntimeError(f"не удалось открыть «{target}»: {exc}")


def shlex_split(s):
    import shlex
    try:
        return shlex.split(s)
    except ValueError:
        return [s]


def close_app(target, ctx):
    """Мягко закрыть приложение по имени процесса."""
    name = (target or "").strip().lower()
    if not name:
        return "Пустое имя", None
    try:
        import psutil
    except ImportError:
        raise RuntimeError("нужен пакет psutil")
    killed = 0
    procs = []
    for p in psutil.process_iter(["name", "exe"]):
        pname = (p.info.get("name") or "").lower()
        if name in pname:
            procs.append(p)
    if not procs:
        return f"Закрытие {name}: процесс не найден", None
    undo = None
    for p in procs[:10]:
        try:
            exe = p.info.get("exe")
            p.terminate()
            killed += 1
            if exe and undo is None:
                def _reopen(path=exe):
                    open_app(path, ctx)
                undo = _reopen
        except Exception:
            pass
    return f"Закрыто процессов {name}: {killed}", undo


def run_shell(target, ctx):
    if not target:
        return "Пустая команда", None
    try:
        r = subprocess.run(target, shell=True, capture_output=True, text=True,
                           timeout=30, creationflags=CREATE_NO_WINDOW)
        out = (r.stdout or r.stderr or "").strip()
        return f"$ {target}" + (f" → {out[:120]}" if out else ""), None
    except Exception as exc:
        raise RuntimeError(f"ошибка команды: {exc}")


def run_python(target, ctx):
    """Запустить Python-код в изолированном процессе."""
    if not target:
        return "Пустой код", None
    code_file = os.path.join(os.path.expanduser("~"), ".aura_snippet.py")
    try:
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(target)
        r = subprocess.run(["python" if os.name == "nt" else "python3", code_file],
                           capture_output=True, text=True, timeout=30,
                           creationflags=CREATE_NO_WINDOW)
        out = (r.stdout or r.stderr or "").strip()
        return "Python: " + (out[:150] or "выполнено"), None
    except Exception as exc:
        raise RuntimeError(f"ошибка python: {exc}")


def type_text(target, ctx):
    if not target:
        return "Печать текста", None
    try:
        import pyperclip
        import pyautogui
        pyperclip.copy(target)
        pyautogui.hotkey("ctrl", "v")
        return f"Вставлен текст ({len(target)} симв.)", None
    except ImportError:
        try:
            import pyautogui
            pyautogui.typewrite(target, interval=0.02)
            return "Напечатан текст (латиницей)", None
        except ImportError:
            raise RuntimeError("нужен пакет pyautogui")


def press(target, ctx):
    if not target:
        return "Клавиши", None
    try:
        import pyautogui
        aliases = {"win": "winleft", "super": "winleft", "cmd": "winleft",
                   "meta": "winleft", "prtsc": "printscreen"}
        keys = [aliases.get(k.strip().lower(), k.strip().lower())
                for k in target.split("+") if k.strip()]
        pyautogui.hotkey(*keys)
        return f"Нажато: {target}", None
    except ImportError:
        raise RuntimeError("нужен пакет pyautogui")


def click(target, ctx):
    try:
        import pyautogui
        if target and "," in target:
            x, y = [int(v.strip()) for v in target.split(",")[:2]]
            pyautogui.click(x, y)
            return f"Клик {x},{y}", None
        pyautogui.click()
        return "Клик", None
    except ImportError:
        raise RuntimeError("нужен пакет pyautogui")


def mouse_move(target, ctx):
    import pyautogui
    x, y = [int(v.strip()) for v in (target or "0,0").split(",")[:2]]
    pyautogui.moveTo(x, y, duration=0.2)
    return f"Курсор → {x},{y}", None


def scroll(target, ctx):
    try:
        import pyautogui
        amount = int(str(target or "-300").split(",")[0])
        pyautogui.scroll(amount)
        return f"Прокрутка {amount}", None
    except ImportError:
        raise RuntimeError("нужен пакет pyautogui")


def volume(target, ctx):
    key = str(target).lower().strip()
    try:
        import pyautogui
        mapping = {"up": "volumeup", "выше": "volumeup", "вверх": "volumeup",
                   "down": "volumedown", "ниже": "volumedown", "вниз": "volumedown",
                   "mute": "volumemute", "выкл": "volumemute", "выключи": "volumemute",
                   "тише": "volumedown", "громче": "volumeup"}
        if key in mapping:
            pyautogui.press(mapping[key])
            return f"Громкость: {key}", None
        if key.isdigit():
            steps = abs(int(key) - 50) // 2
            keyname = "volumeup" if int(key) >= 50 else "volumedown"
            for _ in range(steps):
                pyautogui.press(keyname)
            return f"Громкость ≈ {key}%", None
        raise RuntimeError(f"не понял громкость «{target}»")
    except ImportError:
        raise RuntimeError("нужен пакет pyautogui")


def _brightness_windows():
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
             ".WmiSetBrightness(1, %d)" % int(0)],
            capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def brightness(target, ctx):
    val = int(str(target).strip("% "))
    val = max(5, min(100, val))
    if os.name == "nt":
        ok = _brightness_windows() if False else None
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                 f".WmiSetBrightness(1, {val})"],
                capture_output=True, timeout=15, creationflags=CREATE_NO_WINDOW)
            return f"Яркость {val}%", None
        except Exception as exc:
            raise RuntimeError(f"яркость не изменилась: {exc}")
    if shutil.which("brightnessctl"):
        run_shell(f"brightnessctl set {val}%", ctx)
        return f"Яркость {val}%", None
    raise RuntimeError("управление яркостью недоступно на этой системе")


def create_folder(target, ctx):
    path = _expand(target)
    if not path:
        raise RuntimeError("не указана папка")
    os.makedirs(path, exist_ok=False)

    def undo():
        try:
            os.rmdir(path)
        except OSError:
            pass
    return f"Создана папка {path}", undo


def write_file(target, ctx):
    """target: 'путь | содержимое'"""
    if "|" in target:
        path, content = target.split("|", 1)
    else:
        path, content = target, ""
    path = _expand(path.strip())
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    existed = os.path.exists(path)
    old = ""
    if existed:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            old = f.read()
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    def undo():
        if existed:
            with open(path, "w", encoding="utf-8") as f:
                f.write(old)
        else:
            try:
                os.remove(path)
            except OSError:
                pass
    return f"Записан файл {os.path.basename(path)}", undo


def zip_folder(target, ctx):
    path = _expand(target)
    if not os.path.isdir(path):
        raise RuntimeError(f"папка не найдена: {path}")
    base = shutil.make_archive(path.rstrip("/\\") + "_zip", "zip", path)

    def undo():
        try:
            os.remove(base)
        except OSError:
            pass
    return f"ZIP создан: {os.path.basename(base)}", undo


def rename_path(target, ctx):
    if "|" not in target:
        raise RuntimeError("формат: старый путь | новый путь")
    src, dst = [_expand(p.strip()) for p in target.split("|", 1)]
    if not os.path.exists(src):
        raise RuntimeError(f"не найдено: {src}")
    os.rename(src, dst)

    def undo():
        try:
            os.rename(dst, src)
        except OSError:
            pass
    return f"Переименовано в {os.path.basename(dst)}", undo


def move_path(target, ctx):
    if "|" not in target:
        raise RuntimeError("формат: откуда | куда")
    src, dst = [_expand(p.strip()) for p in target.split("|", 1)]
    if not os.path.exists(src):
        raise RuntimeError(f"не найдено: {src}")
    shutil.move(src, dst)

    def undo():
        try:
            shutil.move(dst, src)
        except OSError:
            pass
    return f"Перемещено {os.path.basename(src)}", undo


def delete_path(target, ctx):
    path = _expand(target)
    if not os.path.exists(path):
        raise RuntimeError(f"не найдено: {path}")
    # безопасная «корзина»: перемещаем в ~/.aura_trash вместо удаления
    trash = os.path.join(os.path.expanduser("~"), ".aura_trash")
    os.makedirs(trash, exist_ok=True)
    dst = os.path.join(trash, os.path.basename(path) + f".{int(time.time())}")
    shutil.move(path, dst)

    def undo():
        try:
            shutil.move(dst, path)
        except OSError:
            pass
    return f"Удалено (в корзине AURA): {os.path.basename(path)}", undo


def power(target, ctx):
    mode = (target or "shutdown").lower()
    if os.name == "nt":
        cmd = f"shutdown /{'r' if mode == 'reboot' else 's'} /t 5"
    else:
        cmd = ("systemctl reboot" if mode == "reboot" else "systemctl poweroff")
    run_shell(cmd, ctx)
    return "Выключение компьютера" if mode != "reboot" else "Перезагрузка", None


def wait(target, ctx):
    try:
        time.sleep(min(float(target or 1), 30))
    except (TypeError, ValueError):
        pass
    return "Пауза", None


def say(target, ctx):
    ctx.say(target or "")
    return f"Фраза: {(target or '')[:50]}", None


HANDLERS = {
    "open_url": open_url, "url": open_url,
    "open_app": open_app, "app": open_app, "open": open_app,
    "open_file": open_app,
    "close_app": close_app,
    "shell": run_shell, "cmd": run_shell,
    "run_python": run_python, "python": run_python,
    "type_text": type_text, "type": type_text,
    "press": press, "hotkey": press,
    "click": click,
    "mouse_move": mouse_move,
    "scroll": scroll,
    "volume": volume,
    "brightness": brightness,
    "create_folder": create_folder, "mkdir": create_folder,
    "write_file": write_file,
    "zip_folder": zip_folder, "zip": zip_folder,
    "rename_path": rename_path, "rename": rename_path,
    "move_path": move_path, "move": move_path,
    "delete_path": delete_path, "delete": delete_path,
    "power": power,
    "wait": wait, "sleep": wait,
    "say": say,
}

_EXTRA_HANDLERS = {}


def register_action(action_type, fn):
    """Расширение из плагинов: новый тип действия."""
    _EXTRA_HANDLERS[action_type.lower()] = fn


def _handler_for(kind):
    return HANDLERS.get(kind) or _EXTRA_HANDLERS.get(kind)


# --------------------------------------------------------------------------
# выполнение со схемой разрешений
# --------------------------------------------------------------------------
def execute_action(action, ctx: ActionContext, say_enabled=True):
    """Одно действие. Возвращает (ok, описание)."""
    if not isinstance(action, dict):
        return False, "неверное действие"
    kind = str(action.get("type", "")).strip().lower()
    target = str(action.get("target", action.get("text", action.get("value", "")) or ""))
    fn = _handler_for(kind)
    if fn is None:
        ctx.log(f"Неизвестный тип действия: «{kind}»", level="error")
        return False, f"неизвестный тип «{kind}»"

    cat = CATEGORY_OF.get(kind)
    if cat and ctx.permissions is not None:
        mode = ctx.permissions.gate(cat)
        if mode == "deny":
            ctx.log(f"Действие «{kind}» заблокировано разрешениями "
                    f"({ctx.permissions.level.upper()}).", level="error")
            return False, f"«{kind}» запрещено настройками"
        if mode == "confirm":
            # подтверждение обрабатывается ДО запуска (см. brain),
            # здесь считаем, что оно уже получено
            pass
    try:
        desc, undo = fn(target, ctx)
    except Exception as exc:
        ctx.log(f"Ошибка действия «{kind}»: {exc}", level="error")
        return False, f"ошибка «{kind}»"
    if ctx.activity is not None and kind != "wait":
        ctx.activity.add(desc or kind, kind=kind, undo=undo,
                         icon="🧩" if kind != "say" else "🗣")
    return True, desc or kind


def collect_categories(actions) -> set:
    cats = set()
    for a in actions or []:
        if isinstance(a, dict):
            cat = CATEGORY_OF.get(str(a.get("type", "")).lower())
            if cat:
                cats.add(cat)
    return cats


def check_confirm_needed(actions, permissions) -> list:
    """Категории, требующие подтверждения на текущем уровне разрешений."""
    needed = []
    for cat in sorted(collect_categories(actions)):
        if permissions is not None and permissions.gate(cat) == "confirm":
            needed.append(cat)
    return needed


def strip_denied(actions, permissions):
    """Убрать действия, запрещённые настройками. Возвращает (список, убранные)."""
    keep, dropped = [], []
    for a in actions or []:
        if isinstance(a, dict):
            cat = CATEGORY_OF.get(str(a.get("type", "")).lower())
            if cat and permissions is not None and permissions.gate(cat) == "deny":
                dropped.append(a.get("type"))
                continue
        keep.append(a)
    return keep, dropped


def execute_actions(actions, ctx: ActionContext) -> int:
    ok = 0
    for action in actions or []:
        if execute_action(action, ctx):
            ok += 1
    return ok
