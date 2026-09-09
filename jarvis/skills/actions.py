# -*- coding: utf-8 -*-
"""Исполнитель действий для своих команд и для ИИ.

Поддерживаемые типы:
  open_url   — открыть ссылку
  open_app   — открыть приложение/файл/папку
  shell      — выполнить команду системы
  type_text  — напечатать текст в активное окно
  press      — нажать горячие клавиши ("win+d", "ctrl+shift+esc")
  volume     — громкость: up / down / mute / 0-100
  say        — озвучить текст
  wait       — пауза, секунды
"""
import os
import shlex
import shutil
import subprocess
import time
import webbrowser

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class ActionContext:
    """Всё, что нужно действиям: сказать, лог, конфиг."""

    def __init__(self, say, log, config):
        self.say = say
        self.log = log
        self.config = config


def _expand(p: str) -> str:
    return os.path.expandvars(os.path.expanduser(p))


def open_url(target: str, ctx: ActionContext):
    if not target:
        return
    if not target.startswith(("http://", "https://", "file://")):
        target = "https://" + target
    webbrowser.open(target)
    ctx.log(f"Открываю {target}")


def open_app(target: str, ctx: ActionContext):
    target = _expand(target)
    if not target:
        return
    try:
        if os.name == "nt":
            os.startfile(target)  # noqa: приложений, файлов и ссылок
        elif os.path.exists(target) or shutil.which(target):
            subprocess.Popen(shlex.split(target) if shutil.which(target) else [target],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", target],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ctx.log(f"Запускаю: {target}")
    except Exception as exc:
        ctx.log(f"Не удалось открыть «{target}»: {exc}", level="error")


def run_shell(target: str, ctx: ActionContext):
    if not target:
        return
    try:
        r = subprocess.run(target, shell=True, capture_output=True, text=True, timeout=30,
                           creationflags=CREATE_NO_WINDOW)
        out = (r.stdout or r.stderr or "").strip()
        ctx.log(f"$ {target}" + (f"\n{out[:400]}" if out else ""))
        return out
    except Exception as exc:
        ctx.log(f"Ошибка команды «{target}»: {exc}", level="error")


def type_text(target: str, ctx: ActionContext):
    if not target:
        return
    try:
        import pyperclip
        import pyautogui
        pyperclip.copy(target)
        pyautogui.hotkey("ctrl", "v")
        ctx.log(f"Вставлен текст: {target[:60]}")
    except ImportError:
        try:
            import pyautogui
            pyautogui.typewrite(target, interval=0.02)  # latin-only
            ctx.log(f"Напечатан текст (латиницей): {target[:60]}")
        except ImportError:
            ctx.log("Нужен пакет pyautogui (pip install pyautogui pyperclip)", level="error")
    except Exception as exc:
        ctx.log(f"Не удалось напечатать текст: {exc}", level="error")


HOTKEY_ALIASES = {"win": "winleft", "super": "winleft", "cmd": "winleft",
                  "meta": "winleft", "prtsc": "printscreen"}


def press(target: str, ctx: ActionContext):
    if not target:
        return
    try:
        import pyautogui
        keys = [HOTKEY_ALIASES.get(k.strip().lower(), k.strip().lower())
                for k in target.split("+") if k.strip()]
        pyautogui.hotkey(*keys)
        ctx.log(f"Нажато: {target}")
    except ImportError:
        ctx.log("Нужен пакет pyautogui (pip install pyautogui)", level="error")
    except Exception as exc:
        ctx.log(f"Не удалось нажать «{target}»: {exc}", level="error")


def volume(target: str, ctx: ActionContext):
    key = str(target).lower().strip()
    try:
        import pyautogui
        mapping = {"up": "volumeup", "выше": "volumeup", "вверх": "volumeup",
                   "down": "volumedown", "ниже": "volumedown", "вниз": "volumedown",
                   "mute": "volumemute", "выкл": "volumemute",
                   "выключи": "volumemute", "тише": "volumedown", "громче": "volumeup"}
        if key in mapping:
            pyautogui.press(mapping[key])
        elif key.isdigit():
            steps = int(key) // 2
            for _ in range(steps):
                pyautogui.press("volumeup" if int(key) > 50 else "volumedown")
        ctx.log(f"Громкость: {target}")
    except ImportError:
        ctx.log("Нужен пакет pyautogui (pip install pyautogui)", level="error")
    except Exception as exc:
        ctx.log(f"Не удалось изменить громкость: {exc}", level="error")


def wait(seconds, ctx: ActionContext):
    try:
        time.sleep(min(float(seconds), 30))
    except (TypeError, ValueError):
        pass


def execute_action(action: dict, ctx: ActionContext):
    """Выполнить одно действие-словарь. Возвращает True при успехе."""
    if not isinstance(action, dict):
        return False
    kind = str(action.get("type", "")).strip().lower()
    target = str(action.get("target", action.get("text", action.get("value", ""))))
    handlers = {
        "open_url": open_url, "url": open_url,
        "open_app": open_app, "app": open_app, "open": open_app,
        "shell": run_shell, "cmd": run_shell,
        "type_text": type_text, "type": type_text,
        "press": press, "hotkey": press,
        "volume": volume,
        "wait": wait, "sleep": wait,
    }
    if kind == "say":
        ctx.say(target)
        return True
    fn = handlers.get(kind)
    if fn is None:
        ctx.log(f"Неизвестный тип действия: «{kind}»", level="error")
        return False
    try:
        fn(target, ctx)
        return True
    except Exception as exc:
        ctx.log(f"Ошибка действия «{kind}»: {exc}", level="error")
        return False


def execute_actions(actions, ctx: ActionContext) -> int:
    ok = 0
    for action in actions or []:
        if execute_action(action, ctx):
            ok += 1
    return ok
