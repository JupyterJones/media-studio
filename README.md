# Media Studio (VideoMaker)

> High-performance image sequence flipbook player, cut trimmer, and instant MP4 video exporter designed for AI generations, stop motion, timelapses, and rendering pipelines.

Media Studio transforms sequential image frames (`.png`, `.jpg`, `.jpeg`, `.webp`) into smooth, animated flipbooks and exported MP4 videos with frame-accurate control over framerate, sub-range slicing, forward/reverse playback, and ping-pong looping.

---

## ⚡ Quick Start

You can run Media Studio through any of its three pre-built standalone AppImages, or directly from source.

### Option 1: Standalone AppImages (Zero Installation)
Ensure the file is executable and run:

```bash
# 1. Standard Python / Flask Studio (auto-launches in browser on port 5300)
./MediaStudio-VideoMaker-x86_64.AppImage

# 2. Native Electron Desktop Window
./Electron-VideoMaker-x86_64.AppImage

# 3. Lightweight Native Rust / WebKitGTK Studio (~74 MB)
./Tauri-VideoMaker-x86_64.AppImage
```

### Option 2: Running from Source
See [INSTALLMENT.md](file:///home/jack/Desktop/media-studio/INSTALLMENT.md) for complete `apt` package prerequisites and `requirements.txt` environment setup.

```bash
# Activate your virtual environment
source venv/bin/activate

# Launch the Web Studio
python3 app.py
```

---

## 📁 Image Directory Structure & "novel_images*" Pattern

Media Studio automatically scans the current working directory for folders beginning with `novel_images*`:

```text
media-studio/
├── static/
│   ├── novel_images0/           <-- Image sequences (auto-detected)
│   │   ├── frame_0001.png
│   │   ├── frame_0002.png
│   │   └── frame_0003.png
│   ├── novel_images_morph/      <-- Another sequence
│   │   ├── 001.jpg
│   │   └── 002.jpg
│   └── demos/                   <-- Auto-created folder for exported MP4 videos
├── MediaStudio-VideoMaker-x86_64.AppImage
├── Electron-VideoMaker-x86_64.AppImage
└── Tauri-VideoMaker-x86_64.AppImage
```

> [!TIP]
> **Automatic Setup**: If no `novel_images*` directory exists when the studio starts, it automatically creates `static/novel_images0/` seeded with sample frames and prepares `static/demos/` for video output.

---

## 🎮 Interface Controls & Features

### 1. Sequential Flipbook Playback
- **Speed Slider (1–60 FPS)**: Directly syncs live view speed with the exported video framerate.
- **Scrubber Bar**: Jump to any frame instantly or scrub smoothly through the animation.
- **Play / Pause**: Toggle playback with instant responsiveness.
- **Frame Stepping**: Step forward or backward frame-by-frame for micro-inspection.

### 2. Cut Trimming & Range Selection
- **`📍 Set Start`**: Sets the cut in-point to the current frame.
- **`🏁 Set End`**: Sets the cut out-point to the current frame.
- **`⇄ Swap (Reverse)`**: Flips the start and end markers to reverse the animation.
- **Automatic Reverse Detection**: Setting `Start Frame > End Frame` (e.g., 50 to 10) automatically generates a reverse-motion video without manual re-ordering.
- **`▶ Preview Cut`**: Loops playback strictly within the selected range before exporting.

### 3. Looping & Effects
- **Loop Modes**: Normal continuous playback or **Ping-Pong** (plays forward to the end, then reverses back smoothly).
- **Loop Multiplier**: Multiply the sequence 1–10 times in the final exported video.

### 4. Video Rendering & MP4 Export
- **One-Click Export**: Click **`🎬 Make Movie`** to encode using embedded hardware-compatible FFmpeg (`libx264`, `yuv420p`, CRF 18).
- **Inline Video Player**: Preview the rendered MP4 directly inside the application upon completion.
- **Instant Download**: Directly download the MP4 or locate it saved in `./static/demos/`.

### 5. Thumbnail Filmstrip & Metadata
- **Interactive Filmstrip**: Browse visual thumbnails along the bottom edge to quickly find keyframes.
- **Frame Inspector**: Displays image dimensions, filename, frame index, and parent sequence metadata.

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Space` | Play / Pause sequence |
| `Left Arrow` | Step 1 frame backward |
| `Right Arrow` | Step 1 frame forward |
| `Home` | Jump to first frame |
| `End` | Jump to last frame |
| `[` | Mark current frame as Cut Start |
| `]` | Mark current frame as Cut End |
| `P` | Toggle Cut Preview loop |

---

## 💻 Command Line (CLI) Video Generation

You can generate MP4 videos directly from your terminal in headless environments or batch scripts using either the Python script or the AppImage:

```bash
# Method A: Using the portable AppImage
./MediaStudio-VideoMaker-x86_64.AppImage [OPTIONS]

# Method B: Using python directly
python3 make_video.py [OPTIONS]
```

### CLI Examples

```bash
# 1. Export all frames from novel_images0 at 12 FPS
python3 make_video.py --dir novel_images0 --fps 12

# 2. Export a trimmed range (frames 15 to 45) at 24 FPS with a Ping-Pong loop
python3 make_video.py --dir novel_images0 --fps 24 --start-frame 15 --end-frame 45 --pingpong

# 3. Export in REVERSE by setting start greater than end
python3 make_video.py --dir novel_images0 --fps 15 --start-frame 60 --end-frame 1

# 4. Repeat sequence 3 times and save to a custom path
python3 make_video.py --dir novel_images0 --loops 3 --output ./my_animation.mp4

# 5. Filter frames matching a keyword and sort by modification timestamp
python3 make_video.py --dir novel_images0 --filter "seed42" --sort time
```

### CLI Options Reference

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `--dir` | `-d` | **Required**: Directory name or path containing images | — |
| `--fps` | `-r` | Framerate in frames per second (1–60) | `10` |
| `--start-frame`| `-s` | 1-based start frame index | `1` |
| `--end-frame` | `-e` | 1-based end frame index (reverse if `< start`) | Last frame |
| `--pingpong` | `-p` | Enable forward-then-reverse ping-pong loop | Disabled |
| `--loops` | `-l` | Number of times to repeat the sequence | `1` |
| `--filter` | `-f` | Filter filenames by substring | None |
| `--sort` | | Sorting strategy: `name` (natural sort) or `time` | `name` |
| `--output` | `-o` | Custom output MP4 destination file path | `static/demos/<auto>.mp4` |

---

## 🛠️ Installation & Compiling

For full installation instructions, APT package requirements for Ubuntu/Debian, Python environment setup, and steps for building all three AppImages, refer to:

👉 **[INSTALLMENT.md](file:///home/jack/Desktop/media-studio/INSTALLMENT.md)**
