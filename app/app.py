import os
import sys
import json
import time
import wave
import io
import base64
import hashlib
import urllib.request
import urllib.error
import urllib.parse
import re
import sqlite3
import ctypes
import logging
import logging.handlers
import threading
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import sounddevice as sd
import pyperclip
import keyring

from PySide6.QtCore import (
    Qt, Signal, QObject, QTimer, QSettings, QElapsedTimer, QUrl, QRectF, QPointF, QPoint, QSize,
    QPropertyAnimation, QEasingCurve
)
from PySide6.QtGui import (
    QIcon, QAction, QPixmap, QPainter, QPen, QColor, QPainterPath, QFont,
    QDesktopServices, QCursor, QLinearGradient, QBrush
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QCheckBox, QLineEdit, QMessageBox, QSystemTrayIcon,
    QMenu, QFrame, QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QDoubleSpinBox, QPlainTextEdit, QSizePolicy, QScrollArea,
    QGraphicsDropShadowEffect, QAbstractItemView, QButtonGroup, QDialog, QProgressDialog
)

APP_NAME = "SHUNCHi"
APP_VERSION = "4.6.0"
APP_VENDOR = "RUHUL"
KEYRING_SERVICE = "SHUNCHi"
KEYRING_USERNAME = "gemini_api_key"
TRANSCRIBE_MODEL = "gemini-3.5-transcribe"
BACKUP_MODEL = "gemini-3.8-flash"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
# Official website. The software reads UPDATE_URL (a small JSON file on the website) to announce new
# versions and to list "More Apps". Change these two lines if the website layout changes.
WEBSITE_URL = "https://shunchiai.com"
WEBSITE_LABEL = "shunchiai.com"
UPDATE_URL = "https://shunchiai.com/update.json"
DOWNLOAD_URL_DEFAULT = "https://shunchiai.com/download"
NOTICES_URL = WEBSITE_URL + "/data/notices.json"      # pop-up messages written in the admin panel
APPS_PAGE_URL = WEBSITE_URL + "/apps/index.html"
IDEA_ENDPOINT = "https://formsubmit.co/ajax/ruhulaaminn@gmail.com"   # where the "app or tool idea" form is delivered
READY_TEXT = "Ready · Win + Left Ctrl = Bangla · Win + Left Shift = English"
UPDATE_CHECK_HOURS = 3
IDEA_FALLBACK_URL = APPS_PAGE_URL + "#suggest"
APP_OWNER = {}      # set by ShunchiApp so the window can ask it to shut down cleanly
INSTALLER_PREFIX = "/theruhulaamin/shunchi_repo_github/releases/download/"
TARGET_RATE = 16000
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "SHUNCHi"
APPDATA = Path(os.getenv("APPDATA", str(Path.home()))) / APP_NAME
APPDATA.mkdir(parents=True, exist_ok=True)
DB_PATH = APPDATA / "history.db"
LOG_PATH = APPDATA / "shunchi.log"

_log_handler = logging.handlers.RotatingFileHandler(
    str(LOG_PATH), maxBytes=1_000_000, backupCount=2, encoding="utf-8"
)
_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])


def resource_path(relative):
    base = getattr(sys, "_MEIPASS", str(Path(__file__).parent))
    return str(Path(base) / relative)


# ----------------------------------------------------------------------------------------------
# Audio helpers
# ----------------------------------------------------------------------------------------------
class StreamResampler:
    """Stateful mono resampler (any input rate -> 16 kHz) built on NumPy only.

    A Kaiser-windowed-sinc low-pass filter removes content above the target Nyquist frequency, then
    linear interpolation picks the output samples. Filter history and the fractional read position
    are kept between chunks, so there are no clicks at chunk boundaries."""

    def __init__(self, in_rate, out_rate=16000, taps=95):
        self.in_rate = int(in_rate)
        self.out_rate = int(out_rate)
        self.passthrough = self.in_rate == self.out_rate
        if self.passthrough:
            return
        cutoff = 0.46 * self.out_rate / self.in_rate
        n = np.arange(taps) - (taps - 1) / 2.0
        h = 2 * cutoff * np.sinc(2 * cutoff * n) * np.kaiser(taps, 8.6)
        self.h = (h / h.sum()).astype(np.float32)
        self.step = self.in_rate / self.out_rate
        self.pos = 0.0
        self.tail = np.zeros(taps - 1, dtype=np.float32)
        self.carry = np.zeros(0, dtype=np.float32)

    def process(self, samples):
        x = np.asarray(samples, dtype=np.float32)
        if self.passthrough or x.size == 0:
            return x
        buf = np.concatenate((self.tail, x))
        filtered = np.convolve(buf, self.h, mode="valid")
        self.tail = buf[-(len(self.h) - 1):]
        stream = np.concatenate((self.carry, filtered))
        n_out = int(np.floor((len(stream) - 1 - self.pos) / self.step)) + 1
        if n_out <= 0:
            self.carry = stream
            return np.zeros(0, dtype=np.float32)
        idx = self.pos + np.arange(n_out) * self.step
        i0 = np.floor(idx).astype(np.int64)
        frac = (idx - i0).astype(np.float32)
        out = stream[i0] * (1 - frac) + stream[np.minimum(i0 + 1, len(stream) - 1)] * frac
        next_pos = self.pos + n_out * self.step
        drop = int(np.floor(next_pos))
        self.carry = stream[drop:]
        self.pos = next_pos - drop
        return out.astype(np.float32)


class VoiceActivityDetector:
    """Adaptive energy-based voice activity detection (pure logic, no Qt, unit-tested).

    The noise floor is learned in the first 0.4 s and keeps adapting during pauses, so a noisy room
    or a rising fan never stops the recording from ending. Speech starts above a threshold that is a
    multiple of the floor and ends after `silence_seconds` of quiet (with hysteresis)."""

    CALIBRATION_SECONDS = 0.4

    def __init__(self, silence_seconds=1.0, no_speech_timeout=8.0, max_seconds=300.0):
        self.silence_seconds = float(silence_seconds)
        # A short pause (about half a second) is announced early with the "pause" event so the app can
        # start transcribing while it waits for the rest of the silence: the text arrives sooner.
        self.pause_hint = max(0.25, min(0.4, self.silence_seconds - 0.25))
        self.hint_sent = False
        self.no_speech_timeout = float(no_speech_timeout)
        self.max_seconds = float(max_seconds)
        self.floor = 60.0
        self.calibration = []
        self.speaking = False
        self.voiced_frames = 0
        self.candidate = 0
        self.last_voice_time = 0.0

    def thresholds(self):
        start = max(self.floor * 3.0, self.floor + 110.0, 170.0)
        stop = max(self.floor * 1.8, self.floor + 55.0, 100.0)
        return start, stop

    def is_voice_frame(self, rms):
        """Used for pre-/post-roll trimming of the recording."""
        start, stop = self.thresholds()
        return rms > (stop if self.speaking else start)

    def process(self, rms, dt, elapsed):
        """Feed one frame. Returns None, 'speech_started', 'pause', 'silence', 'no_speech' or 'max'."""
        rms = float(rms)
        if elapsed >= self.max_seconds:
            return "max"
        if elapsed < self.CALIBRATION_SECONDS:
            self.calibration.append(rms)
            self.floor = float(np.clip(np.percentile(self.calibration, 25), 15.0, 700.0))
            return None
        start, stop = self.thresholds()
        if not self.speaking:
            if rms > start:
                self.candidate += 1
                if self.candidate >= 2:
                    self.speaking = True
                    self.voiced_frames = self.candidate
                    self.last_voice_time = elapsed
                    return "speech_started"
            else:
                self.candidate = 0
                self.floor = float(np.clip(0.92 * self.floor + 0.08 * rms, 15.0, 700.0))
                if elapsed >= self.no_speech_timeout:
                    return "no_speech"
            return None
        if rms > stop:
            self.voiced_frames += 1
            self.last_voice_time = elapsed
            self.hint_sent = False
        else:
            self.floor = float(np.clip(0.97 * self.floor + 0.03 * rms, 15.0, 700.0))
            quiet_for = elapsed - self.last_voice_time
            if quiet_for >= self.silence_seconds and self.voiced_frames >= 3:
                return "silence"
            if quiet_for >= self.pause_hint and not self.hint_sent and self.voiced_frames >= 6:
                self.hint_sent = True
                return "pause"
        return None


def pcm_to_wav(pcm_data, sample_rate=TARGET_RATE):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_data)
    return buffer.getvalue()


def trim_recording(chunks, pre_roll=3, post_roll=4):
    """chunks: list of (pcm_bytes, voiced_flag). Keeps the speech with a little context around it
    so less audio is uploaded (faster) and no long silence confuses the model."""
    voiced = [i for i, (_, flag) in enumerate(chunks) if flag]
    if not voiced:
        return b"", 0
    first = max(0, voiced[0] - pre_roll)
    last = min(len(chunks) - 1, voiced[-1] + post_roll)
    return b"".join(chunk for chunk, _ in chunks[first:last + 1]), len(voiced)


# ----------------------------------------------------------------------------------------------
# Small utilities
# ----------------------------------------------------------------------------------------------
def redact(text, secret):
    text = str(text)
    return text.replace(secret, "[redacted]") if secret else text


class GeminiError(Exception):
    def __init__(self, message, status=None, kind="error"):
        super().__init__(message)
        self.status = status
        self.kind = kind  # error | auth | quota | network | access | empty


def friendly_error(exc):
    """Short, actionable text for the user."""
    if isinstance(exc, GeminiError):
        if exc.kind == "auth":
            return "The Gemini API key was rejected. Create a new key in Google AI Studio and save it again."
        if exc.kind == "quota":
            return "Gemini limit reached. Wait a minute, or check your quota in Google AI Studio."
        if exc.kind == "network":
            return "Could not reach Google Gemini. Check your internet connection."
        if exc.kind == "access":
            return "This API key cannot use the transcription model yet. Check access in Google AI Studio."
        if exc.kind == "empty":
            return "No speech was recognised. Speak a little closer to the microphone."
    text = str(exc) or exc.__class__.__name__
    return text[:260]


def send_ctrl_v():
    """Send Ctrl+V to the focused window with the Win32 SendInput API (no extra dependency)."""
    if os.name != "nt":
        raise RuntimeError("Automatic paste is only available on Windows.")
    from ctypes import wintypes

    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    VK_CONTROL, VK_V, KEYUP = 0x11, 0x56, 0x0002

    def key(vk, up=False):
        return INPUT(1, _INPUTUNION(ki=KEYBDINPUT(vk, 0, KEYUP if up else 0, 0, 0)))

    sequence = (INPUT * 4)(key(VK_CONTROL), key(VK_V), key(VK_V, True), key(VK_CONTROL, True))
    sent = ctypes.windll.user32.SendInput(4, ctypes.byref(sequence), ctypes.sizeof(INPUT))
    if sent != 4:
        raise RuntimeError("Windows blocked the paste keystroke (the target app may be running as administrator).")


def wait_for_modifier_release(timeout=1.5):
    """Wait until Win/Ctrl/Shift/Alt are released so Ctrl+V is not mixed with them."""
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    keys = (0x5B, 0x5C, 0xA2, 0xA3, 0xA0, 0xA1, 0xA4, 0xA5)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(user32.GetAsyncKeyState(k) & 0x8000 for k in keys):
            return
        time.sleep(0.02)


def startup_supported():
    return os.name == "nt" and bool(getattr(sys, "frozen", False))


def startup_enabled():
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return True
    except OSError:
        return False


def set_startup_enabled(enabled):
    """Add/remove the per-user Windows start-up entry. Raises on failure."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, f'"{sys.executable}" --minimized')
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE_NAME)
            except FileNotFoundError:
                pass


def parse_version(text):
    """'4.10.2' -> (4, 10, 2, 0) so versions compare correctly (4.10 > 4.9)."""
    numbers = [int(n) for n in re.findall(r"\d+", str(text or ""))[:4]]
    return tuple(numbers + [0] * (4 - len(numbers))) if numbers else (0, 0, 0, 0)


def is_trusted_installer_url(url):
    """The installer may only come from this project's GitHub releases (https), never from anywhere else."""
    try:
        parts = urllib.parse.urlparse(str(url))
    except ValueError:
        return False
    return (parts.scheme == "https" and (parts.hostname or "").lower() == "github.com"
            and parts.path.lower().startswith(INSTALLER_PREFIX) and parts.path.lower().endswith(".exe"))


def is_trusted_url(url):
    """Downloads must come from https on the official website only."""
    try:
        parts = urllib.parse.urlparse(str(url))
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host == "shunchiai.com" or host.endswith(".shunchiai.com"))


def nearest_option(value, options):
    """Snap a stored number to the closest value offered by a segmented control."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return options[0]
    return min(options, key=lambda option: abs(option - number))


def parse_update_manifest(data):
    """Validate the JSON published at UPDATE_URL. Anything unexpected is rejected or trimmed."""
    if not isinstance(data, dict):
        raise ValueError("update manifest is not an object")
    latest = str(data.get("latest_version") or data.get("version") or "").strip()
    if not re.fullmatch(r"\d+(\.\d+){1,3}", latest):
        raise ValueError("update manifest has no valid version")
    download = str(data.get("download_url") or "").strip()
    if not is_trusted_url(download):
        download = DOWNLOAD_URL_DEFAULT
    apps = []
    raw_apps = data.get("apps")
    for item in (raw_apps if isinstance(raw_apps, list) else [])[:12]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:40]
        url = str(item.get("url") or "").strip()[:300]
        if not name or not url.lower().startswith("https://"):
            continue
        apps.append({"name": name, "tagline": str(item.get("tagline") or "").strip()[:120],
                     "url": url, "badge": str(item.get("badge") or "").strip()[:16]})
    installer_url = str(data.get("installer_url") or "").strip()
    sha = str(data.get("installer_sha256") or "").strip().lower()
    try:
        size = int(data.get("installer_size") or 0)
    except (TypeError, ValueError):
        size = 0
    if not (is_trusted_installer_url(installer_url) and re.fullmatch(r"[0-9a-f]{64}", sha) and 1_000_000 <= size <= 600_000_000):
        installer_url, sha, size = "", "", 0          # no verified installer: the app only opens the download page
    min_raw = str(data.get("min_version") or "").strip()
    min_version = min_raw if re.fullmatch(r"\d+(\.\d+){1,3}", min_raw) else ""
    return {"latest": latest, "download_url": download, "installer_url": installer_url,
            "installer_sha256": sha, "installer_size": size, "min_version": min_version,
            "notes": str(data.get("release_notes") or "").strip()[:600],
            "released": str(data.get("released") or "").strip()[:20], "apps": apps}


def fetch_update_manifest(timeout=8):
    request = urllib.request.Request(
        UPDATE_URL, headers={"User-Agent": f"SHUNCHi/{APP_VERSION}", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(65536)
    return parse_update_manifest(json.loads(raw.decode("utf-8")))


def social_url(network):
    urls = {
        "Facebook": "https://www.facebook.com/iamruhulaamin",
        "Instagram": "https://www.instagram.com/iamruhulaamin/",
        "LinkedIn": "https://www.linkedin.com/search/results/people/?keywords=iamruhulaamin",
    }
    return urls[network]


def parse_notices(data):
    """Validate the pop-up messages published at NOTICES_URL. Unknown or unsafe values are dropped."""
    clean = []
    for raw in (data if isinstance(data, list) else [])[:20]:
        if not isinstance(raw, dict) or raw.get("active") is False:
            continue
        nid = re.sub(r"[^a-z0-9_-]", "", str(raw.get("id") or "").lower())[:40]
        if not nid:
            continue

        def text(key, limit):
            return str(raw.get(key) or "").strip()[:limit]

        item: dict = {"id": nid, "title_en": text("title_en", 90), "title_bn": text("title_bn", 90),
                "body_en": text("body_en", 600), "body_bn": text("body_bn", 600),
                "button_en": text("button_en", 40), "button_bn": text("button_bn", 40)}
        if not (item["title_en"] or item["title_bn"] or item["body_en"] or item["body_bn"]):
            continue
        url = text("button_url", 300)
        item["url"] = url if url.lower().startswith("https://") else ""
        try:
            item["start"] = datetime.strptime(text("start", 10), "%Y-%m-%d").date()
        except ValueError:
            item["start"] = datetime.now().date()
        try:
            item["days"] = max(1, min(365, int(raw.get("days") or 1)))
        except (TypeError, ValueError):
            item["days"] = 1
        try:
            item["times"] = max(1, min(50, int(raw.get("times") or 1)))
        except (TypeError, ValueError):
            item["times"] = 1
        clean.append(item)
    return clean


def notice_due(notice, shown_count, last_shown, now=None):
    """True while the message is inside its date window, has not used up its number of showings,
    and was not shown in the last 3 hours (so one app start never nags more than once)."""
    today = (now or datetime.now()).date()
    if today < notice["start"] or today > notice["start"] + timedelta(days=notice["days"] - 1):
        return False
    if shown_count >= notice["times"]:
        return False
    if last_shown and time.time() - last_shown < 3 * 3600:
        return False
    return True


def close_stream_quietly(stream):
    """Closing a microphone stream can block for seconds on some devices (Bluetooth). Never do it on the UI thread."""
    for action in (stream.stop, stream.close):
        try:
            action()
        except Exception:
            logging.exception("Closing microphone stream failed")


# ----------------------------------------------------------------------------------------------
# History (simple local log of dictations)
# ----------------------------------------------------------------------------------------------
def init_database():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS dictations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                language TEXT NOT NULL,
                duration REAL NOT NULL,
                transcript TEXT NOT NULL
            )
        """)
        con.commit()


def save_history(language, duration, transcript):
    init_database()
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO dictations(created_at, language, duration, transcript) VALUES(?,?,?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), language, float(duration), transcript)
        )
        con.commit()


def read_history(limit=500):
    init_database()
    with sqlite3.connect(DB_PATH) as con:
        return con.execute(
            "SELECT id, created_at, language, duration, transcript FROM dictations ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()


def clear_history():
    init_database()
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM dictations")
        con.commit()


# ----------------------------------------------------------------------------------------------
# Signals, microphone scan, Gemini client, workers, global hotkeys
# ----------------------------------------------------------------------------------------------
class AppSignals(QObject):
    hotkey = Signal(str)
    hotkey_error = Signal(str)
    audio_level = Signal(float, float)       # level 0..1, elapsed seconds
    speech_started = Signal()
    auto_stop = Signal(str)                  # silence | no_speech | max
    transcribed = Signal(str)
    transcribe_failed = Signal(str, str)     # friendly message, kind
    status = Signal(str)
    api_test_finished = Signal(bool, str)
    microphones_ready = Signal(object, object)
    pause_hint = Signal()
    spec_done = Signal(int, str, str, str)   # token, text, friendly message, error kind ("" = success)
    update_result = Signal(object)
    notices_ready = Signal(object)
    idea_result = Signal(bool, str)
    update_progress = Signal(int)
    update_downloaded = Signal(bool, str)


class MicrophoneScanner(threading.Thread):
    """Enumerate PortAudio devices in the background; never block app start-up."""
    def __init__(self, signals):
        super().__init__(daemon=True, name="SHUNCHi-Microphone-Scan")
        self.signals = signals

    def run(self):
        try:
            devices = []
            for index, device in enumerate(sd.query_devices()):
                channels = int(device.get("max_input_channels", 0))
                name = str(device.get("name", f"Microphone {index}"))
                if any(t in name.casefold() for t in ("stereo mix", "sound mapper", "primary sound capture driver")):
                    continue
                if channels > 0:
                    devices.append((index, name, channels, int(device.get("default_samplerate") or 48000)))
            try:
                default_input = sd.default.device[0]
                if default_input is not None and int(default_input) < 0:
                    default_input = None
            except Exception:
                default_input = None
            self.signals.microphones_ready.emit(devices, default_input)
        except Exception as exc:
            logging.warning("Microphone enumeration failed: %s", exc)
            self.signals.microphones_ready.emit([], None)


def gemini_post(api_key, model, payload, timeout=40):
    """POST to generateContent. The key travels in a header, never in the URL or the logs."""
    url = f"{API_BASE}/{model}:generateContent"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        message = raw
        try:
            message = json.loads(raw).get("error", {}).get("message", raw)
        except Exception:
            pass
        low = (message or "").lower()
        if exc.code in (401,) or "api key not valid" in low or "api_key_invalid" in low:
            kind = "auth"
        elif exc.code == 429 or "quota" in low or "resource_exhausted" in low:
            kind = "quota"
        elif exc.code in (403, 404):
            kind = "access"
        else:
            kind = "error"
        if exc.code == 400 and ("api key" in low and "valid" in low):
            kind = "auth"
        raise GeminiError(redact(f"HTTP {exc.code}: {message}", api_key)[:600], exc.code, kind)
    except urllib.error.URLError as exc:
        raise GeminiError(redact(f"Network error: {exc.reason}", api_key), None, "network")
    except (TimeoutError, OSError) as exc:
        raise GeminiError(redact(f"Network error: {exc}", api_key), None, "network")


def extract_text(response):
    """Pull the transcript out of a generateContent response (plain text or audioTranscription)."""
    pieces = []
    for candidate in (response or {}).get("candidates", []) or []:
        for part in (candidate.get("content") or {}).get("parts", []) or []:
            if part.get("thought"):
                continue
            text = part.get("text")
            if not text:
                transcription = part.get("audioTranscription") or part.get("audio_transcription") or {}
                text = transcription.get("text")
            if text:
                pieces.append(str(text).strip())
    return " ".join(p for p in pieces if p).strip()


def audio_part(pcm):
    return {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(pcm_to_wav(pcm)).decode("ascii")}}


_STRATEGY = {"index": 0}   # remembers which request shape worked, so a rejected shape is not retried every time


def transcribe_pcm(api_key, pcm, language, smart):
    """One audio chunk -> text. Tries the dedicated transcribe model first, then plain, then the backup model."""
    hint = ["bn-BD", "en-US"] if language == "bn-BD" else ["en-US"]
    config = {"languageCodes": hint}
    if smart:
        config["mode"] = "SMART"
    strategies = [
        (TRANSCRIBE_MODEL, {"contents": [{"parts": [audio_part(pcm)]}],
                            "generationConfig": {"audioTranscriptionConfig": config}}),
        (TRANSCRIBE_MODEL, {"contents": [{"parts": [audio_part(pcm)]}]}),
        (BACKUP_MODEL, {"contents": [{"parts": [
            {"text": "Transcribe this audio exactly as spoken, in the language(s) spoken (Bangla in Bengali script, "
                     "English in English). Add natural punctuation and remove filler words. Output only the transcript."},
            audio_part(pcm)]}],
            "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}),
    ]
    last_error = None
    deadline = time.monotonic() + 80.0
    first = _STRATEGY["index"] if 0 <= _STRATEGY["index"] < len(strategies) else 0
    order = [first] + [i for i in range(len(strategies)) if i != first]
    clean = True   # True while every earlier attempt was a plain "this request shape is not accepted"
    for index in order:
        model, payload = strategies[index]
        for attempt in range(2):
            if time.monotonic() > deadline:
                raise last_error or GeminiError("Gemini took too long to answer.", None, "network")
            try:
                text = extract_text(gemini_post(api_key, model, payload))
                if text:
                    if clean:
                        _STRATEGY["index"] = index
                    return text
                last_error = GeminiError(f"{model} returned no text", None, "empty")
                clean = False
                break
            except GeminiError as exc:
                last_error = exc
                if exc.kind not in ("error", "access"):
                    clean = False
                logging.warning("Transcription attempt failed (%s, strategy %d): %s", model, index + 1, exc)
                if exc.kind in ("auth", "quota"):
                    raise
                if exc.kind == "network" and attempt == 0:
                    time.sleep(0.8)
                    continue
                if exc.kind == "network":
                    raise
                break
    raise last_error or GeminiError("Transcription failed", None, "error")


class TranscribeWorker(threading.Thread):
    """Send the recorded speech to Gemini once and return the finished, punctuated text."""
    CHUNK_BYTES = 120 * TARGET_RATE * 2

    def __init__(self, api_key, pcm, language, smart, signals, token=None):
        super().__init__(daemon=True, name="SHUNCHi-Transcribe")
        self.api_key, self.pcm, self.language, self.smart, self.signals = api_key, pcm, language, smart, signals
        self.token = token   # not None -> speculative early transcription (result goes to spec_done)

    def _ok(self, text):
        if self.token is None:
            self.signals.transcribed.emit(text)
        else:
            self.signals.spec_done.emit(self.token, text, "", "")

    def _fail(self, message, kind):
        if self.token is None:
            self.signals.transcribe_failed.emit(message, kind)
        else:
            self.signals.spec_done.emit(self.token, "", message, kind or "error")

    def run(self):
        started = time.monotonic()
        try:
            parts = []
            for offset in range(0, len(self.pcm), self.CHUNK_BYTES):
                piece = self.pcm[offset:offset + self.CHUNK_BYTES]
                parts.append(transcribe_pcm(self.api_key, piece, self.language, self.smart))
            text = "\n".join(parts).strip() if self.smart else " ".join(parts).strip()
            logging.info("Transcribed %.1fs of audio in %.1fs%s", len(self.pcm) / (TARGET_RATE * 2),
                         time.monotonic() - started, " (early)" if self.token is not None else "")
            self._ok(text)
        except GeminiError as exc:
            logging.error("Transcription failed: %s", redact(exc, self.api_key))
            self._fail(friendly_error(exc), exc.kind)
        except Exception as exc:
            logging.exception("Unexpected transcription failure")
            self._fail(friendly_error(exc), "error")


class ApiTester(threading.Thread):
    """Checks that the key works with the transcription model (falls back to the backup model)."""
    def __init__(self, api_key, signals):
        super().__init__(daemon=True, name="SHUNCHi-ApiTest")
        self.api_key, self.signals = api_key, signals

    def run(self):
        silence = b"\x00\x00" * int(TARGET_RATE * 1.0)
        try:
            gemini_post(self.api_key, TRANSCRIBE_MODEL,
                        {"contents": [{"parts": [audio_part(silence)]}]}, timeout=30)
            _STRATEGY["index"] = 0
            self.signals.api_test_finished.emit(True, "Connected · Gemini transcription is ready.")
            return
        except GeminiError as exc:
            logging.warning("API test (transcribe model) failed: %s", exc)
            if exc.kind in ("auth", "network", "quota"):
                self.signals.api_test_finished.emit(False, friendly_error(exc))
                return
            first = exc
        try:
            gemini_post(self.api_key, BACKUP_MODEL, {"contents": [{"parts": [{"text": "Reply with OK."}]}]}, timeout=30)
            self.signals.api_test_finished.emit(
                True, "Connected · the backup model will be used (transcription model not available for this key).")
        except GeminiError as exc:
            logging.warning("API test (backup model) failed: %s", exc)
            self.signals.api_test_finished.emit(False, friendly_error(first if exc.kind == "error" else exc))


class UpdateChecker(threading.Thread):
    """Reads the small update manifest from the official website. Never raises into the UI."""
    def __init__(self, signals, manual=False):
        super().__init__(daemon=True, name="SHUNCHi-Update-Check")
        self.signals, self.manual = signals, manual

    def run(self):
        try:
            info = fetch_update_manifest()
            self.signals.update_result.emit({"ok": True, "manual": self.manual, "info": info})
        except urllib.error.HTTPError as exc:
            logging.info("Update check: HTTP %s", exc.code)
            message = "The update service is not available yet." if exc.code == 404 else f"Update server answered {exc.code}."
            self.signals.update_result.emit({"ok": False, "manual": self.manual, "error": message})
        except (urllib.error.URLError, TimeoutError, OSError):
            logging.info("Update check: network unavailable")
            self.signals.update_result.emit({"ok": False, "manual": self.manual,
                                             "error": "Could not reach shunchiai.com. Check your internet connection."})
        except Exception as exc:
            logging.info("Update check: unreadable manifest: %s", exc)
            self.signals.update_result.emit({"ok": False, "manual": self.manual,
                                             "error": "The update information could not be read."})


class NoticeChecker(threading.Thread):
    """Reads the pop-up messages from the official website. Never raises into the UI."""
    def __init__(self, signals):
        super().__init__(daemon=True, name="SHUNCHi-Notices")
        self.signals = signals

    def run(self):
        try:
            request = urllib.request.Request(
                NOTICES_URL, headers={"User-Agent": f"SHUNCHi/{APP_VERSION}", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=8) as response:
                raw = response.read(65536)
            self.signals.notices_ready.emit(parse_notices(json.loads(raw.decode("utf-8"))))
        except Exception as exc:
            logging.info("Notices not available: %s", exc)


class InstallerDownloader(threading.Thread):
    """Downloads the installer, checks its size and SHA-256, and only then reports success."""
    def __init__(self, signals, url, sha256, size, destination):
        super().__init__(daemon=True, name="SHUNCHi-Installer-Download")
        self.signals, self.url, self.sha256, self.size, self.destination = signals, url, sha256, int(size), str(destination)
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        part = self.destination + ".part"
        try:
            os.makedirs(os.path.dirname(self.destination), exist_ok=True)
            request = urllib.request.Request(self.url, headers={"User-Agent": f"SHUNCHi/{APP_VERSION}"})
            digest, done, last_percent = hashlib.sha256(), 0, -1
            with urllib.request.urlopen(request, timeout=30) as response, open(part, "wb") as out:
                total = int(response.headers.get("Content-Length") or self.size or 0)
                while True:
                    if self.cancel_event.is_set():
                        raise InterruptedError("cancelled")
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    percent = min(99, done * 100 // total) if total else 0
                    if percent != last_percent:
                        last_percent = percent
                        self.signals.update_progress.emit(percent)
            if self.size and done != self.size:
                raise ValueError("the downloaded file has the wrong size")
            if digest.hexdigest() != self.sha256:
                raise ValueError("the downloaded file failed the safety check")
            os.replace(part, self.destination)
            self.signals.update_progress.emit(100)
            self.signals.update_downloaded.emit(True, self.destination)
        except InterruptedError:
            self._cleanup(part)
            self.signals.update_downloaded.emit(False, "cancelled")
        except Exception as exc:
            logging.info("Installer download failed: %s", exc)
            self._cleanup(part)
            self.signals.update_downloaded.emit(False, str(exc)[:160])

    @staticmethod
    def _cleanup(part):
        try:
            if os.path.exists(part):
                os.remove(part)
        except OSError:
            pass


class IdeaSender(threading.Thread):
    """Sends the 'app or tool idea' form to the developer. Never raises into the UI."""
    def __init__(self, signals, fields):
        super().__init__(daemon=True, name="SHUNCHi-Idea")
        self.signals, self.fields = signals, fields

    def run(self):
        try:
            payload = dict(self.fields)
            payload.update({"_subject": "SHUNCHi idea: " + str(self.fields.get("Idea", ""))[:80],
                            "_template": "table", "_captcha": "false", "Source": f"SHUNCHi app {APP_VERSION}"})
            request = urllib.request.Request(
                IDEA_ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST",
                headers={"Content-Type": "application/json", "Accept": "application/json",
                         "Origin": WEBSITE_URL, "Referer": WEBSITE_URL + "/apps/index.html",
                         "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) SHUNCHi/{APP_VERSION}"})
            with urllib.request.urlopen(request, timeout=20) as response:
                answer = json.loads(response.read(65536).decode("utf-8") or "{}")
            if str(answer.get("success", "true")).lower() == "false":
                raise ValueError("the form service did not accept the message")
            self.signals.idea_result.emit(True, "Thank you! Your idea reached the developer.")
        except Exception as exc:
            logging.info("Idea form failed: %s", exc)
            self.signals.idea_result.emit(False, "fallback")


class HotkeyManager(threading.Thread):
    """Global left-side modifier chords: Win+Left Ctrl (Bangla) and Win+Left Shift (English)."""
    def __init__(self, signals):
        super().__init__(daemon=True, name="SHUNCHi-Hotkeys")
        self.signals = signals
        self.listener = None

    def run(self):
        try:
            from pynput import keyboard as pk
            pressed, latched, down_since = set(), set(), {}

            def really_down(vk):
                """Win+L, Alt+Tab and similar can swallow a key-release. Ask Windows what is truly held."""
                if os.name != "nt":
                    return True
                try:
                    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
                except Exception:
                    return True

            def drop_stale(current):
                now = time.monotonic()
                for held, vk in ((pk.Key.cmd_l, 0x5B), (pk.Key.ctrl_l, 0xA2), (pk.Key.shift_l, 0xA0)):
                    # Only a key that has been "held" for 2+ seconds AND that Windows says is up is stale
                    # (a lost key-release). A genuinely held key is never dropped, so the shortcut stays reliable.
                    if held in pressed and held != current and now - down_since.get(held, now) > 2.0 and not really_down(vk):
                        pressed.discard(held)
                        down_since.pop(held, None)
                if pk.Key.cmd_l not in pressed or pk.Key.ctrl_l not in pressed:
                    latched.discard("bangla")
                if pk.Key.cmd_l not in pressed or pk.Key.shift_l not in pressed:
                    latched.discard("english")

            def emit_once(name, language):
                if name not in latched:
                    latched.add(name)
                    self.signals.hotkey.emit(language)

            def on_press(key):
                try:
                    drop_stale(key)
                    if key not in pressed:
                        down_since[key] = time.monotonic()
                    pressed.add(key)
                    win = pk.Key.cmd_l in pressed
                    if win and pk.Key.ctrl_l in pressed:
                        emit_once("bangla", "bn-BD")
                    elif win and pk.Key.shift_l in pressed:
                        emit_once("english", "en-US")
                except Exception:
                    logging.exception("Hotkey press handler failed")

            def on_release(key):
                try:
                    pressed.discard(key)
                    down_since.pop(key, None)
                    if pk.Key.cmd_l not in pressed or pk.Key.ctrl_l not in pressed:
                        latched.discard("bangla")
                    if pk.Key.cmd_l not in pressed or pk.Key.shift_l not in pressed:
                        latched.discard("english")
                except Exception:
                    logging.exception("Hotkey release handler failed")

            self.listener = pk.Listener(on_press=on_press, on_release=on_release)
            self.listener.start()
            self.listener.join()
        except Exception as exc:
            logging.error("Global keyboard listener failed: %s", exc)
            self.signals.hotkey_error.emit(
                "SHUNCHi could not register the global shortcuts. Close keyboard-remapping tools "
                "and check Windows security permissions.\n\n" + str(exc))

    def stop(self):
        try:
            if self.listener:
                self.listener.stop()
        except Exception:
            logging.exception("Hotkey listener shutdown failed")


# ----------------------------------------------------------------------------------------------
# Design system
# ----------------------------------------------------------------------------------------------
C_BG = "#F6F8FC"
C_SURFACE = "#FFFFFF"
C_BORDER = "#E3E9F2"
C_TEXT = "#0F172A"
C_MUTED = "#64748B"
C_FAINT = "#94A3B8"
C_PRIMARY = "#2563EB"
C_PRIMARY_DARK = "#1D4ED8"
C_PRIMARY_SOFT = "#EAF2FF"
C_OK = "#15803D"
C_OK_SOFT = "#ECFDF3"
C_WARN = "#B45309"
C_WARN_SOFT = "#FFF7E6"
C_ERR = "#B91C1C"
C_ERR_SOFT = "#FEF2F2"

APP_QSS = """
* { font-family: 'Segoe UI', 'Nirmala UI', sans-serif; }
QMainWindow, QWidget#root { background: @BG@; }
QLabel { background: transparent; border: 0; color: @TEXT@; }
QLabel#pageTitle { font-size: 24px; font-weight: 700; color: @TEXT@; }
QLabel#pageSubtitle { font-size: 13px; color: @MUTED@; }
QLabel#muted { font-size: 12px; color: @MUTED@; }
QLabel#cardTitle { font-size: 15px; font-weight: 700; color: @TEXT@; }
QLabel#cardText { font-size: 13px; color: @MUTED@; }
QFrame#sidebar { background: @SURFACE@; border-right: 1px solid @BORDER@; }
QFrame#card { background: @SURFACE@; border: 1px solid @BORDER@; border-radius: 14px; }
QFrame#footer { background: transparent; border-top: 1px solid @BORDER@; }
QPushButton#nav { background: transparent; border: 0; border-radius: 10px; padding: 11px 14px; text-align: left; font-size: 14px; color: #475569; }
QPushButton#nav:hover { background: #F1F5F9; }
QPushButton#nav:checked { background: @SOFT@; color: @PRIMARY_DARK@; font-weight: 600; }
QPushButton#primary { background: @PRIMARY@; color: white; border: 0; border-radius: 9px; padding: 9px 18px; font-size: 13px; font-weight: 600; }
QPushButton#primary:hover { background: @PRIMARY_DARK@; }
QPushButton#primary:disabled { background: #BFD3FA; }
QPushButton#secondary { background: white; color: #334155; border: 1px solid #D5DDE9; border-radius: 9px; padding: 9px 16px; font-size: 13px; font-weight: 600; }
QPushButton#secondary:hover { background: #F8FAFC; }
QPushButton#danger { background: white; color: @ERR@; border: 1px solid #F3C9C9; border-radius: 9px; padding: 9px 16px; font-size: 13px; font-weight: 600; }
QPushButton#danger:hover { background: @ERR_SOFT@; }
QPushButton#link { background: transparent; border: 0; color: @PRIMARY@; font-size: 12px; font-weight: 600; text-align: left; padding: 2px 0; }
QPushButton#link:hover { color: @PRIMARY_DARK@; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: white; border: 1px solid #D5DDE9; border-radius: 9px; padding: 8px 10px; font-size: 13px; color: @TEXT@; min-height: 20px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid @PRIMARY@; }
QComboBox::drop-down { border: 0; width: 30px; }
@ARROW@
QFrame#segTrack { background: #EDF1F7; border: 0; border-radius: 11px; }
QPushButton#seg { background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 7px 18px; font-size: 13px; font-weight: 600; color: #475569; min-width: 58px; }
QPushButton#seg:hover { color: @TEXT@; }
QPushButton#seg:checked { background: white; color: @PRIMARY_DARK@; border: 1px solid #D5DDE9; }
QPushButton#chip { background: @SOFT@; color: @PRIMARY_DARK@; border: 0; border-radius: 15px; padding: 7px 14px; font-size: 12px; font-weight: 600; }
QPushButton#chip:hover { background: #DCEAFF; }
QComboBox QAbstractItemView { background: white; border: 1px solid @BORDER@; selection-background-color: @SOFT@; selection-color: @TEXT@; outline: 0; }
QPlainTextEdit { background: #F8FAFD; border: 1px solid #D5DDE9; border-radius: 10px; padding: 8px; font-size: 14px; color: @TEXT@; }
QPlainTextEdit:focus { border: 1px solid @PRIMARY@; }
QTableWidget { background: white; border: 1px solid @BORDER@; border-radius: 12px; gridline-color: transparent; font-size: 13px; selection-background-color: @SOFT@; selection-color: @TEXT@; outline: 0; }
QTableWidget::item { padding: 8px 10px; border-bottom: 1px solid #F1F5F9; }
QHeaderView::section { background: #F8FAFC; color: @MUTED@; border: 0; border-bottom: 1px solid @BORDER@; padding: 8px 10px; font-size: 12px; font-weight: 600; }
QScrollArea { background: transparent; border: 0; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #CBD5E1; border-radius: 4px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: #94A3B8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; background: none; border: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { height: 0; }
QToolTip { background: #0F172A; color: white; border: 0; padding: 6px 8px; }
"""


def build_qss(chevron=None):
    arrow = ""
    if chevron:
        arrow = "QComboBox::down-arrow { image: url(%s); width: 12px; height: 12px; }" % chevron
    values = {
        "BG": C_BG, "SURFACE": C_SURFACE, "BORDER": C_BORDER, "TEXT": C_TEXT, "MUTED": C_MUTED,
        "PRIMARY": C_PRIMARY, "PRIMARY_DARK": C_PRIMARY_DARK, "SOFT": C_PRIMARY_SOFT,
        "ERR": C_ERR, "ERR_SOFT": C_ERR_SOFT, "ARROW": arrow,
    }
    qss = APP_QSS
    for key, value in values.items():
        qss = qss.replace(f"@{key}@", value)
    return qss


def ensure_chevron():
    """A small chevron image for combo boxes, drawn once into the app-data folder (None if it fails)."""
    try:
        target = APPDATA / "chevron.png"
        if not target.exists():
            pixmap = QPixmap(24, 24)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor("#64748B"), 2.4)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline([QPointF(6, 9), QPointF(12, 15), QPointF(18, 9)])
            painter.end()
            pixmap.save(str(target), "PNG")
        return target.as_posix() if target.exists() else None
    except Exception:
        logging.exception("Could not create the chevron image")
        return None


def make_icon(kind, color, size=20):
    """Crisp line icons drawn with QPainter (no emoji / icon-font dependency)."""
    s = size * 2
    pixmap = QPixmap(s, s)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), s * 0.085)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    def pt(x, y):
        return QPointF(x * s, y * s)

    def rect(x, y, w, h):
        return QRectF(x * s, y * s, w * s, h * s)

    path = QPainterPath()
    if kind == "home":
        path.moveTo(pt(0.14, 0.50)); path.lineTo(pt(0.50, 0.17)); path.lineTo(pt(0.86, 0.50))
        p.drawPath(path)
        body = QPainterPath()
        body.moveTo(pt(0.25, 0.44)); body.lineTo(pt(0.25, 0.83)); body.lineTo(pt(0.75, 0.83)); body.lineTo(pt(0.75, 0.44))
        p.drawPath(body)
    elif kind == "history":
        p.drawEllipse(rect(0.16, 0.16, 0.68, 0.68))
        path.moveTo(pt(0.50, 0.32)); path.lineTo(pt(0.50, 0.52)); path.lineTo(pt(0.65, 0.61))
        p.drawPath(path)
    elif kind == "settings":
        for y, knob in ((0.30, 0.64), (0.50, 0.36), (0.70, 0.60)):
            p.drawLine(pt(0.16, y), pt(0.84, y))
            p.setBrush(QColor("white"))
            p.drawEllipse(rect(knob - 0.075, y - 0.075, 0.15, 0.15))
            p.setBrush(Qt.NoBrush)
    elif kind == "help":
        p.drawEllipse(rect(0.14, 0.14, 0.72, 0.72))
        q = QPainterPath()
        r = rect(0.37, 0.28, 0.26, 0.24)
        q.arcMoveTo(r, 160)
        q.arcTo(r, 160, -230)
        q.lineTo(pt(0.50, 0.60))
        p.drawPath(q)
        p.drawPoint(pt(0.50, 0.71))
    elif kind == "user":
        p.drawEllipse(rect(0.34, 0.16, 0.32, 0.32))
        q = QPainterPath()
        r = rect(0.20, 0.56, 0.60, 0.60)
        q.arcMoveTo(r, 180)
        q.arcTo(r, 180, -180)
        p.drawPath(q)
    elif kind == "apps":
        for x, y in ((0.18, 0.18), (0.54, 0.18), (0.18, 0.54), (0.54, 0.54)):
            p.drawRoundedRect(rect(x, y, 0.28, 0.28), s * 0.06, s * 0.06)
    p.end()
    return QIcon(pixmap)


class ToggleSwitch(QCheckBox):
    """Modern on/off switch."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C_PRIMARY if self.isChecked() else "#CBD5E1"))
        p.drawRoundedRect(QRectF(0, 0, 46, 26), 13, 13)
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(23 if self.isChecked() else 3, 3, 20, 20))


class SegmentedControl(QFrame):
    """A pill-style choice (like Quick | Normal | Relaxed). Always shows every option; no typing or spinning."""
    valueChanged = Signal(object)

    def __init__(self, options):
        super().__init__()
        self.setObjectName("segTrack")
        self.options = list(options)           # [(label, value), ...]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = []
        for index, (label, _value) in enumerate(self.options):
            button = QPushButton(label)
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)
            self.group.addButton(button, index)
            layout.addWidget(button)
            self.buttons.append(button)
        self.buttons[0].setChecked(True)
        self.group.idClicked.connect(self._clicked)

    def _clicked(self, index):
        self.valueChanged.emit(self.options[index][1])

    def value(self):
        index = self.group.checkedId()
        return self.options[index][1] if 0 <= index < len(self.options) else self.options[0][1]

    def set_value(self, value):
        """Select the option closest to `value` (so older saved numbers still land on a sensible choice)."""
        values = [option[1] for option in self.options]
        self.buttons[values.index(nearest_option(value, values))].setChecked(True)


class NoWheelComboBox(QComboBox):
    """A combo box that ignores the mouse wheel, so scrolling the page never changes the selection."""

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(18)
        self.setMaxVisibleItems(8)

    def wheelEvent(self, event):
        event.ignore()


def open_website(path=""):
    QDesktopServices.openUrl(QUrl(WEBSITE_URL + path))


def make_card(layout_margins=(20, 18, 20, 18), spacing=10):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(*layout_margins)
    layout.setSpacing(spacing)
    return frame, layout


def scroll_page(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(widget)
    area.viewport().setAutoFillBackground(False)
    return area


def key_cap(text):
    label = QLabel(text)
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet(
        "background:#F1F5F9;border:1px solid #D5DDE9;border-bottom:2px solid #C3CDDC;border-radius:7px;"
        "padding:5px 11px;font-size:13px;font-weight:700;color:#1E293B;"
    )
    return label


# ----------------------------------------------------------------------------------------------
# Voice popup widgets
# ----------------------------------------------------------------------------------------------

class WaveformWidget(QWidget):
    """Live voice line. New microphone levels scroll in from the right; older bars fade towards the left."""
    BARS = 46

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "idle"            # idle | listening | processing
        self.phase = 0.0
        self.targets = [0.0] * self.BARS
        self.display = [0.0] * self.BARS
        self.setMinimumHeight(40)
        self.setMaximumHeight(44)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.animator = QTimer(self)
        self.animator.setInterval(30)
        self.animator.timeout.connect(self._animate)

    def showEvent(self, event):
        self.animator.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.animator.stop()
        super().hideEvent(event)

    def set_mode(self, mode):
        self.mode = mode
        self.update()

    def push_value(self, value):
        self.targets = self.targets[1:] + [max(0.0, min(float(value), 1.0))]

    def reset(self):
        self.mode = "idle"
        self.targets = [0.0] * self.BARS
        self.display = [0.0] * self.BARS
        self.update()

    def _animate(self):
        import math
        self.phase += 0.12
        for i in range(self.BARS):
            if self.mode == "processing":
                target = 0.20 + 0.14 * (1 + math.sin(self.phase * 1.5 - i * 0.30))
            else:
                target = self.targets[i]
            self.display[i] += (target - self.display[i]) * 0.40
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        count, gap = self.BARS, 3.0
        bar_width = max(2.0, min(4.0, (self.width() - gap * (count - 1)) / count))
        total = count * bar_width + (count - 1) * gap
        x0 = (self.width() - total) / 2
        cy = self.height() / 2
        import math
        for i in range(count):
            position = i / (count - 1)
            if self.mode == "listening":
                color = QColor(37, 99, 235, int(60 + 195 * position ** 0.8))
            elif self.mode == "processing":
                glow = 0.5 + 0.5 * math.sin(self.phase * 1.8 - i * 0.28)
                color = QColor(37, 99, 235, int(70 + 185 * glow))
            else:
                color = QColor("#D5DCE8")
            value = max(self.display[i], 0.05)
            height = 4.0 + value * (self.height() - 6.0)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x0 + i * (bar_width + gap), cy - height / 2, bar_width, height),
                                    bar_width / 2, bar_width / 2)


class MicOrb(QWidget):
    """Round status badge: pulses with your voice while listening, spins while writing, then shows a tick."""
    PALETTE = {
        "listening": ("#3B82F6", "#2563EB"), "processing": ("#F59E0B", "#D97706"),
        "done": ("#22C55E", "#16A34A"), "error": ("#F87171", "#DC2626"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 46)
        self.state = "listening"
        self.level = 0.0
        self.smooth = 0.0
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._tick)

    def showEvent(self, event):
        self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def set_state(self, state):
        self.state = state
        self.update()

    def set_level(self, value):
        self.level = max(self.level, float(value))

    def _tick(self):
        self.smooth += (self.level - self.smooth) * 0.35
        self.level *= 0.90
        self.angle = (self.angle + 9) % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        centre = QPointF(23, 23)
        top, bottom = self.PALETTE.get(self.state, self.PALETTE["listening"])
        p.setPen(Qt.NoPen)
        if self.state == "listening":
            ring = 17.0 + self.smooth * 6.0
            p.setBrush(QColor(37, 99, 235, 46))
            p.drawEllipse(centre, ring, ring)
        gradient = QLinearGradient(0, 6, 0, 40)
        gradient.setColorAt(0, QColor(top))
        gradient.setColorAt(1, QColor(bottom))
        p.setBrush(QBrush(gradient))
        p.drawEllipse(centre, 15.5, 15.5)

        pen = QPen(QColor("white"), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        if self.state == "listening":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("white"))
            p.drawRoundedRect(QRectF(19.5, 12.0, 7.0, 13.0), 3.5, 3.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(16.0, 16.0, 14.0, 14.0), 180 * 16, 180 * 16)
            p.drawLine(QPointF(23.0, 30.0), QPointF(23.0, 33.0))
            p.drawLine(QPointF(19.5, 33.0), QPointF(26.5, 33.0))
        elif self.state == "processing":
            spin = QPen(QColor("white"), 2.6)
            spin.setCapStyle(Qt.RoundCap)
            p.setPen(spin)
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(15.0, 15.0, 16.0, 16.0), -self.angle * 16, 110 * 16)
            faint = QPen(QColor(255, 255, 255, 90), 2.6)
            faint.setCapStyle(Qt.RoundCap)
            p.setPen(faint)
            p.drawArc(QRectF(15.0, 15.0, 16.0, 16.0), -(self.angle + 180) * 16, 60 * 16)
        elif self.state == "done":
            pen.setWidthF(2.6)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(16.5, 23.5)
            path.lineTo(21.0, 28.0)
            path.lineTo(30.0, 18.0)
            p.drawPath(path)
        else:
            pen.setWidthF(2.6)
            p.setPen(pen)
            p.drawLine(QPointF(23.0, 16.0), QPointF(23.0, 25.0))
            p.drawPoint(QPointF(23.0, 30.0))


class MicPopup(QWidget):
    """Compact floating voice indicator. It never takes keyboard focus and never shows the transcript:
    when you finish speaking, the polished text is typed where your cursor is."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(424, 124)
        self._leaving = False
        self.elapsed = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._tick)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.dismiss)
        self.fade = QPropertyAnimation(self, b"windowOpacity", self)
        self.slide = QPropertyAnimation(self, b"pos", self)
        self.slide.setEasingCurve(QEasingCurve.OutCubic)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 6, 12, 16)
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setStyleSheet(
            "QFrame#panel{background:rgba(255,255,255,0.99);border:1px solid #E1E8F3;border-radius:20px;}"
            "QLabel{border:0;}")
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(15, 23, 42, 58))
        panel.setGraphicsEffect(shadow)
        outer.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 11)
        layout.setSpacing(7)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.orb = MicOrb()
        self.wave = WaveformWidget()
        self.time_label = QLabel("00:00")
        self.time_label.setMinimumWidth(52)
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet(
            f"font-size:13px;font-weight:700;color:{C_PRIMARY_DARK};background:{C_PRIMARY_SOFT};"
            "border-radius:11px;padding:4px 9px;")
        row.addWidget(self.orb)
        row.addWidget(self.wave, 1)
        row.addWidget(self.time_label)
        layout.addLayout(row)

        info = QHBoxLayout()
        info.setSpacing(8)
        self.title_label = QLabel("Listening")
        self.lang_label = QLabel("")
        self.lang_label.setStyleSheet(
            f"font-size:11px;font-weight:700;color:{C_PRIMARY_DARK};background:{C_PRIMARY_SOFT};"
            "border-radius:9px;padding:2px 9px;")
        self.detail_label = QLabel("")
        info.addWidget(self.title_label)
        info.addWidget(self.lang_label)
        info.addWidget(self.detail_label, 1)
        layout.addLayout(info)
        self._style_texts("listening")

    def _style_texts(self, state, detail_color=None):
        color = {"listening": C_PRIMARY_DARK, "processing": C_WARN, "done": C_OK, "error": C_ERR}.get(state, C_TEXT)
        # Solid white label backgrounds: on this see-through window a transparent label would keep the old
        # text underneath the new one ("ghost" text) every time the state changes.
        self.title_label.setStyleSheet(f"font-size:14px;font-weight:700;color:{color};background:#FFFFFF;")
        self.detail_label.setStyleSheet(f"font-size:12px;color:{detail_color or C_MUTED};background:#FFFFFF;")

    # ---- helpers
    def _tick(self):
        seconds = self.elapsed.elapsed() // 1000
        self.time_label.setText(f"{seconds // 60:02d}:{seconds % 60:02d}")

    def place_on_active_screen(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(area.x() + (area.width() - self.width()) // 2, area.y() + area.height() - self.height() - 14)

    def _disconnect_fade(self):
        try:
            self.fade.finished.disconnect(self._after_fade)
        except Exception:
            pass

    def _present(self):
        """Fade + slide in (or just stay if it is already on screen)."""
        self._disconnect_fade()
        self.hide_timer.stop()
        if self.isVisible():
            self._leaving = False
            self.fade.stop()
            self.setWindowOpacity(1.0)
            return
        self._leaving = False
        self.place_on_active_screen()
        target = self.pos()
        start = QPoint(target.x(), target.y() + 14)
        self.setWindowOpacity(0.0)
        self.move(start)
        self.show()
        self.raise_()
        self.fade.stop()
        self.fade.setDuration(170)
        self.fade.setStartValue(0.0)
        self.fade.setEndValue(1.0)
        self.fade.start()
        self.slide.stop()
        self.slide.setDuration(220)
        self.slide.setStartValue(start)
        self.slide.setEndValue(target)
        self.slide.start()

    def dismiss(self):
        self.timer.stop()
        if not self.isVisible() or self._leaving:
            return
        self._leaving = True
        self._disconnect_fade()
        self.fade.stop()
        self.fade.setDuration(180)
        self.fade.setStartValue(self.windowOpacity())
        self.fade.setEndValue(0.0)
        self.fade.finished.connect(self._after_fade)
        self.fade.start()

    def _after_fade(self):
        self._disconnect_fade()
        if self._leaving:
            self._leaving = False
            self.hide()
            self.setWindowOpacity(1.0)

    # ---- states
    def begin(self, language):
        self.wave.reset()
        self.wave.set_mode("listening")
        self.orb.set_state("listening")
        self._style_texts("listening")
        self.title_label.setText("Listening")
        self.lang_label.setText("বাংলা" if language == "bn-BD" else "English")
        self.lang_label.setVisible(True)
        self.detail_label.setText("pause when you finish")
        self.detail_label.setToolTip("")
        self.time_label.setText("00:00")
        self.elapsed.start()
        self.timer.start()
        self._present()

    def set_level(self, level):
        self.wave.push_value(level)
        self.orb.set_level(level)

    def mark_speech(self):
        self.title_label.setText("Listening")

    def set_processing(self):
        self.timer.stop()
        self.wave.set_mode("processing")
        self.orb.set_state("processing")
        self._style_texts("processing")
        self.title_label.setText("Writing")
        self.lang_label.setVisible(False)
        self.detail_label.setText("Typing your text…")

    def finish(self):
        self.timer.stop()
        self.wave.set_mode("idle")
        self.orb.set_state("done")
        self._style_texts("done")
        self.title_label.setText("Done")
        self.lang_label.setVisible(False)
        self.detail_label.setText("Inserted at your cursor")
        self.hide_timer.start(450)

    def show_error(self, message):
        self.timer.stop()
        self.wave.set_mode("idle")
        self.orb.set_state("error")
        self._style_texts("error", C_ERR)
        self.title_label.setText("Notice")
        self.lang_label.setVisible(False)
        self.detail_label.setText(str(message)[:80])
        self.detail_label.setToolTip(str(message))
        self._present()
        self.hide_timer.start(3800)


# ----------------------------------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------------------------------
def page_header(title, subtitle):
    box = QVBoxLayout()
    box.setSpacing(3)
    t = QLabel(title)
    t.setObjectName("pageTitle")
    s = QLabel(subtitle)
    s.setObjectName("pageSubtitle")
    s.setWordWrap(True)
    box.addWidget(t)
    box.addWidget(s)
    return box


class DashboardPage(QWidget):
    BANNER_STYLES = {
        "ok": (C_OK, C_OK_SOFT, "#BBF7D0"),
        "pending": (C_PRIMARY_DARK, C_PRIMARY_SOFT, "#C7DBFB"),
        "missing": (C_WARN, C_WARN_SOFT, "#FDE2A8"),
        "error": (C_ERR, C_ERR_SOFT, "#F7CACA"),
    }

    def __init__(self, open_settings):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 28, 30, 20)
        root.setSpacing(16)
        head = QHBoxLayout()
        head.addLayout(page_header("Dashboard", "Speak in Bangla or English. SHUNCHi types it wherever your cursor is."), 1)
        site_chip = QPushButton(f"{WEBSITE_LABEL}  ↗")
        site_chip.setObjectName("chip")
        site_chip.setCursor(Qt.PointingHandCursor)
        site_chip.clicked.connect(lambda: open_website())
        head.addWidget(site_chip, 0, Qt.AlignTop)
        root.addLayout(head)

        self.update_banner = QFrame()
        self.update_banner.setObjectName("updateBanner")
        self.update_banner.setStyleSheet(
            f"QFrame#updateBanner{{background:{C_PRIMARY_SOFT};border:1px solid #C7DBFB;border-radius:12px;}}")
        update_layout = QHBoxLayout(self.update_banner)
        update_layout.setContentsMargins(16, 11, 14, 11)
        update_layout.setSpacing(10)
        self.update_text = QLabel("")
        self.update_text.setWordWrap(True)
        self.update_text.setStyleSheet(f"color:{C_PRIMARY_DARK};font-size:13px;font-weight:600;")
        self.update_button = QPushButton("Update now")
        self.update_button.setObjectName("primary")
        self.update_button.setCursor(Qt.PointingHandCursor)
        update_layout.addWidget(self.update_text, 1)
        update_layout.addWidget(self.update_button)
        self.update_banner.setVisible(False)
        root.addWidget(self.update_banner)

        self.banner = QFrame()
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(16, 12, 14, 12)
        banner_layout.setSpacing(10)
        self.banner_dot = QLabel("●")
        self.banner_text = QLabel("")
        self.banner_text.setWordWrap(True)
        self.banner_button = QPushButton("Open Settings")
        self.banner_button.setObjectName("secondary")
        self.banner_button.setCursor(Qt.PointingHandCursor)
        self.banner_button.clicked.connect(open_settings)
        banner_layout.addWidget(self.banner_dot)
        banner_layout.addWidget(self.banner_text, 1)
        banner_layout.addWidget(self.banner_button)
        root.addWidget(self.banner)

        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(self._shortcut_card("বাংলা Dictation", "Win", "Left Ctrl", "Speak in Bangla (English words are fine too)"))
        row.addWidget(self._shortcut_card("English Dictation", "Win", "Left Shift", "Speak in English"))
        root.addLayout(row)

        card, layout = make_card((20, 16, 20, 18), 8)
        title = QLabel("Try it here")
        title.setObjectName("cardTitle")
        hint = QLabel("Click inside the box, press a shortcut and speak. Pause when you finish; the text appears here.")
        hint.setObjectName("cardText")
        hint.setWordWrap(True)
        self.practice = QPlainTextEdit()
        self.practice.setPlaceholderText("Your dictated text will be typed here…")
        self.practice.setFixedHeight(100)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.practice)
        root.addWidget(card)

        notes, notes_layout = make_card((20, 16, 20, 16), 8)
        notes_title = QLabel("Before you start")
        notes_title.setObjectName("cardTitle")
        notes_layout.addWidget(notes_title)
        for text in (
            "<b>A Gemini API key is required.</b> Without your own free key SHUNCHi cannot type for you. "
            "Add it once in Settings.",
            "Your writing runs on the <b>free limit of your own Gemini key</b>, so everyday messages and normal work "
            "should go through on the free version.",
            "If you need a much higher limit, a <b>Pro subscription with extended limits</b> is planned for the future.",
        ):
            line = QLabel("•  " + text)
            line.setObjectName("cardText")
            line.setWordWrap(True)
            line.setTextFormat(Qt.RichText)
            notes_layout.addWidget(line)
        root.addWidget(notes)

        self.activity = QLabel("")
        self.activity.setObjectName("muted")
        self.activity.setWordWrap(True)
        root.addWidget(self.activity)
        root.addStretch()
        self.set_api_state("missing", "Add your Gemini API key in Settings to start voice typing.")

    def _shortcut_card(self, title, key_a, key_b, hint):
        card, layout = make_card((20, 16, 20, 16), 10)
        t = QLabel(title)
        t.setObjectName("cardTitle")
        caps = QHBoxLayout()
        caps.setSpacing(8)
        caps.addWidget(key_cap(key_a))
        plus = QLabel("+")
        plus.setStyleSheet(f"color:{C_FAINT};font-size:14px;font-weight:700;")
        caps.addWidget(plus)
        caps.addWidget(key_cap(key_b))
        caps.addStretch()
        h = QLabel(hint)
        h.setObjectName("cardText")
        h.setWordWrap(True)
        layout.addWidget(t)
        layout.addLayout(caps)
        layout.addWidget(h)
        return card

    def set_api_state(self, state, text):
        color, bg, border = self.BANNER_STYLES.get(state, self.BANNER_STYLES["pending"])
        self.banner.setObjectName("banner")
        self.banner.setStyleSheet(f"QFrame#banner{{background:{bg};border:1px solid {border};border-radius:12px;}}")
        self.banner_dot.setStyleSheet(f"color:{color};font-size:12px;")
        self.banner_text.setStyleSheet(f"color:{color};font-size:13px;font-weight:600;")
        self.banner_text.setText(text)
        self.banner_button.setVisible(state != "ok")

    def set_activity(self, text):
        self.activity.setText(text)

    def show_update(self, version, forced=False):
        if forced:
            self.update_text.setText(f"SHUNCHi {version} is required. Please update to keep using voice typing.")
        else:
            self.update_text.setText(f"SHUNCHi {version} is available. Update to get the latest improvements.")
        self.update_button.setText("Update now")
        self.update_banner.setVisible(True)

    def hide_update(self):
        self.update_banner.setVisible(False)


class HistoryPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 28, 30, 20)
        root.setSpacing(14)
        root.addLayout(page_header("Voice History", "Your recent dictations. They are stored only on this computer."))

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search your dictations…")
        self.search.textChanged.connect(self.refresh)
        self.copy_button = QPushButton("Copy")
        self.copy_button.setObjectName("secondary")
        self.copy_button.clicked.connect(self.copy_selected)
        self.clear_button = QPushButton("Clear history")
        self.clear_button.setObjectName("danger")
        self.clear_button.clicked.connect(self.clear_all)
        controls.addWidget(self.search, 1)
        controls.addWidget(self.copy_button)
        controls.addWidget(self.clear_button)
        root.addLayout(controls)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Time", "Language", "Text", ""])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 84)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.cellDoubleClicked.connect(lambda *_: self.copy_selected())
        root.addWidget(self.table, 1)

        self.off_note = QLabel("Voice history is turned off. New dictations are not saved. Turn it on in Settings.")
        self.off_note.setObjectName("muted")
        self.off_note.setWordWrap(True)
        self.off_note.setVisible(False)
        root.addWidget(self.off_note)
        self.empty = QLabel("No dictations yet. Press a shortcut and speak to get started.")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignCenter)
        root.addWidget(self.empty)
        self.refresh()

    def set_recording(self, enabled):
        self.off_note.setVisible(not enabled)

    def refresh(self, *_):
        needle = self.search.text().strip().casefold()
        rows = [r for r in read_history() if not needle or needle in r[4].casefold()]
        self.table.setRowCount(len(rows))
        for row, (_, created, language, _, transcript) in enumerate(rows):
            cells = (created[5:16], "বাংলা" if language == "bn-BD" else "English", transcript.replace("\n", " "))
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, transcript)
                self.table.setItem(row, col, item)
            button = QPushButton("Copy")
            button.setObjectName("secondary")
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip("Copy this dictation")
            button.setStyleSheet("padding:4px 10px;min-height:0;font-size:12px;")
            button.clicked.connect(lambda _=False, b=button, t=transcript: self.copy_text(b, t))
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(6, 6, 6, 6)
            holder_layout.addWidget(button)
            self.table.setCellWidget(row, 3, holder)
        self.empty.setVisible(not rows)
        self.table.setVisible(bool(rows))
        self.copy_button.setEnabled(bool(rows))
        self.clear_button.setEnabled(bool(rows))

    def copy_text(self, button, text):
        QApplication.clipboard().setText(text)
        button.setText("Copied ✓")
        QTimer.singleShot(1400, lambda: self._reset_button(button))

    @staticmethod
    def _reset_button(button):
        try:
            button.setText("Copy")
        except RuntimeError:      # the table was rebuilt meanwhile
            pass

    def copy_selected(self):
        row = self.table.currentRow()
        if row < 0 and self.table.rowCount():
            row = 0
        if row >= 0:
            item = self.table.item(row, 2)
            if item is not None:
                QApplication.clipboard().setText(item.data(Qt.UserRole))
                self.copy_button.setText("Copied ✓")
                QTimer.singleShot(1400, lambda: self.copy_button.setText("Copy"))

    def clear_all(self):
        if QMessageBox.question(self, APP_NAME, "Delete all saved dictations from this computer?") == QMessageBox.Yes:
            clear_history()
            self.refresh()


def setting_row(title, description, control, stacked=False):
    row = QWidget()
    if stacked:
        box = QVBoxLayout(row)
        box.setContentsMargins(0, 6, 0, 6)
        box.setSpacing(8)
        st = QLabel(title)
        st.setStyleSheet(f"font-size:14px;font-weight:600;color:{C_TEXT};")
        sd_ = QLabel(description)
        sd_.setObjectName("muted")
        sd_.setWordWrap(True)
        box.addWidget(st)
        box.addWidget(sd_)
        box.addWidget(control)
        return row
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 6, 0, 6)
    layout.setSpacing(16)
    text = QVBoxLayout()
    text.setSpacing(2)
    t = QLabel(title)
    t.setStyleSheet(f"font-size:14px;font-weight:600;color:{C_TEXT};")
    d = QLabel(description)
    d.setObjectName("muted")
    d.setWordWrap(True)
    text.addWidget(t)
    text.addWidget(d)
    layout.addLayout(text, 1)
    layout.addWidget(control, 0, Qt.AlignVCenter)
    return row


def divider():
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background:{C_BORDER};border:0;")
    return line


class SettingsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_ref = window
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 28, 30, 24)
        root.setSpacing(16)
        root.addLayout(page_header("Settings", "Changes are saved automatically."))

        # ---- API key
        key_card, key_layout = make_card()
        head = QHBoxLayout()
        title = QLabel("Gemini API key")
        title.setObjectName("cardTitle")
        self.key_chip = QLabel("")
        head.addWidget(title)
        head.addStretch()
        head.addWidget(self.key_chip)
        key_layout.addLayout(head)
        about = QLabel("SHUNCHi uses your own free Gemini API key. It is stored in Windows Credential Manager "
                       "and is only used to send your recorded speech to Google for transcription.")
        about.setObjectName("cardText")
        about.setWordWrap(True)
        key_layout.addWidget(about)
        entry = QHBoxLayout()
        entry.setSpacing(8)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.Password)
        self.key_input.setPlaceholderText("Paste your Gemini API key here")
        self.show_button = QPushButton("Show")
        self.show_button.setObjectName("secondary")
        self.show_button.clicked.connect(self._toggle_show)
        entry.addWidget(self.key_input, 1)
        entry.addWidget(self.show_button)
        key_layout.addLayout(entry)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.save_button = QPushButton("Save && test")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self._save_key)
        self.remove_button = QPushButton("Remove key")
        self.remove_button.setObjectName("danger")
        self.remove_button.clicked.connect(self._remove_key)
        get_key = QPushButton("Get a free API key →")
        get_key.setObjectName("link")
        get_key.setCursor(Qt.PointingHandCursor)
        get_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://aistudio.google.com/apikey")))
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.remove_button)
        buttons.addSpacing(8)
        buttons.addWidget(get_key)
        buttons.addStretch()
        key_layout.addLayout(buttons)
        self.key_result = QLabel("")
        self.key_result.setWordWrap(True)
        self.key_result.setObjectName("muted")
        key_layout.addWidget(self.key_result)
        root.addWidget(key_card)

        # ---- Dictation
        dict_card, dict_layout = make_card((20, 14, 20, 14), 0)
        dt = QLabel("Dictation")
        dt.setObjectName("cardTitle")
        dict_layout.addWidget(dt)
        self.smart = ToggleSwitch()
        self.history_on = ToggleSwitch()
        self.silence = SegmentedControl([("Quick", 0.7), ("Normal", 1.0), ("Relaxed", 1.6)])
        self.max_minutes = SegmentedControl([("2 min", 2), ("5 min", 5), ("10 min", 10)])
        self.microphone = NoWheelComboBox()
        self.microphone.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.microphone.addItem("Detecting microphones…", -1)
        dict_layout.addWidget(setting_row("Smart formatting", "Removes filler words, adds punctuation and formats lists.", self.smart))
        dict_layout.addWidget(divider())
        dict_layout.addWidget(setting_row(
            "Finish after a pause",
            "How long you can stay quiet before SHUNCHi stops and types. Quick is fastest; Relaxed suits slow speakers.",
            self.silence))
        dict_layout.addWidget(divider())
        dict_layout.addWidget(setting_row("Longest recording", "A safety limit for one dictation.", self.max_minutes))
        dict_layout.addWidget(divider())
        dict_layout.addWidget(setting_row(
            "Save voice history", "Keep a list of your dictations on this computer. Turn it off and nothing new is saved.", self.history_on))
        dict_layout.addWidget(divider())
        dict_layout.addWidget(setting_row("Microphone", "The input device used for voice typing.", self.microphone, stacked=True))
        root.addWidget(dict_card)

        # ---- Updates
        upd_card, upd_layout = make_card((20, 14, 20, 14), 0)
        ut = QLabel("Updates")
        ut.setObjectName("cardTitle")
        upd_layout.addWidget(ut)
        self.auto_update = ToggleSwitch()
        upd_layout.addWidget(setting_row(
            "Check for updates automatically",
            f"SHUNCHi quietly checks {WEBSITE_LABEL} and tells you when a new version is ready.", self.auto_update))
        upd_layout.addWidget(divider())
        self.check_button = QPushButton("Check now")
        self.check_button.setObjectName("secondary")
        self.check_button.clicked.connect(lambda: self.window_ref.check_updates_manual())
        upd_layout.addWidget(setting_row(f"SHUNCHi {APP_VERSION}", "Look for a newer version now.", self.check_button))
        self.update_status = QLabel("")
        self.update_status.setWordWrap(True)
        self.update_status.setObjectName("muted")
        upd_layout.addWidget(self.update_status)
        root.addWidget(upd_card)

        # ---- General
        gen_card, gen_layout = make_card((20, 14, 20, 14), 0)
        gt = QLabel("General")
        gt.setObjectName("cardTitle")
        gen_layout.addWidget(gt)
        self.startup = ToggleSwitch()
        startup_desc = "Open SHUNCHi quietly in the system tray when you sign in to Windows."
        if not startup_supported():
            startup_desc += " (Available in the installed app.)"
            self.startup.setEnabled(False)
        gen_layout.addWidget(setting_row("Start with Windows", startup_desc, self.startup))
        gen_layout.addWidget(divider())
        site_button = QPushButton(f"Visit {WEBSITE_LABEL}")
        site_button.setObjectName("secondary")
        site_button.setCursor(Qt.PointingHandCursor)
        site_button.clicked.connect(lambda: open_website())
        gen_layout.addWidget(setting_row("Official website", "News, downloads, help and more free apps from the developer.", site_button))
        gen_layout.addWidget(divider())
        log_button = QPushButton("Open")
        log_button.setObjectName("secondary")
        log_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(APPDATA))))
        gen_layout.addWidget(setting_row("Log folder", f"Diagnostic log for troubleshooting · SHUNCHi {APP_VERSION}", log_button))
        root.addWidget(gen_card)
        root.addStretch()

        self.smart.toggled.connect(lambda _: self.window_ref.on_settings_changed())
        self.history_on.toggled.connect(lambda _: self.window_ref.on_settings_changed())
        self.silence.valueChanged.connect(lambda _: self.window_ref.on_settings_changed())
        self.max_minutes.valueChanged.connect(lambda _: self.window_ref.on_settings_changed())
        self.microphone.currentIndexChanged.connect(lambda _: self.window_ref.on_settings_changed())
        self.startup.toggled.connect(self.window_ref.on_startup_toggled)
        self.auto_update.toggled.connect(self.window_ref.on_auto_update_toggled)

    def load_values(self, smart, silence, max_minutes, startup, auto_update=True, history=True):
        for widget in (self.smart, self.silence, self.max_minutes, self.startup, self.auto_update, self.history_on):
            widget.blockSignals(True)
        self.history_on.setChecked(history)
        self.smart.setChecked(smart)
        self.silence.set_value(silence)
        self.max_minutes.set_value(max_minutes)
        self.startup.setChecked(startup)
        self.auto_update.setChecked(auto_update)
        for widget in (self.smart, self.silence, self.max_minutes, self.startup, self.auto_update, self.history_on):
            widget.blockSignals(False)

    def set_update_status(self, text, kind=None):
        color = {"ok": C_OK, "error": C_ERR}.get(kind, C_MUTED)
        self.update_status.setStyleSheet(f"color:{color};font-size:12px;")
        self.update_status.setText(text)

    def set_checking(self, busy):
        self.check_button.setEnabled(not busy)
        self.check_button.setText("Checking…" if busy else "Check now")
        if busy:
            self.set_update_status(f"Checking {WEBSITE_LABEL}…")

    def populate_microphones(self, devices, selected):
        self.microphone.blockSignals(True)
        self.microphone.clear()
        if not devices:
            self.microphone.addItem("No microphone found", -1)
        for index, name, _, _ in devices:
            self.microphone.addItem(name, index)
            if index == selected:
                self.microphone.setCurrentIndex(self.microphone.count() - 1)
        self.microphone.blockSignals(False)

    def selected_microphone(self):
        data = self.microphone.currentData()
        return int(data) if data is not None else -1

    def set_key_status(self, has_key, ok=None):
        if not has_key:
            chip = ("Not set", C_WARN, C_WARN_SOFT)
        elif ok is True:
            chip = ("Connected", C_OK, C_OK_SOFT)
        elif ok is False:
            chip = ("Needs attention", C_ERR, C_ERR_SOFT)
        else:
            chip = ("Saved", C_PRIMARY_DARK, C_PRIMARY_SOFT)
        text, fg, bg = chip
        self.key_chip.setText(text)
        self.key_chip.setStyleSheet(f"color:{fg};background:{bg};border-radius:10px;padding:4px 11px;font-size:12px;font-weight:700;")

    def set_key_result(self, text, ok=None):
        color = C_MUTED if ok is None else (C_OK if ok else C_ERR)
        self.key_result.setStyleSheet(f"color:{color};font-size:12px;")
        self.key_result.setText(text)

    def _toggle_show(self):
        hidden = self.key_input.echoMode() == QLineEdit.Password
        self.key_input.setEchoMode(QLineEdit.Normal if hidden else QLineEdit.Password)
        self.show_button.setText("Hide" if hidden else "Show")

    def _save_key(self):
        self.window_ref.save_api_key(self.key_input.text().strip())

    def _remove_key(self):
        self.window_ref.remove_api_key()

    def set_busy(self, busy):
        self.save_button.setEnabled(not busy)
        self.save_button.setText("Testing…" if busy else "Save && test")


class MoreAppsPage(QWidget):
    """Apps by the same developer. The list comes from the website, so new apps appear without reinstalling."""

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 28, 30, 24)
        root.setSpacing(16)
        root.addLayout(page_header("More Apps", "Free tools from the developer of SHUNCHi."))

        hub, hub_layout = make_card((22, 18, 22, 18), 8)
        hub_title = QLabel("Free apps and everyday tools, in your language")
        hub_title.setObjectName("cardTitle")
        hub_text = QLabel(
            "Voice typing is only the start. The SHUNCHi apps page lists every free app and online tool: "
            "CV maker, invoice maker, PDF tools, image compressor, QR code, Bangla typing and more. "
            "Nothing to install for the online tools.")
        hub_text.setObjectName("cardText")
        hub_text.setWordWrap(True)
        self.hub_button = QPushButton("Open the apps page  ↗")
        self.hub_button.setObjectName("primary")
        self.hub_button.setCursor(Qt.PointingHandCursor)
        self.hub_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(APPS_PAGE_URL)))
        hub_layout.addWidget(hub_title)
        hub_layout.addWidget(hub_text)
        hub_layout.addWidget(self.hub_button, 0, Qt.AlignLeft)
        root.addWidget(hub)

        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(12)
        root.addLayout(self.list_layout)

        idea, idea_layout = make_card((22, 18, 22, 18), 8)
        idea_title = QLabel("অ্যাপ বা টুলের আইডিয়া দিন")
        idea_title.setObjectName("cardTitle")
        idea_text = QLabel("Which app or tool would make your daily work easier? Tell the developer. "
                           "Your idea may become the next free tool.")
        idea_text.setObjectName("cardText")
        idea_text.setWordWrap(True)
        self.idea_name = QLineEdit()
        self.idea_name.setPlaceholderText("Your name (optional)")
        self.idea_name.setMaxLength(80)
        self.idea_contact = QLineEdit()
        self.idea_contact.setPlaceholderText("Phone, Facebook or email, so we can reach you (optional)")
        self.idea_contact.setMaxLength(120)
        self.idea_text = QPlainTextEdit()
        self.idea_text.setPlaceholderText("Describe the app or tool you need…")
        self.idea_text.setFixedHeight(92)
        self.idea_status = QLabel("")
        self.idea_status.setWordWrap(True)
        self.idea_status.setStyleSheet(f"color:{C_MUTED};font-size:12px;")
        self.idea_button = QPushButton("Send idea")
        self.idea_button.setObjectName("primary")
        self.idea_button.setCursor(Qt.PointingHandCursor)
        self.idea_button.clicked.connect(self._send_idea)
        bottom = QHBoxLayout()
        bottom.addWidget(self.idea_button)
        bottom.addWidget(self.idea_status, 1)
        for widget in (idea_title, idea_text, self.idea_name, self.idea_contact, self.idea_text):
            idea_layout.addWidget(widget)
        idea_layout.addLayout(bottom)
        root.addWidget(idea)

        self.more_link = QPushButton(f"Browse everything at {WEBSITE_LABEL}  →")
        self.more_link.setObjectName("link")
        self.more_link.setCursor(Qt.PointingHandCursor)
        self.more_link.clicked.connect(lambda: open_website())
        root.addWidget(self.more_link, 0, Qt.AlignLeft)
        root.addStretch()
        self.signals = None
        self.set_apps([])

    def bind_signals(self, signals):
        self.signals = signals
        signals.idea_result.connect(self._idea_done)

    def _send_idea(self):
        text = self.idea_text.toPlainText().strip()
        if len(text) < 8:
            self.idea_status.setStyleSheet(f"color:{C_ERR};font-size:12px;")
            self.idea_status.setText("Please describe your idea in a few words.")
            return
        if self.signals is None:
            return
        self.idea_button.setEnabled(False)
        self.idea_status.setStyleSheet(f"color:{C_MUTED};font-size:12px;")
        self.idea_status.setText("Sending…")
        IdeaSender(self.signals, {"Name": self.idea_name.text().strip() or "-",
                                  "Contact": self.idea_contact.text().strip() or "-",
                                  "Idea": text[:2000]}).start()

    def _idea_done(self, ok, message):
        self.idea_button.setEnabled(True)
        if not ok and message == "fallback":
            # The direct send did not work (blocked network, service down). Never lose the idea: copy it and
            # open the same form on the website.
            try:
                QApplication.clipboard().setText(self.idea_text.toPlainText().strip())
            except Exception:
                logging.exception("Could not copy the idea text")
            QDesktopServices.openUrl(QUrl(IDEA_FALLBACK_URL))
            self.idea_status.setStyleSheet(f"color:{C_WARN};font-size:12px;")
            self.idea_status.setText("Could not send from the app. The website form opened and your text is copied: paste it there.")
            return
        self.idea_status.setStyleSheet(f"color:{C_OK if ok else C_ERR};font-size:12px;")
        self.idea_status.setText(message)
        if ok:
            self.idea_text.clear()

    def _tile(self, name, logo):
        tile = QLabel()
        tile.setFixedSize(54, 54)
        tile.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(resource_path("assets/shunchi-icon-512.png")) if logo else QPixmap()
        if logo and not pixmap.isNull():
            tile.setPixmap(pixmap.scaled(54, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            tile.setText((name[:1] or "?").upper())
            tile.setStyleSheet(f"background:{C_PRIMARY_SOFT};color:{C_PRIMARY_DARK};border-radius:14px;"
                               "font-size:22px;font-weight:700;")
        return tile

    def _app_card(self, name, tagline, badge, url=None, installed=False, logo=False):
        card, layout = make_card((18, 14, 18, 14), 0)
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(self._tile(name, logo), 0, Qt.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel(name)
        title.setStyleSheet(f"font-size:15px;font-weight:700;color:{C_TEXT};")
        title_row.addWidget(title)
        if badge:
            chip = QLabel(badge)
            chip.setStyleSheet(f"background:{C_PRIMARY_SOFT};color:{C_PRIMARY_DARK};border-radius:9px;"
                               "padding:2px 9px;font-size:11px;font-weight:700;")
            title_row.addWidget(chip)
        title_row.addStretch()
        sub = QLabel(tagline)
        sub.setObjectName("cardText")
        sub.setWordWrap(True)
        text.addLayout(title_row)
        text.addWidget(sub)
        row.addLayout(text, 1)
        if installed:
            state = QLabel("Installed")
            state.setStyleSheet(f"background:{C_OK_SOFT};color:{C_OK};border-radius:10px;padding:5px 12px;"
                                "font-size:12px;font-weight:700;")
            row.addWidget(state, 0, Qt.AlignVCenter)
        elif url:
            button = QPushButton("Open")
            button.setObjectName("secondary")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            row.addWidget(button, 0, Qt.AlignVCenter)
        layout.addLayout(row)
        return card

    def set_apps(self, apps):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.list_layout.addWidget(self._app_card(
            "SHUNCHi", "AI voice typing for Bangla and English, in every Windows app.", f"v{APP_VERSION}",
            installed=True, logo=True))
        shown = 0
        for app in apps or []:
            url = str(app.get("url", ""))
            if not url.lower().startswith("https://"):
                continue
            self.list_layout.addWidget(self._app_card(app.get("name", "App"), app.get("tagline", ""),
                                                      app.get("badge", ""), url=url))
            shown += 1
        if shown == 0:
            self.list_layout.addWidget(self._app_card(
                "More apps are on the way", f"New free tools from the developer will appear here. Follow {WEBSITE_LABEL}.",
                "Coming soon"))


class HelpPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 28, 30, 24)
        root.setSpacing(16)
        root.addLayout(page_header("How to use", "Five quick steps. After that SHUNCHi works in any app."))

        card, layout = make_card((20, 16, 20, 16), 14)
        steps = [
            ("Get a free key", "Open Google AI Studio and create a Gemini API key (Settings has a shortcut)."),
            ("Save it in Settings", "Paste the key and choose Save && test. It is stored in Windows Credential Manager."),
            ("Click where you want to type", "A browser, WhatsApp, Word, Notepad… any text field."),
            ("Press a shortcut and speak", "Win + Left Ctrl for Bangla, Win + Left Shift for English."),
            ("Pause", "When you stop speaking, SHUNCHi stops by itself and types the finished text at your cursor."),
        ]
        for number, (title, text) in enumerate(steps, 1):
            row = QHBoxLayout()
            row.setSpacing(14)
            badge = QLabel(str(number))
            badge.setFixedSize(30, 30)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(f"background:{C_PRIMARY_SOFT};color:{C_PRIMARY_DARK};border-radius:15px;font-weight:700;font-size:13px;")
            col = QVBoxLayout()
            col.setSpacing(1)
            t = QLabel(title)
            t.setStyleSheet(f"font-size:14px;font-weight:600;color:{C_TEXT};")
            d = QLabel(text.replace("&&", "&"))
            d.setObjectName("cardText")
            d.setWordWrap(True)
            col.addWidget(t)
            col.addWidget(d)
            row.addWidget(badge, 0, Qt.AlignTop)
            row.addLayout(col, 1)
            layout.addLayout(row)
        root.addWidget(card)

        tips, tips_layout = make_card((20, 16, 20, 16), 8)
        tt = QLabel("Good to know")
        tt.setObjectName("cardTitle")
        tips_layout.addWidget(tt)
        for line in (
            "Press the same shortcut again to finish early.",
            "You can mix English words into Bangla speech.",
            "If a program runs as administrator, Windows may block auto-typing; the text is then copied so you can press Ctrl + V.",
            "Windows Settings > Privacy > Microphone must allow desktop apps to use the microphone.",
            "Your Gemini key is yours. Never share it and never install modified copies of SHUNCHi.",
            f"New versions, downloads and help are published at {WEBSITE_LABEL}.",
        ):
            label = QLabel("•  " + line)
            label.setObjectName("cardText")
            label.setWordWrap(True)
            tips_layout.addWidget(label)
        root.addWidget(tips)
        root.addStretch()


class DeveloperPage(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 28, 30, 24)
        root.setSpacing(16)
        root.addLayout(page_header("Developer", "The person behind SHUNCHi and the official support channels."))

        card, layout = make_card((22, 20, 22, 20), 12)
        top = QHBoxLayout()
        top.setSpacing(18)
        photo = QLabel()
        photo.setFixedSize(104, 104)
        source = QPixmap(resource_path("assets/developer-ruhul.jpg"))
        rounded = QPixmap(104, 104)
        rounded.fill(Qt.transparent)
        if not source.isNull():
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.Antialiasing)
            clip = QPainterPath()
            clip.addEllipse(0, 0, 104, 104)
            painter.setClipPath(clip)
            scaled = source.scaled(104, 104, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.drawPixmap(QRectF(0, 0, 104, 104), scaled,
                               QRectF(max(0, (scaled.width() - 104) // 2), max(0, (scaled.height() - 104) // 2), 104, 104))
            painter.end()
            photo.setPixmap(rounded)
        info = QVBoxLayout()
        info.setSpacing(3)
        name = QLabel("Ruhul Amin")
        name.setStyleSheet(f"font-size:22px;font-weight:700;color:{C_TEXT};")
        role = QLabel("Creator & Developer · SHUNCHi by RUHUL")
        role.setObjectName("cardText")
        links = QLabel(
            '<a href="https://www.facebook.com/iamruhulaamin" style="color:#2563EB;text-decoration:none;">Facebook</a>'
            ' &nbsp;·&nbsp; <a href="https://www.instagram.com/iamruhulaamin/" style="color:#2563EB;text-decoration:none;">Instagram</a>'
            ' &nbsp;·&nbsp; <a href="https://www.linkedin.com/search/results/people/?keywords=iamruhulaamin" style="color:#2563EB;text-decoration:none;">LinkedIn</a>')
        links.setOpenExternalLinks(True)
        links.setTextInteractionFlags(Qt.TextBrowserInteraction)
        handle = QLabel("@iamruhulaamin")
        handle.setObjectName("muted")
        info.addWidget(name)
        info.addWidget(role)
        info.addWidget(handle)
        info.addSpacing(6)
        info.addWidget(links)
        info.addStretch()
        top.addWidget(photo)
        top.addLayout(info, 1)
        layout.addLayout(top)
        root.addWidget(card)

        story, story_layout = make_card((24, 20, 24, 22), 10)
        story_title = QLabel("Why SHUNCHi was made")
        story_title.setObjectName("cardTitle")
        story_layout.addWidget(story_title)
        paragraphs = (
            "<b>SHUNCHi-র যাত্রা শুরু হয়েছিল একটি প্রশ্ন থেকে—বাংলায় ভয়েস টাইপিং কেন সহজ, দ্রুত এবং সবার জন্য বিনামূল্যে হবে না?</b>",
            "আর কত টাইপিং শিখতে হবে? কেন নিজের ভাষায় কাজ করার জন্য টাকা খরচ করতে হবে? "
            "কেন ছোট ছোট ডিজিটাল কাজ শেখার জন্য ট্রেনিং সেন্টারে দৌড়াতে হবে?",
            "প্রযুক্তি তো আমাদের কাজ সহজ করার জন্য, কঠিন করার জন্য নয়!",
            "সেই ভাবনা থেকেই SHUNCHi-র শুরু। আমাদের লক্ষ্য, এমন সব সহজ ও কার্যকর টুল তৈরি করা, যা সবাই নিজের ভাষায় "
            "ব্যবহার করতে পারবেন—সহজে, স্বাচ্ছন্দ্যে এবং নামমাত্র খরচে।",
            "ভয়েস টাইপিং থেকে শুরু করে ইমেইল, CV তৈরি, ফাইল কনভার্টসহ প্রতিদিনের প্রয়োজনীয় অনেক টুল একে একে যুক্ত হবে SHUNCHi-তে।",
        )
        for text in paragraphs:
            para = QLabel(text)
            para.setWordWrap(True)
            para.setTextFormat(Qt.RichText)
            para.setStyleSheet(f"font-size:14px;color:{C_TEXT};line-height:150%;")
            story_layout.addWidget(para)
        tag = QLabel("SHUNCHi—প্রযুক্তি হোক সহজ, সবার জন্য।")
        tag.setStyleSheet(f"font-size:15px;font-weight:700;color:{C_PRIMARY_DARK};padding-top:4px;")
        story_layout.addWidget(tag)
        root.addWidget(story)

        site_button = QPushButton(f"Visit the developer page at {WEBSITE_LABEL}  →")
        site_button.setObjectName("link")
        site_button.setCursor(Qt.PointingHandCursor)
        site_button.clicked.connect(lambda: open_website("/#developer"))
        root.addWidget(site_button, 0, Qt.AlignLeft)

        official, official_layout = make_card((22, 18, 22, 18), 8)
        ot = QLabel("Official SHUNCHi")
        ot.setObjectName("cardTitle")
        od = QLabel("Product updates, installation help, troubleshooting and new releases.")
        od.setObjectName("cardText")
        od.setWordWrap(True)
        ol = QLabel(
            f'<a href="{WEBSITE_URL}" style="color:#2563EB;text-decoration:none;">Website · {WEBSITE_LABEL}</a><br/>'
            '<a href="https://www.facebook.com/voice.shunchi" style="color:#2563EB;text-decoration:none;">Facebook · @voice.shunchi</a><br/>'
            '<a href="https://www.instagram.com/voice.shunchi/" style="color:#2563EB;text-decoration:none;">Instagram · @voice.shunchi</a><br/>'
            '<a href="mailto:voice.shunchi@gmail.com" style="color:#2563EB;text-decoration:none;">voice.shunchi@gmail.com</a>')
        ol.setOpenExternalLinks(True)
        ol.setTextInteractionFlags(Qt.TextBrowserInteraction)
        official_layout.addWidget(ot)
        official_layout.addWidget(od)
        official_layout.addWidget(ol)
        root.addWidget(official)

        note = QLabel(f"Download updates only from {WEBSITE_LABEL} or the official SHUNCHi pages. "
                      "Do not install modified builds and never share your personal Gemini API key.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)
        root.addStretch()


class NoticeDialog(QDialog):
    """Admin-written pop-up shown on top of the dashboard. Text is plain (never HTML) and links open only https pages."""

    def __init__(self, parent, notice, bangla=True):
        super().__init__(parent)
        self.notice = notice
        self.setWindowTitle("SHUNCHi")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setMaximumWidth(520)
        pick = (lambda bn, en: (bn or en) if bangla else (en or bn))
        title = pick(notice["title_bn"], notice["title_en"])
        body = pick(notice["body_bn"], notice["body_en"])
        label = pick(notice["button_bn"], notice["button_en"])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(12)
        if title:
            head = QLabel(title)
            head.setWordWrap(True)
            head.setTextFormat(Qt.PlainText)
            head.setStyleSheet(f"font-size:18px;font-weight:700;color:{C_TEXT};")
            layout.addWidget(head)
        if body:
            text = QLabel(body)
            text.setWordWrap(True)
            text.setTextFormat(Qt.PlainText)
            text.setStyleSheet(f"font-size:14px;color:{C_MUTED};")
            layout.addWidget(text)
        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton("বন্ধ করুন" if bangla else "Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        if notice["url"] and is_trusted_url(notice["url"]):
            go = QPushButton(label or ("বিস্তারিত" if bangla else "Open"))
            go.setObjectName("primary")
            go.setDefault(True)
            go.clicked.connect(self._open)
            buttons.addWidget(go)
        layout.addLayout(buttons)

    def _open(self):
        QDesktopServices.openUrl(QUrl(self.notice["url"]))
        self.accept()


# ----------------------------------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------------------------------
class MainWindow(QMainWindow):
    NAV = (("Dashboard", "home"), ("Voice History", "history"), ("Settings", "settings"),
           ("How to use", "help"), ("More Apps", "apps"), ("Developer", "user"))

    def __init__(self):
        super().__init__()
        init_database()
        self.signals = AppSignals()
        self.signals.hotkey.connect(self.handle_hotkey)
        self.signals.hotkey_error.connect(self.show_error)
        self.signals.audio_level.connect(self.on_audio_level)
        self.signals.speech_started.connect(self.on_speech_started)
        self.signals.auto_stop.connect(self.stop_recording)
        self.signals.transcribed.connect(self.on_transcribed)
        self.signals.transcribe_failed.connect(self.on_transcribe_failed)
        self.signals.status.connect(self.show_status)
        self.signals.api_test_finished.connect(self.on_api_test_finished)
        self.signals.microphones_ready.connect(self.on_microphones_ready)
        self.signals.pause_hint.connect(self.on_pause_hint)
        self.signals.spec_done.connect(self.on_spec_done)
        self.signals.update_result.connect(self.on_update_result)
        self.signals.notices_ready.connect(self.on_notices)
        self.signals.update_progress.connect(self.on_update_progress)
        self.signals.update_downloaded.connect(self.on_update_downloaded)

        self.setWindowTitle("SHUNCHi by RUHUL")
        self.setWindowIcon(QIcon(resource_path("assets/shunchi.ico")))
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1040, max(820, screen.width() - 80)), min(720, max(600, screen.height() - 80)))
        self.setMinimumSize(min(860, screen.width() - 40), min(600, screen.height() - 60))
        self.center_on_screen()

        self.settings = QSettings("RUHUL", "SHUNCHi")
        self.smart_mode = self.settings.value("smart_mode", True, type=bool)
        self.silence_seconds = nearest_option(self.settings.value("silence_seconds", 0.7), (0.7, 1.0, 1.6))
        self.max_minutes = int(nearest_option(self.settings.value("max_minutes", 5), (2, 5, 10)))
        self.auto_update = self.settings.value("auto_update", True, type=bool)
        self.save_history_enabled = self.settings.value("save_history", True, type=bool)
        self.latest_info = None
        self.update_thread = None
        self.update_downloader = None
        self.update_progress_dialog = None
        self.update_dialog_open = False
        self.force_min = str(self.settings.value("force_min_version", "") or "")
        self.spec_token = 0
        self.spec_state = "none"        # none | running | done | failed
        self.spec_text = ""
        self.spec_voiced = -1
        self.spec_count = 0
        self.spec_adopted = False
        self.pending_pcm = b""

        self.api_key = None
        self.audio_stream = None
        self.input_rate = TARGET_RATE
        self.resampler = None
        self.vad = None
        self.chunks = []
        self.recording = False
        self.processing = False
        self.status_token = 0
        self.watchdog = QTimer(self)
        self.watchdog.setSingleShot(True)
        self.watchdog.timeout.connect(self._unstick)
        self.auto_stop_sent = False
        self.current_language = "bn-BD"
        self.recording_start = 0.0
        self.pending_duration = 0.0
        self.stream_device = None
        self.available_devices = []
        self.mic_scan_complete = False
        self.worker = None
        self.api_tester = None
        self.start_hidden = "--minimized" in sys.argv
        self.hotkeys = HotkeyManager(self.signals)
        self.popup = MicPopup()

        self._build_ui()
        self.settings_page.load_values(self.smart_mode, self.silence_seconds, self.max_minutes,
                                       startup_enabled() if os.name == "nt" else False, self.auto_update,
                                       self.save_history_enabled)
        self.history_page.set_recording(self.save_history_enabled)
        self.more_apps_page.set_apps(self.load_remote_apps())
        self.dashboard_page.update_button.clicked.connect(self.start_update_install)
        self.show_status(READY_TEXT)
        self.mic_scanner = MicrophoneScanner(self.signals)
        self.mic_scanner.start()
        self.hotkeys.start()
        # The window appears straight away (unless Windows started us quietly); the slower checks run after it.
        if not self.start_hidden:
            self.show()
        QTimer.singleShot(120, self.first_run_check)
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(UPDATE_CHECK_HOURS * 3600 * 1000)
        self.update_timer.timeout.connect(self.auto_update_check)
        self.update_timer.start()
        QTimer.singleShot(6000, self.auto_update_check)
        if self.update_is_forced():
            QTimer.singleShot(1500, self.show_forced_update)
        QTimer.singleShot(9000, lambda: NoticeChecker(self.signals).start())

    # ------------------------------------------------------------------ UI
    def center_on_screen(self):
        area = QApplication.primaryScreen().availableGeometry()
        self.move(area.x() + max(0, (area.width() - self.width()) // 2),
                  area.y() + max(0, (area.height() - self.height()) // 2))

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(236)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 22, 18, 18)
        side.setSpacing(4)
        logo = QLabel()
        pixmap = QPixmap(resource_path("assets/shunchi-full-logo.png"))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaledToWidth(168, Qt.SmoothTransformation))
        else:
            logo.setText("SHUNCHi")
            logo.setStyleSheet(f"font-size:24px;font-weight:800;color:{C_TEXT};")
        tagline = QLabel("AI voice typing · by RUHUL")
        tagline.setObjectName("muted")
        side.addWidget(logo)
        side.addWidget(tagline)
        side.addSpacing(18)

        self.nav_buttons = []
        self.nav_icons = []
        for index, (label, kind) in enumerate(self.NAV):
            button = QPushButton("  " + label)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setIconSize(QSize(20, 20))
            self.nav_icons.append((make_icon(kind, "#64748B"), make_icon(kind, C_PRIMARY_DARK)))
            button.clicked.connect(lambda _checked=False, i=index: self.switch_page(i))
            side.addWidget(button)
            self.nav_buttons.append(button)
        side.addStretch()
        hint = QLabel("বাংলা   Win + Left Ctrl\nEnglish   Win + Left Shift")
        hint.setObjectName("muted")
        hint.setStyleSheet(f"color:{C_FAINT};font-size:11px;")
        side.addWidget(hint)
        site_link = QPushButton(WEBSITE_LABEL)
        site_link.setObjectName("link")
        site_link.setCursor(Qt.PointingHandCursor)
        site_link.clicked.connect(lambda: open_website())
        side.addWidget(site_link)
        outer.addWidget(sidebar)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self.dashboard_page = DashboardPage(lambda: self.switch_page(2))
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage(self)
        self.help_page = HelpPage()
        self.more_apps_page = MoreAppsPage()
        self.developer_page = DeveloperPage()
        self.more_apps_page.bind_signals(self.signals)
        self.stack = QStackedWidget()
        for page in (self.dashboard_page, self.history_page, self.settings_page, self.help_page,
                     self.more_apps_page, self.developer_page):
            self.stack.addWidget(scroll_page(page))
        right.addWidget(self.stack, 1)

        footer = QFrame()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(30, 8, 30, 8)
        credit = QLabel(
            f'<a href="{WEBSITE_URL}" style="color:{C_PRIMARY_DARK};text-decoration:none;"><b>{WEBSITE_LABEL}</b></a> &nbsp;·&nbsp; '
            'Built by <b>Ruhul Amin</b> &nbsp;·&nbsp; '
            f'<a href="{social_url("Facebook")}" style="color:{C_MUTED};">Facebook</a> &nbsp;'
            f'<a href="{social_url("Instagram")}" style="color:{C_MUTED};">Instagram</a> &nbsp;'
            f'<a href="{social_url("LinkedIn")}" style="color:{C_MUTED};">LinkedIn</a>')
        credit.setOpenExternalLinks(True)
        credit.setStyleSheet(f"font-size:11px;color:{C_MUTED};")
        version = QLabel(f"SHUNCHi {APP_VERSION}")
        version.setStyleSheet(f"font-size:11px;color:{C_FAINT};")
        footer_layout.addWidget(credit)
        footer_layout.addStretch()
        footer_layout.addWidget(version)
        right.addWidget(footer)
        outer.addLayout(right, 1)
        self.switch_page(0)

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            active = i == index
            button.setChecked(active)
            button.setIcon(self.nav_icons[i][1 if active else 0])
        if index == 1:
            self.history_page.refresh()

    def show_status(self, text):
        """Shows one line under the dashboard and returns to the ready text a few seconds later,
        so an old message such as 'Microphone active' can never stay on screen."""
        text = str(text)
        self.dashboard_page.set_activity(text)
        self.status_token += 1
        if text != READY_TEXT:
            token = self.status_token
            QTimer.singleShot(9000, lambda: self._clear_status(token))

    def _clear_status(self, token):
        if token == self.status_token and not self.recording and not self.processing:
            self.dashboard_page.set_activity(READY_TEXT)

    def _arm_watchdog(self):
        self.watchdog.start(130000)

    def _unstick(self):
        """Safety net: if writing never finishes (network hang, lost signal) release the app so the next
        shortcut works again instead of the dashboard staying busy."""
        if not self.processing:
            return
        logging.warning("Processing watchdog fired; resetting state")
        self.processing = False
        self.spec_token += 1
        self.spec_state = "none"
        self.popup.show_error("Took too long. Please try again.")
        self.show_status("Took too long. Please try again.")

    def show_error(self, message):
        logging.error("Shown to user: %s", message)
        self.show_status(str(message).splitlines()[0] if message else "")
        QMessageBox.warning(self, APP_NAME, str(message))

    # ------------------------------------------------------------------ settings
    def on_settings_changed(self):
        page = self.settings_page
        self.smart_mode = page.smart.isChecked()
        self.silence_seconds = float(page.silence.value())
        self.max_minutes = int(page.max_minutes.value())
        device = page.selected_microphone()
        if device >= 0:
            self.stream_device = device
            self.settings.setValue("input_device", device)
        self.save_history_enabled = page.history_on.isChecked()
        self.history_page.set_recording(self.save_history_enabled)
        self.settings.setValue("save_history", self.save_history_enabled)
        self.settings.setValue("smart_mode", self.smart_mode)
        self.settings.setValue("silence_seconds", self.silence_seconds)
        self.settings.setValue("max_minutes", self.max_minutes)
        self.settings.sync()

    def on_auto_update_toggled(self, checked):
        self.auto_update = bool(checked)
        self.settings.setValue("auto_update", self.auto_update)
        self.settings.sync()
        if self.auto_update:
            self.auto_update_check()

    # ------------------------------------------------------------------ updates + remote apps
    def load_remote_apps(self):
        try:
            raw = json.loads(self.settings.value("remote_apps", "[]") or "[]")
        except Exception:
            return []
        return [a for a in raw if isinstance(a, dict)][:12] if isinstance(raw, list) else []

    def auto_update_check(self):
        if self.auto_update:
            self.start_update_check(False)

    def check_updates_manual(self):
        self.start_update_check(True)

    def start_update_check(self, manual):
        if self.update_thread is not None and self.update_thread.is_alive():
            return
        if manual:
            self.settings_page.set_checking(True)
        self.update_thread = UpdateChecker(self.signals, manual)
        self.update_thread.start()

    def on_notices(self, notices):
        """Shows at most one due pop-up per start. Counts are kept per message id on this computer."""
        if self.recording or self.processing or not self.isVisible():
            QTimer.singleShot(120000, lambda: self.on_notices(notices))     # try again later; never pop up from the tray
            return
        try:
            counts = json.loads(self.settings.value("notice_counts", "{}") or "{}")
        except (TypeError, ValueError):
            counts = {}
        for notice in notices:
            record = counts.get(notice["id"], {})
            if not notice_due(notice, int(record.get("n", 0)), float(record.get("t", 0))):
                continue
            counts[notice["id"]] = {"n": int(record.get("n", 0)) + 1, "t": time.time()}
            counts = {k: v for k, v in counts.items() if k in {n["id"] for n in notices}}
            self.settings.setValue("notice_counts", json.dumps(counts))
            self.settings.sync()
            self.switch_page(0)
            NoticeDialog(self, notice, self.settings.value("ui_bangla", True, type=bool)).exec()
            break

    def update_is_forced(self):
        """True while this version is older than the minimum version the developer requires."""
        return bool(self.force_min) and parse_version(APP_VERSION) < parse_version(self.force_min)

    def on_update_result(self, result):
        manual = bool(result.get("manual"))
        self.settings_page.set_checking(False)
        if not result.get("ok"):
            if manual:
                self.settings_page.set_update_status(result.get("error", "Could not check for updates."), "error")
            return
        info = result["info"]
        try:
            self.settings.setValue("remote_apps", json.dumps(info.get("apps", [])))
            self.force_min = info.get("min_version", "") or ""
            self.settings.setValue("force_min_version", self.force_min)
            self.settings.sync()
        except Exception:
            logging.exception("Could not cache the app list")
        self.more_apps_page.set_apps(info.get("apps", []))
        if parse_version(info["latest"]) > parse_version(APP_VERSION):
            self.latest_info = info
            self.dashboard_page.show_update(info["latest"], self.update_is_forced())
            self.settings_page.set_update_status(f"Version {info['latest']} is available.", "ok")
            if self.update_is_forced():
                self.show_forced_update()
            elif manual or self.settings.value("update_notified", "") != info["latest"]:
                self.settings.setValue("update_notified", info["latest"])
                self.notify_update(info)
        else:
            self.latest_info = None
            self.force_min = ""
            self.settings.setValue("force_min_version", "")
            self.dashboard_page.hide_update()
            self.settings_page.set_update_status(f"You are up to date · SHUNCHi {APP_VERSION}.", "ok" if manual else None)

    def notify_update(self, info):
        """Visible window: ask directly. Hidden in the tray: only a tray message (a dialog could steal focus mid-dictation)."""
        if not self.isVisible():
            tray = getattr(self, "tray_icon", None)
            if tray is not None:
                tray.showMessage(f"SHUNCHi {info['latest']} is available",
                                 "Click here to open SHUNCHi and update.", QSystemTrayIcon.Information, 8000)
            return
        if self.recording or self.processing:
            QTimer.singleShot(20000, lambda: self.notify_update(info))
            return
        if self.update_dialog_open or self.update_busy():
            return
        self.update_dialog_open = True
        try:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("SHUNCHi update")
            box.setText(f"SHUNCHi {info['latest']} is available")
            notes = info.get("notes") or "A newer version is ready."
            box.setInformativeText(f"{notes}\n\nYou have {APP_VERSION}. Update now? It takes about a minute.")
            now_button = box.addButton("Update now", QMessageBox.AcceptRole)
            box.addButton("Later", QMessageBox.RejectRole)
            box.setDefaultButton(now_button)
            box.exec()
            chosen = box.clickedButton() is now_button
        finally:
            self.update_dialog_open = False
        if chosen:
            self.start_update_install()

    def show_forced_update(self):
        """A required update: the window comes forward and the only ways on are updating or leaving."""
        if not self.update_is_forced() or self.update_dialog_open or self.update_busy():
            return
        info = self.latest_info or {"latest": self.force_min, "notes": ""}
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.update_dialog_open = True
        try:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("SHUNCHi update required")
            box.setText(f"Please update to SHUNCHi {info.get('latest') or self.force_min}")
            box.setInformativeText(
                f"This version ({APP_VERSION}) is too old to keep working reliably.\n"
                "The update is free and takes about a minute. Your settings and history stay.")
            now_button = box.addButton("Update now", QMessageBox.AcceptRole)
            page_button = box.addButton("Open download page", QMessageBox.ActionRole)
            exit_button = box.addButton("Exit SHUNCHi", QMessageBox.RejectRole)
            box.setDefaultButton(now_button)
            box.exec()
            clicked = box.clickedButton()
        finally:
            self.update_dialog_open = False
        if clicked is now_button:
            self.start_update_install()
        elif clicked is page_button:
            self.open_download()
        elif clicked is exit_button:
            owner = APP_OWNER.get("app")
            if owner is not None:
                owner.quit()
            else:
                QApplication.quit()

    def update_busy(self):
        return self.update_downloader is not None and self.update_downloader.is_alive()

    def open_download(self):
        url = (self.latest_info or {}).get("download_url") or DOWNLOAD_URL_DEFAULT
        if not is_trusted_url(url):
            url = DOWNLOAD_URL_DEFAULT
        QDesktopServices.openUrl(QUrl(url))

    def start_update_install(self):
        """Download the new installer inside the app, verify it, then start it. Anything unexpected falls
        back to opening the download page, so the user is never stuck."""
        info = self.latest_info or {}
        if os.name != "nt" or not info.get("installer_url") or not info.get("installer_sha256"):
            self.open_download()
            return
        if self.update_busy():
            return
        if self.recording or self.processing:
            QMessageBox.information(self, APP_NAME, "Finish your current dictation first, then update.")
            return
        folder = Path(os.getenv("TEMP", str(APPDATA))) / "SHUNCHi_Update"
        name = "SHUNCHi_Setup_" + re.sub(r"[^0-9.]", "", str(info.get("latest", ""))) + ".exe"
        destination = folder / name
        dialog = QProgressDialog(f"Downloading SHUNCHi {info.get('latest', '')}…", "Cancel", 0, 100, self)
        dialog.setWindowTitle("SHUNCHi update")
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        self.update_progress_dialog = dialog
        self.update_downloader = InstallerDownloader(
            self.signals, info["installer_url"], info["installer_sha256"], info.get("installer_size", 0), destination)
        dialog.canceled.connect(self.update_downloader.cancel)
        self.update_downloader.start()
        dialog.show()

    def on_update_progress(self, percent):
        dialog = self.update_progress_dialog
        if dialog is not None:
            dialog.setValue(int(percent))

    def on_update_downloaded(self, ok, detail):
        dialog, self.update_progress_dialog = self.update_progress_dialog, None
        if dialog is not None:
            try:
                dialog.canceled.disconnect()
            except Exception:
                pass
            dialog.close()
            dialog.deleteLater()
        if ok:
            try:
                os.startfile(detail)            # opens the installer like a double-click (Windows asks for permission itself)
            except Exception as exc:
                logging.exception("Could not start the installer")
                QMessageBox.warning(self, APP_NAME, f"The update was downloaded but could not be started:\n{exc}\n\n"
                                                    "The download page will open instead.")
                self.open_download()
                return
            self.show_status("Installer started. SHUNCHi will close so the update can finish.")
            QTimer.singleShot(1500, self._quit_for_update)
            return
        if detail == "cancelled":
            self.show_status("Update cancelled.")
            return
        QMessageBox.warning(self, APP_NAME, f"The update could not be downloaded ({detail}).\n\n"
                                            "The download page will open so you can update there.")
        self.open_download()

    def _quit_for_update(self):
        owner = APP_OWNER.get("app")
        if owner is not None:
            owner.quit()
        else:
            QApplication.quit()

    def on_startup_toggled(self, checked):
        try:
            set_startup_enabled(bool(checked))
        except Exception as exc:
            logging.exception("Could not change the Windows start-up entry")
            self.settings_page.startup.blockSignals(True)
            self.settings_page.startup.setChecked(not checked)
            self.settings_page.startup.blockSignals(False)
            QMessageBox.warning(self, APP_NAME, f"Windows did not allow the change:\n{exc}")

    def on_microphones_ready(self, devices, default_input):
        self.available_devices = list(devices or [])
        saved = self.settings.value("input_device", None)
        try:
            saved = int(saved) if saved is not None else None
        except Exception:
            saved = None
        ids = [item[0] for item in self.available_devices]
        if saved not in ids:
            saved = default_input if default_input in ids else None
        if saved is None and self.available_devices:
            preferred = next((i[0] for i in self.available_devices
                              if any(t in i[1].casefold() for t in ("microphone", "mic array", "headset", "usb mic"))), None)
            saved = preferred if preferred is not None else self.available_devices[0][0]
        self.stream_device = saved
        self.mic_scan_complete = True
        self.settings_page.populate_microphones(self.available_devices, saved)
        if not self.available_devices:
            self.show_status("No microphone detected · check Windows microphone permissions.")

    # ------------------------------------------------------------------ API key
    def first_run_check(self):
        try:
            self.api_key = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME) or None
        except Exception as exc:
            logging.exception("Windows Credential Manager could not initialise")
            self.api_key = None
            self.dashboard_page.set_api_state("error", "Windows Credential Manager is unavailable. Check your Windows account permissions.")
            self.settings_page.set_key_status(False)
            self.show()
            QMessageBox.critical(self, APP_NAME, f"Windows Credential Manager is unavailable:\n{exc}")
            return
        if self.api_key:
            self.dashboard_page.set_api_state("pending", "Ready · press Win + Left Ctrl (Bangla) or Win + Left Shift (English).")
            self.settings_page.set_key_status(True)
            self.settings_page.set_key_result("A key is saved. Choose “Save & test” with a new key to replace it.")
        else:
            self.dashboard_page.set_api_state("missing", "Add your Gemini API key in Settings to start voice typing.")
            self.settings_page.set_key_status(False)
        if not (self.start_hidden and self.api_key):
            self.show()
            self.raise_()
            self.activateWindow()
            self.start_hidden = False

    def save_api_key(self, key):
        if len(key) < 20 or any(ch.isspace() for ch in key):
            self.settings_page.set_key_result("That does not look like a Gemini API key. Copy it again from Google AI Studio.", False)
            return
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, key)
        except Exception as exc:
            logging.exception("Could not save the API key")
            self.settings_page.set_key_result(f"Windows could not store the key: {exc}", False)
            return
        self.api_key = key
        self.settings_page.set_busy(True)
        self.settings_page.set_key_status(True)
        self.settings_page.set_key_result("Saved. Testing the connection…")
        self.dashboard_page.set_api_state("pending", "Testing your Gemini connection…")
        self.api_tester = ApiTester(key, self.signals)
        self.api_tester.start()

    def remove_api_key(self):
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except Exception:
            pass
        self.api_key = None
        self.settings_page.key_input.clear()
        self.settings_page.set_key_status(False)
        self.settings_page.set_key_result("The key was removed from this computer.")
        self.dashboard_page.set_api_state("missing", "Add your Gemini API key in Settings to start voice typing.")

    def on_api_test_finished(self, success, message):
        self.settings_page.set_busy(False)
        self.settings_page.set_key_status(True, success)
        self.settings_page.set_key_result(message, success)
        if success:
            self.settings_page.key_input.clear()
            self.dashboard_page.set_api_state("ok", "Connected · voice typing is ready.")
        else:
            self.dashboard_page.set_api_state("error", message)

    # ------------------------------------------------------------------ dictation
    def handle_hotkey(self, language):
        if self.recording:
            self.stop_recording("manual")
        elif self.processing:
            self.popup.show_error("Still writing your previous text…")
        else:
            self.start_dictation(language)

    def start_dictation(self, language):
        if self.update_is_forced():
            self.popup.show_error("Please update SHUNCHi first.")
            QTimer.singleShot(0, self.show_forced_update)
            return
        if not self.api_key:
            try:
                self.api_key = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME) or None
            except Exception:
                self.api_key = None
        if not self.api_key:
            self.popup.show_error("Add your Gemini API key in Settings first.")
            self.show_status("Add your Gemini API key in Settings to start voice typing.")
            return
        if not self.mic_scan_complete:
            self.popup.show_error("Microphone is still starting. Try again in a moment.")
            return
        self.current_language = language
        self.chunks = []
        self.auto_stop_sent = False
        self.spec_token += 1                    # forgets any early result left from the previous dictation
        self.spec_state, self.spec_text, self.spec_voiced = "none", "", -1
        self.spec_count, self.spec_adopted, self.pending_pcm = 0, False, b""
        self.vad = VoiceActivityDetector(self.silence_seconds, 8.0, self.max_minutes * 60.0)
        try:
            self._start_microphone()
        except Exception as exc:
            logging.exception("Microphone start failed")
            self.recording = False
            self.popup.show_error("Could not open the microphone. Check Windows microphone permissions.")
            self.show_status(f"Microphone error: {exc}")
            return
        self.popup.begin(language)

    def _start_microphone(self):
        if not self.available_devices:
            raise RuntimeError("No microphone input device was found.")
        selected = next((d for d in self.available_devices if d[0] == self.stream_device), self.available_devices[0])
        self.stream_device = selected[0]
        device, name, max_channels, default_rate = selected
        rates = [r for r in dict.fromkeys([int(default_rate or 48000), 48000, 44100, 32000, 24000, 16000]) if r >= TARGET_RATE]
        channel_options = [1, 2] if int(max_channels) >= 2 else [1]
        last_error = None
        for channels in channel_options:
            for rate in rates:
                candidate = None
                try:
                    sd.check_input_settings(device=device, samplerate=rate, channels=channels, dtype="int16")
                    self.input_rate = rate
                    # Create the resampler BEFORE the stream starts: PortAudio may call back immediately.
                    self.resampler = StreamResampler(rate, TARGET_RATE)
                    self.recording_start = time.monotonic()
                    self.recording = True
                    candidate = sd.InputStream(device=device, samplerate=rate, channels=channels, dtype="int16",
                                               blocksize=max(1024, int(rate * 0.1)), callback=self.audio_callback)
                    candidate.start()
                    self.audio_stream = candidate
                    self.show_status(f"Microphone active · {name} · {rate} Hz")
                    return
                except Exception as exc:
                    last_error = exc
                    self.recording = False
                    if candidate is not None:
                        for action in (candidate.stop, candidate.close):
                            try:
                                action()
                            except Exception:
                                pass
        raise RuntimeError(f"Windows rejected all tested microphone formats for {name}. Last error: {last_error}")

    def audio_callback(self, indata, frames, time_info, status):
        if not self.recording:
            return
        try:
            samples = indata.astype(np.float32)
            mono = samples.mean(axis=1) if samples.ndim > 1 and samples.shape[1] > 1 else samples.reshape(-1)
            mono = mono - float(mono.mean()) if mono.size else mono
            rms = float(np.sqrt(np.mean(mono * mono))) if mono.size else 0.0
            elapsed = time.monotonic() - self.recording_start
            event = self.vad.process(rms, frames / float(self.input_rate), elapsed)
            voiced = self.vad.is_voice_frame(rms)
            pcm = np.clip(self.resampler.process(mono), -32768, 32767).astype("<i2").tobytes()
            if pcm:
                self.chunks.append((pcm, voiced))
            level = min(1.0, (max(0.0, rms - self.vad.floor) / 1800.0) ** 0.55)
            self.signals.audio_level.emit(level, elapsed)
            if event == "speech_started":
                self.signals.speech_started.emit()
            elif event == "pause":
                self.signals.pause_hint.emit()
            elif event in ("silence", "no_speech", "max") and not self.auto_stop_sent:
                self.auto_stop_sent = True
                self.signals.auto_stop.emit(event)
        except Exception:
            logging.exception("Audio callback failed")

    def on_audio_level(self, level, elapsed):
        if self.recording:
            self.popup.set_level(level)

    def on_speech_started(self):
        if self.recording:
            self.popup.mark_speech()

    def on_pause_hint(self):
        """A short pause: start transcribing now. If you finish speaking, the text is already on its way."""
        if (not self.recording or self.vad is None or not self.api_key
                or self.spec_state == "running" or self.spec_count >= 2):
            return
        pcm, voiced_frames = trim_recording(list(self.chunks))
        if voiced_frames < 3 or len(pcm) / float(TARGET_RATE * 2) < 0.6:
            return
        self.spec_token += 1
        self.spec_count += 1
        self.spec_state, self.spec_text, self.spec_adopted = "running", "", False
        self.spec_voiced = self.vad.voiced_frames
        TranscribeWorker(self.api_key, pcm, self.current_language, self.smart_mode, self.signals,
                         token=self.spec_token).start()

    def on_spec_done(self, token, text, message, kind):
        if token != self.spec_token or self.spec_state != "running":
            return                              # an old early request: ignore
        text = (text or "").strip()
        if not kind and text:
            self.spec_state, self.spec_text = "done", text
            if self.spec_adopted:
                self.spec_adopted = False
                self.on_transcribed(text)
            return
        self.spec_state = "failed"
        if self.spec_adopted:                   # the user already finished: do not leave them waiting
            self.spec_adopted = False
            if kind in ("auth", "access", "quota"):
                self.on_transcribe_failed(message, kind)
            else:
                self._start_transcription(self.pending_pcm)

    def _start_transcription(self, pcm):
        self.spec_token += 1                    # any early request still running is now irrelevant
        self.spec_state = "none"
        self.worker = TranscribeWorker(self.api_key, pcm, self.current_language, self.smart_mode, self.signals)
        self.worker.start()

    def stop_recording(self, reason="manual"):
        if not self.recording:
            return
        self.recording = False
        stream, self.audio_stream = self.audio_stream, None
        if stream is not None:
            threading.Thread(target=close_stream_quietly, args=(stream,), daemon=True).start()
        pcm, voiced_frames = trim_recording(self.chunks)
        self.chunks = []
        seconds = len(pcm) / float(TARGET_RATE * 2)
        if reason == "no_speech" or voiced_frames < 3 or seconds < 0.4:
            self.popup.show_error("Didn't hear anything. Try again a little closer to the microphone.")
            return
        self.processing = True
        self._arm_watchdog()
        self.pending_duration = seconds
        self.pending_pcm = pcm
        self.popup.set_processing()
        same_speech = self.vad is not None and self.spec_voiced == self.vad.voiced_frames
        if same_speech and self.spec_state == "done":
            self.on_transcribed(self.spec_text)         # the early result is already here
        elif same_speech and self.spec_state == "running":
            self.spec_adopted = True                    # it will be typed the moment it arrives
        else:
            self._start_transcription(pcm)

    def on_transcribed(self, text):
        self.processing = False
        self.watchdog.stop()
        self.spec_token += 1
        self.spec_state = "none"
        text = (text or "").strip()
        if not text:
            self.popup.show_error("No speech was recognised. Please try again.")
            return
        self.popup.finish()
        self._paste_text(text)                  # type first, bookkeeping afterwards: the text appears sooner
        if self.save_history_enabled:
            try:
                save_history(self.current_language, self.pending_duration, text)
            except Exception:
                logging.exception("Could not save history")
        self.dashboard_page.set_api_state("ok", "Connected · voice typing is working.")
        self.show_status(f"Typed {len(text)} characters.")

    def on_transcribe_failed(self, message, kind):
        self.processing = False
        self.watchdog.stop()
        self.spec_token += 1
        self.spec_state = "none"
        self.popup.show_error(message)
        self.show_status(message)
        if kind in ("auth", "access"):
            self.dashboard_page.set_api_state("error", message)
            self.settings_page.set_key_status(True, False)

    def _paste_text(self, text):
        old = ""
        try:
            try:
                old = pyperclip.paste()
            except Exception:
                old = ""
            pyperclip.copy(text)
            wait_for_modifier_release()
            time.sleep(0.04)
            send_ctrl_v()

            def restore():
                try:
                    if pyperclip.paste() == text and old:
                        pyperclip.copy(old)
                except Exception:
                    pass
            QTimer.singleShot(1500, restore)
        except Exception as exc:
            logging.exception("Auto-paste failed")
            self.popup.show_error("Text copied · press Ctrl + V to paste it.")
            self.show_status(f"Auto-paste unavailable ({exc}). The text is on your clipboard.")

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        if not self.settings.value("tray_hint_shown", False, type=bool):
            self.settings.setValue("tray_hint_shown", True)
            tray = getattr(self, "tray_icon", None)
            if tray is not None:
                tray.showMessage("SHUNCHi is still running",
                                 "Voice typing stays active in the system tray. Right-click the icon and choose Exit to quit.",
                                 QSystemTrayIcon.Information, 6000)


class ShunchiApp:
    def __init__(self):
        self.mutex = self.acquire_mutex()
        if self.mutex is False:
            raise SystemExit(0)
        APP_OWNER["app"] = self
        self.qt = QApplication(sys.argv)
        self.qt.setApplicationName(APP_NAME)
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setWindowIcon(QIcon(resource_path("assets/shunchi.ico")))
        self.qt.setFont(QFont("Segoe UI", 10))
        self.qt.setStyleSheet(build_qss(ensure_chevron()))
        self.window = MainWindow()

        self.tray = QSystemTrayIcon(QIcon(resource_path("assets/shunchi.ico")))
        self.tray.setToolTip("SHUNCHi by RUHUL · AI Voice Typing")
        self.menu = QMenu()
        self.menu_open = QAction("Open SHUNCHi")
        self.menu_open.triggered.connect(self.show_window)
        self.menu_settings = QAction("Settings")
        self.menu_settings.triggered.connect(self.open_settings)
        self.menu_site = QAction(f"Visit {WEBSITE_LABEL}")
        self.menu_site.triggered.connect(lambda: open_website())
        self.menu_update = QAction("Check for updates")
        self.menu_update.triggered.connect(self.check_updates)
        self.menu_exit = QAction("Exit SHUNCHi")
        self.menu_exit.triggered.connect(self.quit)
        self.menu.addAction(self.menu_open)
        self.menu.addAction(self.menu_settings)
        self.menu.addAction(self.menu_site)
        self.menu.addAction(self.menu_update)
        self.menu.addSeparator()
        self.menu.addAction(self.menu_exit)
        self.tray.setContextMenu(self.menu)
        self.window.tray_icon = self.tray
        self.tray.activated.connect(self.tray_activated)
        self.tray.messageClicked.connect(self.on_tray_message)
        self.tray.show()

    def acquire_mutex(self):
        if os.name != "nt":
            return None
        mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "Local\\SHUNCHi_4_SingleInstance")
        if ctypes.windll.kernel32.GetLastError() == 183:
            try:
                user32 = ctypes.windll.user32
                hwnd = user32.FindWindowW(None, "SHUNCHi by RUHUL")
                if hwnd:
                    user32.ShowWindow(hwnd, 9)
                    user32.SetForegroundWindow(hwnd)
            except Exception:
                logging.exception("Could not activate the existing SHUNCHi window")
            ctypes.windll.kernel32.CloseHandle(mutex)
            return False
        return mutex

    def show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def open_settings(self):
        self.window.switch_page(2)
        self.show_window()

    def check_updates(self):
        self.window.switch_page(2)
        self.show_window()
        self.window.check_updates_manual()

    def on_tray_message(self):
        self.window.switch_page(0)
        self.show_window()

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()

    def quit(self):
        try:
            self.window.hotkeys.stop()
            if self.window.audio_stream:
                self.window.audio_stream.stop()
                self.window.audio_stream.close()
        except Exception:
            logging.exception("Shutdown cleanup failed")
        self.tray.hide()
        self.qt.quit()


def main():
    app = ShunchiApp()
    sys.exit(app.qt.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.exception("Fatal SHUNCHi start-up error")
        try:
            ctypes.windll.user32.MessageBoxW(
                0, "SHUNCHi could not start.\n\n" + str(exc) + "\n\nLog: " + str(LOG_PATH), "SHUNCHi by RUHUL", 0x10)
        except Exception:
            print("SHUNCHi failed:", exc)
        raise
