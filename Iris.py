import ast
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
# IRIS v2.2
# Personal local desktop AI assistant
#
# Brain:
#   Qwen3-4B-Q6_K.gguf
#
# User:
#   Eyram
#
# Wake word:
#   Iris
# ============================================================

APP_NAME = "Iris"
VERSION = "2.2.0"

USER_NAME = "Eyram"
WAKE_WORD = "iris"

# ============================================================
# PATHS
# ============================================================

APP_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)

BUNDLE_ROOT = Path(
    getattr(sys, "_MEIPASS", APP_ROOT)
)

BASE_DIR = APP_ROOT

AI_DIR = BASE_DIR / "ai"
VOSK_DIR = BASE_DIR / "model"

MEMORY_FILE = BASE_DIR / "iris_memory.json"
CHAT_FILE = BASE_DIR / "iris_chat_history.json"

QWEN_PATH = AI_DIR / "Qwen3-4B-Q6_K.gguf"

QML_PATH = BASE_DIR / "Main.qml"
QML_BUNDLE_PATH = BUNDLE_ROOT / "Main.qml"


# ============================================================
# PERFORMANCE
# ============================================================

SAMPLE_RATE = 44_100

# Your CPU has 8 logical processors.
N_THREADS = 8
N_THREADS_BATCH = 8

# Larger batches can improve prompt processing.
N_BATCH = 256

# Conversation context.
N_CTX = 4096

# Voice settings.
MIC_DEVICE = 1
VOICE_BLOCKSIZE = 4410

# Voice command timeout.
VOICE_COMMAND_TIMEOUT = 5.5
VOICE_SILENCE_AFTER_TEXT = 0.8

# Qwen generation limits.
TOKEN_LIMITS = {
    "simple": 96,
    "normal": 384,
    "explain": 512,
    "math": 512,
    "code": 768,
}


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = f"""
You are {APP_NAME}, a capable personal desktop AI assistant
running locally on the computer of {USER_NAME}.

Your job is to give complete, accurate, useful answers.

Rules:

- Answer the user's question directly.
- Complete the answer before stopping.
- Do not deliberately shorten an answer when important information
  is still missing.
- Do not begin with filler such as "Sure", "Absolutely", or
  "As an AI".
- Never reveal hidden reasoning, chain-of-thought, or internal analysis.
- Never pretend you performed an action that you did not perform.
- Keep genuinely simple questions concise.
- For complex questions, provide enough explanation to fully answer them.
- For school questions, show important working clearly.
- For mathematics, show the calculation and final answer.
- For coding questions, provide complete runnable code when appropriate.
- For comparisons, explain the important differences directly.
- If a question requires several steps, provide all necessary steps.
- Remember relevant conversation context.
- Do not repeat background unnecessarily.
- Do not invent facts.
- If you do not know something, say so.
- Address the user as Eyram when natural.
- You are Iris. Never call yourself Alexis.
"""


# ============================================================
# OPTIONAL MODULES
# ============================================================

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
    print(f"[VOICE] Vosk unavailable: {exc}")


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
    from ctypes import POINTER, cast
    from pycaw.interfaces import IAudioEndpointVolume
except Exception as exc:
    AudioUtilities = None
    CLSCTX_ALL = None
    POINTER = None
    cast = None
    IAudioEndpointVolume = None
    print(f"[VOLUME] pycaw unavailable: {exc}")


# ============================================================
# OPTIONAL WINDOWS NOTIFICATIONS
# ============================================================

try:
    from winrt.windows.ui.notifications.management import (
        UserNotificationListener,
        UserNotificationListenerAccessStatus,
    )

    WINRT_NOTIFICATIONS_AVAILABLE = True

except Exception as exc:
    UserNotificationListener = None
    UserNotificationListenerAccessStatus = None
    WINRT_NOTIFICATIONS_AVAILABLE = False
    print(f"[NOTIFICATIONS] winrt unavailable: {exc}")


# ============================================================
# LOGGING
# ============================================================

def log(message: str):
    print(f"[Iris] {message}", flush=True)


# ============================================================
# TEXT UTILITIES
# ============================================================

def clean_text(text: str) -> str:
    if not text:
        return ""

    text = str(text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def strip_thinking(text: str) -> str:
    if not text:
        return ""

    text = str(text)

    # Complete thinking blocks.
    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.S | re.I,
    )

    text = re.sub(
        r"<analysis>.*?</analysis>",
        "",
        text,
        flags=re.S | re.I,
    )

    # Unfinished thinking blocks.
    text = re.sub(
        r"<think>.*$",
        "",
        text,
        flags=re.S | re.I,
    )

    text = re.sub(
        r"<analysis>.*$",
        "",
        text,
        flags=re.S | re.I,
    )

    return text.strip()


def speech_text(text: str) -> str:
    """
    Convert an AI answer into something suitable for TTS.
    """

    text = strip_thinking(text)

    if not text:
        return ""

    # Replace code blocks with a short spoken description.
    text = re.sub(
        r"```.*?```",
        "code",
        text,
        flags=re.S,
    )

    # Remove markdown formatting.
    text = re.sub(r"[*_`#]", "", text)

    # Markdown links.
    text = re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        r"\1",
        text,
    )

    # URLs.
    text = re.sub(
        r"https?://\S+",
        "",
        text,
    )

    # Bullet formatting.
    text = re.sub(
        r"\n\s*[-•]\s*",
        ". ",
        text,
    )

    # New lines.
    text = re.sub(
        r"\n+",
        ". ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# JSON STORAGE
# ============================================================

def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
    except Exception as exc:
        log(
            f"Could not read {path.name}: {exc}"
        )

    return default


def save_json(path: Path, data):
    try:
        path.write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        log(
            f"Could not save {path.name}: {exc}"
        )


# ============================================================
# PROCESS LAUNCHER
# ============================================================

def launch(command):
    try:
        subprocess.Popen(
            command,
            shell=isinstance(command, str),
        )

        return True

    except Exception as exc:
        log(
            f"Launch failed: {exc}"
        )

        return False


# ============================================================
# VOLUME
# ============================================================

def set_volume(level: int) -> bool:

    if (
        AudioUtilities is None
        or CLSCTX_ALL is None
        or cast is None
        or POINTER is None
        or IAudioEndpointVolume is None
    ):
        return False

    try:
        level = max(
            0,
            min(100, int(level)),
        )

        device = AudioUtilities.GetSpeakers()

        interface = device.Activate(
            IAudioEndpointVolume._iid_,
            CLSCTX_ALL,
            None,
        )

        volume = cast(
            interface,
            POINTER(IAudioEndpointVolume),
        )

        volume.SetMasterVolumeLevelScalar(
            level / 100.0,
            None,
        )

        return True

    except Exception as exc:
        log(
            f"Volume failed: {exc}"
        )

        return False


def get_volume():
    if (
        AudioUtilities is None
        or CLSCTX_ALL is None
        or cast is None
        or POINTER is None
        or IAudioEndpointVolume is None
    ):
        return None

    try:
        device = AudioUtilities.GetSpeakers()

        interface = device.Activate(
            IAudioEndpointVolume._iid_,
            CLSCTX_ALL,
            None,
        )

        volume = cast(
            interface,
            POINTER(IAudioEndpointVolume),
        )

        value = volume.GetMasterVolumeLevelScalar()

        return round(value * 100)

    except Exception as exc:
        log(
            f"Could not read volume: {exc}"
        )

        return None


# ============================================================
# SAFE CALCULATOR
# ============================================================

def safe_calculate(expression: str):

    try:
        expression = expression.strip()

        if not expression:
            return None

        expression = expression.replace(
            "^",
            "**",
        )

        allowed_characters = set(
            "0123456789+-*/().%^ "
        )

        if any(
            character not in allowed_characters
            for character in expression
        ):
            return None

        tree = ast.parse(
            expression,
            mode="eval",
        )

        allowed_nodes = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.Div,
            ast.Mod,
            ast.Pow,
            ast.USub,
            ast.UAdd,
            ast.Constant,
        )

        for node in ast.walk(tree):
            if not isinstance(
                node,
                allowed_nodes,
            ):
                return None

        value = eval(
            compile(
                tree,
                "<calculator>",
                "eval",
            ),
            {
                "__builtins__": {}
            },
            {},
        )

        if isinstance(
            value,
            (int, float),
        ):
            if math.isfinite(
                float(value)
            ):
                return value

    except Exception:
        return None

    return None


# ============================================================
# QUESTION TYPE
# ============================================================

def detect_question_type(text: str) -> str:

    t = text.lower()

    if any(
        word in t
        for word in (
            "write code",
            "python",
            "javascript",
            "program",
            "function",
            "bug",
            "error",
            "script",
            "code",
            "coding",
            "html",
            "css",
            "sql",
            "java",
            "c++",
            "powershell",
        )
    ):
        return "code"

    if any(
        word in t
        for word in (
            "solve",
            "calculate",
            "equation",
            "factorise",
            "factorize",
            "differentiate",
            "integrate",
            "probability",
            "simplify",
            "find x",
            "find the value",
            "calculate the",
            "work out",
            "what is the answer",
        )
    ):
        return "math"

    if any(
        word in t
        for word in (
            "explain",
            "difference between",
            "how does",
            "why does",
            "describe",
            "compare",
            "how do",
            "tell me about",
            "what is",
            "what are",
            "why is",
            "why are",
        )
    ):
        return "explain"

    if len(t.split()) <= 8:
        return "simple"

    return "normal"


# ============================================================
# COMMAND ROUTER
# ============================================================

class CommandRouter:

    LOCAL_PREFIXES = (
        "open ",
        "launch ",
        "start ",
        "set volume",
        "change volume",
        "volume",
        "lock ",
        "search youtube",
        "calculate ",
        "what time",
        "what's the time",
        "time",
        "date",
        "what date",
        "remember ",
        "forget ",
        "who are you",
        "what are you",
        "hello",
        "hi",
        "hey",
        "read notifications",
        "read my notifications",
        "check notifications",
    )

    @staticmethod
    def classify(text: str) -> str:

        t = text.lower().strip()

        if any(
            t.startswith(prefix)
            for prefix in CommandRouter.LOCAL_PREFIXES
        ):
            return "local"

        if re.fullmatch(
            r"[0-9+\-*/().%^ ]+",
            t,
        ):
            return "calculator"

        if (
            t.startswith("search ")
            or t.startswith("look up ")
            or t.startswith("google ")
        ):
            return "web"

        return "ai"


# ============================================================
# IRIS BACKEND
# ============================================================

class IrisBackend(QObject):

    statusChanged = Signal()
    orbStateChanged = Signal()
    modelReadyChanged = Signal()
    listeningChanged = Signal()
    busyChanged = Signal()

    messageAdded = Signal(str, str)
    streamText = Signal(str)
    answerFinished = Signal(str)
    conversationCleared = Signal()

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

        saved_history = load_json(
            CHAT_FILE,
            [],
        )

        if isinstance(
            saved_history,
            list,
        ):
            for item in saved_history[-12:]:

                if (
                    isinstance(item, dict)
                    and item.get("role")
                    in {
                        "user",
                        "assistant",
                    }
                    and item.get("content")
                ):

                    self.history.append(
                        {
                            "role": item["role"],
                            "content": str(
                                item["content"]
                            ),
                        }
                    )

        self.memory = load_json(
            MEMORY_FILE,
            {
                "facts": [],
                "preferences": [],
            },
        )

        if not isinstance(
            self.memory,
            dict,
        ):
            self.memory = {
                "facts": [],
                "preferences": [],
            }

        self.memory.setdefault(
            "facts",
            [],
        )

        self.memory.setdefault(
            "preferences",
            [],
        )

        # Voice queues.
        self.audio_queue = queue.Queue(
            maxsize=100
        )

        self.tts_queue = queue.Queue(
            maxsize=5
        )

        # Shutdown.
        self.stop_event = threading.Event()

        self.voice_thread = None
        self.tts_thread = None

        self.voice_speaking = threading.Event()

        self.voice_enabled = True


    # ========================================================
    # QT PROPERTIES
    # ========================================================

    @Property(
        str,
        notify=statusChanged,
    )
    def status(self):
        return self._status

    @status.setter
    def status(self, value):

        if self._status != value:
            self._status = value
            self.statusChanged.emit()


    @Property(
        str,
        notify=orbStateChanged,
    )
    def orbState(self):
        return self._orb_state

    @orbState.setter
    def orbState(self, value):

        if self._orb_state != value:
            self._orb_state = value
            self.orbStateChanged.emit()


    @Property(
        bool,
        notify=modelReadyChanged,
    )
    def modelReady(self):
        return self._model_ready

    @modelReady.setter
    def modelReady(self, value):

        if self._model_ready != value:
            self._model_ready = value
            self.modelReadyChanged.emit()


    @Property(
        bool,
        notify=listeningChanged,
    )
    def listening(self):
        return self._listening

    @listening.setter
    def listening(self, value):

        if self._listening != value:
            self._listening = value
            self.listeningChanged.emit()


    @Property(
        bool,
        notify=busyChanged,
    )
    def busy(self):
        return self._busy

    @busy.setter
    def busy(self, value):

        if self._busy != value:
            self._busy = value
            self.busyChanged.emit()


    # ========================================================
    # STARTUP
    # ========================================================

    def start(self):

        # Restore previous conversation to GUI.
        for item in self.history:

            self.messageAdded.emit(
                item["role"],
                item["content"],
            )

        # Start TTS.
        self.tts_thread = threading.Thread(
            target=self._tts_worker,
            daemon=True,
        )

        self.tts_thread.start()

        # Load AI in background.
        threading.Thread(
            target=self._load_model,
            daemon=True,
        ).start()


    # ========================================================
    # LOAD QWEN
    # ========================================================

    def _load_model(self):

        self.status = "Loading AI brain..."
        self.orbState = "thinking"

        if Llama is None:

            self.status = "AI engine unavailable"

            self.errorMessage.emit(
                "llama-cpp-python could not be imported."
            )

            return

        if not QWEN_PATH.exists():

            self.status = "Qwen model not found"
            self.orbState = "error"

            self.errorMessage.emit(
                f"Qwen model not found:\n{QWEN_PATH}"
            )

            return

        log(
            f"Qwen path: {QWEN_PATH}"
        )

        log(
            f"Threads: {N_THREADS}"
        )

        log(
            f"Batch: {N_BATCH}"
        )

        log(
            f"Context: {N_CTX}"
        )

        try:

            self.model = Llama(
                model_path=str(
                    QWEN_PATH
                ),
                n_ctx=N_CTX,
                n_threads=N_THREADS,
                n_threads_batch=N_THREADS_BATCH,
                n_batch=N_BATCH,
                verbose=False,
            )

            # Small warm-up.
            try:

                self.model.create_chat_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT,
                        },
                        {
                            "role": "user",
                            "content":
                                "/no_think Say hello in one word.",
                        },
                    ],
                    max_tokens=4,
                    temperature=0.0,
                    stream=False,
                )

            except Exception as exc:

                log(
                    f"Warm-up warning: {exc}"
                )

            self.modelReady = True
            self.status = "Ready"
            self.orbState = "idle"

            log(
                "Qwen AI brain ready"
            )

        except Exception as exc:

            self.status = "AI brain unavailable"
            self.orbState = "error"

            log(
                f"Qwen load failed: {exc}"
            )

            self.errorMessage.emit(
                str(exc)
            )

            return

        # Start voice after model initialization.
        self._start_voice_if_possible()


    # ========================================================
    # SEND MESSAGE
    # ========================================================

    @Slot(str)
    def sendMessage(self, text):

        text = (text or "").strip()

        if not text:
            return

        if self.busy:
            return

        self.messageAdded.emit(
            "user",
            text,
        )

        threading.Thread(
            target=self._handle_user_text,
            args=(text,),
            daemon=True,
        ).start()


    # ========================================================
    # MESSAGE HANDLER
    # ========================================================

    def _handle_user_text(self, text):

        self.busy = True

        try:

            route = CommandRouter.classify(
                text
            )

            log(
                f"Router: {route} -> {text}"
            )

            # ------------------------------------------------
            # LOCAL COMMAND
            # ------------------------------------------------

            if route == "local":

                self.status = "Executing..."
                self.orbState = "working"

                answer = self._handle_local_command(
                    text
                )

                if answer is not None:

                    self._finish_answer(
                        text,
                        answer,
                    )

                    return

            # ------------------------------------------------
            # CALCULATOR
            # ------------------------------------------------

            if route == "calculator":

                self.status = "Calculating..."
                self.orbState = "working"

                value = safe_calculate(
                    text
                )

                if value is not None:

                    if (
                        isinstance(value, float)
                        and value.is_integer()
                    ):
                        value = int(value)

                    answer = (
                        f"The answer is {value}."
                    )

                    self._finish_answer(
                        text,
                        answer,
                    )

                    return

            # ------------------------------------------------
            # WEB
            # ------------------------------------------------

            if route == "web":

                answer = self._handle_web_command(
                    text
                )

                if answer is not None:

                    self._finish_answer(
                        text,
                        answer,
                    )

                    return

            # ------------------------------------------------
            # LOCAL QWEN
            # ------------------------------------------------

            self.status = "Thinking..."
            self.orbState = "thinking"

            answer = self._generate_answer(
                text
            )

            self._finish_answer(
                text,
                answer,
            )

        except Exception as exc:

            log(
                f"Question handling error: {exc}"
            )

            self.status = "Error"
            self.orbState = "error"

            self.messageAdded.emit(
                "assistant",
                "I couldn't complete that request.",
            )

        finally:

            self.busy = False

            if not self.listening:

                if self.modelReady:

                    self.status = "Ready"
                    self.orbState = "idle"


    # ========================================================
    # FINISH ANSWER
    # ========================================================

    def _finish_answer(
        self,
        user_text,
        answer,
    ):

        answer = strip_thinking(
            answer
        )

        if not answer:

            answer = (
                "I couldn't produce an answer."
            )

        self.messageAdded.emit(
            "assistant",
            answer,
        )

        self.answerFinished.emit(
            answer
        )

        self.speak(
            answer
        )

        # Save conversation.
        self.history.append(
            {
                "role": "user",
                "content": user_text,
            }
        )

        self.history.append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        self.history = self.history[-12:]

        save_json(
            CHAT_FILE,
            self.history,
        )


    # ========================================================
    # BUILD AI CONTEXT
    # ========================================================

    def _context_messages(
        self,
        question,
    ):

        memory_text = ""

        facts = self.memory.get(
            "facts",
            [],
        )[-8:]

        preferences = self.memory.get(
            "preferences",
            [],
        )[-8:]

        if facts or preferences:

            memory_text += (
                "\nUseful memory:\n"
            )

            if facts:

                memory_text += (
                    "Facts: "
                    + "; ".join(
                        map(str, facts)
                    )
                    + "\n"
                )

            if preferences:

                memory_text += (
                    "Preferences: "
                    + "; ".join(
                        map(str, preferences)
                    )
                    + "\n"
                )

        messages = [
            {
                "role": "system",
                "content":
                    SYSTEM_PROMPT
                    + memory_text,
            }
        ]

        # Keep recent conversation.
        messages.extend(
            self.history[-8:]
        )

        messages.append(
            {
                "role": "user",
                "content":
                    "/no_think\n"
                    + question,
            }
        )

        return messages


    # ========================================================
    # GENERATE COMPLETE ANSWER
    # ========================================================

    def _generate_answer(
        self,
        question,
    ):

        if (
            not self.modelReady
            or self.model is None
        ):

            return (
                "My local AI brain is still "
                "starting. Please try again "
                "in a moment."
            )

        mode = detect_question_type(
            question
        )

        max_tokens = TOKEN_LIMITS.get(
            mode,
            TOKEN_LIMITS["normal"],
        )

        messages = self._context_messages(
            question
        )

        first_answer, finish_reason = (
            self._generate_stream(
                messages,
                max_tokens,
            )
        )

        answer = strip_thinking(
            first_answer
        ).strip()

        # ----------------------------------------------------
        # AUTOMATIC CONTINUATION
        # ----------------------------------------------------

        if (
            finish_reason == "length"
            and answer
        ):

            log(
                "Qwen reached token limit. "
                "Continuing answer..."
            )

            continuation_messages = list(
                messages
            )

            continuation_messages.append(
                {
                    "role": "assistant",
                    "content": answer,
                }
            )

            continuation_messages.append(
                {
                    "role": "user",
                    "content":
                        "/no_think\n"
                        "Continue exactly from where "
                        "you stopped. Do not repeat "
                        "the previous answer. Finish "
                        "the remaining parts.",
                }
            )

            continuation_limit = min(
                768,
                max_tokens,
            )

            second_answer, _ = (
                self._generate_stream(
                    continuation_messages,
                    continuation_limit,
                )
            )

            second_answer = strip_thinking(
                second_answer
            ).strip()

            if second_answer:

                answer = (
                    answer.rstrip()
                    + "\n\n"
                    + second_answer.lstrip()
                )

        return answer


    # ========================================================
    # STREAM QWEN
    # ========================================================

    def _generate_stream(
        self,
        messages,
        max_tokens,
    ):

        chunks = []
        finish_reason = None

        started = time.perf_counter()

        with self.model_lock:

            result = (
                self.model.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.35,
                    top_p=0.85,
                    top_k=30,
                    repeat_penalty=1.05,
                    stream=True,
                )
            )

            for item in result:

                choices = item.get(
                    "choices",
                    [],
                )

                if not choices:
                    continue

                choice = choices[0]

                reason = choice.get(
                    "finish_reason"
                )

                if reason:
                    finish_reason = reason

                delta = (
                    choice.get(
                        "delta",
                        {},
                    )
                    or {}
                )

                token = delta.get(
                    "content",
                    "",
                )

                if token:

                    chunks.append(
                        token
                    )

                    preview = strip_thinking(
                        "".join(chunks)
                    )

                    if preview:

                        self.streamText.emit(
                            preview
                        )

        elapsed = (
            time.perf_counter()
            - started
        )

        answer = strip_thinking(
            "".join(chunks)
        ).strip()

        log(
            f"AI response: "
            f"{elapsed:.2f}s | "
            f"tokens={len(chunks)} | "
            f"finish={finish_reason}"
        )

        return answer, finish_reason


    # ========================================================
    # LOCAL WINDOWS COMMANDS
    # ========================================================

    def _handle_local_command(
        self,
        text,
    ):

        t = text.lower().strip()

        # ----------------------------------------------------
        # Greetings
        # ----------------------------------------------------

        if t in {
            "hello",
            "hi",
            "hey",
            "hey iris",
            "hello iris",
        }:

            return (
                f"Hello {USER_NAME}. "
                "What would you like to do?"
            )

        # ----------------------------------------------------
        # Identity
        # ----------------------------------------------------

        if (
            "who are you" in t
            or "what are you" in t
        ):

            return (
                "I'm Iris, your personal "
                "AI assistant running "
                "locally on your computer."
            )

        # ----------------------------------------------------
        # Memory
        # ----------------------------------------------------

        if t.startswith("remember "):

            item = text[
                len("remember "):
            ].strip()

            if item:

                self.memory.setdefault(
                    "facts",
                    [],
                ).append(item)

                self.memory["facts"] = (
                    self.memory["facts"][-20:]
                )

                save_json(
                    MEMORY_FILE,
                    self.memory,
                )

                return (
                    "I'll remember that, Eyram."
                )

        if (
            "forget everything" in t
            or "forget all memory" in t
            or "clear memory" in t
        ):

            self.memory = {
                "facts": [],
                "preferences": [],
            }

            save_json(
                MEMORY_FILE,
                self.memory,
            )

            return (
                "I've cleared the saved memory."
            )

        # ----------------------------------------------------
        # Read memory
        # ----------------------------------------------------

        if (
            t == "what do you remember"
            or t == "what do you know about me"
            or t == "show my memory"
        ):

            facts = self.memory.get(
                "facts",
                [],
            )

            preferences = self.memory.get(
                "preferences",
                [],
            )

            if not facts and not preferences:

                return (
                    "I don't have any saved "
                    "memory yet, Eyram."
                )

            parts = []

            if facts:

                parts.append(
                    "Facts: "
                    + "; ".join(
                        map(str, facts)
                    )
                )

            if preferences:

                parts.append(
                    "Preferences: "
                    + "; ".join(
                        map(str, preferences)
                    )
                )

            return "\n".join(parts)

        # ----------------------------------------------------
        # Volume
        # ----------------------------------------------------

        volume_match = re.search(
            r"(?:set|change)\s+volume\s+to\s+(\d{1,3})",
            t,
        )

        if volume_match:

            level = int(
                volume_match.group(1)
            )

            level = max(
                0,
                min(100, level),
            )

            if set_volume(level):

                return (
                    f"Volume set to "
                    f"{level} percent."
                )

            return (
                "I couldn't control the "
                "Windows volume from this setup."
            )

        if (
            t == "volume"
            or t == "what is my volume"
            or t == "check volume"
        ):

            level = get_volume()

            if level is not None:

                return (
                    f"The current volume "
                    f"is {level} percent."
                )

            return (
                "I couldn't read the Windows volume."
            )

        # ----------------------------------------------------
        # Chrome
        # ----------------------------------------------------

        if t in {
            "open chrome",
            "open google chrome",
            "launch chrome",
            "start chrome",
        }:

            chrome_paths = [
                Path(
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe"
                ),
                Path(
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
                ),
            ]

            for chrome_path in chrome_paths:

                if chrome_path.exists():

                    launch(
                        f'"{chrome_path}"'
                    )

                    return "Opening Chrome."

            launch("chrome.exe")

            return "Opening Chrome."

        # ----------------------------------------------------
        # Notepad
        # ----------------------------------------------------

        if (
            "open notepad" in t
            or t == "launch notepad"
            or t == "start notepad"
        ):

            launch(
                "notepad.exe"
            )

            return "Opening Notepad."

        # ----------------------------------------------------
        # File Explorer
        # ----------------------------------------------------

        if (
            "open file explorer" in t
            or "open explorer" in t
            or "launch explorer" in t
            or "start explorer" in t
        ):

            launch(
                "explorer.exe"
            )

            return "Opening File Explorer."

        # ----------------------------------------------------
        # Windows Settings
        # ----------------------------------------------------

        if (
            "open settings" in t
            or "open windows settings" in t
            or "launch settings" in t
            or "start settings" in t
        ):

            launch(
                "start ms-settings:"
            )

            return "Opening Windows Settings."

        # ----------------------------------------------------
        # Paint
        # ----------------------------------------------------

        if (
            "open paint" in t
            or "launch paint" in t
            or "start paint" in t
        ):

            launch(
                "mspaint.exe"
            )

            return "Opening Paint."

        # ----------------------------------------------------
        # Task Manager
        # ----------------------------------------------------

        if (
            "open task manager" in t
            or "launch task manager" in t
            or "start task manager" in t
        ):

            launch(
                "taskmgr.exe"
            )

            return "Opening Task Manager."

        # ----------------------------------------------------
        # Calculator application
        # ----------------------------------------------------

        if (
            "open calculator" in t
            or "launch calculator" in t
        ):

            launch(
                "calc.exe"
            )

            return "Opening Calculator."

        # ----------------------------------------------------
        # Websites
        # ----------------------------------------------------

        sites = {
            "open youtube":
                "https://www.youtube.com",

            "open facebook":
                "https://www.facebook.com",

            "open instagram":
                "https://www.instagram.com",

            "open google":
                "https://www.google.com",

            "open gmail":
                "https://mail.google.com",

            "open whatsapp":
                "https://web.whatsapp.com",
        }

        if t in sites:

            webbrowser.open(
                sites[t]
            )

            site_name = (
                t[5:]
                .strip()
                .title()
            )

            return (
                f"Opening {site_name}."
            )

        # ----------------------------------------------------
        # YouTube search
        # ----------------------------------------------------

        youtube_prefix = (
            "search youtube for "
        )

        if t.startswith(
            youtube_prefix
        ):

            query = text[
                len(youtube_prefix):
            ].strip()

            if query:

                url = (
                    "https://www.youtube.com/results"
                    "?search_query="
                    + urllib.parse.quote_plus(
                        query
                    )
                )

                webbrowser.open(url)

                return (
                    f"Searching YouTube "
                    f"for {query}."
                )

        # ----------------------------------------------------
        # Time
        # ----------------------------------------------------

        if (
            t.startswith(
                "what time is it"
            )
            or t in {
                "time",
                "what's the time",
                "tell me the time",
            }
        ):

            current_time = (
                datetime.now()
                .strftime("%I:%M %p")
                .lstrip("0")
            )

            return (
                f"It is {current_time}."
            )

        # ----------------------------------------------------
        # Date
        # ----------------------------------------------------

        if (
            t == "date"
            or "what is today's date" in t
            or "what's today's date" in t
            or "tell me the date" in t
        ):

            return (
                datetime.now().strftime(
                    "Today is %A, %B %d, %Y."
                )
            )

        # ----------------------------------------------------
        # Lock PC
        # ----------------------------------------------------

        if (
            "lock my pc" in t
            or "lock the pc" in t
            or "lock computer" in t
            or t == "lock pc"
        ):

            launch(
                "rundll32.exe "
                "user32.dll,LockWorkStation"
            )

            return "Locking the PC."

        # ----------------------------------------------------
        # Restart
        # ----------------------------------------------------

        if (
            t == "restart pc"
            or t == "restart my pc"
            or t == "restart computer"
        ):

            return (
                "Restart command received. "
                "I will not restart automatically "
                "without confirmation."
            )

        # ----------------------------------------------------
        # Read notifications
        # ----------------------------------------------------

        if (
            "read notifications" in t
            or "read my notifications" in t
            or "check notifications" in t
        ):

            return self._read_notifications()

        # ----------------------------------------------------
        # Calculator command
        # ----------------------------------------------------

        if t.startswith(
            "calculate "
        ):

            expression = text[
                len("calculate "):
            ].strip()

            value = safe_calculate(
                expression
            )

            if value is not None:

                if (
                    isinstance(value, float)
                    and value.is_integer()
                ):
                    value = int(value)

                return (
                    f"The answer is {value}."
                )

        return None


    # ========================================================
    # WEB COMMANDS
    # ========================================================

    def _handle_web_command(
        self,
        text,
    ):

        t = text.lower().strip()

        prefixes = (
            "search the web for ",
            "search google for ",
            "search for ",
            "google ",
            "look up ",
        )

        for prefix in prefixes:

            if t.startswith(prefix):

                query = text[
                    len(prefix):
                ].strip()

                if not query:
                    return None

                url = (
                    "https://www.google.com/search?q="
                    + urllib.parse.quote_plus(
                        query
                    )
                )

                webbrowser.open(url)

                return (
                    f"Searching the web "
                    f"for {query}."
                )

        return None


    # ========================================================
    # WINDOWS NOTIFICATIONS
    # ========================================================

    def _read_notifications(self):

        if not WINRT_NOTIFICATIONS_AVAILABLE:

            return (
                "Windows notification reading "
                "is not available because the "
                "WinRT notification module is not "
                "installed."
            )

        try:

            listener = (
                UserNotificationListener.current
            )

            access = (
                listener.request_access_async()
                .get()
            )

            if (
                UserNotificationListenerAccessStatus
                is not None
                and access
                != UserNotificationListenerAccessStatus.ALLOWED
            ):

                return (
                    "Windows has not granted Iris "
                    "permission to read notifications. "
                    "Please allow notification access "
                    "for Iris in Windows."
                )

            notifications = (
                listener.get_notifications_async(
                    0
                ).get()
            )

            if not notifications:

                return (
                    "You have no readable "
                    "Windows notifications."
                )

            results = []

            for notification in list(
                notifications
            )[:8]:

                try:

                    binding = (
                        notification.notification
                        .visual
                        .get_binding(
                            0
                        )
                    )

                    if binding is None:
                        continue

                    text_elements = (
                        binding.get_text_elements()
                    )

                    text_parts = []

                    for element in text_elements:

                        value = getattr(
                            element,
                            "text",
                            "",
                        )

                        if value:
                            text_parts.append(
                                value
                            )

                    if text_parts:

                        results.append(
                            " ".join(
                                text_parts
                            )
                        )

                except Exception:
                    continue

            if not results:

                return (
                    "I found notifications, "
                    "but I couldn't read their text."
                )

            return (
                "Here are your recent notifications: "
                + " | ".join(results)
            )

        except Exception as exc:

            log(
                f"Notification error: {exc}"
            )

            return (
                "I couldn't access Windows "
                "notifications. Make sure Iris "
                "has notification permission."
            )


    # ========================================================
    # TEXT TO SPEECH
    # ========================================================

    def speak(
        self,
        text: str,
    ):

        if pyttsx3 is None:
            return

        text = speech_text(
            text
        )

        if not text:
            return

        try:

            # Prevent huge backlog.
            while (
                self.tts_queue.qsize() >= 2
            ):

                try:
                    self.tts_queue.get_nowait()

                except queue.Empty:
                    break

            self.tts_queue.put_nowait(
                text
            )

        except queue.Full:
            pass


    def _tts_worker(self):

        if pyttsx3 is None:
            return

        try:

            engine = pyttsx3.init()

            engine.setProperty(
                "rate",
                185,
            )

            engine.setProperty(
                "volume",
                1.0,
            )

            # Prefer Microsoft Zira if available.
            for voice in engine.getProperty(
                "voices"
            ):

                name = (
                    getattr(
                        voice,
                        "name",
                        "",
                    )
                    or ""
                ).lower()

                if "zira" in name:

                    engine.setProperty(
                        "voice",
                        voice.id,
                    )

                    break

            while not self.stop_event.is_set():

                try:

                    text = self.tts_queue.get(
                        timeout=0.25
                    )

                except queue.Empty:
                    continue

                self.voice_speaking.set()

                self.orbState = "speaking"
                self.status = "Speaking..."

                try:

                    engine.say(text)
                    engine.runAndWait()

                except Exception as exc:

                    log(
                        f"TTS error: {exc}"
                    )

                finally:

                    self.voice_speaking.clear()

                    if (
                        not self.busy
                        and not self.listening
                    ):

                        if self.modelReady:

                            self.status = "Ready"
                            self.orbState = "idle"

        except Exception as exc:

            log(
                f"TTS worker failed: {exc}"
            )


    # ========================================================
    # VOICE STARTUP
    # ========================================================

    def _start_voice_if_possible(self):

        if (
            sd is None
            or Model is None
            or KaldiRecognizer is None
        ):

            log(
                "Voice disabled: "
                "sounddevice/Vosk unavailable."
            )

            return

        if not VOSK_DIR.exists():

            log(
                "Voice disabled: "
                f"Vosk model folder not found: "
                f"{VOSK_DIR}"
            )

            return

        if (
            self.voice_thread
            and self.voice_thread.is_alive()
        ):
            return

        self.voice_thread = threading.Thread(
            target=self._voice_worker,
            daemon=True,
        )

        self.voice_thread.start()


    # ========================================================
    # AUDIO CALLBACK
    # ========================================================

    def _audio_callback(
        self,
        indata,
        frames,
        callback_time,
        status,
    ):

        if status:

            log(
                f"Microphone status: {status}"
            )

        # Don't listen to Iris speaking.
        if self.voice_speaking.is_set():
            return

        try:

            self.audio_queue.put_nowait(
                bytes(indata)
            )

        except queue.Full:

            try:

                self.audio_queue.get_nowait()

                self.audio_queue.put_nowait(
                    bytes(indata)
                )

            except Exception:
                pass


    # ========================================================
    # DRAIN AUDIO
    # ========================================================

    def _drain_audio(self):

        while True:

            try:
                self.audio_queue.get_nowait()

            except queue.Empty:
                break


    # ========================================================
    # VOSK RECOGNITION
    # ========================================================

    def _recognize_until(
        self,
        recognizer,
        timeout=VOICE_COMMAND_TIMEOUT,
        silence_after_text=VOICE_SILENCE_AFTER_TEXT,
    ):

        started = time.monotonic()

        heard_at = None

        texts = []

        while (
            time.monotonic() - started
            < timeout
            and not self.stop_event.is_set()
        ):

            try:

                data = self.audio_queue.get(
                    timeout=0.12
                )

            except queue.Empty:
                continue

            if recognizer.AcceptWaveform(
                data
            ):

                try:

                    result = json.loads(
                        recognizer.Result()
                    ).get(
                        "text",
                        "",
                    ).strip()

                except Exception:
                    result = ""

                if result:

                    texts.append(result)

                    heard_at = (
                        time.monotonic()
                    )

            else:

                try:

                    partial = json.loads(
                        recognizer.PartialResult()
                    ).get(
                        "partial",
                        "",
                    ).strip()

                except Exception:
                    partial = ""

                if partial:

                    heard_at = (
                        time.monotonic()
                    )

            if (
                heard_at
                and (
                    time.monotonic()
                    - heard_at
                    >= silence_after_text
                )
            ):
                break

        try:

            final = json.loads(
                recognizer.FinalResult()
            ).get(
                "text",
                "",
            ).strip()

        except Exception:
            final = ""

        if final:
            texts.append(final)

        return clean_text(
            " ".join(texts)
        )


    # ========================================================
    # CONTINUOUS VOICE WORKER
    # ========================================================

    def _voice_worker(self):

        log(
            f"Vosk path: {VOSK_DIR}"
        )

        try:

            model = Model(
                str(VOSK_DIR)
            )

        except Exception as exc:

            log(
                f"Vosk model failed: {exc}"
            )

            return

        wake_rec = KaldiRecognizer(
            model,
            SAMPLE_RATE,
        )

        try:

            stream = sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=VOICE_BLOCKSIZE,
                device=MIC_DEVICE,
                dtype="int16",
                channels=1,
                callback=self._audio_callback,
            )

        except Exception as exc:

            log(
                f"Microphone failed: {exc}"
            )

            return

        log(
            "Continuous voice listener ready."
        )

        with stream:

            self.status = "Ready"
            self.orbState = "idle"

            while not self.stop_event.is_set():

                try:

                    data = self.audio_queue.get(
                        timeout=0.2
                    )

                except queue.Empty:
                    continue

                if (
                    self.voice_speaking.is_set()
                    or self.busy
                    or self.listening
                ):
                    continue

                if wake_rec.AcceptWaveform(
                    data
                ):

                    try:

                        heard = json.loads(
                            wake_rec.Result()
                        ).get(
                            "text",
                            "",
                        ).lower()

                    except Exception:
                        heard = ""

                    if WAKE_WORD in heard:

                        self._voice_command_cycle(
                            model
                        )

                        # Reset wake recognizer.
                        wake_rec = KaldiRecognizer(
                            model,
                            SAMPLE_RATE,
                        )


    # ========================================================
    # WAKE WORD -> COMMAND
    # ========================================================

    def _voice_command_cycle(
        self,
        model,
    ):

        self.listening = True

        self.status = "Listening..."
        self.orbState = "listening"

        self._drain_audio()

        # Greeting ONLY after wake word.
        self.speak(
            f"Hello {USER_NAME}. "
            "How can I help you?"
        )

        # Wait for greeting.
        while (
            self.voice_speaking.is_set()
            and not self.stop_event.is_set()
        ):

            time.sleep(0.03)

        self._drain_audio()

        command_rec = KaldiRecognizer(
            model,
            SAMPLE_RATE,
        )

        command = self._recognize_until(
            command_rec,
            timeout=VOICE_COMMAND_TIMEOUT,
            silence_after_text=VOICE_SILENCE_AFTER_TEXT,
        )

        self._drain_audio()

        self.listening = False

        if command:

            log(
                f"Voice command: {command}"
            )

            self.sendMessage(
                command
            )

        else:

            self.status = "Ready"
            self.orbState = "idle"


    # ========================================================
    # NEW CHAT
    # ========================================================

    @Slot()
    def newChat(self):

        self.history.clear()

        save_json(
            CHAT_FILE,
            [],
        )

        self.conversationCleared.emit()

        self.status = "Ready"
        self.orbState = "idle"


    # ========================================================
    # TOGGLE VOICE
    # ========================================================

    @Slot()
    def toggleVoice(self):

        if (
            sd is None
            or Model is None
        ):

            self.errorMessage.emit(
                "Voice recognition is not available."
            )

            return

        self._start_voice_if_possible()

        self.listening = not self.listening

        if self.listening:

            self.status = "Listening..."
            self.orbState = "listening"

            self.speak(
                "Listening."
            )

        else:

            self.status = "Ready"
            self.orbState = "idle"


    # ========================================================
    # STOP
    # ========================================================

    @Slot()
    def stop(self):

        self.stop_event.set()

        # Stop queued speech.
        try:

            while True:
                self.tts_queue.get_nowait()

        except queue.Empty:
            pass


# ============================================================
# MAIN
# ============================================================

def main():

    log(
        f"Starting {APP_NAME} "
        f"v{VERSION} "
        f"for {USER_NAME}"
    )

    log(
        f"Base directory: {BASE_DIR}"
    )

    log(
        f"Qwen path: {QWEN_PATH}"
    )

    log(
        f"Vosk path: {VOSK_DIR}"
    )

    log(
        f"CPU threads: {N_THREADS}"
    )

    log(
        f"Batch size: {N_BATCH}"
    )

    log(
        f"Context size: {N_CTX}"
    )

    app = QGuiApplication(
        sys.argv
    )

    engine = QQmlApplicationEngine()

    # ========================================================
    # QML WARNINGS
    # ========================================================

    def qml_warnings(warnings):

        for warning in warnings:

            log(
                f"QML: {warning.toString()}"
            )

    engine.warnings.connect(
        qml_warnings
    )

    # ========================================================
    # FROZEN APPLICATION SUPPORT
    # ========================================================

    if getattr(
        sys,
        "frozen",
        False,
    ):

        qml_import = (
            BUNDLE_ROOT
            / "PySide6"
            / "qml"
        )

        if qml_import.exists():

            os.environ[
                "QML2_IMPORT_PATH"
            ] = str(
                qml_import
            )

        plugin_path = (
            BUNDLE_ROOT
            / "PySide6"
            / "plugins"
        )

        if plugin_path.exists():

            os.environ[
                "QT_PLUGIN_PATH"
            ] = str(
                plugin_path
            )

    # ========================================================
    # BACKEND
    # ========================================================

    backend = IrisBackend()

    engine.rootContext().setContextProperty(
        "iris",
        backend,
    )

    engine.rootContext().setContextProperty(
        "irisVersion",
        VERSION,
    )

    # ========================================================
    # LOAD QML
    # ========================================================

    candidates = [
        QML_PATH,
        QML_BUNDLE_PATH,
    ]

    qml_loaded = False

    for candidate in candidates:

        if candidate.exists():

            log(
                f"Loading QML: {candidate}"
            )

            engine.load(
                QUrl.fromLocalFile(
                    str(candidate)
                )
            )

            qml_loaded = True

            break

    if not qml_loaded:

        raise RuntimeError(
            "Main.qml not found.\n"
            f"Checked:\n"
            f"{QML_PATH}\n"
            f"{QML_BUNDLE_PATH}"
        )

    if not engine.rootObjects():

        raise RuntimeError(
            "QML engine reported no root "
            "objects. Check the QML messages."
        )

    # ========================================================
    # ERROR SIGNAL
    # ========================================================

    backend.errorMessage.connect(
        lambda msg:
            log(
                f"ERROR: {msg}"
            )
    )

    # ========================================================
    # START BACKEND
    # ========================================================

    backend.start()

    app.aboutToQuit.connect(
        backend.stop
    )

    # ========================================================
    # RUN APPLICATION
    # ========================================================

    sys.exit(
        app.exec()
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()