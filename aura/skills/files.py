# -*- coding: utf-8 -*-
"""Работа с файлами: поиск, последний проект, сбор изображений, дубликаты."""
import hashlib
import os
import time


def search_roots(memory):
    """Папки, среди которых ищем файлы."""
    home = os.path.expanduser("~")
    roots = [home]
    for sub in ("Desktop", "Рабочий стол", "Documents", "Документы",
                "Downloads", "Загрузки"):
        p = os.path.join(home, sub)
        if os.path.isdir(p):
            roots.append(p)
    proj = os.path.expanduser(memory.get_pref("projects_folder", ""))
    if proj and os.path.isdir(proj):
        roots.insert(0, proj)
    return roots


def find_files(query, memory, limit=7):
    """Нечувствительный к регистру поиск по подстроке имени. Только по мелочи."""
    q = query.lower().strip()
    if not q:
        return []
    exts_map = {
        "презентац": (".ppt", ".pptx", ".odp", ".pdf"),
        "документ": (".doc", ".docx", ".odt", ".pdf", ".txt", ".rtf"),
        "картинк": (".png", ".jpg", ".jpeg", ".gif", ".webp"),
        "фото": (".png", ".jpg", ".jpeg", ".heic"),
        "видео": (".mp4", ".mkv", ".avi", ".mov"),
        "музык": (".mp3", ".wav", ".flac", ".ogg"),
        "таблиц": (".xls", ".xlsx", ".csv", ".ods"),
    }
    wanted = None
    for key, exts in exts_map.items():
        if q.startswith(key):
            wanted = exts
            q = q[len(key):].strip()
            break
    results = []
    seen = 0
    for root in search_roots(memory):
        for dirpath, dirnames, filenames in os.walk(root):
            # пропускаем системные и скрытые дебри
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and d not in
                           ("node_modules", "__pycache__", "AppData",
                            "venv", ".venv", "site-packages", "cache", "Cache")]
            for f in filenames:
                fl = f.lower()
                if q in fl and (wanted is None or fl.endswith(wanted)):
                    results.append(os.path.join(dirpath, f))
                    if len(results) >= limit:
                        return results
            seen += 1
    return results


def newest_folder(memory):
    """Самый свежий подкаталог в папке проектов."""
    proj = os.path.expanduser(memory.get_pref("projects_folder", ""))
    if not proj or not os.path.isdir(proj):
        return None
    best, best_t = None, -1
    for name in os.listdir(proj):
        p = os.path.join(proj, name)
        if os.path.isdir(p) and not name.startswith("."):
            try:
                t = os.path.getmtime(p)
            except OSError:
                continue
            if t > best_t:
                best, best_t = p, t
    return best


def collect_images(src):
    """Собрать изображения из папки src в src/изображения."""
    exts = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
    dst = os.path.join(src, "изображения")
    os.makedirs(dst, exist_ok=True)
    count = 0
    for f in os.listdir(src):
        p = os.path.join(src, f)
        if os.path.isfile(p) and f.lower().endswith(exts):
            target = os.path.join(dst, f)
            if not os.path.exists(target):
                import shutil
                shutil.copy2(p, target)
                count += 1
    return dst, count


def find_duplicates(folder, limit_files=800):
    """Группы дубликатов по содержимому (md5). Только файлы < 200 МБ."""
    groups = {}
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            p = os.path.join(dirpath, f)
            try:
                if os.path.getsize(p) > 200 * 1024 * 1024:
                    continue
                h = hashlib.md5()
                with open(p, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                groups.setdefault(h.hexdigest(), []).append(p)
                scanned += 1
                if scanned >= limit_files:
                    return groups, scanned
            except OSError:
                continue
    return {h: ps for h, ps in groups.items() if len(ps) > 1}, scanned


def human_size(n):
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} ТБ"


def folder_stats(path):
    files = dirs = 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirs += len(dirnames)
        for f in filenames:
            files += 1
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return files, dirs, total
