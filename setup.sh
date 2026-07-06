#!/usr/bin/env bash
# Set up the push-to-talk dictation tool.
# Safe to re-run. Needs internet; uses sudo only if available for apt installs,
# otherwise falls back to user-local copies of everything.
set -euo pipefail
cd "$(dirname "$0")"

# --- system packages -------------------------------------------------------
have_sudo() { sudo -n true 2>/dev/null || [ -t 0 ]; }

missing_pkgs=()
command -v xdotool >/dev/null || missing_pkgs+=(xdotool)
dpkg -s libportaudio2 >/dev/null 2>&1 || missing_pkgs+=(libportaudio2)
python3 -c 'import ensurepip' 2>/dev/null || missing_pkgs+=("python3-venv")
python3 -c 'import gi; gi.require_version("Gtk", "3.0")' 2>/dev/null || missing_pkgs+=(python3-gi gir1.2-gtk-3.0)
python3 -c 'import gi; gi.require_version("AyatanaAppIndicator3", "0.1")' 2>/dev/null || missing_pkgs+=(gir1.2-ayatanaappindicator3-0.1)

if [ ${#missing_pkgs[@]} -gt 0 ] && have_sudo; then
    echo ">> Installing system packages: ${missing_pkgs[*]}"
    sudo apt-get install -y "${missing_pkgs[@]}"
fi

# Fallback: extract xdotool from the .deb into ./bin (no root needed).
if ! command -v xdotool >/dev/null && [ ! -x bin/xdotool ]; then
    echo ">> No sudo; extracting xdotool locally into ./bin"
    tmp=$(mktemp -d)
    (cd "$tmp" && apt-get download xdotool libxdo3 >/dev/null)
    for deb in "$tmp"/*.deb; do dpkg -x "$deb" "$tmp/x"; done
    mkdir -p bin/lib
    cp "$tmp"/x/usr/bin/xdotool bin/xdotool.bin
    cp "$tmp"/x/usr/lib/x86_64-linux-gnu/libxdo.so.* bin/lib/
    cat > bin/xdotool <<'EOF'
#!/bin/sh
here=$(dirname "$(readlink -f "$0")")
LD_LIBRARY_PATH="$here/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" exec "$here/xdotool.bin" "$@"
EOF
    chmod +x bin/xdotool
    rm -rf "$tmp"
fi

# --- python environment ----------------------------------------------------
if [ ! -x .venv/bin/python ]; then
    echo ">> Creating virtualenv"
    # --system-site-packages: lets the venv see the system's PyGObject/gi
    # bindings (python3-gi, gir1.2-ayatanaappindicator3-0.1), which have no
    # pip wheel and are needed for the tray icon's menu support.
    if python3 -c 'import ensurepip' 2>/dev/null; then
        python3 -m venv --system-site-packages .venv
    else
        # No ensurepip (python3-venv not installed): bootstrap pip manually.
        python3 -m venv --system-site-packages --without-pip .venv
        curl -fsSL https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
    fi
fi

echo ">> Installing Python packages"
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

echo ">> Pre-downloading Whisper 'base' model"
.venv/bin/python - <<'EOF'
from faster_whisper import WhisperModel
WhisperModel("base", device="cpu", compute_type="int8")
print("model ready")
EOF

echo
echo "Setup complete. Run with:  .venv/bin/python dictate.py"
echo "Hold Right Ctrl to dictate into the focused window."
