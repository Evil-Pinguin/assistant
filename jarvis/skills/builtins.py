# -*- coding: utf-8 -*-
"""Встроенные навыки ассистента.

Каждый навык = имя + список регулярок (по нормализованному тексту) + обработчик.
Обработчик возвращает текст для озвучки (или None, если молчим).

Фазы:
  1 — конкретные команды (погода, время, громкость, приложения…);
  2 — «открой/запусти …» (общий разбор), проверяется ПОСЛЕ пользовательских команд,
      чтобы собственные команды имели приоритет.
"""
import datetime
import os
import random
import re
import shutil
import subprocess


from .actions import open_app as _open_app, open_url as _open_url, press as _press, run_shell

try:
    import requests
except ImportError:
    requests = None


# --------------------------------------------------------------------------
# Контекст, который brain передаёт навыкам
# --------------------------------------------------------------------------
class SkillContext:
    def __init__(self, say, log, config, action_ctx, ear=None, voice=None):
        self.say = say
        self.log = log
        self.config = config
        self.action_ctx = action_ctx
        self.ear = ear
        self.voice = voice
        self.pending_confirm = None   # (prompt, callback) — обрабатывает brain

    def confirm(self, prompt: str, fn):
        self.pending_confirm = (prompt, fn)


class Skill:
    def __init__(self, name, patterns, handler, phase=1):
        self.name = name
        self.patterns = [re.compile(p) for p in patterns]
        self.handler = handler
        self.phase = phase


def _name_suffix(config) -> str:
    name = (config.get("user_name") or "").strip()
    return f", {name}" if name else ""


def _greeting_text(config) -> str:
    h = datetime.datetime.now().hour
    if 5 <= h < 12:
        part = "Доброе утро"
    elif 12 <= h < 18:
        part = "Добрый день"
    elif 18 <= h < 23:
        part = "Добрый вечер"
    else:
        part = "Доброй ночи"
    return f"{part}{_name_suffix(config)}! Слушаю вас."


IDENTITY_TEXT = (
    "Я Джарвис — ваш голосовой ассистент. Умею: открывать программы и сайты, искать в "
    "интернете, узнавать погоду и время, делать скриншоты, управлять громкостью и окнами, "
    "выполнять ваши собственные команды. А ещё я отвечаю на любые вопросы через нейросеть, "
    "если она подключена в настройках. Полный список — во вкладке «Команды»."
)

JOKES = [
    "Программист ставит на ночь два стакана: один с водой — попить, второй пустой — не попить.",
    "Заходит компьютерщик в бар. Бармен: «Что будете?» — «Всё равно, лишь бы работало».",
    "— Почему ты не работаешь? — Я в режиме энергосбережения.",
    "Компьютер позволяет решать проблемы, которых раньше не было.",
    "Есть только два типа задач: «сейчас» и «ну это надолго».",
    "Лучший способ ускорить Windows — уронить ноутбук с большой высоты: пока летит, работает быстрее.",
    "Нейросеть спросили, боится ли она темноты. Она ответила: «Только если там выключат сервер».",
    "Мой компьютер и я идеально понимаем друг друга: он висит, и я висю.",
]

SITE_MAP = {
    "ютуб": "https://youtube.com", "youtube": "https://youtube.com",
    "музыка": "https://music.youtube.com",
    "вк": "https://vk.com", "вконтакте": "https://vk.com",
    "гугл": "https://google.com", "google": "https://google.com",
    "почта": "https://mail.ru", "почту": "https://mail.ru", "джимейл": "https://mail.google.com",
    "гитхаб": "https://github.com", "github": "https://github.com",
    "википедия": "https://ru.wikipedia.org", "википедию": "https://ru.wikipedia.org",
    "твиттер": "https://x.com", "икс": "https://x.com",
    "инстаграм": "https://instagram.com",
    "телеграм": "https://web.telegram.org", "чат gpt": "https://chat.openai.com",
    "переводчик": "https://translate.google.com/?sl=ru&tl=en",
    "карты": "https://maps.google.com",
}

# карточки приложений: имя -> (windows, linux-кандидаты)
APP_TABLE = {
    "блокнот": ("notepad", ["gedit", "kate", "mousepad", "xed"]),
    "notepad": ("notepad", ["gedit"]),
    "калькулятор": ("calc", ["gnome-calculator", "kcalc", "xcalc"]),
    "calc": ("calc", ["gnome-calculator"]),
    "паинт": ("mspaint", ["gimp"]),
    "paint": ("mspaint", ["gimp"]),
    "проводник": ("explorer", None),
    "explorer": ("explorer", None),
    "файлы": ("explorer", ["nautilus", "dolphin", "thunar"]),
    "диспетчер задач": ("taskmgr", None),
    "терминал": (None, ["x-terminal-emulator", "gnome-terminal", "konsole", "xterm"]),
    "cmd": ("cmd", None),
    "консоль": (None, ["x-terminal-emulator", "gnome-terminal", "konsole"]),
    "браузер": ("http://google.com", ["xdg-open"]),
    "browser": ("http://google.com", ["xdg-open"]),
    "интернет": ("http://google.com", ["xdg-open"]),
    "word": ("winword", ["lowriter"]),
    "word документ": ("winword", ["lowriter"]),
    "excel": ("excel", ["localc"]),
    "почта приложение": ("msimap", None),
}


def _resolve_app(name: str):
    """Вернуть цель для открытия приложения под текущую ОС или None."""
    if os.name == "nt":
        win, _ = APP_TABLE.get(name, (None, None))
        return win
    _, candidates = APP_TABLE.get(name, (None, None))
    for cand in (candidates or []):
        if shutil.which(cand):
            return None if cand == "xdg-open" else cand
    return None


def _open_named_app(name: str, ctx: SkillContext) -> bool:
    target = _resolve_app(name)
    if target:
        if target.startswith("http"):
            _open_url(target, ctx.action_ctx)
        else:
            _open_app(target, ctx.action_ctx)
        return True
    return False


# --------------------------------------------------------------------------
# Обработчики
# --------------------------------------------------------------------------
def h_greeting(t, m, ctx):
    return _greeting_text(ctx.config)


def h_identity(t, m, ctx):
    return IDENTITY_TEXT


def h_time(t, m, ctx):
    now = datetime.datetime.now()
    return f"Сейчас {now.hour}:{now.minute:02d}{_name_suffix(ctx.config)}."


def h_date(t, m, ctx):
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
    days = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    d = datetime.date.today()
    return f"Сегодня {d.day} {months[d.month - 1]} {d.year} года, {days[d.weekday()]}."


def h_weather(t, m, ctx):
    if requests is None:
        return "Модуль requests не установлен, не могу узнать погоду."
    city = (m.groupdict().get("city") or "").strip() if m else ""
    if not city:
        city = ctx.config.get("city") or "Москва"
    try:
        r = requests.get(f"https://wttr.in/{re.sub(r' ', '%20', city)}?format=j1&lang=ru",
                         timeout=8, headers={"User-Agent": "curl/8"})
        data = r.json()["current_condition"][0]
        ru_desc = data.get("lang_ru") or []
        desc = (ru_desc[0]["value"] if ru_desc else "") or data["weatherDesc"][0]["value"]
        return (f"Погода в {city}: {desc.lower()}, температура {data['temp_C']} градусов, "
                f"ощущается как {data['FeelsLikeC']}.")
    except Exception:
        return f"Не удалось узнать погоду для города {city}."


def h_search(t, m, ctx):
    q = (m.group("q") or "").strip()
    if not q:
        return None
    _open_url(f"https://www.google.com/search?q={q.replace(' ', '+')}", ctx.action_ctx)
    return f"Ищу в Google: {q}"


def h_youtube(t, m, ctx):
    q = (m.group("q") or "").strip()
    if not q:
        _open_url("https://youtube.com", ctx.action_ctx)
        return "Открываю YouTube"
    _open_url(f"https://www.youtube.com/results?search_query={q.replace(' ', '+')}", ctx.action_ctx)
    return f"Ищу на YouTube: {q}"


def h_music(t, m, ctx):
    url = ctx.config.get("music_url", "https://music.youtube.com")
    _open_url(url, ctx.action_ctx)
    return "Включаю музыку"


def h_screenshot(t, m, ctx):
    try:
        from PIL import ImageGrab
    except ImportError:
        _press("prtsc", ctx.action_ctx)
        return "Скриншот в буфере обмена (установите Pillow, чтобы сохранять файлы)"
    folder = ctx.config.get("screenshots_dir") or os.path.join(
        os.path.expanduser("~"), "Pictures" if os.name == "nt" else "Изображения", "Jarvis")
    try:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, datetime.datetime.now().strftime("shot_%Y%m%d_%H%M%S.png"))
        ImageGrab.grab().save(path)
        _open_app(folder, ctx.action_ctx)
        return f"Скриншот сохранён: {os.path.basename(path)}"
    except Exception as exc:
        _press("prtsc", ctx.action_ctx)
        ctx.log(f"Скриншот файлом не удался ({exc}), отправил в буфер обмена", level="error")
        return "Скриншот в буфере обмена"


VOL_UP = re.compile(r"громче|громк\w*\s*(выше|больше)|звук (выше|больше)")
VOL_DOWN = re.compile(r"тише|громк\w*\s*(ниже|меньше)|звук (ниже|меньше)")
VOL_MUTE = re.compile(r"(выключи|убери)\s+(звук|громкость)|без звука|мьют")
VOL_SET = re.compile(r"громкость (?:на )?(\d{1,3})\s*%?")


def h_volume(t, m, ctx):
    from .actions import volume as _volume
    m_set = VOL_SET.search(t)
    if m_set:
        _volume(m_set.group(1), ctx.action_ctx)
        return f"Ставлю громкость на {m_set.group(1)} процентов"
    if VOL_MUTE.search(t):
        _volume("mute", ctx.action_ctx)
        return "Выключаю звук"
    if VOL_UP.search(t):
        _volume("up", ctx.action_ctx)
        return "Делаю громче"
    if VOL_DOWN.search(t):
        _volume("down", ctx.action_ctx)
        return "Делаю тише"
    return None


def h_media(t, m, ctx):
    from .actions import press as _press2
    if re.search(r"следующ|next", t):
        key = "nexttrack"
        reply = "Следующий трек"
    elif re.search(r"предыдущ", t):
        key = "prevtrack"
        reply = "Предыдущий трек"
    else:
        key = "playpause"
        reply = "Переключаю воспроизведение"
    _press2(key, ctx.action_ctx)
    return reply


def h_type(t, m, ctx):
    text = (m.group("text") or "").strip()
    if not text:
        return None
    from .actions import type_text
    type_text(text, ctx.action_ctx)
    return None  # печать — молча


def h_minimize(t, m, ctx):
    _press("win+d" if os.name == "nt" else "ctrl+super+d", ctx.action_ctx)
    return "Сворачиваю все окна"


def h_lock(t, m, ctx):
    if os.name == "nt":
        run_shell("rundll32.exe user32.dll,LockWorkStation", ctx.action_ctx)
    elif sys_darwin():
        run_shell("osascript -e 'tell application \"System Events\" to keystroke \"q\" using "
                  "{command down, control down}'", ctx.action_ctx)
    else:
        run_shell("loginctl lock-session 2>/dev/null || xdg-screensaver lock || "
                  "gnome-screensaver-command -l", ctx.action_ctx)
    return "Блокирую компьютер"


def sys_darwin():
    return __import__("platform").system() == "Darwin"


def _power_cmd(mode: str) -> str:
    if os.name == "nt":
        return f"shutdown /{'r' if mode == 'reboot' else 's'} /t 5"
    if sys_darwin():
        return ("osascript -e 'tell app \"System Events\" to restart'"
                if mode == "reboot" else
                "osascript -e 'tell app \"System Events\" to shut down'")
    return "systemctl reboot" if mode == "reboot" else "systemctl poweroff"


def h_shutdown(t, m, ctx):
    if ctx.config.get("confirm_power", True):
        ctx.confirm("Выключить компьютер?",
                    lambda: run_shell(_power_cmd("shutdown"), ctx.action_ctx))
        return None
    run_shell(_power_cmd("shutdown"), ctx.action_ctx)
    return "Выключаю компьютер через 5 секунд"


def h_reboot(t, m, ctx):
    if ctx.config.get("confirm_power", True):
        ctx.confirm("Перезагрузить компьютер?",
                    lambda: run_shell(_power_cmd("reboot"), ctx.action_ctx))
        return None
    run_shell(_power_cmd("reboot"), ctx.action_ctx)
    return "Перезагружаю компьютер через 5 секунд"


def h_sleep(t, m, ctx):
    if ctx.ear is not None:
        ctx.ear.paused.set()
    if ctx.config.get("require_wake_word", True):
        return "Ухожу в режим ожидания. Скажите кодовое слово, когда я понадоблюсь."
    return "Ухожу в режим ожидания. Разбудить меня можно кнопкой микрофона."


def h_wake(t, m, ctx):
    if ctx.ear is not None:
        ctx.ear.paused.clear()
    return "Проснулся. Слушаю."


def h_joke(t, m, ctx):
    return random.choice(JOKES)


def h_coin(t, m, ctx):
    return "Орёл!" if random.random() < 0.5 else "Решка!"


def h_dice(t, m, ctx):
    return f"Выпало {random.randint(1, 6)}."


def h_forget(t, m, ctx):
    return "__FORGET_HISTORY__"


def h_battery(t, m, ctx):
    try:
        import psutil
        b = psutil.sensors_battery()
        if b:
            status = "заряжается" if b.power_plugged else "работает от батареи"
            return f"Заряд {round(b.percent)} процентов, {status}."
    except ImportError:
        pass
    except Exception:
        pass
    if os.name == "nt":
        out = run_shell("wmic path Win32_Battery get EstimatedChargeRemaining",
                        ctx.action_ctx) or ""
        digits = re.findall(r"\d+", out)
        if digits:
            return f"Заряд {digits[-1]} процентов."
    elif os.path.isdir("/sys/class/power_supply"):
        try:
            for d in os.listdir("/sys/class/power_supply"):
                cap = f"/sys/class/power_supply/{d}/capacity"
                if os.path.exists(cap):
                    with open(cap) as f:
                        return f"Заряд {f.read().strip()} процентов."
        except Exception:
            pass
    return "Не удалось узнать уровень заряда."


def h_wiki(t, m, ctx):
    q = (m.group("q") or "").strip()
    if not q:
        return None
    _open_url(f"https://ru.wikipedia.org/w/index.php?search={q.replace(' ', '+')}", ctx.action_ctx)
    return f"Открываю Википедию: {q}"


def h_open_browser(t, m, ctx):
    """Фаза 2: «открой/запусти …» — приложения, сайты или поиск."""
    what = (m.group("what") or "").strip()
    what = re.sub(r"^(сайт|страницу|страница|приложение|программу|программа)\s+", "", what)
    if not what:
        return None
    if what in APP_TABLE and _open_named_app(what, ctx):
        return f"Открываю {what}"
    if what in SITE_MAP:
        _open_url(SITE_MAP[what], ctx.action_ctx)
        return f"Открываю {what}"
    if what.startswith(("http", "www")) or ("." in what and " " not in what):
        _open_url(what, ctx.action_ctx)
        return f"Открываю {what}"
    # пробуем как приложение «в лоб» (например, steam, discord)
    if " " not in what and (shutil.which(what) or _resolve_app(what)):
        if not _open_named_app(what, ctx):
            _open_app(what, ctx.action_ctx)
        return f"Запускаю {what}"
    _open_url(f"https://www.google.com/search?q={what.replace(' ', '+')}", ctx.action_ctx)
    return f"Не знаю такой адрес, ищу в Google: {what}"


# --------------------------------------------------------------------------
# Реестр навыков
# --------------------------------------------------------------------------
def get_skills() -> list:
    return [
        # --- управление ассистентом ---
        Skill("wake", [r"^(проснись|разбудиться|разбудись|за работу|подъём)$"], h_wake),
        Skill("sleep", [r"^(спи|спать|отдыхай|отбой|в режим ожидания|стоп слушание|усни)$"], h_sleep),
        Skill("greeting", [r"^(привет|здравствуй|здравствуйте|доброе утро|добрый день|"
                           r"добрый вечер|доброй ночи|хай|hello|hi)\b"], h_greeting),
        Skill("identity", [r"(кто ты|что ты умеешь|как тебя зовут|твои возможности|"
                           r"список команд|^помощь$|^справка$|^help$)"], h_identity),
        Skill("forget", [r"(забудь вс|очисти историю|сотри историю|начни с чистого листа)"], h_forget),

        # --- время и погода ---
        Skill("time", [r"(сколько времени|который час|текущее время|время скажи|скажи время)"], h_time),
        Skill("date", [r"(какое сегодня число|какая сегодня дата|какой сегодня день|"
                       r"какой день недели|какое число|какая дата|сегодняшняя дата)"], h_date),
        Skill("weather", [r"погод\w*\s*(?:сегодня\s*)?(?:в\s+(?P<city>[\wа-я\- ]+?)\s*$)?"],
              h_weather),

        # --- интернет ---
        Skill("search", [r"^(?:найди|поищи|поиск|загугли)\s+(?:в\s+гугл\w*\s+)?(?P<q>.+)$"],
              h_search),
        Skill("youtube", [r"(?:на ютубе|в ютубе|ютуб\w*)\s*(?P<q>.*)$"], h_youtube),
        Skill("music", [r"^(включи музыку|поставь музыку|музыку давай|запусти музыку)$"], h_music),
        Skill("wiki", [r"^(?:что такое|кто так(?:ой|ая|ое)|расскажи про)\s+(?P<q>.+)$"], h_wiki),

        # --- система ---
        Skill("screenshot", [r"(скриншот|скрин экрана|снимок экрана|сфотографируй экран)"],
              h_screenshot),
        Skill("volume", [r"громче|тише|громкость|выключи звук|убери звук|без звука"], h_volume),
        Skill("media", [r"пауз\w*|продолжи|возобнови|следующ\w* (трек|песн\w+|видео)|"
                        r"предыдущ\w* (трек|песн\w+)"],
              h_media),
        Skill("minimize", [r"(сверни (все |всё |)окна|сверни все|покажи рабочий стол|рабочий стол покажи)"],
              h_minimize),
        Skill("type", [r"^(?:напечатай|напиши|набери)\s+(?P<text>.+)$"], h_type),
        Skill("battery", [r"(заряд (батареи|аккумулятора|телефона|ноутбука)|уровень заряд\w+|"
                          r"сколько заряд\w+)"], h_battery),

        # --- питание ---
        Skill("lock", [r"заблокируй (комп|экран|пк|систему)"], h_lock),
        Skill("shutdown", [r"(выключи (комп|пк|системник)|заверши работу|выключение компьютера)"],
              h_shutdown),
        Skill("reboot", [r"(перезагрузи|перезапусти) (комп|пк|систему)"], h_reboot),

        # --- развлечения ---
        Skill("joke", [r"(анекдот|шутк\w+|рассмеши|пошути|поприкол\w+)"], h_joke),
        Skill("coin", [r"(подбрось монет\w+|брось монет\w+|монетка|орёл или решка)"], h_coin),
        Skill("dice", [r"(брось кубик|кинь кубик|кубик брось)"], h_dice),

        # --- фаза 2: общий «открой …» ---
        Skill("open_generic", [r"^(?:открой|запусти|включи)\s+(?P<what>.+)$"],
              h_open_browser, phase=2),
    ]
