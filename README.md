# Push-to-Talk Dictation

Local dictation for Linux Mint (X11/Cinnamon). Hold **Right Ctrl**, speak,
release — the transcription is typed into whatever window has focus.
Everything runs on-device: faster-whisper `base` model, CPU, int8.

## Setup

```sh
./setup.sh
```

Installs Python deps into `.venv/` and pre-downloads the Whisper model
(~75 MB, one time). If sudo is available it apt-installs `xdotool`;
otherwise it extracts a user-local copy into `./bin` automatically.

## Run

```sh
.venv/bin/python dictate.py
```

Leave it running in a terminal. Hold Right Ctrl to record, release to
transcribe and type. Ctrl+C to quit.

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
- Typing uses `xdotool type --clearmodifiers`, so it works in most X11
  apps. It will not work in Wayland sessions.
