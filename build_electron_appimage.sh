#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

APP_DIR="$ROOT_DIR/AppDir_Electron"
OUTPUT_APPIMAGE="$ROOT_DIR/Electron-VideoMaker-x86_64.AppImage"

echo "================================================="
echo "   ⚡ BUILDING ELECTRON-VIDEOMAKER APPIMAGE       "
echo "================================================="

echo "==> [1/5] Extracting Electron runtime..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"

CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/electron"
ELECTRON_ZIP="$(find "$CACHE_DIR" -name "electron-v*-linux-x64.zip" 2>/dev/null | head -n 1 || true)"
if [ -z "$ELECTRON_ZIP" ] || [ ! -f "$ELECTRON_ZIP" ]; then
    echo "Electron zip not found in cache ($CACHE_DIR), attempting download..."
    mkdir -p "$CACHE_DIR"
    ELECTRON_VER="v33.2.0"
    ELECTRON_URL="https://github.com/electron/electron/releases/download/${ELECTRON_VER}/electron-${ELECTRON_VER}-linux-x64.zip"
    curl -L "$ELECTRON_URL" -o "$CACHE_DIR/electron-${ELECTRON_VER}-linux-x64.zip" 2>/dev/null || wget "$ELECTRON_URL" -O "$CACHE_DIR/electron-${ELECTRON_VER}-linux-x64.zip"
    ELECTRON_ZIP="$CACHE_DIR/electron-${ELECTRON_VER}-linux-x64.zip"
fi
if [ -z "$ELECTRON_ZIP" ] || [ ! -f "$ELECTRON_ZIP" ]; then
    echo "ERROR: Electron prebuilt zip could not be found or downloaded!"
    exit 1
fi
echo "    -> Using $ELECTRON_ZIP"
unzip -q "$ELECTRON_ZIP" -d "$APP_DIR"
rm -f "$APP_DIR/resources/default_app.asar"

echo "==> [2/5] Installing Electron App & static assets..."
APP_RESOURCES="$APP_DIR/resources/app"
mkdir -p "$APP_RESOURCES"

cp "$ROOT_DIR/electron_app/package.json" "$APP_RESOURCES/"
cp "$ROOT_DIR/electron_app/main.cjs" "$APP_RESOURCES/"
cp "$ROOT_DIR/electron_app/index.html" "$APP_RESOURCES/"

# Bundle sample frames for standalone initial demo
mkdir -p "$APP_RESOURCES/static/novel_images-Appdemo"
if [ -d "$ROOT_DIR/static/novel_images0" ]; then
    cp "$ROOT_DIR/static/novel_images0"/* "$APP_RESOURCES/static/novel_images-Appdemo/" 2>/dev/null || true
fi

echo "==> [3/5] Embedding standalone FFmpeg..."
mkdir -p "$APP_DIR/bin"
FFMPEG_SRC="$(which ffmpeg 2>/dev/null || echo "/usr/local/bin/ffmpeg")"
if [ -x "$FFMPEG_SRC" ]; then
    echo "    -> Copying ffmpeg from $FFMPEG_SRC..."
    cp "$FFMPEG_SRC" "$APP_DIR/bin/ffmpeg"
    chmod +x "$APP_DIR/bin/ffmpeg"
fi

# Icon
ICON_SRC="$ROOT_DIR/icon.png"
if [ ! -f "$ICON_SRC" ]; then
    ICON_SRC="$ROOT_DIR/tauri_app/src-tauri/icons/icon.png"
fi
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$APP_DIR/electron.png"
    cp "$ICON_SRC" "$APP_RESOURCES/icon.png"
fi

echo "==> [4/5] Creating Desktop Entry and AppRun..."
cat << 'EOF' > "$APP_DIR/electron-videomaker.desktop"
[Desktop Entry]
Type=Application
Name=Electron VideoMaker
GenericName=Native Desktop Video Maker Studio
Comment=Native Electron high-performance image flipbook player and video exporter
Exec=AppRun %F
Icon=electron
Categories=AudioVideo;Video;Graphics;
Terminal=false
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

exec "${HERE}/electron" "${HERE}/resources/app" --no-sandbox "$@"
EOF

chmod +x "$APP_DIR/AppRun" "$APP_DIR/electron"

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
fi

if [ -z "$APPIMAGETOOL" ]; then
    echo "ERROR: appimagetool not found! Please ensure appimagetool is in PATH or ~/.local/bin."
    exit 1
fi

echo "    -> Using appimagetool: $APPIMAGETOOL"
ARCH=x86_64 "$APPIMAGETOOL" "$APP_DIR" "$OUTPUT_APPIMAGE"
chmod +x "$OUTPUT_APPIMAGE"

# Clean up temporary AppDir to save disk space
rm -rf "$APP_DIR"

echo "================================================="
echo "   ✓ ELECTRON APPIMAGE SUCCESSFULLY CREATED!     "
echo "   - Local: $OUTPUT_APPIMAGE"
echo "================================================="
ls -lh "$OUTPUT_APPIMAGE"
