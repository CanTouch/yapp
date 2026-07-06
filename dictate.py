#!/usr/bin/env python3
"""YAPP - push-to-talk dictation for Linux and Windows.

Hold Right Ctrl to record from the microphone; release to transcribe
locally with faster-whisper and type the result into the focused window
(xdotool on Linux/X11, direct key injection via pynput on Windows).
"""

import argparse
import collections
import datetime
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import numpy as np
import pystray
import sounddevice as sd
from PIL import Image, ImageDraw
from pynput import keyboard

SAMPLE_RATE = 16000  # what Whisper expects
PREROLL_SECONDS = 0.25  # audio kept from just before the key press
POSTROLL_SECONDS = 0.3  # keep recording briefly after release; users let go mid-word
MIN_UTTERANCE_SECONDS = 0.3

APP_DIR = Path(__file__).resolve().parent
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")


def state_dir() -> Path:
    """Per-user directory for logs/locks; survives across runs, not synced anywhere."""
    if IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    d = base / "yapp"
    d.mkdir(parents=True, exist_ok=True)
    return d


class _Tee:
    """Duplicates writes to every non-None stream given; tolerates closed/missing ones.

    Needed because autostart launches (pythonw.exe, .desktop Terminal=false)
    have no real stdout/stderr, so print() output would otherwise vanish.
    """

    def __init__(self, *streams):
        self._streams = [s for s in streams if s]

    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass


def setup_logging():
    log_file = open(state_dir() / "dictation.log", "a", buffering=1, encoding="utf-8")
    log_file.write(f"\n--- started {datetime.datetime.now().isoformat(timespec='seconds')} ---\n")
    sys.stdout = _Tee(sys.stdout, log_file)
    sys.stderr = _Tee(sys.stderr, log_file)


_lock_handle = None  # kept open for the process lifetime; garbage-collecting it drops the lock


def acquire_single_instance_lock():
    global _lock_handle
    _lock_handle = open(state_dir() / "dictation.lock", "a+b")
    try:
        if IS_WINDOWS:
            import msvcrt
            _lock_handle.seek(0)
            msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("Another instance of the dictation app is already running.")


if IS_WINDOWS:
    import winreg

    AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    AUTOSTART_NAME = "YAPP"

    def autostart_enabled() -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
                winreg.QueryValueEx(key, AUTOSTART_NAME)
            return True
        except FileNotFoundError:
            return False

    def set_autostart(enabled: bool):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                # pythonw avoids a console window flashing up at every login.
                python = Path(sys.executable).with_name("pythonw.exe")
                if not python.exists():
                    python = Path(sys.executable)
                script = Path(__file__).resolve()
                winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, f'"{python}" "{script}"')
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_NAME)
                except FileNotFoundError:
                    pass

else:
    AUTOSTART_FILE = Path.home() / ".config" / "autostart" / "yapp.desktop"
    _OLD_AUTOSTART_FILE = Path.home() / ".config" / "autostart" / "dictation.desktop"

    def autostart_enabled() -> bool:
        if not AUTOSTART_FILE.exists():
            return False
        return "X-GNOME-Autostart-enabled=false" not in AUTOSTART_FILE.read_text()

    def set_autostart(enabled: bool):
        AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
        python = sys.executable
        script = str(Path(__file__).resolve())
        AUTOSTART_FILE.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=YAPP\n"
            "Comment=Hold Right Ctrl to dictate; local faster-whisper transcription\n"
            f'Exec="{python}" "{script}"\n'
            "Terminal=false\n"
            f"X-GNOME-Autostart-enabled={'true' if enabled else 'false'}\n"
        )
        # Drop the pre-rename autostart entry so we don't end up autostarting twice.
        _OLD_AUTOSTART_FILE.unlink(missing_ok=True)


def make_icon_image() -> Image.Image:
    """A simple mic glyph on a rounded square, legible even at tray size."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, size - 2, size - 2), radius=16, fill=(88, 86, 214, 255))
    fg = (255, 255, 255, 255)
    d.rounded_rectangle((26, 12, 38, 34), radius=6, fill=fg)
    d.arc((20, 20, 44, 44), start=20, end=160, fill=fg, width=3)
    d.line((32, 40, 32, 48), fill=fg, width=3)
    d.line((24, 48, 40, 48), fill=fg, width=3)
    return img


if IS_LINUX:
    def find_typer() -> str:
        """System xdotool, or the local copy setup.sh extracts when sudo isn't available."""
        local = APP_DIR / "bin" / "xdotool"
        if shutil.which("xdotool"):
            return "xdotool"
        if local.exists():
            return str(local)
        sys.exit("xdotool not found. Run setup.sh or: sudo apt install xdotool")

    def type_text(typer: str, text: str):
        subprocess.run(
            [typer, "type", "--clearmodifiers", "--delay", "12", "--", text],
            check=True,
        )

else:
    _kb_controller = keyboard.Controller()

    def find_typer():
        return None  # nothing to locate; pynput injects keys directly

    def type_text(typer, text: str):
        _kb_controller.type(text)


class Recorder:
    """Keeps one InputStream open so recording starts instantly on key press.

    A short pre-roll buffer catches speech that begins right as the key
    goes down.
    """

    def __init__(self, device=None):
        self._lock = threading.Lock()
        self._recording = False
        self._chunks = []
        preroll_chunks = max(1, int(PREROLL_SECONDS * SAMPLE_RATE / 1024))
        self._preroll = collections.deque(maxlen=preroll_chunks)
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=1024,
            device=device,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(f"  [audio] {status}", file=sys.stderr)
        with self._lock:
            if self._recording:
                self._chunks.append(indata.copy())
            else:
                self._preroll.append(indata.copy())

    def start(self):
        with self._lock:
            if self._recording:
                return
            self._chunks = list(self._preroll)
            self._preroll.clear()
            self._recording = True

    def stop(self) -> np.ndarray:
        with self._lock:
            self._recording = False
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.empty(0, dtype=np.float32)
        return np.concatenate(chunks).ravel()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="base", help="Whisper model size (default: base)")
    parser.add_argument("--language", default="en",
                        help="Language code, or 'auto' to detect (default: en)")
    parser.add_argument("--device", default=None, help="sounddevice input device")
    parser.add_argument("--key", default="ctrl_r",
                        help="pynput key name for push-to-talk (default: ctrl_r)")
    args = parser.parse_args()

    setup_logging()
    acquire_single_instance_lock()

    typer = find_typer()
    language = None if args.language == "auto" else args.language
    hotkey = getattr(keyboard.Key, args.key)

    print(f"Loading faster-whisper '{args.model}' (CPU, int8)...")
    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device="cpu", compute_type="int8")

    recorder = Recorder(device=args.device)
    jobs = queue.Queue()

    def transcribe_worker():
        while True:
            audio = jobs.get()
            try:
                duration = len(audio) / SAMPLE_RATE
                if duration < MIN_UTTERANCE_SECONDS:
                    print(f"  (too short: {duration:.2f}s, ignored)")
                    continue
                print(f"  transcribing {duration:.1f}s...")
                segments, _ = model.transcribe(
                    audio,
                    language=language,
                    beam_size=5,
                    vad_filter=True,
                    condition_on_previous_text=False,
                )
                text = " ".join(seg.text.strip() for seg in segments).strip()
                if not text:
                    print("  (no speech detected)")
                    continue
                try:
                    type_text(typer, text)
                    print(f"  typed: {text}")
                except Exception as e:
                    print(f"  typing failed ({e}); text was: {text}", file=sys.stderr)
            except Exception:
                # One bad utterance must not kill this thread — otherwise dictation
                # silently stops working until the app is relaunched.
                print("  transcription job failed:", file=sys.stderr)
                traceback.print_exc()

    threading.Thread(target=transcribe_worker, daemon=True).start()

    key_held = threading.Event()
    paused = threading.Event()

    def on_press(key):
        if paused.is_set():
            return
        if key == hotkey and not key_held.is_set():
            key_held.set()
            recorder.start()
            print("* recording... (release to transcribe)")

    def on_release(key):
        if key == hotkey:
            key_held.clear()

            def finish():
                time.sleep(POSTROLL_SECONDS)
                # If the key was pressed again during the post-roll, the same
                # recording just continues; the next release will finish it.
                if not key_held.is_set():
                    jobs.put(recorder.stop())

            threading.Thread(target=finish, daemon=True).start()

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    print(f"YAPP ready. Hold {args.key} to dictate. Use the tray icon to pause or quit.")

    def toggle_pause(icon, item):
        if paused.is_set():
            paused.clear()
            print("* resumed")
        else:
            paused.set()
            print("* paused")

    def toggle_autostart(icon, item):
        set_autostart(not autostart_enabled())

    def quit_app(icon, item):
        icon.stop()
        listener.stop()

    icon = pystray.Icon(
        "yapp",
        make_icon_image(),
        "YAPP - push-to-talk dictation",
        menu=pystray.Menu(
            pystray.MenuItem("Paused", toggle_pause, checked=lambda item: paused.is_set()),
            pystray.MenuItem("Start at login", toggle_autostart, checked=lambda item: autostart_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", quit_app),
        ),
    )
    icon.run()


if __name__ == "__main__":
    main()
