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
HOST_DIR = os.environ.get("HOST_DIR") or os.getcwd()
STATIC_DIR = os.environ.get("WORKSPACE_STATIC") or os.path.join(HOST_DIR, "static")

# Auto-create static directory and demos directory
os.makedirs(STATIC_DIR, exist_ok=True)
DEMOS_DIR = os.path.join(STATIC_DIR, "demos")
os.makedirs(DEMOS_DIR, exist_ok=True)

# Auto-ensure novel_images* pattern exists
pattern = os.path.join(STATIC_DIR, "novel_images*")
if not glob.glob(pattern):
    sample_dir = os.path.join(STATIC_DIR, "novel_images0")
    os.makedirs(sample_dir, exist_ok=True)


def natural_sort_key(s):
    """Sort strings containing numbers naturally (e.g., 1, 2, 10 instead of 1, 10, 2)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def prune_old_videos(demos_dir=DEMOS_DIR, max_videos=1000):
    """
    Ensures only the latest `max_videos` files are kept in the demos directory.
    Deletes the oldest files if the count exceeds max_videos.
    """
    if not os.path.exists(demos_dir):
        return
    try:
        videos = [
            os.path.join(demos_dir, f)
            for f in os.listdir(demos_dir)
            if f.lower().endswith((".mp4", ".webm", ".mkv")) and os.path.isfile(os.path.join(demos_dir, f))
        ]
        if len(videos) > max_videos:
            # Sort by modification time, newest first
            videos.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            excess_videos = videos[max_videos:]
            for old_video in excess_videos:
                try:
                    os.remove(old_video)
                except OSError as e:
                    print(f"[WARN] Failed to delete old video {old_video}: {e}")
            print(f"[*] Pruned {len(excess_videos)} old video(s); retained the latest {max_videos}.")
    except Exception as e:
        print(f"[WARN] Video pruning error: {e}")


def create_video_from_directory(
    dir_name_or_path,
    fps=10,
    pingpong=False,
    loops=1,
    output_path=None,
    filter_keyword=None,
    sort_by="name",
    start_frame=None,
    end_frame=None
):
    """
    Renders sequential images from a directory into a high-quality H.264 MP4 video.
    Supports start_frame and end_frame slicing (1-based indices), with automatic
    reverse order if start_frame > end_frame.
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
    total_available = len(image_paths)

    # Frame Range (Start & End) slicing
    range_suffix = ""
    is_reverse = False
    actual_start = 1
    actual_end = total_available

    if start_frame is not None or end_frame is not None:
        try:
            s = int(start_frame) if start_frame is not None else 1
        except (ValueError, TypeError):
            s = 1
        try:
            e = int(end_frame) if end_frame is not None else total_available
        except (ValueError, TypeError):
            e = total_available

        # Clamp between 1 and total_available
        s = max(1, min(total_available, s))
        e = max(1, min(total_available, e))
        actual_start = s
        actual_end = e

        if s <= e:
            # Forward sequence
            image_paths = image_paths[s - 1 : e]
            range_suffix = f"_f{s}-to-f{e}"
        else:
            # Reverse sequence (e.g. frame 50 down to frame 10)
            is_reverse = True
            image_paths = image_paths[e - 1 : s][::-1]
            range_suffix = f"_f{s}-to-f{e}_REV"

    if not image_paths:
        raise ValueError("Selected frame range resulted in 0 frames")

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
        out_filename = f"{dir_basename}{range_suffix}_{fps}fps{mode_suffix}_{timestamp}.mp4"
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

        # Resolve ffmpeg binary path explicitly
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            for fallback in ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/bin/ffmpeg"]:
                if os.path.exists(fallback):
                    ffmpeg_bin = fallback
                    break
        if not ffmpeg_bin:
            raise FileNotFoundError("Could not find 'ffmpeg' executable in PATH or standard system locations.")

        ffmpeg_cmd = [
            ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "warning",
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

    # Automatically keep only the latest 1000 generated videos
    prune_old_videos(demos_dir=os.path.dirname(os.path.abspath(output_path)), max_videos=1000)

    return {
        "output_path": output_path,
        "frames": total_frames,
        "fps": fps,
        "duration": duration,
        "filesize_mb": filesize_mb,
        "elapsed": elapsed,
        "start_frame": actual_start,
        "end_frame": actual_end,
        "is_reverse": is_reverse
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
        "--fps", "-r", type=int, default=10,
        help="Frame rate in frames per second (default: 10)"
    )
    parser.add_argument(
        "--pingpong", "-p", action="store_true",
        help="Create a ping-pong loop (forward then backward)"
    )
    parser.add_argument(
        "--loops", "-l", type=int, default=1,
        help="Number of times to repeat the sequence (default: 1)"
    )
    parser.add_argument(
        "--start-frame", "-s", type=int, default=None,
        help="Optional 1-based start frame number (e.g. 10)"
    )
    parser.add_argument(
        "--end-frame", "-e", type=int, default=None,
        help="Optional 1-based end frame number (e.g. 45). If start > end, video is reversed."
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
            sort_by=args.sort,
            start_frame=args.start_frame,
            end_frame=args.end_frame
        )
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
