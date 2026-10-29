#!/usr/bin/env bash
set -e

# Change to repository root
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

APP_DIR="$ROOT_DIR/AppDir"
OUTPUT_APPIMAGE="$ROOT_DIR/MediaStudio-VideoMaker-x86_64.AppImage"

echo "================================================="
echo "   🎬 BUILDING MEDIASTUDIO VIDEOMAKER APPIMAGE   "
echo "================================================="

echo "==> [1/5] Preparing AppDir structure..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/usr/bin"
mkdir -p "$APP_DIR/usr/share/applications"
mkdir -p "$APP_DIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APP_DIR/usr/share/sample_frames"
mkdir -p "$APP_DIR/usr/lib/python3/site-packages"

echo "==> [2/5] Copying application code and assets..."
cp "$ROOT_DIR/app.py" "$APP_DIR/usr/bin/app.py"
cp "$ROOT_DIR/make_video.py" "$APP_DIR/usr/bin/make_video.py"
chmod +x "$APP_DIR/usr/bin/app.py" "$APP_DIR/usr/bin/make_video.py"

cp -r "$ROOT_DIR/templates" "$APP_DIR/usr/bin/templates"

# Only bundle sample frames (novel_images0) rather than all local work directories
mkdir -p "$APP_DIR/usr/bin/static/demos"
if [ -d "$ROOT_DIR/static/novel_images0" ]; then
    mkdir -p "$APP_DIR/usr/bin/static/novel_images0"
    cp "$ROOT_DIR/static/novel_images0"/* "$APP_DIR/usr/bin/static/novel_images0/" 2>/dev/null || true
    cp "$ROOT_DIR/static/novel_images0"/* "$APP_DIR/usr/share/sample_frames/" 2>/dev/null || true
fi

# Bundle ffmpeg binary for 100% self-contained portable execution
FFMPEG_SRC="$(which ffmpeg 2>/dev/null || echo "/usr/local/bin/ffmpeg")"
if [ -x "$FFMPEG_SRC" ]; then
    echo "    -> Embedding ffmpeg binary from $FFMPEG_SRC..."
    cp "$FFMPEG_SRC" "$APP_DIR/usr/bin/ffmpeg"
    chmod +x "$APP_DIR/usr/bin/ffmpeg"
fi

echo "==> [3/5] Bundling Python dependencies (Flask, Pillow, Jinja2, etc.)..."
SITE_PACKAGES_DIR="$APP_DIR/usr/lib/python3/site-packages"

# Dynamically locate Python site-packages
VENV_PACKAGES=""
if [ -n "$VIRTUAL_ENV" ] && [ -d "$VIRTUAL_ENV/lib" ]; then
    VENV_PACKAGES="$(find "$VIRTUAL_ENV/lib" -type d -name "site-packages" 2>/dev/null | head -n 1 || true)"
fi
if [ -z "$VENV_PACKAGES" ] || [ ! -d "$VENV_PACKAGES" ]; then
    VENV_PACKAGES="$(python3 -c 'import flask, os; print(os.path.dirname(os.path.dirname(flask.__file__)))' 2>/dev/null || true)"
fi
if [ -z "$VENV_PACKAGES" ] || [ ! -d "$VENV_PACKAGES" ]; then
    VENV_PACKAGES="$(python3 -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null || true)"
fi

if [ -z "$VENV_PACKAGES" ] || [ ! -d "$VENV_PACKAGES" ]; then
    echo "ERROR: Could not locate Python site-packages with Flask and Pillow!"
    exit 1
fi
echo "    -> Using Python packages from: $VENV_PACKAGES"

LIBS_TO_BUNDLE=(
    "flask"
    "werkzeug"
    "jinja2"
    "click"
    "itsdangerous"
    "blinker"
    "markupsafe"
    "PIL"
    "pillow.libs"
)

for lib in "${LIBS_TO_BUNDLE[@]}"; do
    if [ -d "$VENV_PACKAGES/$lib" ]; then
        cp -r "$VENV_PACKAGES/$lib" "$SITE_PACKAGES_DIR/"
    elif [ -f "$VENV_PACKAGES/$lib.py" ]; then
        cp "$VENV_PACKAGES/$lib.py" "$SITE_PACKAGES_DIR/"
    fi
    for dist in "$VENV_PACKAGES"/$lib*.dist-info; do
        if [ -d "$dist" ]; then
            cp -r "$dist" "$SITE_PACKAGES_DIR/"
        fi
    done
done

# Copy Icon
ICON_SRC="$ROOT_DIR/icon.png"
if [ ! -f "$ICON_SRC" ]; then
    ICON_SRC="$ROOT_DIR/tauri_app/src-tauri/icons/icon.png"
fi
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$APP_DIR/mediastudio.png"
    cp "$ICON_SRC" "$APP_DIR/usr/share/icons/hicolor/256x256/apps/mediastudio.png"
fi

echo "==> [4/5] Creating Desktop Entry and AppRun..."
cat << 'EOF' > "$APP_DIR/mediastudio.desktop"
[Desktop Entry]
Type=Application
Name=MediaStudio VideoMaker
GenericName=Image Sequence to Video Studio
Comment=High-performance image flipbook player and video exporter
Exec=AppRun %F
Icon=mediastudio
Categories=AudioVideo;Video;Graphics;
Terminal=false
StartupNotify=true
EOF

cp "$APP_DIR/mediastudio.desktop" "$APP_DIR/usr/share/applications/mediastudio.desktop"

cat << 'EOF' > "$APP_DIR/AppRun"
#!/usr/bin/env bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}

export HERE
export PATH="${HERE}/usr/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"
export PYTHONPATH="${HERE}/usr/lib/python3/site-packages:${PYTHONPATH}"
export PYTHONUNBUFFERED=1

# Determine host workspace directory (where the user opened or called the AppImage)
HOST_DIR="$PWD"
export HOST_DIR
export WORKSPACE_STATIC="${HOST_DIR}/static"

# Auto-create static directory and demos directory if missing
mkdir -p "${WORKSPACE_STATIC}"
mkdir -p "${WORKSPACE_STATIC}/demos"

# Auto-ensure pattern = os.path.join(STATIC_DIR, "novel_images*")
shopt -s nullglob
matching_dirs=("${WORKSPACE_STATIC}"/novel_images*)
shopt -u nullglob

if [ ${#matching_dirs[@]} -eq 0 ]; then
    echo "[*] Auto-creating default ${WORKSPACE_STATIC}/novel_images0 directory..."
    mkdir -p "${WORKSPACE_STATIC}/novel_images0"
    if [ -d "${HERE}/usr/share/sample_frames" ]; then
        cp -n "${HERE}/usr/share/sample_frames"/* "${WORKSPACE_STATIC}/novel_images0/" 2>/dev/null || true
    fi
fi

# Check CLI arguments:
# If user passed arguments (like --dir, --fps, etc.), execute CLI video generator directly
if [ "$#" -gt 0 ] && [ "$1" != "%F" ] && [ "$1" != "%f" ] && [ "$1" != "%U" ] && [ "$1" != "%u" ]; then
    exec python3 "${HERE}/usr/bin/make_video.py" "$@"
fi

# Otherwise, launch Flask Web Studio and open browser
echo "=========================================================="
echo " 🎬 MediaStudio VideoMaker"
echo " 📁 Working Directory : ${HOST_DIR}"
echo " 📁 Static Directory  : ${WORKSPACE_STATIC}"
echo " 🌐 Launching UI on   : http://localhost:5300"
echo "=========================================================="

# Auto-open browser in background after 1.5 seconds
(
    sleep 1.5
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://localhost:5300" >/dev/null 2>&1
    elif command -v sensible-browser >/dev/null 2>&1; then
        sensible-browser "http://localhost:5300" >/dev/null 2>&1
    fi
) &

exec python3 "${HERE}/usr/bin/app.py"
EOF

chmod +x "$APP_DIR/AppRun"

echo "==> [5/5] Packaging AppImage..."
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
    echo "ERROR: appimagetool not found! Please install appimagetool or place it in ~/.local/bin or PATH."
    exit 1
fi

echo "    -> Using appimagetool: $APPIMAGETOOL"
ARCH=x86_64 "$APPIMAGETOOL" "$APP_DIR" "$OUTPUT_APPIMAGE"
chmod +x "$OUTPUT_APPIMAGE"

# Clean up AppDir to save space
rm -rf "$APP_DIR"

echo "================================================="
echo "   ✓ APPIMAGE SUCCESSFULLY CREATED!              "
echo "   - Local: $OUTPUT_APPIMAGE"
echo "================================================="
ls -lh "$OUTPUT_APPIMAGE"
