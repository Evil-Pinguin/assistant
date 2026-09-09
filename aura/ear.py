# -*- coding: utf-8 -*-
"""Слух AURA: микрофон + распознавание речи.

Два движка:
  * google — SpeechRecognition + бесплатный Google Web Speech API (нужен интернет);
  * vosk  — офлайн-распознавание (pip install vosk + модель).

Режимы:
  * с кодовым словом: сначала «аврора», затем команда;
  * прямой: каждая фраза — команда.
"""
import json
import re
import threading
import time

try:
    import speech_recognition as sr
    SR_OK = True
except Exception:  # pragma: no cover
    SR_OK = False


class Ear:
    def __init__(self, config, emit, on_text):
        self.config = config
        self.emit = emit                      # события для GUI
        self.on_text = on_text                # колбэк: распознанный текст -> Brain
        self.running = threading.Event()
        self.paused = threading.Event()       # «спим» до кодового слова
        self._push = threading.Event()        # кнопка «Слушать» (push-to-talk)
        self._thread = None
        self._vosk_model = None
        self.followup_until = 0.0             # диалог: слушаем без кодового слова

    # ---------- публичный API ----------
    def start(self):
        if not SR_OK:
            self.emit("log", level="error",
                      msg="Микрофон недоступен: не установлен SpeechRecognition "
                          "(pip install SpeechRecognition PyAudio)")
            return False
        if self.is_alive:
            return True
        self.running.set()
        self._thread = threading.Thread(target=self._loop, name="ear", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self.running.clear()
        self._push.set()  # разбудить поток, чтобы он увидел stop

    @property
    def is_alive(self):
        return bool(self._thread and self._thread.is_alive() and self.running.is_set())

    def listen_once(self):
        """Разовое прослушивание по кнопке (работает даже в режиме сна)."""
        if not self.is_alive:
            if not self.start():
                return False
        self._push.set()
        return True

    # ---------- вспомогательное ----------
    @staticmethod
    def normalize(text: str) -> str:
        text = text.lower().replace("ё", "е")
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()

    def _match_wake(self, text: str) -> bool:
        wake = self.normalize(self.config.get("wake_word", "аврора"))
        if not wake:
            return True
        # «аврора», «авроры», «аврора слушай» и т.п.
        return any(tok.startswith(wake) for tok in text.split())

    # --- распознавание (текст + уверенность 0..1) ---
    def _recognize(self, recognizer, source_audio):
        engine = (self.config.get("stt_engine") or "google").lower()
        if engine == "vosk":
            return self._recognize_vosk(source_audio), 0.9
        lang = self.config.get("language", "ru-RU")
        try:
            data = recognizer.recognize_google(source_audio, language=lang,
                                               show_all=True)
            alts = (data or {}).get("alternative") or []
            if alts:
                best = alts[0]
                conf = best.get("confidence")
                text = (best.get("text") or "").strip()
                return text, (float(conf) if conf is not None else 0.75)
        except TypeError:  # старые версии без show_all
            pass
        return recognizer.recognize_google(source_audio, language=lang).strip(), 0.8

    def _recognize_vosk(self, audio) -> str:
        try:
            from vosk import Model, KaldiRecognizer
        except ImportError:
            raise RuntimeError("Vosk не установлен: pip install vosk")
        if self._vosk_model is None:
            path = self.config.get("vosk_model_path", "")
            if not path:
                raise RuntimeError("Не указан путь к модели Vosk (Настройки → Слух)")
            self.emit("log", level="system", msg=f"Загружаю модель Vosk: {path} …")
            self._vosk_model = Model(path)
        rec = KaldiRecognizer(self._vosk_model, 16000)
        rec.AcceptWaveform(audio.get_raw_data(convert_rate=16000, convert_width=2))
        return json.loads(rec.FinalResult()).get("text", ""), 0.9

    # --- основной цикл ---
    def _loop(self):
        r = sr.Recognizer()
        r.dynamic_energy_threshold = True
        r.energy_threshold = 300
        try:
            device_index = int(self.config.get("mic_device_index", -1))
            mic = (sr.Microphone(device_index=device_index)
                   if device_index >= 0 else sr.Microphone())
        except Exception as exc:
            self._mic_failed(exc)
            return
        try:
            with mic as source:
                self.emit("log", level="system", msg="Калибрую микрофон под шум…")
                r.adjust_for_ambient_noise(source, duration=1)
                self.emit("mic_state", active=True)
                self.emit("log", level="system", msg="Микрофон активен.")
                self._listen_loop(r, source)
        except Exception as exc:
            if self.running.is_set():
                self._mic_failed(exc)
        self.running.clear()
        self.emit("mic_state", active=False)

    def _mic_failed(self, exc):
        self.running.clear()
        self.emit("log", level="error",
                  msg=f"Микрофон недоступен: {exc}. Проверьте устройство и установку "
                      f"PyAudio (pip install PyAudio). Печатайте команды в окне управления.")
        self.emit("mic_state", active=False)

    def _listen_loop(self, r, source):
        while self.running.is_set():
            if self.paused.is_set() and not self._push.is_set():
                time.sleep(0.15)
                continue
            push_talk = self._push.is_set()
            self._push.clear()
            wake_required = self.config.get("require_wake_word", True)
            wait_label = ("Слушаю…" if (push_talk or not wake_required)
                          else "Жду кодовое слово…")
            self.emit("state", name="listening", label=wait_label)
            try:
                audio = r.listen(source, timeout=4 if not push_talk else 6,
                                 phrase_time_limit=6)
            except Exception:  # WaitTimeoutError и пр. — тишина, обычный цикл
                self.emit("state",
                          name="idle" if self.paused.is_set() else "listening",
                          label="Ожидаю…" if self.paused.is_set() else wait_label)
                continue

            # VU-метр: уровень захваченной фразы (проигрывается в UI)
            try:
                self.emit("vu", levels=audio_levels(audio))
            except Exception:
                pass

            try:
                text, confidence = self._recognize(r, audio)
            except RuntimeError as exc:
                self.emit("log", level="error", msg=str(exc))
                self.emit("state", name="alert", label="Ошибка распознавания")
                time.sleep(2)
                continue
            except Exception as exc:
                name = type(exc).__name__
                if name == "RequestError":
                    self.emit("log", level="error",
                              msg="Сервис распознавания недоступен (нет интернета?). "
                                  "Для офлайна: pip install vosk и укажите модель в настройках.")
                    self.emit("state", name="alert", label="Нет связи с сервисом")
                    time.sleep(2)
                else:  # UnknownValueError — не разобрал речь
                    self.emit("state", name="idle",
                              label="Не расслышал" if push_talk else wait_label)
                continue

            text = (text or "").strip()
            if not text:
                continue
            norm = self.normalize(text)
            self.emit("heard", text=text, confidence=round(confidence, 2))

            # низкая уверенность → честно переспросим
            min_conf = float(self.config.get("stt_min_confidence", 0.5))
            if confidence < min_conf and not push_talk:
                self.emit("log", level="error",
                          msg=f"Не уверена, что расслышала («{text}», "
                              f"уверенность {confidence:.0%}). Повторите или напечатайте.")
                self.emit("state", name="alert", label="НЕ РАСЛЫШАЛА")
                continue

            # диалоговый режим: после недавнего ответа AURA кодовое слово не нужно
            in_dialog = time.time() < self.followup_until

            # режим кодового слова
            if wake_required and not push_talk and not in_dialog:
                if not self._match_wake(norm):
                    continue
                wake = self.normalize(self.config.get("wake_word", "аврора"))
                rest = " ".join(t for t in norm.split() if not t.startswith(wake))
                self.emit("heard", text=text)
                if rest:                            # команда прозвучала сразу
                    self.followup_until = time.time() + float(
                        self.config.get("dialog_followup_sec", 25))
                    self.on_text(rest, "voice")
                else:                                # ждём команду следом
                    self.emit("state", name="listening", label="Слушаю команду…")
                    try:
                        audio2 = r.listen(source, timeout=5, phrase_time_limit=8)
                        cmd = self._recognize(r, audio2).strip()
                    except Exception:
                        cmd = ""
                    if cmd:
                        self.emit("heard", text=cmd)
                        self.followup_until = time.time() + float(
                            self.config.get("dialog_followup_sec", 25))
                        self.on_text(cmd, "voice")
                    else:
                        self.emit("log", level="system", msg="Команда не расслышана.")
                continue

            # прямой режим / push-to-talk / диалог
            if not wake_required or push_talk or in_dialog:
                self.followup_until = time.time() + float(
                    self.config.get("dialog_followup_sec", 25))
            self.on_text(text, "voice")

def audio_levels(audio, chunks=16) -> list:
    """Уровни громкости captured-фразы (0..1) для VU-метра."""
    try:
        data = audio.get_raw_data(convert_width=2)
        import audioop
        total = len(data)
        step = max(1, total // chunks)
        levels = []
        for i in range(chunks):
            part = data[i * step:(i + 1) * step]
            if not part:
                levels.append(0.0)
                continue
            rms = audioop.rms(part, 2)
            levels.append(min(1.0, rms / 3000))
        return levels
    except Exception:
        return [0.0] * chunks
