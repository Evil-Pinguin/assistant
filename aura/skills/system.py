# -*- coding: utf-8 -*-
"""Системные утилиты: диагностика «почему тормозит», статус, топ процессов."""
import datetime
import os


def _fmt_gb(n):
    return f"{n / (1024 ** 3):.1f} ГБ"


def system_status():
    """Краткий статус: CPU, RAM, диск, батарея."""
    import psutil
    cpu = psutil.cpu_percent(interval=0.4)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.expanduser("~") if os.name == "nt" else "/")
    lines = [f"Процессор {round(cpu)}%, память {round(mem.percent)}% "
             f"(свободно {_fmt_gb(mem.available)}), "
             f"диск {round(disk.percent)}% (свободно {_fmt_gb(disk.free)})"]
    boot = datetime.datetime.fromtimestamp(psutil.boot_time())
    lines.append(f"Система работает с {boot.strftime('%H:%M')}")
    b = getattr(psutil, "sensors_battery", lambda: None)()
    if b:
        lines.append(f"Батарея {round(b.percent)}%"
                     f"{' (заряжается)' if b.power_plugged else ''}")
    return "\n".join(lines)


def top_processes(n=5):
    """Топ процессов по памяти: [(имя, память_str, pid)]."""
    import psutil
    procs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            mi = p.info.get("memory_info")
            if mi is not None:
                procs.append(((p.info.get("name") or "?")[:24],
                              mi.rss, p.pid))
        except Exception:
            continue
    procs.sort(key=lambda x: -x[1])
    return [(name, _fmt_gb(rss), pid) for name, rss, pid in procs[:n]]


def why_slow():
    """Диагностика: что грузит систему. Возвращает (текст, главный_виновник)."""
    import psutil
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/" if os.name != "nt" else "C:\\")
    top = top_processes(4)
    lines = [f"Процессор {round(cpu)}%, память {round(mem.percent)}%, "
             f"диск {round(disk.percent)}%."]
    if top:
        lines.append("Топ по памяти: " + "; ".join(f"{n} — {m}" for n, m, _ in top))
    culprit = top[0] if (top and mem.percent > 85) else None
    advice = []
    if mem.percent > 85:
        advice.append("память почти заполнена")
    if disk.percent > 92:
        advice.append("диск переполнен")
    if cpu > 90:
        advice.append("процессор перегружен")
    if advice:
        lines.append("Проблема: " + ", ".join(advice) + ".")
    else:
        lines.append("Критичных проблем не вижу.")
    return "\n".join(lines), culprit
