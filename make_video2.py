#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_video.py - Generate MP4 videos from sequential images at custom FPS.

Usage:
    python3 make_video.py --dir novel_images6 --fps 15
    python3 make_video.py --dir static/novel_images0 --fps 10 --pingpong
    python3 make_video.py --dir novel_images4 --fps 24 --loops 2 --output my_video.mp4
"""

import os
import sys
import glob
import re
import argparse
import tempfile
import subprocess
import shutil
import time
from PIL import Image

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DEMOS_DIR = os.path.join(STATIC_DIR, "demos")


def natural_sort_key(s):
    """Sort strings containing numbers naturally (e.g., 1, 2, 10 instead of 1, 10, 2)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def create_video_from_directory(
    dir_name_or_path,
    fps=1,
    pingpong=False,
    loops=2,
    output_path=None,
    filter_keyword=None,
    sort_by="name"
):
    """
    Renders sequential images from a directory into a high-quality H.264 MP4 video.
    """
    # Resolve directory path
    if os.path.isabs(dir_name_or_path):
        target_dir = dir_name_or_path
    elif os.path.isdir(os.path.join(STATIC_DIR, dir_name_or_path)):
        target_dir = os.path.join(STATIC_DIR, dir_name_or_path)
    elif os.path.isdir(dir_name_or_path):
        target_dir = os.path.abspath(dir_name_or_path)
    else:
        raise FileNotFoundError(f"Directory not found: {dir_name_or_path}")

    dir_basename = os.path.basename(target_dir.rstrip("/\\"))
    valid_exts = (".png", ".jpg", ".jpeg", ".webp")

    # Discover and sort files
    raw_files = [
        f for f in os.listdir(target_dir)
        if f.lower().endswith(valid_exts) and not f.startswith(".")
    ]

    if filter_keyword:
        kw = filter_keyword.lower()
        raw_files = [f for f in raw_files if kw in f.lower()]

    if not raw_files:
        raise ValueError(f"No valid image frames found in {target_dir}")

    if sort_by == "time":
        raw_files.sort(key=lambda f: os.path.getmtime(os.path.join(target_dir, f)), reverse=True)
    else:
        raw_files.sort(key=natural_sort_key)

    image_paths = [os.path.join(target_dir, f) for f in raw_files]

    # Apply ping-pong ordering if requested
    if pingpong and len(image_paths) > 2:
        image_paths = image_paths + image_paths[-2:0:-1]

    # Apply loops
    if loops > 1:
        image_paths = image_paths * loops

    total_frames = len(image_paths)

    # Determine output path
    if not output_path:
        os.makedirs(DEMOS_DIR, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        mode_suffix = "_pingpong" if pingpong else ""
        out_filename = f"{dir_basename}_{fps}fps{mode_suffix}_{timestamp}.mp4"
        output_path = os.path.join(DEMOS_DIR, out_filename)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    print(f"[*] Preparing {total_frames} frames from '{dir_basename}' at {fps} FPS...")
    start_time = time.time()

    # Create temporary directory with normalized frames for FFmpeg
    with tempfile.TemporaryDirectory(prefix="flipbook_vid_") as tmpdir:
        for idx, img_path in enumerate(image_paths):
            target_symlink = os.path.join(tmpdir, f"frame_{idx:06d}.png")
            if img_path.lower().endswith(".png"):
                try:
                    os.symlink(os.path.abspath(img_path), target_symlink)
                except Exception:
                    shutil.copyfile(img_path, target_symlink)
            else:
                # Convert jpg/webp on the fly
                try:
                    with Image.open(img_path) as im:
                        im.convert("RGB").save(target_symlink, "PNG")
                except Exception as e:
                    print(f"[!] Warning: failed to convert {img_path}: {e}")

        # Execute FFmpeg encoding
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
            "-framerate", str(fps),
            "-i", os.path.join(tmpdir, "frame_%06d.png"),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "18",
            output_path
        ]

        res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg failed with code {res.returncode}:\n{res.stderr}")

    duration = total_frames / fps
    filesize_mb = os.path.getsize(output_path) / (1024 * 1024)
    elapsed = time.time() - start_time

    print(f"[✓] Success! Video created in {elapsed:.2f}s:")
    print(f"    - Destination: {output_path}")
    print(f"    - Frames:      {total_frames}")
    print(f"    - Framerate:   {fps} FPS")
    print(f"    - Duration:    {duration:.2f}s")
    print(f"    - File Size:   {filesize_mb:.2f} MB")

    return {
        "output_path": output_path,
        "frames": total_frames,
        "fps": fps,
        "duration": duration,
        "filesize_mb": filesize_mb,
        "elapsed": elapsed
    }


def main():
    parser = argparse.ArgumentParser(
        description="Convert sequential images from novel_images directories to MP4 video."
    )
    parser.add_argument(
        "--dir", "-d", required=True,
        help="Directory name (e.g., novel_images6) or path containing images"
    )
    parser.add_argument(
        "--fps", "-r", type=int, default=1,
        help="Frame rate in frames per second (default: 10)"
    )
    parser.add_argument(
        "--pingpong", "-p", action="store_true",
        help="Create a ping-pong loop (forward then backward)"
    )
    parser.add_argument(
        "--loops", "-l", type=int, default=2,
        help="Number of times to repeat the sequence (default: 1)"
    )
    parser.add_argument(
        "--filter", "-f", default=None,
        help="Optional text filter for filenames (e.g. .png or seed)"
    )
    parser.add_argument(
        "--sort", choices=["name", "time"], default="name",
        help="Sort frames naturally by filename or by timestamp (default: name)"
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Custom output file path (.mp4)"
    )

    args = parser.parse_args()

    try:
        create_video_from_directory(
            dir_name_or_path=args.dir,
            fps=args.fps,
            pingpong=args.pingpong,
            loops=args.loops,
            output_path=args.output,
            filter_keyword=args.filter,
            sort_by=args.sort
        )
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
