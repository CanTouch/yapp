#!/usr/bin/env bash
# Extracts a self-contained, relocatable xdotool + libxdo into ./bin
# (no root needed). Used by setup.sh when sudo isn't available, and by
# the Linux PyInstaller build so the packaged binary doesn't depend on
# a system xdotool install.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -x bin/xdotool ]; then
    exit 0
fi

echo ">> Extracting a local xdotool into ./bin"
tmp=$(mktemp -d)
(cd "$tmp" && apt-get download xdotool libxdo3 >/dev/null)
for deb in "$tmp"/*.deb; do dpkg -x "$deb" "$tmp/x"; done
mkdir -p bin/lib
cp "$tmp"/x/usr/bin/xdotool bin/xdotool.bin
cp "$tmp"/x/usr/lib/x86_64-linux-gnu/libxdo.so.* bin/lib/
cat > bin/xdotool <<'SCRIPT'
#!/bin/sh
here=$(dirname "$(readlink -f "$0")")
LD_LIBRARY_PATH="$here/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" exec "$here/xdotool.bin" "$@"
SCRIPT
chmod +x bin/xdotool
rm -rf "$tmp"
