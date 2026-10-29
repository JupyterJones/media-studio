# Installation & Setup Guide

This guide covers all system prerequisites (`apt`), Python virtual environment setup (`requirements.txt`), running the applications from source, and compiling standalone AppImages.

---

## 1. System Requirements & APT Packages (Ubuntu / Debian)

Ensure your system is up to date and install the required core system packages:

### Core Runtime (CLI & Python Studio)
```bash
sudo apt update && sudo apt install -y \
    ffmpeg \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    unzip
```

> [!NOTE]
> **AppImage Runtime (FUSE)**: Modern Ubuntu versions require the FUSE compatibility library to run AppImages:
> - **Ubuntu 24.04+**: `sudo apt install -y libfuse2t64`
> - **Ubuntu 22.04 / Debian 11+**: `sudo apt install -y libfuse2`

---

### Optional: Dependencies for Compiling Tauri & Electron From Source

If you intend to compile the **Tauri (Rust)** or **Electron** apps from source:

#### For Tauri (WebKitGTK + Rust):
```bash
sudo apt install -y \
    build-essential \
    libwebkit2gtk-4.1-dev \
    libgtk-3-dev \
    libayatana-appindicator3-dev \
    librsvg2-dev \
    libssl-dev
```
Install the Rust toolchain (if not already installed):
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
```

#### For Electron (Node.js):
Ensure Node.js (v18+) and npm are installed:
```bash
sudo apt install -y nodejs npm
```

#### For Packaging AppImages (`appimagetool`):
Download and place `appimagetool` in your `~/.local/bin` or system PATH:
```bash
mkdir -p ~/.local/bin
curl -L -o ~/.local/bin/appimagetool "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
chmod +x ~/.local/bin/appimagetool
```

---

## 2. Python Virtual Environment Setup

Set up a dedicated virtual environment and install the required Python packages:

```bash
# 1. Create a virtual environment
python3 -m venv venv

# 2. Activate the virtual environment
source venv/bin/activate

# 3. Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### `requirements.txt` Details
- **`Flask>=3.0.0`**: Powers the lightweight local web studio interface and API endpoints.
- **`Pillow>=10.0.0`**: Provides fast image decoding, inspection, thumbnail resizing, and frame validation.

---

## 3. Running Media Studio From Source

### A. Python / Flask Web Studio
```bash
source venv/bin/activate
python3 app.py
```
Open your browser to `http://localhost:5300`.

### B. CLI Video Encoder
```bash
source venv/bin/activate

# Basic encode from a directory matching static/novel_images*
python3 make_video.py --dir novel_images0 --fps 12

# Cut trimming with ping-pong loop
python3 make_video.py --dir novel_images0 --fps 15 --start-frame 10 --end-frame 50 --pingpong
```

### C. Native Electron Desktop App
```bash
cd electron_app
npm start
```

### D. Native Tauri Rust Desktop App
```bash
cd tauri_app/src-tauri
cargo run --release
```

---

## 4. Building Standalone AppImages

To build fully self-contained portable `.AppImage` binaries that run without installation:

```bash
# 1. Standard Python/Flask AppImage (~80 MB)
chmod +x build_appimage.sh
./build_appimage.sh

# 2. Native Electron Desktop AppImage (~191 MB)
chmod +x build_electron_appimage.sh
./build_electron_appimage.sh

# 3. Lightweight Native Rust/Tauri AppImage (~74 MB)
chmod +x build_tauri_appimage.sh
./build_tauri_appimage.sh
```

All three AppImages will be generated directly in the project directory.
