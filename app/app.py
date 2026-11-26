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


from PySide6.QtCore import (
    Qt, Signal, QObject, QTimer, QSettings, QElapsedTimer, QUrl, QRectF, QRect, QPointF, QPoint, QSize,
    QPropertyAnimation, QEasingCurve, QEvent
)
from PySide6.QtGui import (
    QIcon, QAction, QPixmap, QPainter, QPen, QColor, QPainterPath, QFont,
    QDesktopServices, QCursor, QLinearGradient, QBrush, QFontMetrics
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QCheckBox, QLineEdit, QMessageBox, QSystemTrayIcon,
    QMenu, QFrame, QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QPlainTextEdit, QSizePolicy, QScrollArea, QWidgetAction,
    QAbstractItemView, QButtonGroup, QDialog, QProgressDialog
)

APP_NAME = "SHUNCHi"
APP_VERSION = "5.0.2"
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
READY_TEXT_KEY = READY_TEXT
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
# Instant splash: the window below appears at once, BEFORE the slow libraries (NumPy, PortAudio,
# Credential Manager) are loaded, so SHUNCHi never looks like it is doing nothing.
# ----------------------------------------------------------------------------------------------
SPLASH = None


def _show_splash():
    global SPLASH
    try:
        from PySide6.QtWidgets import QSplashScreen
        app = QApplication.instance() or QApplication(sys.argv)
        pix = QPixmap(420, 210)
        pix.fill(QColor("#FFFFFF"))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#E3E9F2"), 2))
        painter.drawRect(1, 1, 418, 208)
        logo = QPixmap(resource_path("assets/shunchi-full-logo.png"))
        if not logo.isNull():
            logo = logo.scaledToWidth(210, Qt.SmoothTransformation)
            painter.drawPixmap((420 - logo.width()) // 2, 36, logo)
        painter.setPen(QColor("#64748B"))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(QRect(0, 140, 420, 26), Qt.AlignCenter, "Starting SHUNCHi…  ·  SHUNCHi চালু হচ্ছে…")
        painter.setPen(QPen(QColor("#2563EB"), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(150, 184, 270, 184)
        painter.end()
        SPLASH = QSplashScreen(pix, Qt.WindowStaysOnTopHint)
        SPLASH.show()
        app.processEvents()
    except Exception:
        SPLASH = None


def _another_copy_running():
    try:
        handle = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, "Local\\SHUNCHi_4_SingleInstance")
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
    except Exception:
        pass
    return False


if __name__ == "__main__" and os.name == "nt" and "--minimized" not in sys.argv and not _another_copy_running():
    _show_splash()

import numpy as np
import sounddevice as sd
import pyperclip
import keyring


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


class SecretStore:
    """Keeps the Gemini key so it survives restarts and reboots.

    Windows Credential Manager entries written by the 'keyring' library are sometimes dropped when a
    PC that is not on a company domain is restarted. So the key is ALSO kept in a file that only this
    Windows user can open (encrypted with Windows DPAPI). Reading tries the file first, then the
    Credential Manager, and heals whichever copy is missing."""
    FILE = APPDATA / "key.dat"
    ENTROPY = b"SHUNCHi-key-v1"

    @staticmethod
    def _blob(data):
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
        buf = ctypes.create_string_buffer(data, len(data))
        return Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf, Blob

    @classmethod
    def _dpapi(cls, data, protect):
        inb, keep1, Blob = cls._blob(data)
        ent, keep2, _ = cls._blob(cls.ENTROPY)
        out = Blob()
        crypt = ctypes.windll.crypt32
        ok = (crypt.CryptProtectData if protect else crypt.CryptUnprotectData)(
            ctypes.byref(inb), None, ctypes.byref(ent), None, None, 0, ctypes.byref(out))
        if not ok:
            raise OSError("Windows DPAPI failed")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)

    @classmethod
    def _file_get(cls):
        if os.name != "nt" or not cls.FILE.exists():
            return None
        try:
            return cls._dpapi(cls.FILE.read_bytes(), False).decode("utf-8").strip() or None
        except Exception:
            logging.exception("Could not read the saved key file")
            return None

    @classmethod
    def _file_set(cls, key):
        if os.name != "nt":
            return False
        try:
            tmp = cls.FILE.with_suffix(".tmp")
            tmp.write_bytes(cls._dpapi(key.encode("utf-8"), True))
            os.replace(str(tmp), str(cls.FILE))
            return True
        except Exception:
            logging.exception("Could not write the key file")
            return False

    @staticmethod
    def _ring_get():
        try:
            return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME) or None
        except Exception:
            logging.exception("Credential Manager read failed")
            return None

    @staticmethod
    def _ring_set(key):
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, key)
            return True
        except Exception:
            logging.exception("Credential Manager write failed")
            return False

    @classmethod
    def get(cls):
        key = cls._file_get()
        if not key:
            key = cls._ring_get()
            if key:
                cls._file_set(key)                 # heal the file copy
        return key or None

    @classmethod
    def save(cls, key):
        """True if at least one place kept the key."""
        a = cls._file_set(key)
        b = cls._ring_set(key)
        return a or b

    @classmethod
    def delete(cls):
        try:
            if cls.FILE.exists():
                cls.FILE.unlink()
        except Exception:
            logging.exception("Could not delete the key file")
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except Exception:
            pass


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
        UPDATE_URL + "?t=" + str(int(time.time() // 60)), headers={"User-Agent": f"SHUNCHi/{APP_VERSION}", "Cache-Control": "no-cache"})
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
# ----------------------------------------------------------------------------------------------
# Dashboard language (English / Bangla)
# ----------------------------------------------------------------------------------------------
UI_BN = True
BN = {
    "Dashboard": "ড্যাশবোর্ড",
    "Voice History": "ভয়েস হিস্টোরি",
    "Settings": "সেটিংস",
    "How to use": "কীভাবে ব্যবহার করবেন",
    "More Apps": "আরও অ্যাপ",
    "Developer": "ডেভেলপার",
    "AI voice typing · by RUHUL": "এআই ভয়েস টাইপিং · RUHUL",
    "Speak in Bangla or English. SHUNCHi types it wherever your cursor is.":
        "বাংলা বা ইংরেজিতে বলুন। আপনার কার্সর যেখানে আছে, SHUNCHi সেখানেই লিখে দেবে।",
    "Open Settings": "সেটিংস খুলুন",
    "Update now": "এখনই আপডেট করুন",
    "Bangla Dictation": "বাংলা ভয়েস টাইপিং",
    "English Dictation": "ইংলিশ ভয়েস টাইপিং",
    "Speak in Bangla (English words are fine too)": "বাংলায় বলুন (মাঝে ইংরেজি শব্দ থাকলেও সমস্যা নেই)",
    "Speak in English": "ইংরেজিতে বলুন",
    "Try it here": "এখানেই চেষ্টা করে দেখুন",
    "Click inside the box, press a shortcut and speak. Pause when you finish; the text appears here.":
        "বক্সের ভেতরে ক্লিক করে শর্টকাট চাপুন, তারপর কথা বলুন। বলা শেষ হলে একটু থামুন, লেখাটি এখানে বসে যাবে।",
    "Your dictated text will be typed here…": "আপনার বলা কথা এখানে লেখা হবে…",
    "Before you start": "শুরু করার আগে",
    "Add your Gemini API key in Settings to start voice typing.": "ভয়েস টাইপিং শুরু করতে সেটিংসে গিয়ে আপনার Gemini API key দিন।",
    "Add your Gemini API key in Settings first.": "আগে সেটিংসে গিয়ে আপনার Gemini API key দিন।",
    "Ready · press Win + Left Ctrl (Bangla) or Win + Left Shift (English).":
        "তৈরি · বাংলার জন্য Win + Left Ctrl, ইংরেজির জন্য Win + Left Shift চাপুন।",
    "Testing your Gemini connection…": "Gemini-র সাথে সংযোগ যাচাই করা হচ্ছে…",
    "Connected · voice typing is ready.": "সংযুক্ত হয়েছে · এখন ভয়েস টাইপিং ব্যবহার করতে পারবেন।",
    "Connected · voice typing is working.": "সংযুক্ত · ভয়েস টাইপিং ঠিকমতো চলছে।",
    "Windows Credential Manager is unavailable. Check your Windows account permissions.":
        "Windows Credential Manager পাওয়া যাচ্ছে না। আপনার Windows অ্যাকাউন্টের পারমিশন দেখে নিন।",
    READY_TEXT_KEY: "তৈরি · Win + Left Ctrl = বাংলা · Win + Left Shift = ইংরেজি",
    "Took too long. Please try again.": "অনেক সময় লেগে যাচ্ছে। আবার চেষ্টা করুন।",
    "Update cancelled.": "আপডেট বাতিল করা হয়েছে।",
    "Installer started. SHUNCHi will close so the update can finish.": "ইনস্টলার চালু হয়েছে। আপডেট শেষ করতে SHUNCHi এখন বন্ধ হবে।",
    "No microphone detected · check Windows microphone permissions.": "কোনো মাইক্রোফোন পাওয়া যায়নি · Windows-এর মাইক্রোফোন পারমিশন দেখে নিন।",
}
NOTES_EN = (
    "<b>A Gemini API key is required.</b> Without your own free key SHUNCHi cannot type for you. Add it once in Settings.",
    "Your writing runs on the <b>free limit of your own Gemini key</b>, so everyday messages and normal work "
    "should go through on the free version.",
    "If you need a much higher limit, a <b>Pro subscription with extended limits</b> is planned for the future.",
)
NOTES_BN = (
    "<b>Gemini API key লাগবে।</b> নিজের ফ্রি key ছাড়া SHUNCHi লিখে দিতে পারবে না। সেটিংসে মাত্র একবার দিলেই হবে।",
    "আপনার লেখা চলবে <b>আপনার নিজের Gemini key-এর ফ্রি লিমিটে</b>। তাই সাধারণ মেসেজ আর রোজকার কাজ ফ্রিতেই হয়ে যাওয়ার কথা।",
    "আরও বেশি লিমিট লাগলে ভবিষ্যতে <b>বাড়তি লিমিটসহ Pro সাবস্ক্রিপশন</b> আনার পরিকল্পনা আছে।",
)


def T(text):
    """Translate a known interface text for the Bangla dashboard; anything unknown stays as it is."""
    text = str(text)
    if not UI_BN:
        return text
    if text in BN:
        return BN[text]
    m = re.fullmatch(r"Typed (\d+) characters\.", text)
    if m:
        return f"{m.group(1)}টি অক্ষর লেখা হয়েছে।"
    if text.startswith("Microphone active · "):
        return "মাইক্রোফোন চালু · " + text[len("Microphone active · "):]
    return text


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
    videos_ready = Signal(object)
    idea_result = Signal(bool, str)
    account_done = Signal(str, bool, object)
    update_progress = Signal(int)
    update_downloaded = Signal(bool, str)


class MicrophoneScanner(threading.Thread):
    """Enumerate PortAudio devices in the background; never block app start-up."""
    def __init__(self, signals, refresh=False):
        super().__init__(daemon=True, name="SHUNCHi-Microphone-Scan")
        self.signals = signals
        self.refresh = refresh

    def run(self):
        try:
            if self.refresh:
                try:        # PortAudio caches its device list; reload it (e.g. when Windows audio started late)
                    sd._terminate()
                    sd._initialize()
                except Exception:
                    logging.exception("PortAudio refresh failed")
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


class VideoLoader(threading.Thread):
    """Reads the video list that the website already shows (YouTube ids) and fetches the small thumbnails. Never raises into the UI."""
    URL = WEBSITE_URL + "/data/videos.json"

    def __init__(self, signals):
        super().__init__(daemon=True, name="SHUNCHi-Videos")
        self.signals = signals

    def run(self):
        videos = []
        try:
            request = urllib.request.Request(self.URL + "?t=" + str(int(time.time() // 300)),
                                             headers={"User-Agent": f"SHUNCHi/{APP_VERSION}", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=8) as response:
                raw = json.loads(response.read(131072).decode("utf-8"))
            for item in (raw if isinstance(raw, list) else [])[:6]:
                vid = str(item.get("id", ""))
                if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                    continue
                thumb = b""
                try:
                    with urllib.request.urlopen(urllib.request.Request(
                            f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg", headers={"User-Agent": f"SHUNCHi/{APP_VERSION}"}), timeout=6) as r:
                        thumb = r.read(400000)
                except Exception:
                    thumb = b""
                videos.append({"id": vid, "title_en": str(item.get("title_en") or item.get("title_bn") or "")[:160],
                               "title_bn": str(item.get("title_bn") or item.get("title_en") or "")[:160], "thumb": thumb})
        except Exception as exc:
            logging.info("Videos not available: %s", exc)
        self.signals.videos_ready.emit(videos)


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


# ---------------------------------------------------------------------------------------------- account (optional)
FB_CONFIG_URL = WEBSITE_URL + "/data/firebase-config.json"
IDT_URL = "https://identitytoolkit.googleapis.com/v1"
STS_URL = "https://securetoken.googleapis.com/v1/token"
FS_URL = "https://firestore.googleapis.com/v1"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
ACCOUNT_PAGE_URL = WEBSITE_URL + "/account/index.html"

ACCOUNT_ERRORS = {
    "EMAIL_EXISTS": "This email already has an account. Log in instead.",
    "INVALID_LOGIN_CREDENTIALS": "Wrong email or password.", "INVALID_PASSWORD": "Wrong email or password.",
    "EMAIL_NOT_FOUND": "No account with this email. Create one.", "INVALID_EMAIL": "Enter a valid email.",
    "WEAK_PASSWORD": "Password must be at least 6 characters.", "MISSING_PASSWORD": "Enter your password.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many tries. Wait a little and try again.",
    "USER_DISABLED": "This account is disabled.", "OPERATION_NOT_ALLOWED": "This sign-in method is not turned on yet.",
}


class AccountError(Exception):
    pass


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def fs_value(value):
    if isinstance(value, datetime):
        return {"timestampValue": value.strftime("%Y-%m-%dT%H:%M:%SZ")}
    return {"stringValue": str(value)}


def fs_fields(doc):
    out = {}
    for key, value in (doc or {}).get("fields", {}).items():
        out[key] = value.get("stringValue", value.get("timestampValue", ""))
    return out


WEB_LOGIN_DONE_HTML = """<!DOCTYPE html><html lang="bn"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>SHUNCHi</title>
<style>body{font-family:'Segoe UI','Nirmala UI',sans-serif;background:#F6F8FC;color:#0F172A;display:grid;place-items:center;min-height:100vh;margin:0}
.b{background:#fff;border:1px solid #E3E9F2;border-radius:20px;padding:36px 32px;max-width:420px;text-align:center;box-shadow:0 18px 50px rgba(15,23,42,.08)}
.i{width:64px;height:64px;border-radius:50%;background:#ECFDF3;color:#15803D;font-size:34px;display:grid;place-items:center;margin:0 auto 14px}
h1{font-size:22px;margin:0 0 8px}p{color:#64748B;margin:4px 0;line-height:1.55}.e{color:#B91C1C}</style></head><body><div class="b">
<div class="i" id="i">&#8987;</div><h1 id="h">Please wait&hellip;</h1><p id="p"></p></div>
<script>
(function(){
var h=new URLSearchParams(location.hash.slice(1)),s=h.get("state"),r=h.get("rt");
try{history.replaceState(null,"","/cb")}catch(e){}
function ok(){document.getElementById("i").innerHTML="&#10003;";document.getElementById("h").textContent="Login successful / লগইন সফল হয়েছে";
document.getElementById("p").innerHTML="You can close this tab and go back to SHUNCHi.<br>এই ট্যাব বন্ধ করে SHUNCHi অ্যাপে ফিরে যান।"}
function bad(){var i=document.getElementById("i");i.innerHTML="!";i.style.background="#FEF2F2";i.className="i e";i.style.color="#B91C1C";document.getElementById("h").textContent="Login failed / লগইন হয়নি";
document.getElementById("p").innerHTML="Go back to SHUNCHi and try again.<br>অ্যাপে ফিরে গিয়ে আবার চেষ্টা করুন।"}
if(!s||!r){bad();return}
fetch("/token",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({state:s,rt:r})}).then(function(x){x.ok?ok():bad()},bad);
})();
</script></body></html>"""


class AccountService:
    """Optional account (Firebase). Nothing in the app needs it. Uses the public REST endpoints, so no extra package."""

    def __init__(self, settings):
        self.settings = settings
        self._cfg = None
        self._id_token = ""
        self._exp = 0.0
        self._lock = threading.RLock()
        self.profile_cache = {}

    # --- state
    @property
    def logged_in(self):
        return bool(self.settings.value("acct/refresh", "", type=str))

    @property
    def name(self):
        return self.settings.value("acct/name", "", type=str)

    @property
    def email(self):
        return self.settings.value("acct/email", "", type=str)

    @property
    def uid(self):
        return self.settings.value("acct/uid", "", type=str)

    # --- http
    def _http(self, url, data=None, method=None, headers=None, form=False, timeout=20):
        body = None
        hdrs = {"User-Agent": f"SHUNCHi/{APP_VERSION}"}
        if data is not None:
            if form:
                body = urllib.parse.urlencode(data).encode("utf-8")
                hdrs["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                body = json.dumps(data).encode("utf-8")
                hdrs["Content-Type"] = "application/json"
        hdrs.update(headers or {})
        if "googleapis.com" in url:
            hdrs.setdefault("Referer", WEBSITE_URL + "/")   # keeps working if the Firebase key is limited to shunchiai.com
        req = urllib.request.Request(url, data=body, method=method or ("POST" if body is not None else "GET"), headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(2_000_000).decode("utf-8") or "{}"
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            try:
                info = json.loads(exc.read(20000).decode("utf-8"))
            except Exception:
                info = {}
            err = info.get("error", {})
            msg = (err.get("message") if isinstance(err, dict) else str(err)) or ""
            code = msg.split(" ")[0].split(":")[0]
            if exc.code == 403 and "PERMISSION" in str(err):
                raise AccountError("Your account cannot do this (it may be blocked).")
            raise AccountError(ACCOUNT_ERRORS.get(code, "Could not reach the account service. Check your internet and try again."))
        except (urllib.error.URLError, TimeoutError, OSError):
            raise AccountError("No internet connection.")

    def config(self):
        if self._cfg:
            return self._cfg
        try:
            cfg = self._http(FB_CONFIG_URL + "?t=" + str(int(time.time() // 600)))
        except AccountError:
            cfg = {}
        if not cfg.get("apiKey") or not cfg.get("projectId"):
            raise AccountError("Accounts are not turned on yet.")
        self._cfg = cfg
        return cfg

    def _key(self):
        return "?key=" + urllib.parse.quote(self.config()["apiKey"])

    # --- session
    def _store(self, info):
        with self._lock:
            self._id_token = info.get("idToken") or info.get("id_token") or ""
            self._exp = time.time() + int(info.get("expiresIn") or info.get("expires_in") or 3600) - 60
            refresh = info.get("refreshToken") or info.get("refresh_token") or ""
            uid = info.get("localId") or info.get("user_id") or ""
            if refresh:
                self.settings.setValue("acct/refresh", refresh)
            if uid:
                self.settings.setValue("acct/uid", uid)
            if info.get("email"):
                self.settings.setValue("acct/email", info["email"])
            if info.get("displayName") is not None and "displayName" in info:
                self.settings.setValue("acct/name", info.get("displayName") or "")

    def token(self):
        with self._lock:
            if self._id_token and time.time() < self._exp:
                return self._id_token
            refresh = self.settings.value("acct/refresh", "", type=str)
            if not refresh:
                raise AccountError("Please log in.")
            try:
                info = self._http(STS_URL + self._key(), {"grant_type": "refresh_token", "refresh_token": refresh}, form=True)
            except AccountError as exc:
                raise AccountError("Please log in again.") if "reach" in str(exc) else exc
            self._store(info)
            return self._id_token

    def logout(self):
        with self._lock:
            self._id_token = ""
            self._exp = 0.0
            self.profile_cache = {}
            for key in ("acct/refresh", "acct/uid", "acct/email", "acct/name"):
                self.settings.remove(key)

    # --- sign in / up
    def signup(self, name, email, password):
        info = self._http(f"{IDT_URL}/accounts:signUp" + self._key(), {"email": email, "password": password, "returnSecureToken": True})
        self._store(info)
        self._http(f"{IDT_URL}/accounts:update" + self._key(), {"idToken": self._id_token, "displayName": name, "returnSecureToken": False})
        self.settings.setValue("acct/name", name)
        self._write_user({"name": name, "email": email, "phone": "", "address": "", "createdAt": datetime.utcnow()})
        try:
            self._http(f"{IDT_URL}/accounts:sendOobCode" + self._key(), {"requestType": "VERIFY_EMAIL", "idToken": self._id_token})
        except AccountError:
            pass
        return {"name": name, "email": email}

    def login(self, email, password):
        info = self._http(f"{IDT_URL}/accounts:signInWithPassword" + self._key(), {"email": email, "password": password, "returnSecureToken": True})
        self._store(info)
        self._touch()
        return {"name": self.name, "email": self.email}

    def reset_password(self, email):
        self._http(f"{IDT_URL}/accounts:sendOobCode" + self._key(), {"requestType": "PASSWORD_RESET", "email": email})
        return True

    def web_login(self, cancel=None, timeout=300):
        """Login in the browser. The app opens shunchiai.com/app-login, the website signs the user in (Google or email) and
        hands the session back through a one-shot page on 127.0.0.1 (this computer only). Nothing is typed inside the app."""
        import http.server
        import webbrowser
        import hmac
        self.config()   # a clear error here if accounts are switched off
        state = _b64url(os.urandom(18))
        got = {}
        page = WEB_LOGIN_DONE_HTML.encode("utf-8")

        class Handler(http.server.BaseHTTPRequestHandler):
            def _send(self, code, body, ctype="text/html; charset=utf-8"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if urllib.parse.urlparse(self.path).path == "/cb":
                    self._send(200, page)
                else:
                    self._send(404, b"", "text/plain")

            def do_POST(self):
                try:
                    size = min(int(self.headers.get("Content-Length") or 0), 8000)
                    data = json.loads(self.rfile.read(size).decode("utf-8") or "{}")
                except Exception:
                    return self._send(400, b"{}", "application/json")
                rt = str(data.get("rt") or "")
                if urllib.parse.urlparse(self.path).path == "/token" and rt and not got and hmac.compare_digest(str(data.get("state") or ""), state):
                    got["rt"] = rt
                    return self._send(200, b"{}", "application/json")
                self._send(403, b"{}", "application/json")

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        server.timeout = 1
        url = f"{WEBSITE_URL}/app-login/?" + urllib.parse.urlencode({"port": server.server_address[1], "state": state, "lang": "bn" if UI_BN else "en"})
        try:
            if not webbrowser.open(url):
                raise AccountError(f"Could not open your browser. Open {WEBSITE_LABEL} in a browser and log in there.")
            end = time.time() + timeout
            while not got and time.time() < end and not (cancel is not None and cancel.is_set()):
                server.handle_request()
        finally:
            server.server_close()
        if cancel is not None and cancel.is_set():
            raise AccountError("Login cancelled.")
        if not got:
            raise AccountError("Login timed out. Try again.")
        info = self._http(STS_URL + self._key(), {"grant_type": "refresh_token", "refresh_token": got["rt"]}, form=True)
        self._store(info)
        look = self._http(f"{IDT_URL}/accounts:lookup" + self._key(), {"idToken": self._id_token})
        user = (look.get("users") or [{}])[0]
        self.settings.setValue("acct/email", user.get("email", ""))
        self.settings.setValue("acct/name", user.get("displayName") or "")
        if not self._read_user():
            self._write_user({"name": self.name, "email": self.email, "phone": "", "address": "", "createdAt": datetime.utcnow()})
        self._touch()
        return {"name": self.name, "email": self.email}

    def google_login(self, open_browser=None, timeout=180):
        """Google sign-in for a desktop app: browser + a one-shot local page (loopback), then Firebase signInWithIdp."""
        import http.server
        import webbrowser
        cfg = self.config()
        client_id = cfg.get("googleClientId", "")
        if not client_id:
            raise AccountError("Google sign-in is not set up for the app yet. Use email, or sign in with Google on the website.")
        verifier = _b64url(os.urandom(32))
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        state = _b64url(os.urandom(12))
        got = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if "code" in query or "error" in query:
                    got.update({k: v[0] for k, v in query.items()})
                    page = ("<html><body style='font-family:sans-serif;text-align:center;margin-top:15vh'>"
                            "<h2>SHUNCHi</h2><p>You are signed in. You can close this tab and go back to the app.</p></body></html>")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(page.encode("utf-8"))
                else:
                    self.send_response(204)
                    self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        server.timeout = 1
        redirect = f"http://127.0.0.1:{server.server_address[1]}"
        url = GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": "openid email profile",
            "code_challenge": challenge, "code_challenge_method": "S256", "state": state, "prompt": "select_account"})
        try:
            (open_browser or webbrowser.open)(url)
            end = time.time() + timeout
            while not got and time.time() < end:
                server.handle_request()
        finally:
            server.server_close()
        if not got:
            raise AccountError("Google sign-in timed out. Try again.")
        if got.get("error") or got.get("state") != state or not got.get("code"):
            raise AccountError("Google sign-in was cancelled.")
        form = {"code": got["code"], "client_id": client_id, "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier}
        if cfg.get("googleClientSecret"):
            form["client_secret"] = cfg["googleClientSecret"]
        tok = self._http(GOOGLE_TOKEN_URL, form, form=True)
        id_token = tok.get("id_token")
        if not id_token:
            raise AccountError("Google sign-in failed. Try again.")
        info = self._http(f"{IDT_URL}/accounts:signInWithIdp" + self._key(), {
            "postBody": "id_token=" + urllib.parse.quote(id_token) + "&providerId=google.com", "requestUri": "http://localhost",
            "returnSecureToken": True, "returnIdpSignInToken": True})
        self._store(info)
        if not self.name and info.get("fullName"):
            self.settings.setValue("acct/name", info["fullName"])
        if not self._read_user():
            self._write_user({"name": self.name, "email": self.email, "phone": "", "address": "", "createdAt": datetime.utcnow()})
        self._touch()
        return {"name": self.name, "email": self.email}

    # --- firestore
    def _doc_url(self, path):
        return f"{FS_URL}/projects/{urllib.parse.quote(self.config()['projectId'])}/databases/(default)/documents/{path}"

    def _auth(self):
        return {"Authorization": "Bearer " + self.token()}

    def _write_user(self, fields):
        mask = "&".join("updateMask.fieldPaths=" + urllib.parse.quote(k) for k in fields)
        body = {"fields": {k: fs_value(v) for k, v in fields.items()}}
        return self._http(self._doc_url(f"users/{self.uid}") + "?" + mask, body, method="PATCH", headers=self._auth())

    def _read_user(self):
        try:
            return fs_fields(self._http(self._doc_url(f"users/{self.uid}"), headers=self._auth()))
        except AccountError:
            return {}

    def _touch(self):
        try:
            self._write_user({"lastActive": datetime.utcnow(), "email": self.email})
        except AccountError:
            pass

    def profile(self):
        if not getattr(self, "_touched", False):
            self._touched = True
            self._touch()
        data = self._read_user()
        data.setdefault("name", self.name)
        data.setdefault("email", self.email)
        self.profile_cache = data
        return data

    def save_profile(self, name, phone, address):
        self._write_user({"name": name[:60], "phone": phone[:30], "address": address[:160]})
        if name != self.name:
            self._http(f"{IDT_URL}/accounts:update" + self._key(), {"idToken": self.token(), "displayName": name, "returnSecureToken": False})
            self.settings.setValue("acct/name", name)
        return self.profile()

    def add_idea(self, code, title, details):
        fields = {"track": code, "title": title[:120], "details": details[:1200], "type": "App idea", "createdAt": datetime.utcnow()}
        body = {"fields": {k: fs_value(v) for k, v in fields.items()}}
        self._http(self._doc_url(f"users/{self.uid}/ideas/{code}"), body, method="PATCH", headers=self._auth())
        return True

    def list_ideas(self):
        data = self._http(self._doc_url(f"users/{self.uid}/ideas") + "?pageSize=100", headers=self._auth())
        ideas = [fs_fields(d) for d in data.get("documents", [])]
        ideas.sort(key=lambda i: i.get("createdAt", ""), reverse=True)
        try:
            status = self._http(WEBSITE_URL + "/data/ideas-status.json?t=" + str(int(time.time())))
        except AccountError:
            status = {}
        for idea in ideas:
            rec = status.get(hashlib.sha256(idea.get("track", "").encode("utf-8")).hexdigest())
            idea["status"] = (rec or {}).get("s", "pending")
            idea["feedback"] = (rec or {}).get("f", "")
            idea["steps"] = [(e.get("s", ""), e.get("t", "")) for e in (rec or {}).get("h", [])]
        return ideas


class AccountTask(threading.Thread):
    """Runs one account call off the UI thread and reports back through a signal."""

    def __init__(self, signals, action, func, *args):
        super().__init__(daemon=True)
        self.signals, self.action, self.func, self.args = signals, action, func, args

    def run(self):
        try:
            result = self.func(*self.args)
            self.signals.account_done.emit(self.action, True, result)
        except AccountError as exc:
            self.signals.account_done.emit(self.action, False, str(exc))
        except Exception as exc:
            logging.info("Account task %s failed: %s", self.action, exc)
            self.signals.account_done.emit(self.action, False, "Something went wrong. Try again.")


def _b64u_int(text):
    text = str(text).replace("-", "+").replace("_", "/")
    return int.from_bytes(base64.b64decode(text + "=" * (-len(text) % 4)), "big")


def _mgf1(seed, length):
    out, counter = b"", 0
    while len(out) < length:
        out += hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        counter += 1
    return out[:length]


def rsa_oaep_encrypt(jwk, data):
    """RSA-OAEP (SHA-256) with the developer's PUBLIC key, in 190-byte pieces. Same format as the website's
    browser code, so the admin panel can open both. Returns a list of base64 strings."""
    n, e = _b64u_int(jwk["n"]), _b64u_int(jwk["e"])
    k = (n.bit_length() + 7) // 8
    h_len = 32
    room = k - 2 * h_len - 2
    pieces = []
    for start in range(0, len(data), room):
        m = data[start:start + room]
        l_hash = hashlib.sha256(b"").digest()
        db = l_hash + b"\x00" * (room - len(m)) + b"\x01" + m
        seed = os.urandom(h_len)
        masked_db = bytes(a ^ b for a, b in zip(db, _mgf1(seed, k - h_len - 1)))
        masked_seed = bytes(a ^ b for a, b in zip(seed, _mgf1(masked_db, h_len)))
        em = b"\x00" + masked_seed + masked_db
        pieces.append(base64.b64encode(pow(int.from_bytes(em, "big"), e, n).to_bytes(k, "big")).decode("ascii"))
    return pieces


TRACK_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_tracking_code():
    return "SH-" + "".join(TRACK_ALPHABET[b % 32] for b in os.urandom(8))


class IdeaSender(threading.Thread):
    """Sends the 'app or tool idea' form to the developer. Never raises into the UI."""
    def __init__(self, signals, fields):
        super().__init__(daemon=True, name="SHUNCHi-Idea")
        self.signals, self.fields = signals, fields
        self.code = new_tracking_code()

    def _send_github(self):
        """Primary route: one issue in the developer's private idea inbox. The token lives only on the website.
        Name, email, phone and address are encrypted with the developer's public key before they are sent."""
        def get(path):
            with urllib.request.urlopen(urllib.request.Request(
                    WEBSITE_URL + path, headers={"User-Agent": f"SHUNCHi/{APP_VERSION}"}), timeout=12) as r:
                return json.loads(r.read(16384).decode("utf-8") or "{}")
        cfg = get("/data/ideas-config.json")
        repo, token = str(cfg.get("repo", "")), str(cfg.get("token", ""))
        if not repo or not token:
            raise ValueError("idea inbox is not configured")
        try:
            jwk = get("/data/ideas-key.json")
            jwk = jwk if jwk.get("n") and jwk.get("e") else None
        except Exception:
            jwk = None
        f = self.fields
        idea = str(f.get("Idea", "")).strip()
        pii = {k: str(f.get(k, "")) for k in ("Name", "Email", "Phone", "Address")}
        meta = {"Type": "App idea", "Idea": idea, "Details": "", "Language": "-", "Page": "-",
                "Source": f"SHUNCHi app {APP_VERSION}", "Track": self.code}
        if jwk:
            meta["enc"] = rsa_oaep_encrypt(jwk, json.dumps(pii, ensure_ascii=False).encode("utf-8"))
            who = "**Personal details:** encrypted\n"
        else:
            meta.update(pii)
            who = "".join(f"**{k}:** {v}\n" for k, v in pii.items())
        meta_json = json.dumps(meta, ensure_ascii=False).replace(">", "\\u003e")
        body = f"**Tracking:** {self.code}\n**Source:** SHUNCHi app {APP_VERSION}\n{who}\n{idea}\n\n<!--shunchi:{meta_json}-->"
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/issues", method="POST",
            data=json.dumps({"title": f"[{self.code}] " + idea.replace("\n", " ")[:90], "body": body}, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json", "User-Agent": f"SHUNCHi/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status != 201:
                raise ValueError(f"GitHub HTTP {r.status}")

    def run(self):
        try:
            self._send_github()
            self.signals.idea_result.emit(True, f"Thank you! Your idea reached the developer. Tracking number: {self.code}")
            return
        except Exception as exc:
            logging.info("Idea inbox failed, trying the mail form: %s", exc)
        try:
            payload = dict(self.fields)
            payload.update({"Tracking": self.code, "_subject": f"SHUNCHi idea {self.code}: " + str(self.fields.get("Idea", ""))[:80],
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
            self.signals.idea_result.emit(True, f"Thank you! Your idea reached the developer. Tracking number: {self.code}")
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
QMenu { background: white; border: 1px solid @BORDER@; padding: 6px 0; }
QMenu::item { padding: 8px 22px; color: @TEXT@; }
QMenu::item:selected { background: @SOFT@; color: @TEXT@; }
QMenu::separator { height: 1px; background: @BORDER@; margin: 6px 10px; }
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


class _WrapFix(QObject):
    """Word-wrapped labels inside scroll areas sometimes keep a too-small height (text overlaps the next
    block, or is cut off). This gives each one the height its text needs at its current width."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            fit_label(obj)
        return False


_WRAP_FIX = None


def fit_label(label):
    try:
        width = label.width()
        if width > 20:
            height = label.heightForWidth(width)
            if height > 0 and label.minimumHeight() != height:
                label.setMinimumHeight(height)
    except Exception:
        pass


def harden_labels(root):
    """Call after building a page and after its texts change."""
    global _WRAP_FIX
    if _WRAP_FIX is None:
        _WRAP_FIX = _WrapFix()
    for label in root.findChildren(QLabel):
        if label.wordWrap():
            if not label.property("wrapFixed"):
                label.setProperty("wrapFixed", True)
                label.installEventFilter(_WRAP_FIX)
            label.setMinimumHeight(0)
            fit_label(label)


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
        self.animator.setInterval(16)
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
        self.phase += 0.07
        for i in range(self.BARS):
            if self.mode == "processing":
                target = 0.20 + 0.14 * (1 + math.sin(self.phase * 1.5 - i * 0.30))
            else:
                target = self.targets[i]
            self.display[i] += (target - self.display[i]) * 0.30
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))      # opaque: no trails on the see-through popup
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
        self.timer.setInterval(16)
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
        self.smooth += (self.level - self.smooth) * 0.22
        self.level *= 0.94
        self.angle = (self.angle + 5) % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#FFFFFF"))            # opaque: no trails on the see-through popup
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
    when you finish speaking, the polished text is typed where your cursor is.

    Every piece of text is painted by this one widget (no child labels), and the animated children paint an
    opaque background. On a see-through Windows window that is what keeps old pixels from showing through."""
    W, H = 424, 124

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self.W, self.H)
        self._leaving = False
        self.state = "listening"
        self.title, self.lang, self.detail, self.clock = "Listening", "", "", "00:00"
        self.detail_color = C_MUTED
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
        self.orb = MicOrb(self)
        self.wave = WaveformWidget(self)
        self.panel = QRectF(12, 6, self.W - 24, self.H - 22)          # the white card (room around it for the shadow)
        x0, y0 = int(self.panel.left()) + 16, int(self.panel.top()) + 12
        self.orb.move(x0, y0)
        self.wave.setGeometry(x0 + 58, y0 + 3, int(self.panel.width()) - 16 - 16 - 58 - 70, 40)
        self.text_y = y0 + 46 + 10
        self.x0 = x0

    # ---- painting
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.transparent)                        # wipe everything first: no ghosts
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setPen(Qt.NoPen)
        for i in range(9):                                             # soft shadow
            grow = 9 - i
            p.setBrush(QColor(15, 23, 42, 5 + i))
            p.drawRoundedRect(self.panel.adjusted(-grow * 0.7, -grow * 0.4, grow * 0.7, grow * 1.1), 20 + grow * 0.6, 20 + grow * 0.6)
        p.setBrush(QColor("#FFFFFF"))
        p.setPen(QPen(QColor("#E1E8F3"), 1))
        p.drawRoundedRect(self.panel, 20, 20)
        p.setPen(Qt.NoPen)

        # clock chip (right of the first row)
        font = QFont(self.font())
        font.setPixelSize(13)
        font.setBold(True)
        p.setFont(font)
        chip_w = max(58, QFontMetrics(font).horizontalAdvance(self.clock) + 22)
        chip = QRectF(self.panel.right() - 16 - chip_w, self.panel.top() + 12 + 12, chip_w, 22)
        p.setBrush(QColor(C_PRIMARY_SOFT))
        p.drawRoundedRect(chip, 11, 11)
        p.setPen(QColor(C_PRIMARY_DARK))
        p.drawText(chip, Qt.AlignCenter, self.clock)

        # second row: title, language chip, detail
        color = {"listening": C_PRIMARY_DARK, "processing": C_WARN, "done": C_OK, "error": C_ERR}.get(self.state, C_TEXT)
        tf = QFont(self.font())
        tf.setPixelSize(14)
        tf.setBold(True)
        p.setFont(tf)
        p.setPen(QColor(color))
        tm = QFontMetrics(tf)
        x = float(self.x0)
        tw = tm.horizontalAdvance(self.title)
        p.drawText(QRectF(x, self.text_y, tw + 4, 22), Qt.AlignVCenter | Qt.AlignLeft, self.title)
        x += tw + 10
        if self.lang:
            lf = QFont(self.font())
            lf.setPixelSize(11)
            lf.setBold(True)
            lw = QFontMetrics(lf).horizontalAdvance(self.lang) + 20
            lrect = QRectF(x, self.text_y + 2, lw, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C_PRIMARY_SOFT))
            p.drawRoundedRect(lrect, 9, 9)
            p.setFont(lf)
            p.setPen(QColor(C_PRIMARY_DARK))
            p.drawText(lrect, Qt.AlignCenter, self.lang)
            x += lw + 10
        df = QFont(self.font())
        df.setPixelSize(12)
        p.setFont(df)
        p.setPen(QColor(self.detail_color))
        room = self.panel.right() - 16 - x
        text = QFontMetrics(df).elidedText(self.detail, Qt.ElideRight, int(max(40, room)))
        p.drawText(QRectF(x, self.text_y, max(40, room), 22), Qt.AlignVCenter | Qt.AlignLeft, text)

    def _set(self, state=None, title=None, lang=None, detail=None, detail_color=None):
        if state is not None:
            self.state = state
        if title is not None:
            self.title = title
        if lang is not None:
            self.lang = lang
        if detail is not None:
            self.detail = detail
        self.detail_color = detail_color or C_MUTED
        self.update()

    # ---- helpers
    def _tick(self):
        seconds = self.elapsed.elapsed() // 1000
        clock = f"{seconds // 60:02d}:{seconds % 60:02d}"
        if clock != self.clock:
            self.clock = clock
            self.update(QRect(int(self.panel.right()) - 100, int(self.panel.top()) + 16, 100, 30))

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
        self.clock = "00:00"
        self._set("listening", "Listening", "বাংলা" if language == "bn-BD" else "English", "pause when you finish")
        self.elapsed.start()
        self.timer.start()
        self._present()

    def set_level(self, level):
        self.wave.push_value(level)
        self.orb.set_level(level)

    def mark_speech(self):
        pass

    def set_processing(self):
        self.timer.stop()
        self.wave.set_mode("processing")
        self.orb.set_state("processing")
        self._set("processing", "Writing", "", "Typing your text…")

    def finish(self):
        self.timer.stop()
        self.wave.set_mode("idle")
        self.orb.set_state("done")
        self._set("done", "Done", "", "Inserted at your cursor")
        self.hide_timer.start(450)

    def show_error(self, message):
        self.timer.stop()
        self.wave.set_mode("idle")
        self.orb.set_state("error")
        self._set("error", "Notice", "", str(message)[:80], C_ERR)
        self.setToolTip(str(message))
        self._present()
        self.hide_timer.start(3800)


# ----------------------------------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------------------------------
class ClickFrame(QFrame):
    """A frame that behaves like a button (used for the channel rows and the video cards)."""
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


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

    def __init__(self, open_settings, on_language=None, on_account=None):
        super().__init__()
        self.on_account = on_account
        self._acct = {"in": False}
        self._api = ("missing", "Add your Gemini API key in Settings to start voice typing.")
        self._act = ""
        self._upd = None
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 20)
        root.setSpacing(14)
        head = QHBoxLayout()
        head.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        self.title_lbl = QLabel("Dashboard")
        self.title_lbl.setObjectName("pageTitle")
        self.sub_lbl = QLabel("")
        self.sub_lbl.setObjectName("pageSubtitle")
        self.sub_lbl.setWordWrap(True)
        titles.addWidget(self.title_lbl)
        titles.addWidget(self.sub_lbl)
        head.addLayout(titles, 1)
        self.lang_switch = SegmentedControl([("EN", False), ("বাংলা", True)])
        self.lang_switch.set_value(UI_BN)
        if on_language is not None:
            self.lang_switch.valueChanged.connect(on_language)
        head.addWidget(self.lang_switch, 0, Qt.AlignTop)
        self.acct_chip = QPushButton("")
        self.acct_chip.setObjectName("chip")
        self.acct_chip.setCursor(Qt.PointingHandCursor)
        self.acct_chip.setIconSize(QSize(16, 16))
        self.acct_chip.clicked.connect(self._account_clicked)
        head.addWidget(self.acct_chip, 0, Qt.AlignTop)
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
        self.card_bn = self._shortcut_card("Win", "Left Ctrl")
        self.card_en = self._shortcut_card("Win", "Left Shift")
        row.addWidget(self.card_bn[0])
        row.addWidget(self.card_en[0])
        root.addLayout(row)

        card, layout = make_card((20, 16, 20, 18), 8)
        self.try_title = QLabel("Try it here")
        self.try_title.setObjectName("cardTitle")
        self.try_hint = QLabel("")
        self.try_hint.setObjectName("cardText")
        self.try_hint.setWordWrap(True)
        self.practice = QPlainTextEdit()
        self.practice.setMinimumHeight(96)
        self.practice.setMaximumHeight(140)
        layout.addWidget(self.try_title)
        layout.addWidget(self.try_hint)
        layout.addWidget(self.practice)
        root.addWidget(card)

        # "Before you start" is the one thing every new user must read, so it is red.
        self.notes = QFrame()
        self.notes.setObjectName("notes")
        self.notes.setStyleSheet(
            f"QFrame#notes{{background:{C_ERR_SOFT};border:1px solid #F3B8B8;border-radius:14px;}}"
            "QFrame#notes QLabel{background:transparent;border:0;}")
        notes_layout = QVBoxLayout(self.notes)
        notes_layout.setContentsMargins(20, 16, 20, 16)
        notes_layout.setSpacing(8)
        self.notes_title = QLabel("Before you start")
        self.notes_title.setStyleSheet(f"font-size:15px;font-weight:700;color:{C_ERR};")
        notes_layout.addWidget(self.notes_title)
        self.note_lines = []
        for _ in NOTES_EN:
            line = QLabel("")
            line.setWordWrap(True)
            line.setTextFormat(Qt.RichText)
            line.setStyleSheet("font-size:13px;color:#7F1D1D;")
            notes_layout.addWidget(line)
            self.note_lines.append(line)
        root.addWidget(self.notes)

        self.activity = QLabel("")
        self.activity.setObjectName("muted")
        self.activity.setWordWrap(True)
        root.addWidget(self.activity)
        root.addStretch()
        self.retranslate()

    def _shortcut_card(self, key_a, key_b):
        card, layout = make_card((20, 16, 20, 16), 10)
        t = QLabel("")
        t.setObjectName("cardTitle")
        caps = QHBoxLayout()
        caps.setSpacing(8)
        caps.addWidget(key_cap(key_a))
        plus = QLabel("+")
        plus.setStyleSheet(f"color:{C_FAINT};font-size:14px;font-weight:700;")
        caps.addWidget(plus)
        caps.addWidget(key_cap(key_b))
        caps.addStretch()
        h = QLabel("")
        h.setObjectName("cardText")
        h.setWordWrap(True)
        layout.addWidget(t)
        layout.addLayout(caps)
        layout.addWidget(h)
        return card, t, h

    def retranslate(self):
        """Re-writes every dashboard text in the chosen language."""
        self.title_lbl.setText(T("Dashboard"))
        self.sub_lbl.setText(T("Speak in Bangla or English. SHUNCHi types it wherever your cursor is."))
        self.banner_button.setText(T("Open Settings"))
        self.update_button.setText(T("Update now"))
        self.card_bn[1].setText(T("Bangla Dictation"))
        self.card_bn[2].setText(T("Speak in Bangla (English words are fine too)"))
        self.card_en[1].setText(T("English Dictation"))
        self.card_en[2].setText(T("Speak in English"))
        self.try_title.setText(T("Try it here"))
        self.try_hint.setText(T("Click inside the box, press a shortcut and speak. Pause when you finish; the text appears here."))
        self.practice.setPlaceholderText(T("Your dictated text will be typed here…"))
        self.notes_title.setText(T("Before you start"))
        for line, text in zip(self.note_lines, NOTES_BN if UI_BN else NOTES_EN):
            line.setText("•  " + text)
        self.set_api_state(*self._api)
        self.set_activity(self._act)
        if self._upd:
            self.show_update(*self._upd)
        self.lang_switch.set_value(UI_BN)
        self._paint_account()
        harden_labels(self)

    # ---- account corner (top right): Log in / Sign up, or the name with the profile menu
    def set_account(self, info):
        """info: {"in": bool, "name", "email", "phone", "address"}; called by the main window whenever the account changes."""
        self._acct = dict(info or {"in": False})
        self._paint_account()

    def _paint_account(self):
        try:
            a = self._acct
            try:
                self.acct_chip.setIcon(make_icon("user", C_PRIMARY_DARK, 16))
            except Exception:
                pass
            if a.get("in"):
                label = (a.get("name") or a.get("email") or "").strip() or T("Your profile")
                if len(label) > 18:
                    label = label[:17] + "…"
                self.acct_chip.setText(f" {label}  ▾")
                self.acct_chip.setToolTip(T("Account menu"))
            else:
                self.acct_chip.setText(" " + T("Log in / Sign up"))
                self.acct_chip.setToolTip("")
        except Exception:
            logging.exception("account chip")

    def _account_clicked(self):
        try:
            if not self._acct.get("in"):
                if self.on_account:
                    self.on_account("page")
                return
            self._show_account_menu()
        except Exception:
            logging.exception("account menu")

    def _show_account_menu(self):
        a = self._acct
        menu = QMenu(self)
        name = (a.get("name") or a.get("email") or "").strip()
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(16, 12, 20, 8)
        hl.setSpacing(12)
        avatar = QLabel(AccountPage._initials(name or "?"))
        avatar.setFixedSize(40, 40)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(f"background:{C_PRIMARY};color:white;border-radius:20px;font-size:14px;font-weight:700;")
        col = QVBoxLayout()
        col.setSpacing(1)
        n = QLabel(html_escape(name))
        n.setStyleSheet(f"font-size:14px;font-weight:700;color:{C_TEXT};")
        m = QLabel(html_escape(a.get("email", "")))
        m.setStyleSheet(f"font-size:12px;color:{C_MUTED};")
        col.addWidget(n)
        col.addWidget(m)
        hl.addWidget(avatar)
        hl.addLayout(col)
        wa = QWidgetAction(menu)
        wa.setDefaultWidget(head)
        menu.addAction(wa)
        menu.addSeparator()
        rows = QWidget()
        rl = QVBoxLayout(rows)
        rl.setContentsMargins(16, 4, 20, 4)
        rl.setSpacing(6)
        for title, key in (("Phone", "phone"), ("Address", "address")):
            val = (a.get(key) or "").strip()
            if len(val) > 46:
                val = val[:45] + "…"
            line = QLabel(f"<span style='color:{C_MUTED};font-size:11px;'>{html_escape(T(title))}</span><br>"
                          f"<span style='color:{C_TEXT if val else C_FAINT};font-size:13px;'>{html_escape(val or T('Not added'))}</span>")
            line.setTextFormat(Qt.RichText)
            rl.addWidget(line)
        wr = QWidgetAction(menu)
        wr.setDefaultWidget(rows)
        menu.addAction(wr)
        menu.addSeparator()
        act_open = menu.addAction(T("Open my profile"))
        act_out = menu.addAction(T("Log out"))
        act_open.triggered.connect(lambda: self.on_account and self.on_account("page"))
        act_out.triggered.connect(lambda: self.on_account and self.on_account("logout"))
        menu.ensurePolished()
        width = max(menu.sizeHint().width(), 260)
        menu.setMinimumWidth(width)
        pos = self.acct_chip.mapToGlobal(QPoint(self.acct_chip.width() - width, self.acct_chip.height() + 6))
        menu.exec(pos)

    def set_api_state(self, state, text):
        self._api = (state, text)
        color, bg, border = self.BANNER_STYLES.get(state, self.BANNER_STYLES["pending"])
        self.banner.setObjectName("banner")
        self.banner.setStyleSheet(f"QFrame#banner{{background:{bg};border:1px solid {border};border-radius:12px;}}")
        self.banner_dot.setStyleSheet(f"color:{color};font-size:12px;")
        self.banner_text.setStyleSheet(f"color:{color};font-size:13px;font-weight:600;")
        self.banner_text.setText(T(text))
        self.banner_text.setMinimumHeight(0)
        QTimer.singleShot(0, lambda: fit_label(self.banner_text))
        self.banner_button.setVisible(state != "ok")

    def set_activity(self, text):
        self._act = text
        self.activity.setText(T(text))
        self.activity.setMinimumHeight(0)
        QTimer.singleShot(0, lambda: fit_label(self.activity))

    def show_update(self, version, forced=False):
        self._upd = (version, forced)
        if UI_BN:
            self.update_text.setText(
                f"SHUNCHi {version} আপডেট করা জরুরি। ভয়েস টাইপিং চালিয়ে যেতে এখনই আপডেট করুন।" if forced
                else f"SHUNCHi {version} এসে গেছে। নতুন ফিচার ও উন্নতি পেতে আপডেট করুন।")
        elif forced:
            self.update_text.setText(f"SHUNCHi {version} is required. Please update to keep using voice typing.")
        else:
            self.update_text.setText(f"SHUNCHi {version} is available. Update to get the latest improvements.")
        self.update_button.setText(T("Update now"))
        self.update_banner.setVisible(True)

    def hide_update(self):
        self._upd = None
        self.update_banner.setVisible(False)


class HistoryPage(QWidget):
    def __init__(self, on_toggle=None):
        super().__init__()
        self.on_toggle = on_toggle
        self._recording = True
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 28, 30, 20)
        root.setSpacing(14)
        self._opened = False        # the table is built the first time the page is opened (faster start-up)
        self.header = page_header("Voice History", "Your recent dictations. They are stored only on this computer.")
        root.addLayout(self.header)

        # on / off switch, right here on the page
        sw_card, sw_box = make_card((20, 14, 20, 14), 6)
        sw_row = QHBoxLayout()
        sw_row.setSpacing(14)
        sw_col = QVBoxLayout()
        sw_col.setSpacing(2)
        self.sw_title = QLabel()
        self.sw_title.setObjectName("cardTitle")
        self.sw_desc = QLabel()
        self.sw_desc.setObjectName("cardText")
        self.sw_desc.setWordWrap(True)
        sw_col.addWidget(self.sw_title)
        sw_col.addWidget(self.sw_desc)
        self.state_pill = QLabel()
        self.state_pill.setAlignment(Qt.AlignCenter)
        self.rec_switch = ToggleSwitch()
        self.rec_switch.setChecked(True)
        self.rec_switch.toggled.connect(self._switch_toggled)
        sw_row.addLayout(sw_col, 1)
        sw_row.addWidget(self.state_pill, 0, Qt.AlignVCenter)
        sw_row.addWidget(self.rec_switch, 0, Qt.AlignVCenter)
        sw_box.addLayout(sw_row)
        root.addWidget(sw_card)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.search = QLineEdit()
        self.search.textChanged.connect(self.refresh)
        self.copy_button = QPushButton()
        self.copy_button.setObjectName("secondary")
        self.copy_button.clicked.connect(self.copy_selected)
        self.clear_button = QPushButton()
        self.clear_button.setObjectName("danger")
        self.clear_button.clicked.connect(self.clear_all)
        controls.addWidget(self.search, 1)
        controls.addWidget(self.copy_button)
        controls.addWidget(self.clear_button)
        root.addLayout(controls)

        self.table = QTableWidget(0, 4)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 96)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(56)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setMinimumHeight(220)
        self.table.cellDoubleClicked.connect(lambda *_: self.copy_selected())
        root.addWidget(self.table, 1)

        self.off_note = QLabel()
        self.off_note.setObjectName("muted")
        self.off_note.setWordWrap(True)
        self.off_note.setVisible(False)
        root.addWidget(self.off_note)
        self.empty = QLabel()
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        root.addWidget(self.empty)
        self.retranslate()

    # ---- texts (English / বাংলা)
    def retranslate(self):
        self.header.itemAt(0).widget().setText(T("Voice History"))
        self.header.itemAt(1).widget().setText(T("Your recent dictations. They are stored only on this computer."))
        self.sw_title.setText(T("Save my dictations"))
        self.sw_desc.setText(T("Keep a list of what you dictate on this computer. Turn it off and nothing new is saved."))
        self.search.setPlaceholderText(T("Search your dictations…"))
        self.copy_button.setText(T("Copy"))
        self.clear_button.setText(T("Clear history"))
        self.table.setHorizontalHeaderLabels([T("Time"), T("Language"), T("Text"), ""])
        self.off_note.setText(T("History is off, so new dictations are not saved. Turn the switch above on to save them again."))
        self.empty.setText(T("No dictations yet. Press a shortcut and speak to get started."))
        self._paint_state()
        if self._opened:
            self.refresh()

    def _paint_state(self):
        on = self.rec_switch.isChecked()
        self.state_pill.setText(T("ON") if on else T("OFF"))
        color, bg = (C_OK, C_OK_SOFT) if on else (C_MUTED, "#EEF2F7")
        self.state_pill.setStyleSheet(f"background:{bg};color:{color};border-radius:11px;padding:3px 12px;font-size:11.5px;font-weight:700;")
        self.off_note.setVisible(not on)

    def _switch_toggled(self, on):
        self._paint_state()
        if self.on_toggle is not None:
            try:
                self.on_toggle(bool(on))
            except Exception:
                logging.exception("History switch failed")

    def set_recording(self, enabled):
        """Called by the main window when the setting changes elsewhere (Settings page, startup)."""
        self.rec_switch.blockSignals(True)
        self.rec_switch.setChecked(bool(enabled))
        self.rec_switch.blockSignals(False)
        self._paint_state()

    def refresh(self, *_):
        self._opened = True
        needle = self.search.text().strip().casefold()
        rows = [r for r in read_history() if not needle or needle in r[4].casefold()][:200]
        self.table.setRowCount(len(rows))
        for row, (_, created, language, _, transcript) in enumerate(rows):
            cells = (created[5:16], "বাংলা" if language == "bn-BD" else "English", transcript.replace("\n", " "))
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, transcript)
                self.table.setItem(row, col, item)
            button = QPushButton(T("Copy"))
            button.setObjectName("secondary")
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(T("Copy this dictation"))
            button.setFixedHeight(32)
            button.setStyleSheet("padding:0 12px;min-height:0;font-size:12px;")
            button.clicked.connect(lambda _=False, b=button, t=transcript: self.copy_text(b, t))
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(6, 0, 10, 0)
            holder_layout.setAlignment(Qt.AlignVCenter)
            holder_layout.addWidget(button)
            self.table.setCellWidget(row, 3, holder)
        self.empty.setVisible(not rows and self.rec_switch.isChecked())
        self.table.setVisible(bool(rows))
        self.table.scrollToTop()
        self.copy_button.setEnabled(bool(rows))
        self.clear_button.setEnabled(bool(rows))

    def copy_text(self, button, text):
        QApplication.clipboard().setText(text)
        button.setText(T("Copied ✓"))
        QTimer.singleShot(1400, lambda: self._reset_button(button))

    @staticmethod
    def _reset_button(button):
        try:
            button.setText(T("Copy"))
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
                self.copy_button.setText(T("Copied ✓"))
                QTimer.singleShot(1400, lambda: self.copy_button.setText(T("Copy")))

    def clear_all(self):
        if QMessageBox.question(self, APP_NAME, T("Delete all saved dictations from this computer?")) == QMessageBox.Yes:
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
        self.account = None
        self.autofill_button = QPushButton("Fill from my account")
        self.autofill_button.setCursor(Qt.PointingHandCursor)
        self.autofill_button.setVisible(False)
        self.autofill_button.clicked.connect(self._autofill)
        self.idea_name = QLineEdit()
        self.idea_name.setPlaceholderText("Your name *")
        self.idea_name.setMaxLength(60)
        self.idea_email = QLineEdit()
        self.idea_email.setPlaceholderText("Email *")
        self.idea_email.setMaxLength(80)
        self.idea_phone = QLineEdit()
        self.idea_phone.setPlaceholderText("Phone *")
        self.idea_phone.setMaxLength(30)
        self.idea_address = QLineEdit()
        self.idea_address.setPlaceholderText("Address *")
        self.idea_address.setMaxLength(160)
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
        for widget in (idea_title, idea_text, self.idea_text, self.autofill_button, self.idea_name, self.idea_email, self.idea_phone, self.idea_address):
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

    def bind_account(self, account):
        self.account = account
        self.refresh_account()

    def retranslate_account(self):
        self.autofill_button.setText(T("Fill from my account"))

    def refresh_account(self):
        self.autofill_button.setVisible(bool(self.account and self.account.logged_in))

    def _autofill(self):
        p = self.account.profile_cache or {}
        self.idea_name.setText(p.get("name") or self.account.name)
        self.idea_email.setText(p.get("email") or self.account.email)
        if p.get("phone"):
            self.idea_phone.setText(p["phone"])
        if p.get("address"):
            self.idea_address.setText(p["address"])

    def _send_idea(self):
        text = self.idea_text.toPlainText().strip()
        if len(text) < 8:
            self.idea_status.setStyleSheet(f"color:{C_ERR};font-size:12px;")
            self.idea_status.setText("Please describe your idea in a few words.")
            return
        name, email = self.idea_name.text().strip(), self.idea_email.text().strip()
        phone, address = self.idea_phone.text().strip(), self.idea_address.text().strip()
        problem = ""
        if not (name and email and phone and address):
            problem = "Name, email, phone and address are required."
        elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            problem = "Please enter a valid email."
        elif not re.fullmatch(r"[0-9+()\-\s]{6,30}", phone):
            problem = "Please enter a valid phone number."
        if problem:
            self.idea_status.setStyleSheet(f"color:{C_ERR};font-size:12px;")
            self.idea_status.setText(problem)
            return
        if self.signals is None:
            return
        self.idea_button.setEnabled(False)
        self.idea_status.setStyleSheet(f"color:{C_MUTED};font-size:12px;")
        self.idea_status.setText("Sending…")
        self._pending_idea = text
        IdeaSender(self.signals, {"Name": name, "Email": email, "Phone": phone, "Address": address,
                                  "Contact": f"{email} · {phone}", "Idea": text[:2000]}).start()

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
            code = re.search(r"SH-[A-Z2-9]{8}", message)
            if code and self.account is not None and self.account.logged_in:
                text = getattr(self, "_pending_idea", "")
                AccountTask(self.signals, "idea_saved", self.account.add_idea, code.group(0), text[:80], text).start()
            if code:
                try:
                    QApplication.clipboard().setText(code.group(0))
                except Exception:
                    pass
                self.idea_status.setText(f"{message}  (copied). Check its status at {WEBSITE_LABEL}/apps/#idea-status")

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


BN.update({
    "Account": "অ্যাকাউন্ট", "Optional account": "অ্যাকাউন্ট (ঐচ্ছিক)",
    "Your account": "আপনার অ্যাকাউন্ট", "Log in": "লগইন", "Sign up": "সাইন আপ", "Log out": "লগআউট",
    "Continue with Google": "Google দিয়ে চালিয়ে যান", "Forgot password?": "পাসওয়ার্ড ভুলে গেছেন?",
    "Name": "নাম", "Email": "ইমেইল", "Password": "পাসওয়ার্ড", "Phone": "ফোন", "Address": "ঠিকানা",
    "Create account": "অ্যাকাউন্ট খুলুন", "Save": "সেভ", "Saved.": "সেভ হয়েছে।", "My details": "আমার তথ্য",
    "My ideas": "আমার আইডিয়াগুলো", "Open my profile on the website": "ওয়েবসাইটে আমার প্রোফাইল দেখুন",
    "Fill from my account": "অ্যাকাউন্টের তথ্য দিয়ে পূরণ করুন",
    "An account is optional. SHUNCHi works fully without it. An account keeps your ideas with their status, your details for quick filling, and your data in the upcoming tools.":
        "অ্যাকাউন্ট না খুললেও চলবে, SHUNCHi এমনিতেই পুরোপুরি কাজ করে। অ্যাকাউন্ট থাকলে পাঠানো আইডিয়া ও তার অবস্থা দেখা যাবে, ফর্মে নাম-ফোন-ঠিকানা এক ক্লিকে বসবে, আর পরে আসা টুলগুলোর ডেটাও আপনার অ্যাকাউন্টেই থাকবে।",
    "Please wait…": "একটু অপেক্ষা করুন…", "Enter your name.": "আপনার নাম লিখুন।", "Enter a valid email.": "সঠিক ইমেইল ঠিকানা দিন।",
    "Password must be at least 6 characters.": "পাসওয়ার্ড অন্তত ৬ অক্ষরের হতে হবে।",
    "Password reset email sent. Check your inbox.": "পাসওয়ার্ড রিসেটের ইমেইল পাঠানো হয়েছে। আপনার ইনবক্স দেখুন।",
    "Type your email first.": "আগে আপনার ইমেইল ঠিকানা লিখুন।", "No ideas yet.": "এখনো কোনো আইডিয়া পাঠাননি।",
    "Your account is blocked, so ideas are not saved to your profile.": "আপনার অ্যাকাউন্টটি ব্লক করা আছে, তাই আইডিয়া প্রোফাইলে সেভ হবে না।",
    "Pending": "অপেক্ষমাণ", "Under analysis": "যাচাই চলছে", "Approved": "অনুমোদিত", "Not taken forward": "আপাতত নেওয়া হচ্ছে না",
    "Wrong email or password.": "ইমেইল বা পাসওয়ার্ড ভুল হয়েছে।", "No internet connection.": "ইন্টারনেট সংযোগ নেই।",
    "This email already has an account. Log in instead.": "এই ইমেইলে আগেই অ্যাকাউন্ট খোলা আছে। লগইন করুন।",
    "No account with this email. Create one.": "এই ইমেইলে কোনো অ্যাকাউন্ট নেই। নতুন অ্যাকাউন্ট খুলুন।",
    "Accounts are not turned on yet.": "অ্যাকাউন্ট ফিচার এখনো চালু হয়নি।",
})

STATUS_LABEL = {"pending": "Pending", "analysis": "Under analysis", "approved": "Approved", "rejected": "Not taken forward"}


BN.update({
    "Log in / Sign up": "লগইন / সাইন আপ", "Open my profile": "আমার প্রোফাইল খুলুন", "Not added": "দেওয়া হয়নি",
    "Your profile": "আপনার প্রোফাইল", "Account menu": "অ্যাকাউন্ট মেনু",
    "Password must be at least 8 characters.": "পাসওয়ার্ড অন্তত ৮ অক্ষরের হতে হবে।",
    "Save my dictations": "আমার বলা কথাগুলো সেভ রাখুন",
    "History is on": "হিস্টোরি চালু হয়েছে", "History is off": "হিস্টোরি বন্ধ হয়েছে",
    "Keep a list of what you dictate on this computer. Turn it off and nothing new is saved.": "আপনি যা বলেন, তার একটি তালিকা এই কম্পিউটারেই জমা থাকবে। বন্ধ রাখলে নতুন কিছু সেভ হবে না।",
    "Your recent dictations. They are stored only on this computer.": "আপনার সাম্প্রতিক ভয়েস টাইপিং। এগুলো শুধু এই কম্পিউটারেই থাকে।",
    "ON": "চালু", "OFF": "বন্ধ", "Search your dictations…": "লেখা খুঁজুন…", "Copy": "কপি", "Copied ✓": "কপি হয়েছে ✓",
    "Clear history": "হিস্টোরি মুছে ফেলুন", "Time": "সময়", "Language": "ভাষা", "Text": "লেখা", "Copy this dictation": "এই লেখাটি কপি করুন",
    "History is off, so new dictations are not saved. Turn the switch above on to save them again.": "হিস্টোরি বন্ধ আছে, তাই নতুন কিছু সেভ হচ্ছে না। আবার সেভ করতে চাইলে উপরের সুইচটি চালু করুন।",
    "No dictations yet. Press a shortcut and speak to get started.": "এখনো কিছু বলা হয়নি। শর্টকাট চেপে কথা বলে দেখুন।",
    "Delete all saved dictations from this computer?": "এই কম্পিউটার থেকে সেভ করা সব লেখা মুছে ফেলবেন?",
    "Five quick steps. After that SHUNCHi works in any app.": "মাত্র পাঁচ ধাপ। এরপর যেকোনো অ্যাপে SHUNCHi দিয়ে লিখতে পারবেন।",
    "Good to know": "কিছু দরকারি কথা", "Video guides": "ভিডিও গাইড", "More videos on shunchiai.com": "আরও ভিডিও shunchiai.com-এ",
    "Watch on YouTube": "YouTube-এ দেখুন", "Loading videos…": "ভিডিও আসছে…",
    "Connect to the internet to see the video guides.": "ভিডিও দেখতে ইন্টারনেটে যুক্ত হোন।",
    "Voice History": "ভয়েস হিস্টোরি", "How to use": "কীভাবে ব্যবহার করবেন",
    "Log in / Sign up in browser": "ব্রাউজারে লগইন / সাইন আপ করুন", "Cancel": "বাতিল",
    "or use email and password here": "অথবা এখানেই ইমেইল ও পাসওয়ার্ড দিয়ে করুন", "Why log in?": "লগইন করলে কী লাভ?",
    "Track every idea you send, with its status and the developer's feedback": "আপনার পাঠানো প্রতিটি আইডিয়ার অবস্থা ও ডেভেলপারের মতামত দেখতে পারবেন",
    "Fill your name, phone and address in one click": "নাম, ফোন ও ঠিকানা এক ক্লিকে ফর্মে বসাতে পারবেন",
    "One account for this app and shunchiai.com": "অ্যাপ ও shunchiai.com, দুই জায়গাতেই একই অ্যাকাউন্ট",
    "Your data for the upcoming tools stays with your account": "পরে আসা টুলগুলোর ডেটা আপনার অ্যাকাউন্টেই জমা থাকবে",
    "Your browser opened. Log in there with Google or email, then come back here.": "ব্রাউজার খুলেছে। সেখানে Google বা ইমেইল দিয়ে লগইন করে এই অ্যাপে ফিরে আসুন।",
    "Login successful. Welcome": "লগইন সফল হয়েছে। স্বাগতম", "Login cancelled.": "লগইন বাতিল করা হয়েছে।",
    "Login timed out. Try again.": "সময় শেষ হয়ে গেছে। আবার চেষ্টা করুন।",
    "Could not open your browser. Open shunchiai.com in a browser and log in there.": "ব্রাউজার খোলা যায়নি। নিজে ব্রাউজারে shunchiai.com খুলে সেখানে লগইন করুন।",
    "Account created. We emailed you a verification link (needed to comment on the website).":
        "অ্যাকাউন্ট খোলা হয়েছে। আপনার ইমেইলে একটি ভেরিফিকেশন লিংক পাঠানো হয়েছে (ওয়েবসাইটে মন্তব্য করতে এটি লাগবে)।",
})


class AccountPage(QWidget):
    """Optional login / sign up and the profile. The app never asks for it."""

    def __init__(self, account, signals, on_change):
        super().__init__()
        self.account, self.signals, self.on_change = account, signals, on_change
        self.mode = "login"
        signals.account_done.connect(self._done)
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 28, 30, 24)
        root.setSpacing(16)
        self.header = page_header("Your account", "Optional. SHUNCHi works fully without it.")
        root.addLayout(self.header)
        self.stack = QStackedWidget()
        root.addWidget(self.stack)
        root.addStretch()

        # --- logged out
        out_card, out = make_card((22, 18, 22, 18), 10)
        self.intro = QLabel()
        self.intro.setObjectName("cardText")
        self.intro.setWordWrap(True)
        self.tabs = SegmentedControl([(T("Log in"), "login"), (T("Sign up"), "signup")])
        self.tabs.valueChanged.connect(self._set_mode)
        self.f_name = QLineEdit()
        self.f_name.setMaxLength(60)
        self.f_email = QLineEdit()
        self.f_email.setMaxLength(80)
        self.f_pass = QLineEdit()
        self.f_pass.setEchoMode(QLineEdit.Password)
        self.f_pass.setMaxLength(100)
        self.go_button = QPushButton()
        self.go_button.setObjectName("primary")
        self.go_button.setCursor(Qt.PointingHandCursor)
        self.go_button.clicked.connect(self._submit)
        self.f_pass.returnPressed.connect(self._submit)
        # Main way in: the browser (Google or email on the website), then straight back here.
        self.google_button = QPushButton()
        self.google_button.setObjectName("primary")
        self.google_button.setMinimumHeight(42)
        self.google_button.setCursor(Qt.PointingHandCursor)
        self.google_button.clicked.connect(self._google)
        self.cancel_button = QPushButton()
        self.cancel_button.setObjectName("link")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.clicked.connect(self._cancel_web)
        self.cancel_button.setVisible(False)
        self.benefits = QLabel()
        self.benefits.setTextFormat(Qt.RichText)
        self.benefits.setWordWrap(True)
        self.benefits.setStyleSheet(f"background:{C_PRIMARY_SOFT};border-radius:12px;padding:12px 14px;font-size:13px;color:{C_TEXT};")
        self.or_label = QLabel()
        self.or_label.setObjectName("muted")
        self.or_label.setAlignment(Qt.AlignCenter)
        self._web_cancel = None
        self._login_kind = ""
        self.forgot = QPushButton()
        self.forgot.setObjectName("link")
        self.forgot.setCursor(Qt.PointingHandCursor)
        self.forgot.clicked.connect(self._forgot)
        self.out_status = QLabel("")
        self.out_status.setWordWrap(True)
        for w in (self.intro, self.benefits, self.google_button, self.cancel_button, self.or_label,
                  self.tabs, self.f_name, self.f_email, self.f_pass):
            out.addWidget(w)
        row = QHBoxLayout()
        row.addWidget(self.go_button)
        row.addStretch()
        out.addLayout(row)
        out.addWidget(self.forgot, 0, Qt.AlignLeft)
        out.addWidget(self.out_status)
        self.stack.addWidget(out_card)

        # --- logged in
        in_wrap = QWidget()
        in_l = QVBoxLayout(in_wrap)
        in_l.setContentsMargins(0, 0, 0, 0)
        in_l.setSpacing(14)
        head_card, head = make_card((22, 18, 22, 18), 6)
        top = QHBoxLayout()
        self.avatar = QLabel("?")
        self.avatar.setFixedSize(52, 52)
        self.avatar.setAlignment(Qt.AlignCenter)
        self.avatar.setStyleSheet(f"background:{C_PRIMARY};color:white;border-radius:26px;font-size:18px;font-weight:700;")
        who = QVBoxLayout()
        self.who_name = QLabel("")
        self.who_name.setObjectName("cardTitle")
        self.who_mail = QLabel("")
        self.who_mail.setObjectName("cardText")
        who.addWidget(self.who_name)
        who.addWidget(self.who_mail)
        self.logout_button = QPushButton()
        self.logout_button.setCursor(Qt.PointingHandCursor)
        self.logout_button.clicked.connect(self._logout)
        top.addWidget(self.avatar)
        top.addSpacing(12)
        top.addLayout(who, 1)
        top.addWidget(self.logout_button)
        head.addLayout(top)
        self.blocked = QLabel("")
        self.blocked.setWordWrap(True)
        self.blocked.setStyleSheet(f"color:{C_ERR};font-size:12px;")
        head.addWidget(self.blocked)
        in_l.addWidget(head_card)

        det_card, det = make_card((22, 18, 22, 18), 8)
        self.det_title = QLabel()
        self.det_title.setObjectName("cardTitle")
        self.p_name = QLineEdit()
        self.p_name.setMaxLength(60)
        self.p_phone = QLineEdit()
        self.p_phone.setMaxLength(30)
        self.p_address = QLineEdit()
        self.p_address.setMaxLength(160)
        self.save_button = QPushButton()
        self.save_button.setObjectName("primary")
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.clicked.connect(self._save)
        self.in_status = QLabel("")
        self.in_status.setWordWrap(True)
        for w in (self.det_title, self.p_name, self.p_phone, self.p_address):
            det.addWidget(w)
        r2 = QHBoxLayout()
        r2.addWidget(self.save_button)
        r2.addWidget(self.in_status, 1)
        det.addLayout(r2)
        in_l.addWidget(det_card)

        ideas_card, ideas = make_card((22, 18, 22, 18), 8)
        self.ideas_title = QLabel()
        self.ideas_title.setObjectName("cardTitle")
        self.ideas_box = QVBoxLayout()
        self.ideas_box.setSpacing(8)
        ideas.addWidget(self.ideas_title)
        ideas.addLayout(self.ideas_box)
        self.web_button = QPushButton()
        self.web_button.setCursor(Qt.PointingHandCursor)
        self.web_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ACCOUNT_PAGE_URL)))
        ideas.addWidget(self.web_button, 0, Qt.AlignLeft)
        in_l.addWidget(ideas_card)
        self.stack.addWidget(in_wrap)
        self.retranslate()
        self.refresh()

    # --- text
    def retranslate(self):
        self.intro.setText(T("An account is optional. SHUNCHi works fully without it. An account keeps your ideas with their status, your details for quick filling, and your data in the upcoming tools."))
        self.tabs.buttons[0].setText(T("Log in"))
        self.tabs.buttons[1].setText(T("Sign up"))
        self.f_name.setPlaceholderText(T("Name") + " *")
        self.f_email.setPlaceholderText(T("Email") + " *")
        self.f_pass.setPlaceholderText(T("Password") + " *")
        self.google_button.setText(T("Log in / Sign up in browser"))
        self.cancel_button.setText(T("Cancel"))
        self.or_label.setText(T("or use email and password here"))
        self.benefits.setText(
            "<b>" + T("Why log in?") + "</b><br>"
            + "✓ " + T("Track every idea you send, with its status and the developer's feedback") + "<br>"
            + "✓ " + T("Fill your name, phone and address in one click") + "<br>"
            + "✓ " + T("One account for this app and shunchiai.com") + "<br>"
            + "✓ " + T("Your data for the upcoming tools stays with your account"))
        self.forgot.setText(T("Forgot password?"))
        self.logout_button.setText(T("Log out"))
        self.det_title.setText(T("My details"))
        self.p_name.setPlaceholderText(T("Name"))
        self.p_phone.setPlaceholderText(T("Phone"))
        self.p_address.setPlaceholderText(T("Address"))
        self.save_button.setText(T("Save"))
        self.ideas_title.setText(T("My ideas"))
        self.web_button.setText(T("Open my profile on the website") + "  ↗")
        self._set_mode(self.mode)

    def _set_mode(self, mode):
        self.mode = mode
        signup = mode == "signup"
        self.f_name.setVisible(signup)
        self.forgot.setVisible(not signup)
        self.go_button.setText(T("Create account") if signup else T("Log in"))
        self.out_status.setText("")

    def _say(self, label, text, ok=None):
        color = C_MUTED if ok is None else (C_OK if ok else C_ERR)
        label.setStyleSheet(f"color:{color};font-size:12px;")
        label.setText(T(text))

    # --- actions
    def _busy(self, on):
        for w in (self.go_button, self.google_button, self.forgot, self.save_button):
            w.setEnabled(not on)

    def _submit(self):
        name, email, pw = self.f_name.text().strip(), self.f_email.text().strip(), self.f_pass.text()
        if self.mode == "signup" and not name:
            return self._say(self.out_status, "Enter your name.", False)
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            return self._say(self.out_status, "Enter a valid email.", False)
        if len(pw) < (8 if self.mode == "signup" else 6):
            return self._say(self.out_status, "Password must be at least 8 characters." if self.mode == "signup"
                             else "Password must be at least 6 characters.", False)
        self._busy(True)
        self._say(self.out_status, "Please wait…")
        if self.mode == "signup":
            AccountTask(self.signals, "login", self.account.signup, name, email, pw).start()
        else:
            AccountTask(self.signals, "login", self.account.login, email, pw).start()

    def _google(self):
        """Opens shunchiai.com/app-login in the browser; the website signs in and hands the session back to this app."""
        self._busy(True)
        self._login_kind = "web"
        self._web_cancel = threading.Event()
        self.cancel_button.setVisible(True)
        self._say(self.out_status, "Your browser opened. Log in there with Google or email, then come back here.")
        AccountTask(self.signals, "login", self.account.web_login, self._web_cancel).start()

    def _cancel_web(self):
        if self._web_cancel is not None:
            self._web_cancel.set()

    def _forgot(self):
        email = self.f_email.text().strip()
        if not email:
            return self._say(self.out_status, "Type your email first.", False)
        AccountTask(self.signals, "reset", self.account.reset_password, email).start()

    def _logout(self):
        self.account.logout()
        self.f_pass.clear()
        self.refresh()
        self.on_change()

    def _save(self):
        if not self.p_name.text().strip():
            return self._say(self.in_status, "Enter your name.", False)
        self._busy(True)
        AccountTask(self.signals, "save", self.account.save_profile, self.p_name.text().strip(),
                    self.p_phone.text().strip(), self.p_address.text().strip()).start()

    def _done(self, action, ok, data):
        if action == "login":
            self._busy(False)
            self.cancel_button.setVisible(False)
            if not ok:
                self._login_kind = ""
                return self._say(self.out_status, str(data), False)
            via_web = self._login_kind == "web"
            was_signup = self.mode == "signup" and not via_web
            self._login_kind = ""
            self.f_pass.clear()
            self.refresh()
            self.on_change()
            if via_web:
                self._bring_to_front()
                self._say(self.in_status, T("Login successful. Welcome") + (", " + self.account.name if self.account.name else "") + "!", True)
            if was_signup:
                self._say(self.in_status, "Account created. We emailed you a verification link (needed to comment on the website).", True)
        elif action == "reset":
            self._say(self.out_status, "Password reset email sent. Check your inbox." if ok else str(data), ok)
        elif action == "save":
            self._busy(False)
            self._say(self.in_status, "Saved." if ok else str(data), ok)
            if ok:
                self.on_change()
        elif action == "profile" and ok:
            p = data or {}
            self.p_name.setText(p.get("name", ""))
            self.p_phone.setText(p.get("phone", ""))
            self.p_address.setText(p.get("address", ""))
            self.blocked.setText(T("Your account is blocked, so ideas are not saved to your profile.") if p.get("status") == "blocked" else "")
            self.who_name.setText(p.get("name") or self.account.email)
            self.avatar.setText(self._initials(p.get("name") or self.account.email))
            self.on_change()
        elif action == "ideas" and ok:
            self._show_ideas(data or [])
        elif action == "idea_saved" and ok:
            self.refresh()

    def _bring_to_front(self):
        """After a browser login: show the app again so the user sees that the login worked."""
        try:
            w = self.window()
            if w.isMinimized():
                w.showNormal()
            w.show()
            w.raise_()
            w.activateWindow()
            QApplication.alert(w, 4000)
        except Exception:
            logging.exception("Could not bring the window to the front")

    @staticmethod
    def _initials(text):
        parts = [w[0] for w in str(text).split()[:2] if w]
        return ("".join(parts) or "?").upper()

    def _show_ideas(self, ideas):
        while self.ideas_box.count():
            item = self.ideas_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not ideas:
            label = QLabel(T("No ideas yet."))
            label.setObjectName("cardText")
            self.ideas_box.addWidget(label)
            return
        for idea in ideas:
            label = QLabel(f"<b>{html_escape(idea.get('title', ''))}</b> &nbsp; <span style='color:{C_PRIMARY_DARK}'>"
                           f"{html_escape(T(STATUS_LABEL.get(idea.get('status'), 'Pending')))}</span><br>"
                           f"<span style='color:{C_MUTED}'>{html_escape(idea.get('track', ''))}</span>"
                           + ("<br><span style='color:%s'>%s</span>" % (C_MUTED, " → ".join(
                               html_escape(T(STATUS_LABEL.get(st, st))) + (f" ({html_escape(dt)})" if dt else "") for st, dt in idea.get("steps", [])))
                              if idea.get("steps") else "")
                           + (f"<br>{html_escape(idea.get('feedback', ''))}" if idea.get("feedback") else ""))
            label.setWordWrap(True)
            label.setTextFormat(Qt.RichText)
            self.ideas_box.addWidget(label)

    def refresh(self):
        if self.account.logged_in:
            self.stack.setCurrentIndex(1)
            self.who_name.setText(self.account.name or self.account.email)
            self.who_mail.setText(self.account.email)
            self.avatar.setText(self._initials(self.account.name or self.account.email))
            AccountTask(self.signals, "profile", self.account.profile).start()
            AccountTask(self.signals, "ideas", self.account.list_ideas).start()
        else:
            self.stack.setCurrentIndex(0)
            self._set_mode(self.mode)


def html_escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class HelpPage(QWidget):
    STEPS = (
        ("Get a free key", "Open Google AI Studio and create a Gemini API key (Settings has a shortcut).",
         "ফ্রি কী নিন", "Google AI Studio-তে গিয়ে একটি Gemini API key বানিয়ে নিন (Settings-এ শর্টকাট বাটন আছে)।"),
        ("Save it in Settings", "Paste the key and choose Save & test. It is kept safely on this computer.",
         "Settings-এ সেভ করুন", "key-টি পেস্ট করে Save & test চাপুন। এটি আপনার কম্পিউটারেই নিরাপদে রাখা থাকে।"),
        ("Click where you want to type", "A browser, WhatsApp, Word, Notepad… any text field.",
         "যেখানে লিখবেন সেখানে ক্লিক করুন", "ব্রাউজার, WhatsApp, Word, Notepad… যেকোনো লেখার জায়গায়।"),
        ("Press a shortcut and speak", "Win + Left Ctrl for Bangla, Win + Left Shift for English.",
         "শর্টকাট চেপে বলতে থাকুন", "বাংলার জন্য Win + Left Ctrl, ইংরেজির জন্য Win + Left Shift।"),
        ("Pause", "When you stop speaking, SHUNCHi stops by itself and types the finished text at your cursor.",
         "একটু থামুন", "কথা শেষ করে থামলেই SHUNCHi নিজে থেমে যায় এবং লেখাটি আপনার কার্সরের জায়গায় বসিয়ে দেয়।"),
    )
    TIPS = (
        ("Press the same shortcut again to finish early.", "তাড়াতাড়ি শেষ করতে চাইলে একই শর্টকাট আবার চাপুন।"),
        ("You can mix English words into Bangla speech.", "বাংলা বলার মাঝে ইংরেজি শব্দ মিশিয়েও বলতে পারেন।"),
        ("If a program runs as administrator, Windows may block auto-typing; the text is then copied so you can press Ctrl + V.",
         "কোনো প্রোগ্রাম অ্যাডমিন হিসেবে চললে Windows অটো-টাইপিং আটকে দিতে পারে। তখন লেখাটি কপি হয়ে যায়, আপনি Ctrl + V চাপুন।"),
        ("Windows Settings > Privacy > Microphone must allow desktop apps to use the microphone.",
         "Windows Settings > Privacy > Microphone থেকে ডেস্কটপ অ্যাপকে মাইক্রোফোন ব্যবহারের অনুমতি দিয়ে রাখতে হবে।"),
        ("Your Gemini key is yours. Never share it and never install modified copies of SHUNCHi.",
         "Gemini key শুধু আপনার। এটি কাউকে দেবেন না, আর SHUNCHi-র কোনো পরিবর্তিত কপি ইনস্টল করবেন না।"),
        (f"New versions, downloads and help are published at {WEBSITE_LABEL}.",
         f"নতুন ভার্সন, ডাউনলোড ও সাহায্য সবসময় {WEBSITE_LABEL}-এ পাবেন।"),
    )

    def __init__(self):
        super().__init__()
        self._videos = None
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 28, 30, 24)
        root.setSpacing(16)
        self.header = page_header("How to use", "Five quick steps. After that SHUNCHi works in any app.")
        root.addLayout(self.header)

        card, layout = make_card((20, 16, 20, 16), 14)
        self.step_labels = []
        for number, _step in enumerate(self.STEPS, 1):
            row = QHBoxLayout()
            row.setSpacing(14)
            badge = QLabel(str(number))
            badge.setFixedSize(30, 30)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(f"background:{C_PRIMARY_SOFT};color:{C_PRIMARY_DARK};border-radius:15px;font-weight:700;font-size:13px;")
            col = QVBoxLayout()
            col.setSpacing(1)
            t = QLabel()
            t.setStyleSheet(f"font-size:14px;font-weight:600;color:{C_TEXT};")
            t.setWordWrap(True)
            d = QLabel()
            d.setObjectName("cardText")
            d.setWordWrap(True)
            col.addWidget(t)
            col.addWidget(d)
            row.addWidget(badge, 0, Qt.AlignTop)
            row.addLayout(col, 1)
            layout.addLayout(row)
            self.step_labels.append((t, d))
        root.addWidget(card)

        # video guides (the same videos as on the website)
        vcard, vbox = make_card((20, 16, 20, 16), 12)
        vhead = QHBoxLayout()
        self.video_title = QLabel()
        self.video_title.setObjectName("cardTitle")
        self.video_site = QPushButton()
        self.video_site.setObjectName("link")
        self.video_site.setCursor(Qt.PointingHandCursor)
        self.video_site.clicked.connect(lambda: open_website("/videos/"))
        vhead.addWidget(self.video_title, 1)
        vhead.addWidget(self.video_site, 0, Qt.AlignRight)
        vbox.addLayout(vhead)
        self.video_box = QVBoxLayout()
        self.video_box.setSpacing(10)
        vbox.addLayout(self.video_box)
        root.addWidget(vcard)

        tips, tips_layout = make_card((20, 16, 20, 16), 8)
        self.tips_title = QLabel()
        self.tips_title.setObjectName("cardTitle")
        tips_layout.addWidget(self.tips_title)
        self.tip_labels = []
        for _tip in self.TIPS:
            label = QLabel()
            label.setObjectName("cardText")
            label.setWordWrap(True)
            tips_layout.addWidget(label)
            self.tip_labels.append(label)
        root.addWidget(tips)
        root.addStretch()
        self.retranslate()
        self._fill_videos()

    def retranslate(self):
        self.header.itemAt(0).widget().setText(T("How to use"))
        self.header.itemAt(1).widget().setText(T("Five quick steps. After that SHUNCHi works in any app."))
        for (t, d), (te, de, tb, db) in zip(self.step_labels, self.STEPS):
            t.setText(tb if UI_BN else te)
            d.setText(db if UI_BN else de)
        self.tips_title.setText(T("Good to know"))
        for label, (en, bn) in zip(self.tip_labels, self.TIPS):
            label.setText("•  " + (bn if UI_BN else en))
        self.video_title.setText(T("Video guides"))
        self.video_site.setText(T("More videos on shunchiai.com") + "  ↗")
        self._fill_videos()

    def set_videos(self, videos):
        self._videos = list(videos or [])
        self._fill_videos()

    def _fill_videos(self):
        while self.video_box.count():
            item = self.video_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if self._videos is None:
            msg = QLabel(T("Loading videos…"))
            msg.setObjectName("cardText")
            self.video_box.addWidget(msg)
            return
        if not self._videos:
            msg = QLabel(T("Connect to the internet to see the video guides."))
            msg.setObjectName("cardText")
            msg.setWordWrap(True)
            self.video_box.addWidget(msg)
            return
        for video in self._videos:
            self.video_box.addWidget(self._video_card(video))

    def _video_card(self, video):
        url = "https://www.youtube.com/watch?v=" + video["id"]
        frame = ClickFrame()
        frame.setObjectName("vidRow")
        frame.setStyleSheet(
            f"QFrame#vidRow{{background:#F8FAFD;border:1px solid {C_BORDER};border-radius:12px;}}"
            f"QFrame#vidRow:hover{{background:{C_PRIMARY_SOFT};border:1px solid #C7DBFB;}}")
        row = QHBoxLayout(frame)
        row.setContentsMargins(10, 10, 14, 10)
        row.setSpacing(14)
        thumb = QLabel()
        thumb.setFixedSize(160, 90)
        thumb.setAlignment(Qt.AlignCenter)
        pix = QPixmap()
        if video.get("thumb") and pix.loadFromData(video["thumb"]):
            pix = pix.scaled(160, 90, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            rounded = QPixmap(160, 90)
            rounded.fill(Qt.transparent)
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.Antialiasing)
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(0, 0, 160, 90), 9, 9)
            painter.setClipPath(clip)
            painter.drawPixmap(0, 0, pix)
            painter.end()
            thumb.setPixmap(rounded)
        else:
            thumb.setText("▶")
            thumb.setStyleSheet(f"background:{C_TEXT};color:white;border-radius:9px;font-size:26px;")
        col = QVBoxLayout()
        col.setSpacing(4)
        title = QLabel(video["title_bn"] if UI_BN else video["title_en"])
        title.setWordWrap(True)
        title.setStyleSheet(f"background:transparent;border:0;font-size:13.5px;font-weight:700;color:{C_TEXT};")
        watch = QLabel(T("Watch on YouTube") + "  ↗")
        watch.setStyleSheet(f"background:transparent;border:0;font-size:12.5px;font-weight:600;color:{C_PRIMARY_DARK};")
        for w in (thumb, title, watch):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        col.addStretch()
        col.addWidget(title)
        col.addWidget(watch)
        col.addStretch()
        row.addWidget(thumb)
        row.addLayout(col, 1)
        frame.clicked.connect(lambda u=url: QDesktopServices.openUrl(QUrl(u)))
        return frame


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

        try:
            root.addWidget(self._official_card())
        except Exception:
            logging.exception("Official card failed")
            fallback = QLabel(f"Official SHUNCHi: {WEBSITE_URL}  ·  voice.shunchi@gmail.com")
            fallback.setObjectName("cardText")
            root.addWidget(fallback)

        root.addStretch()


    @staticmethod
    def _channel_button(glyph, color, title, handle, url):
        """One official channel as a clickable row: coloured badge, name, handle and an arrow."""
        row_frame = ClickFrame()
        row_frame.setObjectName("chRow")
        row_frame.setFixedHeight(66)
        row_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row_frame.setStyleSheet(
            f"QFrame#chRow{{background:#F8FAFD;border:1px solid {C_BORDER};border-radius:12px;}}"
            f"QFrame#chRow:hover{{background:{C_PRIMARY_SOFT};border:1px solid #C7DBFB;}}")
        row = QHBoxLayout(row_frame)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(12)
        badge = QLabel(glyph)
        badge.setFixedSize(38, 38)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"background:{color};color:white;border-radius:19px;font-size:13px;font-weight:700;")
        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)
        t = QLabel(title)
        t.setStyleSheet(f"background:transparent;border:0;font-size:13.5px;font-weight:700;color:{C_TEXT};")
        h = QLabel(handle)
        h.setStyleSheet(f"background:transparent;border:0;font-size:12px;color:{C_MUTED};")
        col.addWidget(t)
        col.addWidget(h)
        arrow = QLabel("↗")
        arrow.setStyleSheet(f"background:transparent;border:0;font-size:15px;color:{C_FAINT};")
        for w in (badge, t, h, arrow):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row.addWidget(badge)
        row.addLayout(col, 1)
        row.addWidget(arrow)
        row_frame.clicked.connect(lambda u=url: QDesktopServices.openUrl(QUrl(u)))
        return row_frame

    def _official_card(self):
        card, layout = make_card((24, 22, 24, 22), 14)
        head = QHBoxLayout()
        head.setSpacing(14)
        logo = QLabel()
        logo.setFixedSize(46, 46)
        pix = QPixmap(resource_path("assets/shunchi-icon-512.png"))
        if not pix.isNull():
            logo.setPixmap(pix.scaled(46, 46, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        titles = QVBoxLayout()
        titles.setSpacing(2)
        ot = QLabel("Official SHUNCHi")
        ot.setStyleSheet(f"font-size:18px;font-weight:700;color:{C_TEXT};")
        od = QLabel("Product updates, installation help, troubleshooting and new releases.")
        od.setObjectName("cardText")
        od.setWordWrap(True)
        titles.addWidget(ot)
        titles.addWidget(od)
        badge = QLabel("✓  Official")
        badge.setStyleSheet(f"background:{C_OK_SOFT};color:{C_OK};border:1px solid #BBF7D0;border-radius:11px;"
                            "padding:3px 10px;font-size:11.5px;font-weight:700;")
        head.addWidget(logo, 0, Qt.AlignTop)
        head.addLayout(titles, 1)
        head.addWidget(badge, 0, Qt.AlignTop)
        layout.addLayout(head)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{C_BORDER};border:0;")
        layout.addWidget(line)

        rows = (
            (("W", C_PRIMARY, "Website", WEBSITE_LABEL, WEBSITE_URL),
             ("@", C_WARN, "Email support", "voice.shunchi@gmail.com", "mailto:voice.shunchi@gmail.com")),
            (("f", "#1877F2", "Facebook", "@voice.shunchi", "https://www.facebook.com/voice.shunchi"),
             ("IG", "#C13584", "Instagram", "@voice.shunchi", "https://www.instagram.com/voice.shunchi/")),
        )
        for pair in rows:
            r = QHBoxLayout()
            r.setSpacing(12)
            for spec in pair:
                r.addWidget(self._channel_button(*spec))
            layout.addLayout(r)

        safe = QFrame()
        safe.setObjectName("safeNote")
        safe.setStyleSheet(f"QFrame#safeNote{{background:{C_WARN_SOFT};border:1px solid #FDE2A8;border-radius:12px;}}"
                           "QFrame#safeNote QLabel{background:transparent;border:0;}")
        sl = QHBoxLayout(safe)
        sl.setContentsMargins(14, 10, 14, 10)
        sl.setSpacing(10)
        shield = QLabel("!")
        shield.setFixedSize(22, 22)
        shield.setAlignment(Qt.AlignCenter)
        shield.setStyleSheet(f"background:{C_WARN};color:white;border-radius:11px;font-size:13px;font-weight:800;")
        note = QLabel(f"Download updates only from {WEBSITE_LABEL} or the official SHUNCHi pages. "
                      "Do not install modified builds and never share your personal Gemini API key.")
        note.setWordWrap(True)
        note.setStyleSheet(f"font-size:12.5px;color:{C_WARN};font-weight:600;")
        sl.addWidget(shield, 0, Qt.AlignTop)
        sl.addWidget(note, 1)
        layout.addWidget(safe)
        return card


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
           ("How to use", "help"), ("More Apps", "apps"), ("Developer", "user"), ("Account", "user"))

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
        self.update_prompted_for = ""
        self.force_min = str(self.settings.value("force_min_version", "") or "")
        self.spec_token = 0
        self._key_retries = 0
        self._mic_rescans = 0
        self._hook_deaths = 0
        self._shown_once = False
        self._last_tick = time.monotonic()
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

        global UI_BN
        UI_BN = self.settings.value("ui_bangla", True, type=bool)
        self._build_ui()
        self.settings_page.load_values(self.smart_mode, self.silence_seconds, self.max_minutes,
                                       startup_enabled() if os.name == "nt" else False, self.auto_update,
                                       self.save_history_enabled)
        self.history_page.set_recording(self.save_history_enabled)
        self.more_apps_page.set_apps(self.load_remote_apps())
        self.dashboard_page.update_button.clicked.connect(self.start_update_install)
        self.show_status(READY_TEXT)
        self.signals.videos_ready.connect(self.help_page.set_videos)
        QTimer.singleShot(1500, lambda: VideoLoader(self.signals).start())
        self.mic_scanner = MicrophoneScanner(self.signals)
        self.mic_scanner.start()
        self.hotkeys.start()
        # Windows can silently drop a keyboard hook (right after logon, after sleep, or when the system is busy).
        # A small watchdog re-registers it whenever that may have happened.
        self.hook_timer = QTimer(self)
        self.hook_timer.setInterval(5000)
        self.hook_timer.timeout.connect(self._hook_watchdog)
        self.hook_timer.start()
        for delay in (8000, 25000, 60000):
            QTimer.singleShot(delay, self._restart_hotkeys)
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
        tagline = QLabel(T("AI voice typing · by RUHUL"))
        tagline.setObjectName("muted")
        self.tagline = tagline
        side.addWidget(logo)
        side.addWidget(tagline)
        side.addSpacing(18)

        self.nav_buttons = []
        self.nav_icons = []
        for index, (label, kind) in enumerate(self.NAV):
            button = QPushButton("  " + T(label))
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
        self.dashboard_page = DashboardPage(lambda: self.switch_page(2), self.set_ui_language, self._dashboard_account)
        self.history_page = HistoryPage(self._history_toggled)
        self.settings_page = SettingsPage(self)
        self.help_page = HelpPage()
        self.more_apps_page = MoreAppsPage()
        self.developer_page = DeveloperPage()
        self.account = AccountService(self.settings)
        self.account_page = AccountPage(self.account, self.signals, self._account_changed)
        self.more_apps_page.bind_signals(self.signals)
        self.more_apps_page.bind_account(self.account)
        self.stack = QStackedWidget()
        for page in (self.dashboard_page, self.history_page, self.settings_page, self.help_page,
                     self.more_apps_page, self.developer_page, self.account_page):
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
        harden_labels(self)
        self._sync_dashboard_account()
        self.switch_page(0)

    def set_ui_language(self, bangla):
        """Dashboard language switch (English / বাংলা). Remembered for the next start."""
        global UI_BN
        UI_BN = bool(bangla)
        self.settings.setValue("ui_bangla", UI_BN)
        for button, (label, _kind) in zip(self.nav_buttons, self.NAV):
            button.setText("  " + T(label))
        self.tagline.setText(T("AI voice typing · by RUHUL"))
        self.dashboard_page.retranslate()
        self.account_page.retranslate()
        self.more_apps_page.retranslate_account()
        self.history_page.retranslate()
        self.help_page.retranslate()

    def _account_changed(self):
        self.more_apps_page.refresh_account()
        self._sync_dashboard_account()

    def _sync_dashboard_account(self):
        """Keeps the account corner of the dashboard (Log in / name + profile menu) in step with the account."""
        try:
            acc = self.account
            if not acc.logged_in:
                self.dashboard_page.set_account({"in": False})
                return
            p = acc.profile_cache or {}
            self.dashboard_page.set_account({
                "in": True, "name": p.get("name") or acc.name, "email": p.get("email") or acc.email,
                "phone": p.get("phone", ""), "address": p.get("address", "")})
        except Exception:
            logging.exception("Dashboard account sync failed")

    def _dashboard_account(self, action):
        """Clicks from the dashboard account corner: open the Account page, or log out."""
        if action == "logout":
            self.account_page._logout()
        else:
            self.switch_page(len(self.NAV) - 1)

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            active = i == index
            button.setChecked(active)
            button.setIcon(self.nav_icons[i][1 if active else 0])
        if index == 1:
            self.history_page.refresh()
        QTimer.singleShot(0, lambda: harden_labels(self.stack.currentWidget()))

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

    # ------------------------------------------------------------------ keyboard hook health
    def _restart_hotkeys(self):
        if self.recording or self.processing:
            return
        try:
            self.hotkeys.stop()
        except Exception:
            logging.exception("Old hotkey listener would not stop")
        self.hotkeys = HotkeyManager(self.signals)
        self.hotkeys.start()
        logging.info("Hotkey listener (re)started")

    def _hook_watchdog(self):
        now = time.monotonic()
        slept = now - self._last_tick > 20          # the timer is 5 s: a big gap means the PC was asleep
        self._last_tick = now
        dead = not self.hotkeys.is_alive()
        if dead and self._hook_deaths >= 5:
            dead = False                            # it keeps failing: stop retrying (the person was already told why)
        if dead:
            self._hook_deaths += 1
        if slept or dead:
            self._restart_hotkeys()

    # ------------------------------------------------------------------ settings
    def _history_toggled(self, enabled):
        """The History page switch: keep the Settings page and the saved setting in step."""
        self.save_history_enabled = bool(enabled)
        self.settings.setValue("save_history", self.save_history_enabled)
        self.settings.sync()
        page = self.settings_page
        page.history_on.blockSignals(True)
        page.history_on.setChecked(self.save_history_enabled)
        page.history_on.blockSignals(False)
        self.show_status(T("History is on") if enabled else T("History is off"))

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

    def showEvent(self, event):
        """Opening the window from the tray (or after a quiet start) is the moment to tell about a waiting update."""
        super().showEvent(event)
        info = getattr(self, "latest_info", None)
        if not info:
            return
        if self.update_is_forced():
            QTimer.singleShot(400, self.show_forced_update)
        elif self.update_prompted_for != info.get("latest"):
            QTimer.singleShot(900, lambda: self.notify_update(info) if self.isVisible() else None)

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
            elif manual or self.update_prompted_for != info["latest"]:
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
        self.update_prompted_for = info["latest"]      # once per start; it comes back next time SHUNCHi opens
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
            # Right after Windows starts the audio service may not be ready: look again a few times.
            if self._mic_rescans < 6:
                self._mic_rescans += 1
                QTimer.singleShot(4000, lambda: MicrophoneScanner(self.signals, refresh=True).start())
            else:
                self.show_status("No microphone detected · check Windows microphone permissions.")

    # ------------------------------------------------------------------ API key
    def first_run_check(self):
        self.api_key = SecretStore.get()
        if not self.api_key and self._key_retries < 3:
            # Right after Windows starts, the credential store may not be ready yet. Look again a little later
            # before telling the person anything.
            self._key_retries += 1
            QTimer.singleShot(2500 * self._key_retries, self.first_run_check)
            if self.start_hidden:
                return
        if self.api_key:
            self.dashboard_page.set_api_state("pending", "Ready · press Win + Left Ctrl (Bangla) or Win + Left Shift (English).")
            self.settings_page.set_key_status(True)
            self.settings_page.set_key_result("A key is saved. Choose “Save & test” with a new key to replace it.")
        else:
            self.dashboard_page.set_api_state("missing", "Add your Gemini API key in Settings to start voice typing.")
            self.settings_page.set_key_status(False)
        if not (self.start_hidden and self.api_key) and not self._shown_once:
            self._shown_once = True
            self.show()
            self.raise_()
            self.activateWindow()
            self.start_hidden = False

    def save_api_key(self, key):
        if len(key) < 20 or any(ch.isspace() for ch in key):
            self.settings_page.set_key_result("That does not look like a Gemini API key. Copy it again from Google AI Studio.", False)
            return
        if not SecretStore.save(key):
            self.settings_page.set_key_result("Windows could not store the key. Check your Windows account permissions.", False)
            return
        self.api_key = key
        self.settings_page.set_busy(True)
        self.settings_page.set_key_status(True)
        self.settings_page.set_key_result("Saved. Testing the connection…")
        self.dashboard_page.set_api_state("pending", "Testing your Gemini connection…")
        self.api_tester = ApiTester(key, self.signals)
        self.api_tester.start()

    def remove_api_key(self):
        SecretStore.delete()
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
            self.api_key = SecretStore.get()
            if self.api_key:
                self.dashboard_page.set_api_state("pending", "Ready · press Win + Left Ctrl (Bangla) or Win + Left Shift (English).")
                self.settings_page.set_key_status(True)
        if not self.api_key:
            self.popup.show_error("Add your Gemini API key in Settings first.")
            self.show_status("Add your Gemini API key in Settings to start voice typing.")
            return
        if not self.mic_scan_complete or not self.available_devices:
            # Scan again right now instead of making the person wait.
            try:
                MicrophoneScanner(self.signals, refresh=True).run()
            except Exception:
                logging.exception("Immediate microphone scan failed")
        if not self.available_devices:
            self.popup.show_error("No microphone found. Check Windows microphone permissions.")
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
        self.qt = QApplication.instance() or QApplication(sys.argv)
        self.qt.setApplicationName(APP_NAME)
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setWindowIcon(QIcon(resource_path("assets/shunchi.ico")))
        self.qt.setFont(QFont("Segoe UI", 10))
        self.qt.setStyleSheet(build_qss(ensure_chevron()))
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
        self.tray.activated.connect(self.tray_activated)
        self.tray.messageClicked.connect(self.on_tray_message)
        self.tray.show()                    # visible at once; the window is built right after
        self.qt.processEvents()
        self.window = MainWindow()
        self.window.tray_icon = self.tray
        # At Windows start-up the taskbar may not exist yet; make sure the icon really appears.
        for delay in (3000, 10000, 30000):
            QTimer.singleShot(delay, self._ensure_tray)
        try:
            if SPLASH is not None:
                SPLASH.close()
        except Exception:
            logging.exception("Splash close failed")

    def _ensure_tray(self):
        try:
            if not self.tray.isVisible():
                self.tray.hide()
                self.tray.show()
        except Exception:
            logging.exception("Tray refresh failed")

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
