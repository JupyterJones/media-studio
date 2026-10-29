#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

APP_DIR="$ROOT_DIR/AppDir_Tauri_DEV"
OUTPUT_APPIMAGE="$ROOT_DIR/Tauri-VideoMaker-DEV-x86_64.AppImage"

echo "================================================="
echo "   ⚡ BUILDING TAURI-VIDEOMAKER DEV APPIMAGE      "
echo "================================================="

echo "==> [1/5] Checking compiled Tauri release binary..."
RELEASE_BIN="$ROOT_DIR/tauri_app/src-tauri/target/release/app"
if [ ! -f "$RELEASE_BIN" ]; then
    echo "Release binary not found! Compiling via cargo..."
    cd "$ROOT_DIR/tauri_app/src-tauri"
    cargo build --release
    cd "$ROOT_DIR"
fi

echo "    -> Found release binary: $(ls -lh "$RELEASE_BIN" | awk '{print $5}')"

echo "==> [2/5] Setting up AppDir structure..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/usr/bin"
mkdir -p "$APP_DIR/bin"
mkdir -p "$APP_DIR/static/novel_images-Appdemo"

cp "$RELEASE_BIN" "$APP_DIR/usr/bin/tauri-videomaker"
chmod +x "$APP_DIR/usr/bin/tauri-videomaker"

# Bundle sample frames for standalone initial demo
if [ -d "$ROOT_DIR/static/novel_images0" ]; then
    cp "$ROOT_DIR/static/novel_images0"/* "$APP_DIR/static/novel_images-Appdemo/" 2>/dev/null || true
fi

echo "==> [3/5] Embedding standalone FFmpeg..."
FFMPEG_SRC="$(which ffmpeg 2>/dev/null || echo "/usr/local/bin/ffmpeg")"
if [ -x "$FFMPEG_SRC" ]; then
    cp "$FFMPEG_SRC" "$APP_DIR/bin/ffmpeg"
    chmod +x "$APP_DIR/bin/ffmpeg"
fi

# Icon
ICON_SRC="$ROOT_DIR/icon.png"
if [ ! -f "$ICON_SRC" ]; then
    ICON_SRC="$ROOT_DIR/tauri_app/src-tauri/icons/icon.png"
fi
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$APP_DIR/tauri.png"
fi

echo "==> [4/5] Creating Desktop Entry and AppRun with Terminal Logging..."
cat << 'EOF' > "$APP_DIR/tauri-videomaker.desktop"
[Desktop Entry]
Type=Application
Name=Tauri VideoMaker DEV
GenericName=Native Rust Desktop Video Maker Studio (DEV)
Comment=Native Tauri lightweight image flipbook player and video exporter with live console logs
Exec=AppRun %F
Icon=tauri
Categories=AudioVideo;Video;Graphics;Development;
Terminal=true
StartupNotify=true
EOF

cat << 'EOF' > "$APP_DIR/AppRun"
#!/usr/bin/env bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}

export HERE
export PATH="${HERE}/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"
export FFMPEG_BIN="${HERE}/bin/ffmpeg"

# Determine host workspace directory
if [ -n "$PORTABLE_EXECUTABLE_DIR" ]; then
    HOST_DIR="$PORTABLE_EXECUTABLE_DIR"
else
    HOST_DIR="$PWD"
fi
export HOST_DIR

LOG_FILE="/tmp/tauri_videomaker_dev.log"
echo "==========================================================" | tee -a "$LOG_FILE"
echo "  🚀 TAURI VIDEOMAKER DEV LAUNCHER" | tee -a "$LOG_FILE"
echo "  Date:     $(date)" | tee -a "$LOG_FILE"
echo "  HOST_DIR: $HOST_DIR" | tee -a "$LOG_FILE"
echo "  PWD:      $PWD" | tee -a "$LOG_FILE"
echo "  Logging:  $LOG_FILE" | tee -a "$LOG_FILE"
echo "==========================================================" | tee -a "$LOG_FILE"

exec "${HERE}/usr/bin/tauri-videomaker" "$@" 2>&1 | tee -a "$LOG_FILE"
EOF

chmod +x "$APP_DIR/AppRun"

echo "==> [5/5] Packaging AppImage using appimagetool..."
APPIMAGETOOL=""
if command -v appimagetool >/dev/null 2>&1; then
    APPIMAGETOOL="$(command -v appimagetool)"
elif [ -x "$HOME/.local/bin/appimagetool" ]; then
    APPIMAGETOOL="$HOME/.local/bin/appimagetool"
elif [ -x "$ROOT_DIR/bin/appimagetool" ]; then
    APPIMAGETOOL="$ROOT_DIR/bin/appimagetool"
elif [ -x "/usr/local/bin/appimagetool" ]; then
    APPIMAGETOOL="/usr/local/bin/appimagetool"
else
    echo "ERROR: appimagetool not found! Please ensure appimagetool is in PATH or ~/.local/bin."
    exit 1
fi

echo "    -> Using $APPIMAGETOOL"
ARCH=x86_64 "$APPIMAGETOOL" "$APP_DIR" "$OUTPUT_APPIMAGE"

chmod +x "$OUTPUT_APPIMAGE"

# Clean up AppDir to save space
rm -rf "$APP_DIR"

echo "================================================="
echo "   ✅ TAURI DEV APPIMAGE READY!"
echo "   Location: $OUTPUT_APPIMAGE"
echo "   Size:     $(ls -lh "$OUTPUT_APPIMAGE" | awk '{print $5}')"
echo "   Live Log: /tmp/tauri_videomaker_dev.log"
echo "================================================="
