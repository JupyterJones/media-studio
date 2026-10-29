#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Novel Images Sequential Flipbook Player & Monitor Application
Allows browsing directories matching static/novel_images* with a dropdown selector
and viewing the frames in a high-performance flipbook format with adjustable FPS (1-30),
normal loop and ping-pong modes, scrubber, thumbnail gallery, and metadata inspection.
"""

import os
import sys
import glob
import json
import re
import time
import datetime
import inspect
import signal
import shutil
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from make_video import create_video_from_directory
from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
    redirect,
    url_for,
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
HOST_DIR = os.environ.get("HOST_DIR") or os.getcwd()
STATIC_DIR = os.environ.get("WORKSPACE_STATIC") or os.path.join(HOST_DIR, "static")

# Auto-create static directory and demos directory
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "demos"), exist_ok=True)

# Auto-ensure novel_images* pattern exists
pattern = os.path.join(STATIC_DIR, "novel_images*")
if not glob.glob(pattern):
    sample_dir = os.path.join(STATIC_DIR, "novel_images0")
    os.makedirs(sample_dir, exist_ok=True)
    # If app bundle has bundled sample frames, copy them over
    bundled_sample = os.path.join(BASE_DIR, "static", "novel_images0")
    if os.path.exists(bundled_sample):
        for f in os.listdir(bundled_sample):
            src_f = os.path.join(bundled_sample, f)
            dst_f = os.path.join(sample_dir, f)
            if not os.path.exists(dst_f) and os.path.isfile(src_f):
                try:
                    shutil.copyfile(src_f, dst_f)
                except Exception:
                    pass

TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
app = Flask(
    __name__,
    static_folder=STATIC_DIR,
    static_url_path="/static",
    template_folder=TEMPLATES_DIR
)
app.config["TEMPLATES_AUTO_RELOAD"] = True
LOG_FILE_PATH = os.path.join(STATIC_DIR, "app_log.txt")

# Ensure the log file exists or create it
if not os.path.exists(LOG_FILE_PATH):
    try:
        with open(LOG_FILE_PATH, "w") as f:
            f.write("")
    except Exception:
        pass


def logit(*args):
    """
    Lightweight file-based logging utility for debugging and runtime diagnostics.
    Accepts ANY number of positional arguments and safely joins them into a
    single log message.
    """
    try:
        timestr = datetime.datetime.now().strftime("%A_%b-%d-%Y_%H-%M-%S")
        frame = inspect.stack()[1]
        filename = os.path.basename(frame.filename)
        lineno = frame.lineno

        parts = []
        for arg in args:
            if isinstance(arg, (list, tuple, set)):
                parts.append(" ".join(map(str, arg)))
            else:
                parts.append(str(arg))

        message_str = " ".join(parts)
        log_message = f"{timestr} - File: {filename}, Line: {lineno}: {message_str}\n"

        with open(LOG_FILE_PATH, "a") as f:
            f.write(log_message)
    except Exception as e:
        print(f"[LOGIT ERROR] {e}")


def natural_sort_key(s):
    """Sort strings containing numbers naturally (e.g. 1, 2, 10 instead of 1, 10, 2)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def get_novel_image_directories():
    """
    Discovers all directories under static/ that match novel_images*.
    Returns a list of directory objects sorted naturally.
    """
    pattern = os.path.join(STATIC_DIR, "novel_images*")
    dir_paths = glob.glob(pattern)
    directories = []
    valid_exts = (".png", ".jpg", ".jpeg", ".webp")

    for dp in dir_paths:
        if not os.path.isdir(dp):
            continue
        dname = os.path.basename(dp)
        try:
            img_files = [
                f for f in os.listdir(dp)
                if f.lower().endswith(valid_exts) and not f.startswith(".")
            ]
            count = len(img_files)
        except Exception:
            count = 0

        # Detect metadata type
        meta_type = "generic"
        if os.path.exists(os.path.join(dp, "cfg.json")):
            meta_type = "cfg"
        elif os.path.exists(os.path.join(dp, "slerp.json")):
            meta_type = "slerp"
        elif os.path.exists(os.path.join(dp, "models.json")):
            meta_type = "models"
        elif os.path.exists(os.path.join(dp, "generations.json")):
            meta_type = "generations"

        type_labels = {
            "cfg": "CFG Sweep",
            "slerp": "SLERP Morph",
            "models": "Models Comparison",
            "generations": "Generations",
            "generic": "Image Sequence",
        }

        try:
            mtime = os.path.getmtime(dp)
        except Exception:
            mtime = 0

        directories.append({
            "name": dname,
            "count": count,
            "meta_type": meta_type,
            "type_label": type_labels.get(meta_type, "Images"),
            "mtime": mtime,
        })

    directories.sort(key=lambda d: natural_sort_key(d["name"]))
    return directories


def get_directory_data(dirname, sort_by="name", filter_prefix=""):
    """
    Retrieves all images and metadata for a specified novel_images directory.
    """
    # Security: avoid path traversal
    if not re.match(r"^novel_images[\w-]*$", dirname):
        return {"success": False, "error": f"Invalid directory name: {dirname}"}

    dir_path = os.path.join(STATIC_DIR, dirname)
    if not os.path.isdir(dir_path):
        return {"success": False, "error": f"Directory '{dirname}' does not exist"}

    valid_exts = (".png", ".jpg", ".jpeg", ".webp")
    try:
        raw_files = [
            f for f in os.listdir(dir_path)
            if f.lower().endswith(valid_exts) and not f.startswith(".")
        ]
    except Exception as e:
        return {"success": False, "error": str(e)}

    if filter_prefix:
        fp_low = filter_prefix.lower()
        raw_files = [f for f in raw_files if fp_low in f.lower()]

    if sort_by == "time":
        raw_files.sort(
            key=lambda f: os.path.getmtime(os.path.join(dir_path, f)),
            reverse=True,
        )
    else:
        raw_files.sort(key=natural_sort_key)

    # Parse metadata if present
    meta_info = {
        "type": "generic",
        "seed": "---",
        "model": "---",
        "prompt": "",
        "prompt2": "",
        "total_runs": len(raw_files),
        "last_completed_val": "---",
    }
    file_meta_map = {}

    # Check metadata JSON files in order of priority
    for candidate in ["cfg.json", "slerp.json", "models.json", "generations.json"]:
        json_path = os.path.join(dir_path, candidate)
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as jf:
                    jdata = json.load(jf)

                if candidate == "cfg.json" and "runs" in jdata:
                    meta_info["type"] = "cfg"
                    meta_info["seed"] = jdata.get("seed", "---")
                    meta_info["model"] = jdata.get("model", "---")
                    meta_info["prompt"] = jdata.get("prompt", "")
                    meta_info["total_runs"] = len(jdata.get("runs", []))
                    last_cfg = jdata.get("last_completed_cfg")
                    if last_cfg is not None:
                        meta_info["last_completed_val"] = f"{float(last_cfg):.3f}"
                    for r in jdata.get("runs", []):
                        fn = r.get("file")
                        if fn:
                            cfg_val = (
                                f"{float(r['guidance_scale']):.3f}"
                                if r.get("guidance_scale") is not None
                                else "---"
                            )
                            file_meta_map[fn] = {
                                "label": f"CFG: {cfg_val}",
                                "meta": f"CFG {cfg_val} • Step {r.get('steps', '---')}",
                                "cfg": r.get("guidance_scale"),
                                "step": r.get("steps"),
                                "seed": r.get("seed"),
                                "model": r.get("model"),
                                "prompt": r.get("prompt"),
                            }
                    break

                elif candidate == "slerp.json":
                    meta_info["type"] = "slerp"
                    meta_info["seed"] = jdata.get("seed", "---")
                    meta_info["model"] = jdata.get("model", "---")
                    meta_info["prompt"] = jdata.get("prompt1", "")
                    meta_info["prompt2"] = jdata.get("prompt2", "")
                    meta_info["total_runs"] = jdata.get(
                        "total_frames", len(jdata.get("frames", []))
                    )
                    last_t = jdata.get("last_completed_t")
                    if last_t is not None:
                        meta_info["last_completed_val"] = f"{float(last_t):.3f}"
                    for fr in jdata.get("frames", []):
                        fn = fr.get("file")
                        if fn:
                            t_val = (
                                f"{float(fr.get('t', 0.0)):.3f}"
                                if fr.get("t") is not None
                                else "0.000"
                            )
                            file_meta_map[fn] = {
                                "label": f"t = {t_val}",
                                "meta": f"t = {t_val} • Frame #{fr.get('index', 0)}",
                                "t": fr.get("t"),
                                "index": fr.get("index"),
                            }
                    break

                elif candidate == "models.json" and "runs" in jdata:
                    meta_info["type"] = "models"
                    meta_info["seed"] = jdata.get("seed", "---")
                    meta_info["model"] = jdata.get("model", "---")
                    meta_info["prompt"] = jdata.get("prompt", "")
                    meta_info["total_runs"] = len(jdata.get("runs", []))
                    for r in jdata.get("runs", []):
                        fn = r.get("file")
                        if fn:
                            m_clean = (r.get("model") or "").split(".")[0]
                            cfg_val = (
                                f"{float(r['guidance_scale']):.1f}"
                                if r.get("guidance_scale") is not None
                                else ""
                            )
                            file_meta_map[fn] = {
                                "label": m_clean or fn,
                                "meta": f"{m_clean} (CFG {cfg_val})" if cfg_val else m_clean,
                                "model": r.get("model"),
                                "cfg": r.get("guidance_scale"),
                                "step": r.get("steps"),
                                "seed": r.get("seed"),
                            }
                    break

                elif candidate == "generations.json":
                    meta_info["type"] = "generations"
                    if isinstance(jdata, dict):
                        meta_info["prompt"] = jdata.get("prompt", "")
                        meta_info["seed"] = jdata.get("seed", "---")
                        meta_info["model"] = jdata.get("model", "---")
                    break

            except Exception as e:
                logit(f"Error parsing metadata {json_path}: {e}")

    images = []
    for idx, f in enumerate(raw_files):
        fpath = os.path.join(dir_path, f)
        fm = file_meta_map.get(f, {})
        label = fm.get("label", f)
        meta = fm.get("meta", f)
        try:
            mtime = os.path.getmtime(fpath)
        except Exception:
            mtime = 0

        images.append({
            "index": idx,
            "filename": f,
            "path": f"/static/{dirname}/{f}",
            "label": label,
            "meta": meta,
            "mtime": mtime,
            "extra": fm,
        })

    return {
        "success": True,
        "directory": dirname,
        "count": len(images),
        "metadata": meta_info,
        "images": images,
    }


# --------------------------------------------------
# ROUTES
# --------------------------------------------------

@app.route("/")
@app.route("/flipbook")
def flipbook():
    """Main flipbook player view."""
    directories = get_novel_image_directories()
    selected_dir = request.args.get("dir", "").strip()

    valid_dir_names = [d["name"] for d in directories]
    if not selected_dir or selected_dir not in valid_dir_names:
        # Default to the first directory or empty
        selected_dir = valid_dir_names[0] if valid_dir_names else ""

    return render_template(
        "live_slerp.html",
        directories=directories,
        selected_dir=selected_dir,
    )


@app.route("/videos")
def videos_view():
    """Video gallery view."""
    return render_template("index.html")


@app.route("/api/directories", methods=["GET"])
def api_directories():
    """API endpoint to list all novel_images* directories."""
    dirs = get_novel_image_directories()
    return jsonify({"success": True, "directories": dirs})


@app.route("/api/images", methods=["GET"])
def api_images():
    """API endpoint to get sequential images and metadata for a directory."""
    dirname = request.args.get("dir", "").strip()
    sort_by = request.args.get("sort", "name")
    filter_prefix = request.args.get("filter", "").strip()

    if not dirname:
        dirs = get_novel_image_directories()
        if dirs:
            dirname = dirs[0]["name"]
        else:
            return jsonify({"success": False, "error": "No novel_images directories found"})

    data = get_directory_data(dirname, sort_by=sort_by, filter_prefix=filter_prefix)
    return jsonify(data)


@app.route("/api/export_video", methods=["POST"])
def api_export_video():
    """
    API endpoint to generate an MP4 video from the currently viewed novel_images directory.
    Respects current view FPS, loop mode (normal or ping-pong), sort order, and filters.
    """
    req = request.get_json(force=True, silent=True) or {}
    dirname = req.get("dir", "").strip()
    raw_fps = req.get("fps", 10)
    try:
        fps = max(1, min(60, int(float(raw_fps))))
    except (ValueError, TypeError):
        fps = 10

    pingpong = bool(req.get("pingpong", False))
    raw_loops = req.get("loops", 1)
    try:
        loops = max(1, min(10, int(raw_loops)))
    except (ValueError, TypeError):
        loops = 1

    sort_by = req.get("sort", "name")
    filter_keyword = req.get("filter", "").strip()

    raw_start = req.get("start_frame")
    raw_end = req.get("end_frame")
    start_frame = int(raw_start) if raw_start is not None else None
    end_frame = int(raw_end) if raw_end is not None else None

    if not dirname:
        dirs = get_novel_image_directories()
        if dirs:
            dirname = dirs[0]["name"]
        else:
            return jsonify({"success": False, "error": "No novel_images directories found"})

    try:
        result = create_video_from_directory(
            dir_name_or_path=dirname,
            fps=fps,
            pingpong=pingpong,
            loops=loops,
            filter_keyword=filter_keyword,
            sort_by=sort_by,
            start_frame=start_frame,
            end_frame=end_frame
        )
        rel_video_path = os.path.relpath(result["output_path"], STATIC_DIR)
        return jsonify({
            "success": True,
            "filename": os.path.basename(result["output_path"]),
            "video_url": f"/static/{rel_video_path}",
            "file_size_mb": round(result["filesize_mb"], 2),
            "fps": result["fps"],
            "frames": result["frames"],
            "duration": round(result["duration"], 2),
            "elapsed": round(result["elapsed"], 2),
            "start_frame": result.get("start_frame"),
            "end_frame": result.get("end_frame"),
            "is_reverse": result.get("is_reverse", False)
        })
    except Exception as e:
        logit(f"Video export error for {dirname}: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route("/favicon.ico")
def favicon():
    """Dynamic favicon generator."""
    size = (32, 32)
    favicon_img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(favicon_img)
    draw.ellipse([(0, 0), size], fill=(255, 255, 0))

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

    try:
        font = ImageFont.truetype(font_path, 24)
        text = "F"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_pos = ((size[0] - text_width) // 2, (size[1] - text_height) // 2)
        draw.text(text_pos, text, font=font, fill=(255, 0, 0))
    except Exception:
        pass

    buf = BytesIO()
    favicon_img.save(buf, format="ICO")
    buf.seek(0)
    return Response(buf.getvalue(), content_type="image/x-icon")


# --------------------------------------------------
# MAIN
# --------------------------------------------------

if __name__ == "__main__":
    def exit_gracefully(signum, frame):
        print("\n[*] Shutting down Flipbook server gracefully...")
        os._exit(0)

    signal.signal(signal.SIGINT, exit_gracefully)
    signal.signal(signal.SIGTERM, exit_gracefully)

    print("[*] Starting Novel Images Flipbook server on http://localhost:5300 ...")
    app.run(debug=True, host="0.0.0.0", port=5300)
