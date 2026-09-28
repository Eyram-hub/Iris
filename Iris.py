import json
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

# ============================================================
# IRIS — clean rebuild
# Main brain: Qwen3-4B-Q6_K.gguf (existing model)
# UI: PySide6 + QML
# Voice: Vosk + sounddevice + pyttsx3
# ============================================================

APP_NAME = "Iris"
USER_NAME = "Eyram"
WAKE_WORD = "iris"

APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", APP_ROOT))
BASE_DIR = APP_ROOT
AI_DIR = BASE_DIR / "ai"
VOSK_DIR = BASE_DIR / "model"
MEMORY_FILE = BASE_DIR / "iris_memory.json"
QWEN_PATH = AI_DIR / "Qwen3-4B-Q6_K.gguf"
QML_PATH = BASE_DIR / "Main.qml"
QML_BUNDLE_PATH = BUNDLE_ROOT / "Main.qml"

SAMPLE_RATE = 44_100
MIC_DEVICE = 1
N_THREADS = 7
N_BATCH = 128
N_CTX = 1536

# Keep normal answers short enough to finish quickly on CPU.
TOKEN_LIMITS = {
    "simple": 48,
    "normal": 72,
    "explain": 96,
    "math": 112,
    "code": 144,
}

SYSTEM_PROMPT = f"""You are {APP_NAME}, a fast, capable personal desktop AI assistant for {USER_NAME}.
Answer naturally and directly, like a polished modern AI assistant.
Rules:
- Give the answer first. Do not begin with filler such as 'Sure', 'Absolutely', or 'As an AI'.
- Do not reveal hidden reasoning, chain-of-thought, or internal analysis.
- Use concise explanations for simple questions and more detail only when useful.
- Use numbered steps for procedures and bullets for lists.
- For school questions, explain the key working clearly.
- For coding, provide runnable code and briefly explain what matters.
- Keep the conversation context in mind and understand follow-up questions.
- Never pretend you performed an action you did not perform.
- The user is {USER_NAME}; address them by name only when it sounds natural.
"""

# -------------------- Optional imports --------------------
try:
    import sounddevice as sd
except Exception as exc:
    sd = None
    print(f"[VOICE] sounddevice unavailable: {exc}")

try:
    from vosk import Model, KaldiRecognizer
except Exception as exc:
    Model = None
    KaldiRecognizer = None
    print(f"[VOICE] vosk unavailable: {exc}")

try:
    import pyttsx3
except Exception as exc:
    pyttsx3 = None
    print(f"[TTS] pyttsx3 unavailable: {exc}")

try:
    from llama_cpp import Llama
except Exception as exc:
    Llama = None
    print(f"[AI] llama_cpp unavailable: {exc}")

try:
    from pycaw.pycaw import AudioUtilities
    from comtypes import CLSCTX_ALL
    from ctypes import cast, POINTER
    from pycaw.interfaces import IAudioEndpointVolume
except Exception:
    AudioUtilities = None
    CLSCTX_ALL = None
    cast = POINTER = IAudioEndpointVolume = None


# -------------------- Utilities --------------------
def log(message: str):
    print(f"[Iris] {message}", flush=True)


def clean_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", (text or "").strip())


def strip_thinking(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I)
    text = re.sub(r"<analysis>.*?</analysis>", "", text, flags=re.S | re.I)
    return text.strip()


def speech_text(text: str) -> str:
    text = strip_thinking(text)
    text = re.sub(r"```.*?```", "code", text, flags=re.S)
    text = re.sub(r"[*_`#]", "", text)
    text = re.sub(r"\|", ". ", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\n+", ". ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detect_question_type(text: str) -> str:
    t = text.lower()
    if any(x in t for x in ("write code", "python", "javascript", "program", "function", "bug", "error", "script")):
        return "code"
    if any(x in t for x in ("solve", "calculate", "equation", "factorise", "factorize", "differentiate", "integrate", "probability")):
        return "math"
    if any(x in t for x in ("explain", "difference between", "how does", "why does", "describe")):
        return "explain"
    if len(t.split()) <= 10:
        return "simple"
    return "normal"


def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"Could not read {path.name}: {exc}")
    return default


def save_json(path: Path, data):
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        log(f"Could not save {path.name}: {exc}")


def launch(command):
    try:
        subprocess.Popen(command, shell=isinstance(command, str))
        return True
    except Exception as exc:
        log(f"Launch failed: {exc}")
        return False


def set_volume(level: int) -> bool:
    if AudioUtilities is None:
        return False
    try:
        level = max(0, min(100, int(level)))
        device = AudioUtilities.GetSpeakers()
        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return True
    except Exception as exc:
        log(f"Volume failed: {exc}")
        return False


def safe_calculate(expression: str):
    allowed = set("0123456789+-*/().% ^")
    expression = expression.replace("^", "**").strip()
    if not expression or any(ch not in allowed for ch in expression):
        return None
    if "**" in expression and "**" not in expression.replace("***", ""):
        pass
    try:
        tree = __import__("ast").parse(expression, mode="eval")
        allowed_nodes = (
            __import__("ast").Expression,
            __import__("ast").BinOp,
            __import__("ast").UnaryOp,
            __import__("ast").Add,
            __import__("ast").Sub,
            __import__("ast").Mult,
            __import__("ast").Div,
            __import__("ast").Mod,
            __import__("ast").Pow,
            __import__("ast").USub,
            __import__("ast").UAdd,
            __import__("ast").Constant,
        )
        if not all(isinstance(node, allowed_nodes) for node in __import__("ast").walk(tree)):
            return None
        value = eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, {})
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return value
    except Exception:
        return None
    return None


class IrisBackend(QObject):
    statusChanged = Signal()
    orbStateChanged = Signal()
    modelReadyChanged = Signal()
    listeningChanged = Signal()
    busyChanged = Signal()
    messageAdded = Signal(str, str)
    streamText = Signal(str)
    answerFinished = Signal(str)
    errorMessage = Signal(str)

    def __init__(self):
        super().__init__()
        self._status = "Starting Iris..."
        self._orb_state = "starting"
        self._model_ready = False
        self._listening = False
        self._busy = False
        self.model = None
        self.model_lock = threading.Lock()
        self.history = []
        self.memory = load_json(MEMORY_FILE, {"facts": [], "preferences": []})
        if not isinstance(self.memory, dict):
            self.memory = {"facts": [], "preferences": []}
        self.audio_queue = queue.Queue(maxsize=100)
        self.tts_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.voice_thread = None
        self.tts_thread = None
        self.voice_speaking = threading.Event()

    # ---------- Qt properties ----------
    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if self._status != value:
            self._status = value
            self.statusChanged.emit()

    @Property(str, notify=orbStateChanged)
    def orbState(self):
        return self._orb_state

    @orbState.setter
    def orbState(self, value):
        if self._orb_state != value:
            self._orb_state = value
            self.orbStateChanged.emit()

    @Property(bool, notify=modelReadyChanged)
    def modelReady(self):
        return self._model_ready

    @modelReady.setter
    def modelReady(self, value):
        if self._model_ready != value:
            self._model_ready = value
            self.modelReadyChanged.emit()

    @Property(bool, notify=listeningChanged)
    def listening(self):
        return self._listening

    @listening.setter
    def listening(self, value):
        if self._listening != value:
            self._listening = value
            self.listeningChanged.emit()

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    @busy.setter
    def busy(self, value):
        if self._busy != value:
            self._busy = value
            self.busyChanged.emit()

    # ---------- Startup ----------
    def start(self):
        self.tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self.tts_thread.start()

        threading.Thread(target=self._load_model, daemon=True).start()
        threading.Thread(target=self._startup_greeting, daemon=True).start()

    def _startup_greeting(self):
        time.sleep(1.2)
        self.speak(f"Hello {USER_NAME}. I'm Iris. How can I help you?")

    def _load_model(self):
        self.status = "Loading AI brain..."
        self.orbState = "thinking"
        if Llama is None:
            self.status = "AI engine unavailable"
            self.errorMessage.emit("llama-cpp-python could not be imported.")
            return
        if not QWEN_PATH.exists():
            self.status = "Qwen model not found"
            self.errorMessage.emit(str(QWEN_PATH))
            return

        log(f"Qwen path: {QWEN_PATH}")
        try:
            self.model = Llama(
                model_path=str(QWEN_PATH),
                n_ctx=N_CTX,
                n_threads=N_THREADS,
                n_threads_batch=N_THREADS,
                n_batch=N_BATCH,
                verbose=False,
            )
            # Warm up using the smallest useful generation.
            try:
                self.model.create_chat_completion(
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": "/no_think Say hello in one word."},
                    ],
                    max_tokens=4,
                    temperature=0.0,
                    stream=False,
                )
            except Exception as exc:
                log(f"Warm-up warning: {exc}")
            self.modelReady = True
            self.status = "Ready"
            self.orbState = "idle"
            log("Qwen AI brain ready")
        except Exception as exc:
            self.status = "AI brain unavailable"
            self.orbState = "error"
            log(f"Qwen load failed: {exc}")
            self.errorMessage.emit(str(exc))

        self._start_voice_if_possible()

    # ---------- Chat ----------
    @Slot(str)
    def sendMessage(self, text):
        text = (text or "").strip()
        if not text or self.busy:
            return
        self.messageAdded.emit("user", text)
        threading.Thread(target=self._handle_user_text, args=(text,), daemon=True).start()

    def _handle_user_text(self, text: str):
        self.busy = True
        self.status = "Thinking..."
        self.orbState = "thinking"
        try:
            command_answer = self._handle_local_command(text)
            if command_answer is not None:
                answer = command_answer
                self._finish_answer(text, answer)
                return

            answer = self._generate_answer(text)
            self._finish_answer(text, answer)
        except Exception as exc:
            log(f"Question handling error: {exc}")
            self.status = "Error"
            self.orbState = "error"
            self.messageAdded.emit("assistant", "I couldn't complete that request.")
        finally:
            self.busy = False
            if not self.listening:
                self.status = "Ready" if self.modelReady else self.status
                self.orbState = "idle" if self.modelReady else self.orbState

    def _finish_answer(self, user_text, answer):
        answer = strip_thinking(answer)
        if not answer:
            answer = "I couldn't produce an answer."
        self.messageAdded.emit("assistant", answer)
        self.answerFinished.emit(answer)
        self.speak(answer)
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": answer})
        del self.history[:-8]

    def _context_messages(self, question: str):
        memory_text = ""
        facts = self.memory.get("facts", [])[-8:]
        prefs = self.memory.get("preferences", [])[-8:]
        if facts or prefs:
            memory_text = "\nUseful memory:\n"
            if facts:
                memory_text += "Facts: " + "; ".join(map(str, facts)) + "\n"
            if prefs:
                memory_text += "Preferences: " + "; ".join(map(str, prefs)) + "\n"

        messages = [{"role": "system", "content": SYSTEM_PROMPT + memory_text}]
        messages.extend(self.history[-6:])
        messages.append({"role": "user", "content": "/no_think " + question})
        return messages

    def _generate_answer(self, question: str) -> str:
        if not self.modelReady or self.model is None:
            return "My local AI brain is still starting. Please try again in a moment."

        mode = detect_question_type(question)
        max_tokens = TOKEN_LIMITS[mode]
        messages = self._context_messages(question)

        chunks = []
        started = time.perf_counter()
        with self.model_lock:
            result = self.model.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.55,
                top_p=0.85,
                top_k=30,
                repeat_penalty=1.05,
                stream=True,
            )
            for item in result:
                choice = item.get("choices", [{}])[0]
                delta = choice.get("delta", {}) or {}
                token = delta.get("content", "")
                if token:
                    chunks.append(token)
                    preview = strip_thinking("".join(chunks))
                    if preview:
                        self.streamText.emit(preview)

        elapsed = time.perf_counter() - started
        answer = strip_thinking("".join(chunks)).strip()
        log(f"AI response: {elapsed:.2f}s | mode={mode} | tokens~{len(chunks)}")
        return answer

    # ---------- Local commands / deterministic helpers ----------
    def _handle_local_command(self, text: str):
        t = text.lower().strip()

        if t in {"hello", "hi", "hey iris", "hello iris"}:
            return f"Hello {USER_NAME}. What would you like to do?"

        if "who are you" in t or "what are you" in t:
            return "I'm Iris, your personal AI assistant running on your computer."

        if t.startswith("remember "):
            item = text[9:].strip()
            if item:
                self.memory.setdefault("facts", []).append(item)
                save_json(MEMORY_FILE, self.memory)
                return "I'll remember that."

        if "forget everything" in t:
            self.memory = {"facts": [], "preferences": []}
            save_json(MEMORY_FILE, self.memory)
            return "I've cleared the saved memory."

        m = re.search(r"set volume to\s+(\d{1,3})", t)
        if m:
            level = int(m.group(1))
            if set_volume(level):
                return f"Volume set to {max(0, min(100, level))} percent."
            return "I couldn't control the Windows volume from this setup."

        if t in {"open chrome", "open google chrome"}:
            ok = launch(r'"C:\Program Files\Google\Chrome\Application\chrome.exe"')
            return "Opening Chrome." if ok else "I couldn't find Chrome at the usual path."

        if "open notepad" in t:
            launch("notepad.exe")
            return "Opening Notepad."

        if "open file explorer" in t or t == "open explorer":
            launch("explorer.exe")
            return "Opening File Explorer."

        if "open settings" in t or "open windows settings" in t:
            launch("start ms-settings:")
            return "Opening Windows Settings."

        if "open paint" in t:
            launch("mspaint.exe")
            return "Opening Paint."

        if "open task manager" in t:
            launch("taskmgr.exe")
            return "Opening Task Manager."

        sites = {
            "open youtube": "https://www.youtube.com",
            "open facebook": "https://www.facebook.com",
            "open instagram": "https://www.instagram.com",
            "open google": "https://www.google.com",
        }
        if t in sites:
            webbrowser.open(sites[t])
            return f"Opening {t[5:].strip().title()}."

        if t.startswith("search youtube for "):
            q = text[len("search youtube for "):].strip()
            webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q))
            return f"Searching YouTube for {q}."

        if t.startswith("search the web for "):
            q = text[len("search the web for "):].strip()
            webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(q))
            return f"Searching the web for {q}."

        if t.startswith("calculate "):
            expression = text[10:].strip()
            value = safe_calculate(expression)
            return f"The answer is {value}." if value is not None else None

        if t.startswith("what time is it") or t == "time":
            return datetime.now().strftime("It is %I:%M %p.").lstrip("0")

        if t == "date" or "what is today's date" in t:
            return datetime.now().strftime("Today is %A, %B %d, %Y.")

        if "lock my pc" in t or "lock the pc" in t:
            launch("rundll32.exe user32.dll,LockWorkStation")
            return "Locking the PC."

        return None

    # ---------- TTS ----------
    def speak(self, text: str):
        if pyttsx3 is None:
            return
        text = speech_text(text)
        if text:
            try:
                self.tts_queue.put_nowait(text)
            except queue.Full:
                pass

    def _tts_worker(self):
        if pyttsx3 is None:
            return
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 178)
            engine.setProperty("volume", 1.0)
            for voice in engine.getProperty("voices"):
                name = (getattr(voice, "name", "") or "").lower()
                if "zira" in name:
                    engine.setProperty("voice", voice.id)
                    break
            while not self.stop_event.is_set():
                try:
                    text = self.tts_queue.get(timeout=0.25)
                except queue.Empty:
                    continue
                self.voice_speaking.set()
                self.orbState = "speaking"
                self.status = "Speaking..."
                try:
                    engine.say(text)
                    engine.runAndWait()
                except Exception as exc:
                    log(f"TTS error: {exc}")
                finally:
                    self.voice_speaking.clear()
                    if not self.busy and not self.listening:
                        self.status = "Ready"
                        self.orbState = "idle"
        except Exception as exc:
            log(f"TTS worker failed: {exc}")

    # ---------- Voice ----------
    def _start_voice_if_possible(self):
        if sd is None or Model is None or KaldiRecognizer is None:
            log("Voice disabled: sounddevice/Vosk unavailable")
            return
        if not VOSK_DIR.exists():
            log(f"Voice disabled: Vosk model folder not found: {VOSK_DIR}")
            return
        if self.voice_thread and self.voice_thread.is_alive():
            return
        self.voice_thread = threading.Thread(target=self._voice_worker, daemon=True)
        self.voice_thread.start()

    def _audio_callback(self, indata, frames, callback_time, status):
        if status:
            log(f"Microphone status: {status}")
        if self.voice_speaking.is_set():
            return
        try:
            self.audio_queue.put_nowait(bytes(indata))
        except queue.Full:
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.put_nowait(bytes(indata))
            except Exception:
                pass

    def _drain_audio(self):
        while True:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def _recognize_until(self, recognizer, timeout=5.0, silence_after_text=1.2):
        started = time.monotonic()
        heard_at = None
        texts = []
        while time.monotonic() - started < timeout and not self.stop_event.is_set():
            try:
                data = self.audio_queue.get(timeout=0.15)
            except queue.Empty:
                continue
            if recognizer.AcceptWaveform(data):
                try:
                    result = json.loads(recognizer.Result()).get("text", "").strip()
                except Exception:
                    result = ""
                if result:
                    texts.append(result)
                    heard_at = time.monotonic()
            else:
                try:
                    partial = json.loads(recognizer.PartialResult()).get("partial", "").strip()
                except Exception:
                    partial = ""
                if partial:
                    heard_at = time.monotonic()
            if heard_at and time.monotonic() - heard_at >= silence_after_text:
                break
        try:
            final = json.loads(recognizer.FinalResult()).get("text", "").strip()
        except Exception:
            final = ""
        if final:
            texts.append(final)
        return clean_text(" ".join(texts))

    def _voice_worker(self):
        log(f"Vosk path: {VOSK_DIR}")
        try:
            model = Model(str(VOSK_DIR))
        except Exception as exc:
            log(f"Vosk model failed: {exc}")
            return

        wake_rec = KaldiRecognizer(model, SAMPLE_RATE)
        try:
            stream = sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=4410,
                device=MIC_DEVICE,
                dtype="int16",
                channels=1,
                callback=self._audio_callback,
            )
        except Exception as exc:
            log(f"Microphone failed: {exc}")
            return

        log("Continuous voice listener ready")
        with stream:
            self.status = "Ready"
            while not self.stop_event.is_set():
                try:
                    data = self.audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                if self.voice_speaking.is_set() or self.busy:
                    continue

                if wake_rec.AcceptWaveform(data):
                    try:
                        heard = json.loads(wake_rec.Result()).get("text", "").lower()
                    except Exception:
                        heard = ""
                    if WAKE_WORD in heard:
                        self._voice_command_cycle(model)

    def _voice_command_cycle(self, model):
        self.listening = True
        self.status = "Listening..."
        self.orbState = "listening"
        self._drain_audio()
        self.speak(f"Hello {USER_NAME}. How can I help you?")
        # Wait for the wake greeting to finish before listening again.
        while self.voice_speaking.is_set() and not self.stop_event.is_set():
            time.sleep(0.05)
        self._drain_audio()

        command_rec = KaldiRecognizer(model, SAMPLE_RATE)
        command = self._recognize_until(command_rec, timeout=5.0, silence_after_text=1.1)
        self._drain_audio()
        self.listening = False
        if command:
            log(f"Voice command: {command}")
            self.sendMessage(command)
        else:
            self.status = "Ready"
            self.orbState = "idle"

    @Slot()
    def toggleVoice(self):
        if sd is None or Model is None:
            self.errorMessage.emit("Voice recognition is not available because sounddevice or Vosk is missing.")
            return
        self._start_voice_if_possible()
        self.listening = not self.listening
        if self.listening:
            self.status = "Listening..."
            self.orbState = "listening"
            self.speak("Listening.")
        else:
            self.status = "Ready"
            self.orbState = "idle"

    @Slot()
    def stop(self):
        self.stop_event.set()


def main():
    log(f"Starting {APP_NAME} for {USER_NAME}")
    log(f"Base directory: {BASE_DIR}")
    log(f"Qwen path: {QWEN_PATH}")
    log(f"Vosk path: {VOSK_DIR}")

    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()

    # Surface the real QML errors instead of hiding them behind an empty rootObjects list.
    def qml_warnings(warnings):
        for warning in warnings:
            log(f"QML: {warning.toString()}")

    engine.warnings.connect(qml_warnings)

    # PyInstaller's Qt runtime normally sets these, but make the frozen app explicit and robust.
    if getattr(sys, "frozen", False):
        qml_import = BUNDLE_ROOT / "PySide6" / "qml"
        if qml_import.exists():
            os.environ["QML2_IMPORT_PATH"] = str(qml_import)
        plugin_path = BUNDLE_ROOT / "PySide6" / "plugins"
        if plugin_path.exists():
            os.environ["QT_PLUGIN_PATH"] = str(plugin_path)

    backend = IrisBackend()
    engine.rootContext().setContextProperty("iris", backend)

    candidates = [QML_PATH, QML_BUNDLE_PATH]
    qml_loaded = False
    for candidate in candidates:
        if candidate.exists():
            log(f"Loading QML: {candidate}")
            engine.load(QUrl.fromLocalFile(str(candidate)))
            qml_loaded = True
            break

    if not qml_loaded:
        raise RuntimeError(f"Main.qml not found. Checked: {QML_PATH} and {QML_BUNDLE_PATH}")

    if not engine.rootObjects():
        raise RuntimeError("QML engine reported no root objects. Check the QML messages printed above.")

    backend.errorMessage.connect(lambda msg: log(f"ERROR: {msg}"))
    backend.start()

    app.aboutToQuit.connect(backend.stop)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
