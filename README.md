# Push-to-Talk Dictation

Local dictation for Linux (X11) and Windows. Hold **Right Ctrl**, speak,
release — the transcription is typed into whatever window has focus.
Everything runs on-device: faster-whisper `base` model, CPU, int8. No
audio or text ever leaves the machine.

A system tray icon lets you pause/resume dictation, toggle "Start at
login," and quit — no terminal needed day-to-day.

## Setup

**Linux:**

```sh
./setup.sh
```

Installs Python deps into `.venv/` and pre-downloads the Whisper model
(~75 MB, one time). If sudo is available it apt-installs `xdotool` and
the GTK/AppIndicator bindings needed for the tray menu; otherwise it
extracts a user-local copy of `xdotool` into `./bin` automatically.

**Windows (PowerShell):**

```powershell
.\setup.ps1
```

Requires Python 3.9+ on PATH. Installs deps into `.venv\` and
pre-downloads the Whisper model.

## Run

**Linux:**

```sh
.venv/bin/python dictate.py
```

**Windows:**

```powershell
.venv\Scripts\python.exe dictate.py
```

Hold Right Ctrl to record, release to transcribe and type. Use the tray
icon to pause, enable "Start at login," or quit.

Options:

- `--language auto` — auto-detect language (default: `en`)
- `--model small` — larger model for better accuracy (slower)
- `--key ctrl_l` — different push-to-talk key (any `pynput` key name)
- `--device NAME` — specific input device (see `python -m sounddevice`)

## Notes

- A ~0.25 s pre-roll and 0.3 s post-roll are captured around the key hold,
  so words aren't clipped if you press/release mid-word.
- Very short holds (< 0.3 s of audio) are ignored, so an accidental tap
  of Right Ctrl types nothing.
- On Linux, typing uses `xdotool type --clearmodifiers`, which works in
  most X11 apps but not in Wayland sessions.
- On Windows, typing is injected directly via `pynput`, so no extra
  system tool is required.
- "Start at login" writes an XDG autostart entry on Linux
  (`~/.config/autostart/dictation.desktop`) or a registry Run key on
  Windows (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).
