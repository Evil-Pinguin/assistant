# -*- coding: utf-8 -*-
"""Встроенные навыки AURA.

Каждый навык = имя + регулярки (по нормализованному тексту) + обработчик.
Фазы: 1 — конкретные команды; 2 — общий «открой …» (после пользовательских).
"""
import datetime
import os
import random
import re
import shutil

from .actions import (open_app as _open_app, open_url as _open_url, press as _press,
                      run_shell, volume as _volume)
from . import files as F
from . import system as SYS

try:
    import requests
except ImportError:
    requests = None


class SkillContext:
    def __init__(self, say, log, config, action_ctx, ear=None, voice=None,
                 brain=None, memory=None):
        self.say = say
        self.log = log
        self.config = config
        self.action_ctx = action_ctx
        self.ear = ear
        self.voice = voice
        self.brain = brain
        self.memory = memory
        self.pending_confirm = None

    def confirm(self, prompt, fn):
        self.pending_confirm = (prompt, fn)


class Skill:
    def __init__(self, name, patterns, handler, phase=1):
        self.name = name
        self.patterns = [re.compile(p) for p in patterns]
        self.handler = handler
        self.phase = phase


def _name_suffix(config):
    name = (config.get("user_name") or "").strip()
    return f", {name}" if name else ""


def _greeting_text(config):
    h = datetime.datetime.now().hour
    if 5 <= h < 12:
        part = "Доброе утро"
    elif 12 <= h < 18:
        part = "Добрый день"
    elif 18 <= h < 23:
        part = "Добрый вечер"
    else:
        part = "Доброй ночи"
    return f"{part}{_name_suffix(config)}! Слушаю."


IDENTITY_TEXT = (
    "Я Аврора, ваш ассистент. Открываю программы и сайты, управляю громкостью, "
    "делаю скриншоты и вижу экран, ищу файлы, помню ваши привычки и выполняю ваши "
    "команды и режимы. Подключите нейросеть в настройках — и я буду вести любой "
    "разговор. Подробности во вкладке «Команды»."
)

JOKES = [
    "Программист ставит на ночь два стакана: один с водой — попить, второй пустой — не попить.",
    "— Почему ты не работаешь? — Я в режиме энергосбережения.",
    "Компьютер позволяет решать проблемы, которых раньше не было.",
    "Мой компьютер и я идеально понимаем друг друга: он висит, и я висю.",
    "Нейросеть спросили, боится ли она темноты. Она ответила: только если там выключат сервер.",
]

SITE_MAP = {
    "ютуб": "https://youtube.com", "youtube": "https://youtube.com",
    "музыка": "https://music.youtube.com",
    "вк": "https://vk.com", "вконтакте": "https://vk.com",
    "гугл": "https://google.com", "google": "https://google.com",
    "почта": "https://mail.ru", "почту": "https://mail.ru", "джимейл": "https://mail.google.com",
    "гитхаб": "https://github.com", "github": "https://github.com",
    "мои гитхаб проекты": "https://github.com?tab=repositories",
    "википедия": "https://ru.wikipedia.org", "википедию": "https://ru.wikipedia.org",
    "твиттер": "https://x.com", "икс": "https://x.com",
    "инстаграм": "https://instagram.com",
    "телеграм": "https://web.telegram.org", "чат gpt": "https://chat.openai.com",
    "переводчик": "https://translate.google.com/?sl=ru&tl=en",
    "карты": "https://maps.google.com",
    "нотион": "https://notion.so", "notion": "https://notion.so",
}

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
    "excel": ("excel", ["localc"]),
    "vs код": ("code", ["code"]),
    "vs code": ("code", ["code"]),
    "visual студио код": ("code", ["code"]),
    "спотифай": ("spotify", ["spotify"]),
    "spotify": ("spotify", ["spotify"]),
    "дискорд": ("discord", ["discord"]),
    "discord": ("discord", ["discord"]),
    "стим": ("steam", ["steam"]),
    "steam": ("steam", ["steam"]),
    "обс": ("obs", ["obs"]),
    "obs": ("obs", ["obs"]),
    "докер": ("docker", ["docker"]),
    "docker": ("docker", ["docker"]),
}


def _resolve_app(name):
    if os.name == "nt":
        return APP_TABLE.get(name, (None, None))[0]
    _, candidates = APP_TABLE.get(name, (None, None))
    for cand in (candidates or []):
        if shutil.which(cand):
            return cand
    return None


def _open_named_app(name, ctx):
    target = _resolve_app(name)
    if target:
        if target.startswith("http"):
            _open_url(target, ctx.action_ctx)
        else:
            _open_app(target, ctx.action_ctx)
        return True
    return False


# ==========================================================================
# обработчики
# ==========================================================================
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
    days = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота",
            "воскресенье"]
    d = datetime.date.today()
    return f"Сегодня {d.day} {months[d.month - 1]} {d.year} года, {days[d.weekday()]}."


def h_weather(t, m, ctx):
    if requests is None:
        return "Модуль requests не установлен."
    city = (m.groupdict().get("city") or "").strip() if m else ""
    if not city:
        city = ctx.config.get("city") or "Москва"
    try:
        r = requests.get(f"https://wttr.in/{re.sub(r' ', '%20', city)}?format=j1&lang=ru",
                         timeout=8, headers={"User-Agent": "curl/8"})
        data = r.json()["current_condition"][0]
        ru_desc = data.get("lang_ru") or []
        desc = (ru_desc[0]["value"] if ru_desc else "") or data["weatherDesc"][0]["value"]
        return (f"Погода в {city}: {desc.lower()}, {data['temp_C']} градусов, "
                f"ощущается как {data['FeelsLikeC']}.")
    except Exception:
        return f"Не удалось узнать погоду для {city}."


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
    _open_url(f"https://www.youtube.com/results?search_query={q.replace(' ', '+')}",
              ctx.action_ctx)
    return f"Ищу на YouTube: {q}"


def h_music(t, m, ctx):
    url = ctx.config.get("music_url", "https://music.youtube.com")
    _open_url(url, ctx.action_ctx)
    return "Включаю музыку"


def h_wiki(t, m, ctx):
    q = (m.group("q") or "").strip()
    if not q:
        return None
    _open_url(f"https://ru.wikipedia.org/w/index.php?search={q.replace(' ', '+')}",
              ctx.action_ctx)
    return f"Открываю Википедию: {q}"


def h_screenshot(t, m, ctx):
    try:
        from PIL import ImageGrab
    except ImportError:
        _press("prtsc", ctx.action_ctx)
        return "Скриншот в буфере обмена (установите Pillow, чтобы сохранять файлы)"
    folder = ctx.config.get("screenshots_dir") or os.path.join(
        os.path.expanduser("~"), "Pictures" if os.name == "nt" else "Изображения", "AURA")
    try:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder,
                            datetime.datetime.now().strftime("shot_%Y%m%d_%H%M%S.png"))
        ImageGrab.grab().save(path)
        _open_app(folder, ctx.action_ctx)
        return f"Скриншот сохранён: {os.path.basename(path)}"
    except Exception as exc:
        _press("prtsc", ctx.action_ctx)
        ctx.log(f"Скриншот файлом не удался: {exc}", level="error")
        return "Скриншот в буфере обмена"


VOL_SET = re.compile(r"громкость (?:на )?(\d{1,3})\s*%?")
VOL_MUTE = re.compile(r"(выключи|убери)\s+(звук|громкость)|без звука|мьют")
VOL_UP = re.compile(r"громче|громк\w*\s*(выше|больше)|звук (выше|больше)")
VOL_DOWN = re.compile(r"тише|громк\w*\s*(ниже|меньше)|звук (ниже|меньше)")


def h_volume(t, m, ctx):
    m_set = VOL_SET.search(t)
    if m_set:
        _volume(m_set.group(1), ctx.action_ctx)
        return f"Громкость на {m_set.group(1)} процентов"
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
    if re.search(r"следующ|next", t):
        key, reply = "nexttrack", "Следующий трек"
    elif re.search(r"предыдущ", t):
        key, reply = "prevtrack", "Предыдущий трек"
    else:
        key, reply = "playpause", "Переключаю воспроизведение"
    _press(key, ctx.action_ctx)
    return reply


def h_type(t, m, ctx):
    from .actions import type_text
    text = (m.group("text") or "").strip()
    if not text:
        return None
    type_text(text, ctx.action_ctx)
    return None


def h_minimize(t, m, ctx):
    _press("win+d" if os.name == "nt" else "ctrl+super+d", ctx.action_ctx)
    return "Сворачиваю все окна"


def h_lock(t, m, ctx):
    if os.name == "nt":
        run_shell("rundll32.exe user32.dll,LockWorkStation", ctx.action_ctx)
    else:
        run_shell("loginctl lock-session 2>/dev/null || xdg-screensaver lock",
                  ctx.action_ctx)
    return "Блокирую компьютер"


def h_shutdown(t, m, ctx):
    if ctx.config.get("confirm_power", True):
        ctx.confirm("Выключить компьютер?",
                    lambda: run_shell("shutdown /s /t 5" if os.name == "nt"
                                      else "systemctl poweroff", ctx.action_ctx))
        return None
    from .actions import power
    power("shutdown", ctx.action_ctx)
    return "Выключаю компьютер через 5 секунд"


def h_reboot(t, m, ctx):
    if ctx.config.get("confirm_power", True):
        ctx.confirm("Перезагрузить компьютер?",
                    lambda: run_shell("shutdown /r /t 5" if os.name == "nt"
                                      else "systemctl reboot", ctx.action_ctx))
        return None
    from .actions import power
    power("reboot", ctx.action_ctx)
    return "Перезагружаю через 5 секунд"


def h_sleep(t, m, ctx):
    if ctx.ear is not None:
        ctx.ear.paused.set()
    if ctx.config.get("require_wake_word", True):
        return "Ухожу в режим ожидания. Скажите кодовое слово, когда я понадоблюсь."
    return "Ухожу в режим ожидания. Разбудите кнопкой микрофона."


def h_wake(t, m, ctx):
    if ctx.ear is not None:
        ctx.ear.paused.clear()
    return "Я здесь. Слушаю."


def h_joke(t, m, ctx):
    return random.choice(JOKES)


def h_coin(t, m, ctx):
    return "Орёл!" if random.random() < 0.5 else "Решка!"


def h_dice(t, m, ctx):
    return f"Выпало {random.randint(1, 6)}."


def h_forget(t, m, ctx):
    return "__FORGET_HISTORY__"


# --- новое в AURA -------------------------------------------------------
def h_status(t, m, ctx):
    try:
        return SYS.system_status().replace("\n", ". ")
    except Exception as exc:
        ctx.log(f"Статус: {exc}", level="error")
        return "Не удалось собрать статистику. Нужен пакет psutil."


def h_why(t, m, ctx):
    try:
        text, culprit = SYS.why_slow()
        ctx.log(text, level="system")
        if culprit:
            name, mem, pid = culprit
            def close_it():
                from .actions import ActionContext, execute_action
                execute_action({"type": "close_app", "target": name.split(".")[0]},
                               ctx.action_ctx)
            ctx.confirm(f"Похоже, {name} использует {mem}. Закрыть?", close_it)
            return None
        return text.replace("\n", ". ")
    except Exception as exc:
        ctx.log(f"Диагностика: {exc}", level="error")
        return "Нужен пакет psutil для диагностики."


def h_find_file(t, m, ctx):
    q = (m.group("q") or "").strip()
    if not q:
        return None
    found = F.find_files(q, ctx.memory)
    if not found:
        return f"Ничего похожего на «{q}» не нашла."
    ctx.log("Найдено:\n" + "\n".join(found))
    _open_app(os.path.dirname(found[0]), ctx.action_ctx)
    if len(found) == 1:
        return f"Нашла: {os.path.basename(found[0])}. Открыла папку."
    return f"Нашла {len(found)} файлов, открыла папку с первым."


def h_create_folder(t, m, ctx):
    name = (m.group("q") or "").strip()
    if not name:
        return None
    from .actions import create_folder
    base = os.path.expanduser(ctx.memory.get_pref(
        "projects_folder", os.path.join("~", "Projects")))
    path = name if os.path.isabs(name) else os.path.join(base, name)
    try:
        create_folder(path, ctx.action_ctx)
        return f"Создала папку {name}"
    except Exception as exc:
        return f"Не получилось: {exc}"


def h_zip(t, m, ctx):
    from .actions import zip_folder
    path = (m.group("q") or "").strip()
    if not path:
        return None
    if not os.path.isabs(path):
        base = os.path.expanduser(ctx.memory.get_pref(
            "projects_folder", os.path.join("~", "Projects")))
        cand = os.path.join(base, path)
        path = cand if os.path.isdir(cand) else os.path.join(os.path.expanduser("~"), path)
    try:
        zip_folder(path, ctx.action_ctx)
        return "Архив готов"
    except Exception as exc:
        return f"Не получилось: {exc}"


def h_duplicates(t, m, ctx):
    path = (m.group("q") or "").strip()
    if not path or not os.path.isdir(os.path.expanduser(path)):
        base = os.path.expanduser(ctx.memory.get_pref(
            "projects_folder", os.path.join("~", "Projects")))
        path = os.path.join(base, path) if path else base
    if not os.path.isdir(path):
        return "Папка не найдена."
    groups, scanned = F.find_duplicates(path)
    if not groups:
        return f"Дубликатов нет (просмотрела {scanned} файлов)."
    lines = []
    for ps in list(groups.values())[:5]:
        lines.append(f"• {os.path.basename(ps[0])} × {len(ps)}")
    ctx.log("Дубликаты:\n" + "\n".join(
        "\n".join("   " + p for p in ps) for ps in list(groups.values())[:5]))
    return f"Нашла дубликаты: {'; '.join(lines)}. Скажите, какие удалить."


def h_collect_images(t, m, ctx):
    path = (m.group("q") or "").strip() or os.path.join(os.path.expanduser("~"),
                                                        "Downloads", "Загрузки")
    if not os.path.isdir(os.path.expanduser(path)):
        return "Папка не найдена."
    try:
        dst, count = F.collect_images(os.path.expanduser(path))
        return f"Собрала {count} изображений в {os.path.basename(dst)}"
    except Exception as exc:
        return f"Не получилось: {exc}"


def h_remember(t, m, ctx):
    text = (m.group("fact") or "").strip()
    if not text:
        return None
    text = re.sub(r"^(что|то,?\s*что|что я)\s+", "", text)
    # «моя папка проектов D:/X» → предпочтение
    m2 = re.search(r"(мо[яи]|моя|мой)\s+(папк\w* проектов|папк\w*)\s+(.+)", text)
    if m2 and not os.path.isabs(text):
        pass
    m3 = re.search(r"папк\w*\s+проектов\s+[:\-]?\s*(.+)", text)
    if m3:
        path = m3.group(1).strip().strip('"').rstrip(".")
        ctx.config.set_pref("projects_folder", path)
        return f"Запомнила: папка проектов {path}"
    m4 = re.search(r"меня зовут\s+(\w+)", text)
    if m4:
        ctx.config.set("user_name", m4.group(1).capitalize())
        ctx.config.save()
        return f"Приятно! Буду звать вас {m4.group(1).capitalize()}"
    ctx.memory.add_fact(text)
    return f"Запомнила: {text}"


def h_recall(t, m, ctx):
    return ctx.memory.summary()


def h_forget_all(t, m, ctx):
    def do():
        ctx.memory.clear_facts()
    ctx.confirm("Очистить всю память о фактах?", do)
    return None


def h_last_project(t, m, ctx):
    p = F.newest_folder(ctx.memory)
    if not p:
        return ("Скажите «запомни: папка проектов D:/Projects» — и я буду знать, "
                "где искать проекты.")
    _open_app(p, ctx.action_ctx)
    return f"Открываю последний проект: {os.path.basename(p)}"


def h_undo(t, m, ctx):
    if ctx.brain is None:
        return None
    ctx.brain.undo_last_async()
    return None


def h_screen(t, m, ctx):
    if ctx.brain is None:
        return None
    return ctx.brain.vision_analyze("Что изображено на этом скриншоте? Ответь кратко.")


def h_screen_click(t, m, ctx):
    if ctx.brain is None:
        return None
    target = (m.group("q") or "").strip()
    return ctx.brain.vision_click(target)


def h_close_app(t, m, ctx):
    from .actions import close_app
    name = (m.group("q") or "").strip()
    if not name:
        return None
    name = {"браузер": "chrome", "блокнот": "notepad",
            "диспетчер задач": "taskmgr"}.get(name, name)
    try:
        text, _ = close_app(name, ctx.action_ctx)
        if "не найден" in text:
            return f"Процесс {name} не запущен."
        return text + ". Могу вернуть — скажите «отмени»."
    except Exception as exc:
        return f"Не получилось: {exc}"


def h_brightness(t, m, ctx):
    from .actions import brightness
    m2 = re.search(r"(\d{1,3})", t)
    if not m2:
        return None
    try:
        brightness(m2.group(1), ctx.action_ctx)
        return f"Яркость на {m2.group(1)} процентов"
    except Exception as exc:
        return str(exc)


# --- фаза 2: «открой …» ---------------------------------------------------
def h_open_generic(t, m, ctx):
    what = (m.group("what") or "").strip()
    what = re.sub(r"^(сайт|страницу|страница|приложение|программу|программа|файл)\s+",
                  "", what)
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
    if " " not in what and (shutil.which(what) or _resolve_app(what)):
        if not _open_named_app(what, ctx):
            _open_app(what, ctx.action_ctx)
        return f"Запускаю {what}"
    # может, это файл?
    found = F.find_files(what, ctx.memory, limit=1)
    if found:
        _open_app(found[0], ctx.action_ctx)
        return f"Открываю файл {os.path.basename(found[0])}"
    _open_url(f"https://www.google.com/search?q={what.replace(' ', '+')}", ctx.action_ctx)
    return f"Не знаю такой адрес, ищу в Google: {what}"


# ==========================================================================
# реестр
# ==========================================================================
def get_skills():
    return [
        # --- ассистент ---
        Skill("wake", [r"^(проснись|разбудись|за работу|подъём|подъем)$"], h_wake),
        Skill("sleep", [r"^(спи|спать|отдыхай|отбой|в режим ожидания|усни)$"], h_sleep),
        Skill("greeting", [r"^(привет|здравствуй|здравствуйте|доброе утро|добрый день|"
                           r"добрый вечер|доброй ночи|хай|hello|hi)\b"], h_greeting),
        Skill("identity", [r"(кто ты|что ты умеешь|как тебя зовут|твои возможности|"
                           r"список команд|^помощь$|^справка$|^help$)"], h_identity),
        Skill("forget", [r"(забудь вс|очисти историю|сотри историю|начни с чистого листа)"],
              h_forget),

        # --- время/погода ---
        Skill("time", [r"(сколько времени|который час|текущее время|скажи время)"], h_time),
        Skill("date", [r"(какое сегодня число|какая сегодня дата|какой сегодня день|"
                       r"какой день недели|какое число|какая дата)"], h_date),
        Skill("weather", [r"погод\w*\s*(?:сегодня\s*)?(?:в\s+(?P<city>[\wа-я\- ]+?)\s*$)?"],
              h_weather),

        # --- интернет ---
        Skill("find_file", [r"^(?:найди|поищи)\s+(?:файл|документ|презентац\w*|картинк\w*|"
                            r"фото|видео|таблиц\w*|папку)\s+(?P<q>.+)$"], h_find_file),
        Skill("search", [r"^(?:найди|поищи|загугли)\s+(?:в\s+гугл\w*\s+)?(?P<q>.+)$"],
              h_search),
        Skill("youtube", [r"(?:на ютубе|в ютубе|ютуб\w*)\s*(?P<q>.*)$"], h_youtube),
        Skill("music", [r"^(включи музыку|поставь музыку|запусти музыку)$"], h_music),
        Skill("wiki", [r"^(?:что такое|кто так(?:ой|ая|ое)|расскажи про)\s+(?P<q>.+)$"],
              h_wiki),

        # --- система ---
        Skill("screenshot", [r"(скриншот|скрин экрана|снимок экрана|сфотографируй экран)"],
              h_screenshot),
        Skill("volume", [r"громче|тише|громкость|выключи звук|убери звук|без звука"],
              h_volume),
        Skill("media", [r"пауз\w*|продолжи|возобнови|следующ\w* (трек|песн\w+|видео)|"
                        r"предыдущ\w* (трек|песн\w+)"], h_media),
        Skill("minimize", [r"(сверни (все |всё |)окна|сверни все|покажи рабочий стол)"],
              h_minimize),
        Skill("type", [r"^(?:напечатай|напиши|набери)\s+(?P<text>.+)$"], h_type),
        Skill("lock", [r"заблокируй (комп|экран|пк|систему)"], h_lock),
        Skill("shutdown", [r"(выключи (комп|пк|системник|компьютер)|заверши работу)"],
              h_shutdown),
        Skill("reboot", [r"(перезагрузи|перезапусти) (комп|пк|систему|компьютер)"],
              h_reboot),
        Skill("brightness", [r"(яркость|затемни экран|сделай экран (ярче|темнее)|"
                             r" brightness)"], h_brightness),

        # --- диагностика ---
        Skill("status", [r"(статус системы|состояние системы|загрузка процессора|"
                         r"загрузк\w+ сист|сколько памяти|сколько свободного места|"
                         r"уровень заряд|сколько заряд|как батарея)"], h_status),
        Skill("why", [r"(почему (компьютер|комп|ноутбук|пк|всё|все)?\s*тормозит|"
                      r"что грузит (систему|компьютер|процессор)|почему всё висит|"
                      r"что с системой)"], h_why),

        Skill("create_folder", [r"^(?:создай|сделай)\s+папку\s+(?P<q>.+)$"], h_create_folder),
        Skill("zip", [r"^(?:заархивируй|сделай zip|заzipуй)\s+(?:папку\s+)?(?P<q>.+)$"],
              h_zip),
        Skill("duplicates", [r"(найди|проверь)\s+дубликат\w*\s*(?:в папке\s*)?(?P<q>.*)$"],
              h_duplicates),
        Skill("collect_images", [r"собери\s+(все\s+)?изображени\w*\s*(?:из папки\s+)?"
                                 r"(?P<q>.*)$"], h_collect_images),

        # --- память ---
        Skill("remember", [r"^(?:запомни|запиши себе)[,:]?\s*(?P<fact>.+)$"], h_remember),
        Skill("recall", [r"(что ты помнишь|покажи память|что запомнила|твоя память)"],
              h_recall),
        Skill("forget_all", [r"(забудь всё|очисти память|сотри память|забудь факты)"],
              h_forget_all),
        Skill("last_project", [r"(открой (мой |)последний (проект|проекты)|"
                               r"мой последний проект)"], h_last_project),

        # --- активность и зрение ---
        Skill("undo", [r"(отмени (последнее действие|последн\w+|это)|отмен\w+ действие|"
                       r"верни (как было|последнее))"], h_undo),
        Skill("screen", [r"(что (у меня )?(сейчас )?на экране|что ты видишь|"
                         r"опиши( мне)? экран|посмотри на экран|что это на экране)"],
              h_screen),
        Skill("screen_click", [r"нажми на (?P<q>.+?)\s*(?:на экране|кнопку)"],
              h_screen_click),

        # --- приложения ---
        Skill("close_app", [r"^(?:закрой|закрыть)\s+(?P<q>.+)$"], h_close_app),

        # --- развлечения ---
        Skill("joke", [r"(анекдот|шутк\w+|рассмеши|пошути)"], h_joke),
        Skill("coin", [r"(подбрось монет\w+|брось монет\w+|орёл или решка)"], h_coin),
        Skill("dice", [r"(брось кубик|кинь кубик)"], h_dice),

        # --- фаза 2 ---
        Skill("open_generic", [r"^(?:открой|запусти|включи)\s+(?P<what>.+)$"],
              h_open_generic, phase=2),
    ]
