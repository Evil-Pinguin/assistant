# -*- coding: utf-8 -*-
"""ContextEngine: AURA знает, что происходит в компьютере.

Возможности:
  * system()       — CPU / RAM / диск / сеть (psutil + сокет-проверка);
  * active_app()   — активное окно (Windows: ctypes; прочие ОС — None);
  * open_windows() — заголовки видимых окон (best-effort);
  * running_apps() — пользовательские приложения без системного шума;
  * note()         — персистентный журнал событий (data/journal.json);
  * sessions()     — кластеризация журнала в рабочие сессии;
  * find_past_session() — «сделай как вчера»;
  * guess_project() — эвристика «над чем сейчас работают»;
  * resolve_deictic() — «закрой ЭТО» → активное окно;
  * start_monitor() — фоновый монитор: пороги RAM/CPU/диск/сеть → on_alert.

Принцип проактивности: монитор НИЧЕГО не делает сам — только замечает и
сообщает. Решение всегда за пользователем.
"""
import datetime
import json
import os
import re
import threading
import time
from collections import deque

from .config import DATA_DIR

JOURNAL_FILE = os.path.join(DATA_DIR, "journal.json")

# слова-указания на «текущее» окно
DEICTIC = {"это", "эту", "этот", "тут", "текущее", "текущую", "текущий",
           "активное", "активную", "активный"}

ALERT_TEXTS = {
    "ram_high": "Память занята на {ram:.0f} процентов. Могу найти процессы, которые её потребляют.",
    "cpu_high": "Процессор под нагрузкой {cpu:.0f} процентов уже несколько минут.",
    "disk_low": "На системном диске осталось меньше {disk:.0f} процентов свободного места.",
    "net_lost": "Похоже, пропал интернет.",
}

# системный шум, не показываем как «приложения»
_NOISE = {
    "svchost", "runtimebroker", "csrss", "dwm", "winlogon", "services",
    "lsass", "smss", "system", "idle", "registry", "memory compression",
    "fontdrvhost", "sihost", "taskhostw", "explorer", "conhost",
    "python", "pythonw", "cmd", "powershell", "audiodg", "spoolsv",
    "searchapp", "searchhost", "startmenuexperiencehost",
    "shellexperiencehost", "textinputhost", "widgets", "msedgewebview2",
    "securityhealthservice", "securityhealthsystray", "wudfhost",
    "aura", "main", "qttranslator", "sh", "bash",
}

_APP_TITLES = {
    "visual studio code", "vscode", "code", "mozilla firefox",
    "google chrome", "chrome", "krita", "blender", "unity", "unity hub",
    "discord", "telegram", "steam", "obs", "spotify", "word", "excel",
}


def evaluate_alerts(stats, prev_streak=0, prev_online=None, th=None):
    """Чистая функция порогов. → (коды, новая_серия_CPU)."""
    th = th or {}
    ram_th = th.get("ram_alert_pct", 90)
    cpu_th = th.get("cpu_alert_pct", 92)
    disk_th = th.get("disk_alert_pct_free", 10)
    codes = []
    ram = stats.get("ram")
    cpu = stats.get("cpu")
    disk = stats.get("disk_free_pct")
    online = stats.get("online")
    if isinstance(ram, (int, float)) and ram >= ram_th:
        codes.append("ram_high")
    if isinstance(cpu, (int, float)) and cpu >= cpu_th:
        streak = prev_streak + 1
        if streak >= 2:
            codes.append("cpu_high")
    else:
        streak = 0
    if isinstance(disk, (int, float)) and disk <= disk_th:
        codes.append("disk_low")
    if prev_online is True and online is False:
        codes.append("net_lost")
    return codes, streak


class ContextEngine:
    COOLDOWN_SEC = 600          # один и тот же алерт — не чаще раза в 10 минут

    def __init__(self, emit=None, config=None, journal_path=JOURNAL_FILE):
        self.emit = emit or (lambda *a, **k: None)
        self.config = config or {}
        self.journal_path = journal_path
        self.on_alert = None            # fn(code: str, text: str)
        self._journal = deque(maxlen=400)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._cpu_streak = 0
        self._was_online = None
        self._alerts_at = {}
        self._net_cache = (0.0, None)   # (ts, online)
        self._load_journal()

    def _cfg(self, key, default=None):
        try:
            return self.config.get(key, default)
        except Exception:
            return default

    # ------------------------- система -------------------------
    def net_online(self, ttl=30.0):
        """True / False / None (неизвестно). Кэш на ttl секунд."""
        ts, cached = self._net_cache
        if time.time() - ts < ttl:
            return cached
        online = None
        try:
            import socket
            s = socket.create_connection(("1.1.1.1", 53), timeout=2)
            s.close()
            online = True
        except OSError:
            online = False
        except Exception:
            online = None
        self._net_cache = (time.time(), online)
        return online

    def system(self):
        """Снимок состояния ПК: cpu, ram, диск, сеть."""
        st = {"cpu": None, "ram": None, "ram_used": None, "ram_total": None,
              "disk_free_pct": None, "online": None}
        try:
            import psutil
            st["cpu"] = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()
            st["ram"] = vm.percent
            st["ram_used"] = round(vm.used / (1 << 30), 1)
            st["ram_total"] = round(vm.total / (1 << 30), 1)
            du = psutil.disk_usage(os.path.abspath(os.sep))
            st["disk_free_pct"] = round(100 - du.percent, 1)
        except Exception:
            pass
        st["online"] = self.net_online()
        return st

    # ------------------------- окна и процессы -------------------------
    def active_app(self):
        """Активное окно: {"title", "exe", "pid"} или None."""
        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            exe = ""
            try:
                import psutil
                exe = psutil.Process(pid.value).name()
            except Exception:
                pass
            return {"title": buf.value or "", "exe": exe, "pid": int(pid.value)}
        except Exception:
            return None

    def open_windows(self, limit=12):
        """Заголовки видимых окон (Windows). На других ОС — []."""
        if os.name != "nt":
            return []
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            titles = []

            def _cb(hwnd, _lparam):
                try:
                    if user32.IsWindowVisible(hwnd):
                        n = user32.GetWindowTextLengthW(hwnd)
                        if n > 2:
                            buf = ctypes.create_unicode_buffer(n + 1)
                            user32.GetWindowTextW(hwnd, buf, n + 1)
                            titles.append(buf.value)
                except Exception:
                    pass
                return 1

            proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(proto(_cb), 0)
            return titles[:limit]
        except Exception:
            return []

    def running_apps(self, limit=12):
        """Уникальные пользовательские приложения (без системного шума)."""
        names = []
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                n = (p.info.get("name") or "").strip()
                if not n:
                    continue
                base = n.lower()
                if base.endswith(".exe"):
                    base = base[:-4]
                if base in _NOISE or len(base) < 2 or base[0].isdigit():
                    continue
                if base not in names:
                    names.append(base)
                if len(names) >= limit:
                    break
        except Exception:
            pass
        return names

    def guess_project(self):
        """Эвристика «над чем работает пользователь» → строка или None."""
        act = self.active_app()
        title = (act or {}).get("title") or ""
        for part in re.split(r"[—–\-•|]", title):
            part = part.strip()
            low = part.lower()
            if not part or low in _APP_TITLES:
                continue
            if low.endswith((".py", ".js", ".ts", ".tsx", ".cpp", ".c", ".cs",
                             ".md", ".json", ".html", ".css", ".png", ".blend")):
                continue
            if 2 <= len(part) <= 40:
                return part
        with self._lock:
            for e in reversed(self._journal):
                if e.get("kind") in ("workflow", "plan"):
                    desc = (e.get("desc") or "")[:40]
                    if desc:
                        return desc
        return None

    def resolve_deictic(self, name):
        """«это» / «текущее» → активное окно (dict) или None."""
        if (name or "").strip().lower().rstrip(".,!?") in DEICTIC:
            return self.active_app()
        return None

    # ------------------------- журнал -------------------------
    def note(self, kind, desc, actions=None):
        """Записать событие. Повтор той же записи в течение 120 с — обновление."""
        now = time.time()
        with self._lock:
            if self._journal:
                last = self._journal[-1]
                if (last.get("kind") == kind and last.get("desc") == desc
                        and now - last.get("ts", 0) < 120):
                    last["ts"] = now
                    self._save_journal()
                    return last
            entry = {"ts": now, "kind": kind, "desc": desc,
                     "actions": actions or None}
            self._journal.append(entry)
            self._save_journal()
        return entry

    def recent(self, n=10):
        """Последние n записей (новые сверху)."""
        with self._lock:
            return [dict(e) for e in list(self._journal)[-n:]][::-1]

    def sessions(self, gap_sec=900):
        """Кластеризация журнала: пауза > gap_sec = новая сессия."""
        with self._lock:
            entries = sorted(list(self._journal), key=lambda e: e.get("ts", 0))
        sessions, cur, prev_ts = [], [], None
        for e in entries:
            ts = e.get("ts", 0)
            if prev_ts is not None and ts - prev_ts > gap_sec:
                sessions.append(cur)
                cur = []
            cur.append(e)
            prev_ts = ts
        if cur:
            sessions.append(cur)
        return sessions

    def find_past_session(self, now=None, max_steps=8):
        """Последняя сессия НЕ из сегодняшнего дня → {"started", "steps"} | None."""
        now = now or time.time()
        today_start = datetime.datetime.fromtimestamp(now).replace(
            hour=0, minute=0, second=0, microsecond=0).timestamp()
        past = [s for s in self.sessions()
                if s and s[0].get("ts", 0) < today_start]
        if not past:
            return None
        steps, seen = [], set()
        for e in past[-1]:
            if not e.get("actions"):
                continue
            if e.get("desc") in seen:
                continue
            seen.add(e["desc"])
            steps.append(e)
            if len(steps) >= max_steps:
                break
        if not steps:
            return None
        return {"started": past[-1][0].get("ts", 0), "steps": steps}

    def _load_journal(self):
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for e in data[-400:]:
                    if isinstance(e, dict) and e.get("ts"):
                        self._journal.append(e)
        except Exception:
            pass

    def _save_journal(self):
        try:
            os.makedirs(os.path.dirname(self.journal_path) or ".", exist_ok=True)
            tmp = self.journal_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(list(self._journal)[-400:], f, ensure_ascii=False)
            os.replace(tmp, self.journal_path)
        except Exception:
            pass

    # ------------------------- снимок для ИИ -------------------------
    def snapshot_text(self):
        """Компактный блок «КОНТЕКСТ ПК: …» для системного промпта ИИ."""
        st = self.system()
        bits = []
        cpu, ram = st.get("cpu"), st.get("ram")
        if isinstance(cpu, (int, float)) and isinstance(ram, (int, float)):
            bits.append(f"CPU {cpu:.0f}%, RAM {ram:.0f}%")
        net = st.get("online")
        if net is True:
            bits.append("интернет есть")
        elif net is False:
            bits.append("интернета нет")
        act = self.active_app()
        if act:
            bits.append("активное окно: "
                        + (act.get("title") or act.get("exe") or "?")[:60])
        wins = self.open_windows()
        if wins:
            bits.append("открыты окна: " + ", ".join(t[:30] for t in wins[:5]))
        else:
            apps = self.running_apps(limit=6)
            if apps:
                bits.append("приложения: " + ", ".join(apps[:6]))
        proj = self.guess_project()
        if proj:
            bits.append(f"вероятная задача: {proj}")
        bits = [b for b in bits if b]
        return ("КОНТЕКСТ ПК: " + "; ".join(bits)) if bits else ""

    # ------------------------- монитор -------------------------
    def start_monitor(self, interval=None):
        if self._thread is not None:
            return
        self._interval = max(5, int(interval or self._cfg(
            "context_monitor_interval", 12)))
        self._stop.clear()
        self._thread = threading.Thread(target=self._monitor_loop,
                                        name="aura-context", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _monitor_loop(self):
        while not self._stop.wait(self._interval):
            try:
                stats = self.system()
            except Exception:
                continue
            th = {
                "ram_alert_pct": self._cfg("ram_alert_pct", 90),
                "cpu_alert_pct": self._cfg("cpu_alert_pct", 92),
                "disk_alert_pct_free": self._cfg("disk_alert_pct_free", 10),
            }
            codes, self._cpu_streak = evaluate_alerts(
                stats, self._cpu_streak, self._was_online, th)
            if stats.get("online") is not None:
                self._was_online = stats.get("online")
            fmt = {k: (v if isinstance(v, (int, float)) else 0)
                   for k, v in stats.items()}
            now = time.time()
            for code in codes:
                if now - self._alerts_at.get(code, 0) < self.COOLDOWN_SEC:
                    continue
                self._alerts_at[code] = now
                text = ALERT_TEXTS.get(code, code).format(**fmt)
                self.emit("proactive", code=code, text=text)
                if self.on_alert:
                    try:
                        self.on_alert(code, text)
                    except Exception:
                        pass
