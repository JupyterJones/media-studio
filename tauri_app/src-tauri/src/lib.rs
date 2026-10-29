use std::collections::{HashMap, HashSet};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::Arc;
use std::time::Instant;
use tiny_http::{Header, Response, Server, StatusCode};
use url::Url;

pub fn log_dev(msg: &str) {
    let dur = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    let line = format!("[{:010}] [TAURI-DEV] {}\n", dur.as_secs(), msg);
    print!("{}", line);
    let _ = std::io::stdout().flush();

    let paths = [
        PathBuf::from("/tmp/tauri_videomaker_dev.log"),
    ];
    for p in &paths {
        if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(p) {
            let _ = f.write_all(line.as_bytes());
        }
    }
}

// Natural sort key representation
#[derive(Clone, Eq, PartialEq, Ord, PartialOrd)]
enum KeyChunk {
    Text(String),
    Num(u64),
}

fn natural_key(s: &str) -> Vec<KeyChunk> {
    let mut chunks = Vec::new();
    let mut chars = s.chars().peekable();
    while let Some(&c) = chars.peek() {
        if c.is_ascii_digit() {
            let mut num_str = String::new();
            while let Some(&d) = chars.peek() {
                if d.is_ascii_digit() {
                    num_str.push(d);
                    chars.next();
                } else {
                    break;
                }
            }
            chunks.push(KeyChunk::Num(num_str.parse().unwrap_or(0)));
        } else {
            let mut text = String::new();
            while let Some(&t) = chars.peek() {
                if !t.is_ascii_digit() {
                    text.push(t.to_ascii_lowercase());
                    chars.next();
                } else {
                    break;
                }
            }
            chunks.push(KeyChunk::Text(text));
        }
    }
    chunks
}

fn get_host_dir() -> PathBuf {
    if let Ok(portable) = std::env::var("PORTABLE_EXECUTABLE_DIR") {
        if !portable.is_empty() {
            let p = PathBuf::from(portable);
            log_dev(&format!("Using PORTABLE_EXECUTABLE_DIR: {:?}", p));
            return p;
        }
    }
    if let Ok(owd) = std::env::var("OWD") {
        if !owd.is_empty() {
            let p = PathBuf::from(owd);
            log_dev(&format!("Using OWD: {:?}", p));
            return p;
        }
    }
    if let Ok(host) = std::env::var("HOST_DIR") {
        if !host.is_empty() {
            let p = PathBuf::from(host);
            log_dev(&format!("Using HOST_DIR: {:?}", p));
            return p;
        }
    }
    let p = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    log_dev(&format!("Using current_dir as host_dir: {:?}", p));
    p
}

fn find_candidate_locations(host_dir: &Path) -> Vec<PathBuf> {
    let mut locs = Vec::new();
    // 1. host_dir/static
    let s1 = host_dir.join("static");
    if s1.is_dir() {
        locs.push(s1);
    }
    // 2. host_dir itself (e.g. if novel_images* folder is directly in the launch folder)
    if host_dir.is_dir() && !locs.contains(&host_dir.to_path_buf()) {
        locs.push(host_dir.to_path_buf());
    }
    locs
}

fn find_directory_path(host_dir: &Path, name: &str) -> Option<PathBuf> {
    for loc in find_candidate_locations(host_dir) {
        let p = loc.join(name);
        if p.is_dir() {
            return Some(p);
        }
    }
    None
}

fn ensure_workspace_directories(host_dir: &Path) {
    let static_dir = host_dir.join("static");
    let demos_dir = static_dir.join("demos");

    let _ = fs::create_dir_all(&static_dir);
    let _ = fs::create_dir_all(&demos_dir);

    // Check if any novel_images exists in host_dir or host_dir/static
    let has_novel = find_candidate_locations(host_dir).iter().any(|loc| {
        if let Ok(entries) = fs::read_dir(loc) {
            for entry in entries.flatten() {
                if let Ok(ft) = entry.file_type() {
                    if ft.is_dir() && entry.file_name().to_string_lossy().starts_with("novel_images") {
                        return true;
                    }
                }
            }
        }
        false
    });

    if !has_novel {
        let sample_dir = static_dir.join("novel_images-Appdemo");
        let _ = fs::create_dir_all(&sample_dir);

        // Copy bundled sample frames from the AppImage package if available
        if let Ok(here) = std::env::var("HERE") {
            let bundled_sample = Path::new(&here).join("static/novel_images-Appdemo");
            let fallback_sample = Path::new(&here).join("static/novel_images0");
            let source = if bundled_sample.is_dir() {
                bundled_sample
            } else {
                fallback_sample
            };
            if source.is_dir() {
                if let Ok(entries) = fs::read_dir(&source) {
                    for entry in entries.flatten() {
                        let path = entry.path();
                        if path.is_file() {
                            let dest = sample_dir.join(entry.file_name());
                            if !dest.exists() {
                                let _ = fs::copy(&path, &dest);
                            }
                        }
                    }
                }
            }
        }
    }
}

fn find_ffmpeg() -> String {
    // Check bundled bin first
    if let Ok(here) = std::env::var("HERE") {
        let bundled = Path::new(&here).join("bin/ffmpeg");
        if bundled.is_file() {
            return bundled.to_string_lossy().to_string();
        }
    }
    let local = Path::new("./bin/ffmpeg");
    if local.is_file() {
        return local.to_string_lossy().to_string();
    }
    let sys = Path::new("/usr/local/bin/ffmpeg");
    if sys.is_file() {
        return "/usr/local/bin/ffmpeg".to_string();
    }
    "ffmpeg".to_string()
}

fn handle_directories(host_dir: &Path) -> String {
    log_dev(&format!("handle_directories() scanning for host_dir: {:?}", host_dir));
    ensure_workspace_directories(host_dir);
    let mut dirs_list = Vec::new();
    let mut seen = HashSet::new();

    let candidate_parents = find_candidate_locations(host_dir);
    log_dev(&format!("Candidate search locations: {:?}", candidate_parents));
    let valid_exts = [".png", ".jpg", ".jpeg", ".webp"];

    for parent in candidate_parents {
        if let Ok(entries) = fs::read_dir(&parent) {
            for entry in entries.flatten() {
                if let Ok(ft) = entry.file_type() {
                    if ft.is_dir() {
                        let name = entry.file_name().to_string_lossy().to_string();
                        if name.starts_with("novel_images") && !seen.contains(&name) {
                            seen.insert(name.clone());
                            let full_path = entry.path();
                            let mut file_count = 0;

                            if let Ok(files) = fs::read_dir(&full_path) {
                                for file in files.flatten() {
                                    let fname = file.file_name().to_string_lossy().to_lowercase();
                                    if valid_exts.iter().any(|ext| fname.ends_with(ext))
                                        && !fname.starts_with('.')
                                    {
                                        file_count += 1;
                                    }
                                }
                            }

                            log_dev(&format!("  -> Found directory '{}' with {} frames at {:?}", name, file_count, full_path));

                            let (dir_type, dir_label) = if full_path.join("models.json").is_file() {
                                ("models", "Model Comparison")
                            } else if full_path.join("cfg.json").is_file() {
                                ("cfg", "CFG Sweep")
                            } else if full_path.join("slerp.json").is_file() {
                                ("slerp", "SLERP Morph")
                            } else if full_path.join("generations.json").is_file() {
                                ("generations", "Generations")
                            } else {
                                ("generic", "Image Sequence")
                            };

                            dirs_list.push(serde_json::json!({
                                "name": name,
                                "count": file_count,
                                "type": dir_type,
                                "type_label": dir_label
                            }));
                        }
                    }
                }
            }
        }
    }

    dirs_list.sort_by(|a, b| {
        let name_a = a["name"].as_str().unwrap_or("");
        let name_b = b["name"].as_str().unwrap_or("");
        natural_key(name_a).cmp(&natural_key(name_b))
    });

    log_dev(&format!("handle_directories() completed with {} directories", dirs_list.len()));

    serde_json::json!({
        "success": true,
        "count": dirs_list.len(),
        "directories": dirs_list
    })
    .to_string()
}

fn handle_images(host_dir: &Path, dir_name: &str, sort_by: &str, filter_kw: &str) -> String {
    log_dev(&format!("handle_images() requested: dir={} sort={} filter={}", dir_name, sort_by, filter_kw));
    ensure_workspace_directories(host_dir);
    let target_dir = match find_directory_path(host_dir, dir_name) {
        Some(p) => {
            log_dev(&format!("  -> Resolved directory '{}' to {:?}", dir_name, p));
            p
        }
        None => {
            log_dev(&format!("  -> Directory NOT FOUND: '{}'", dir_name));
            return serde_json::json!({
                "success": false,
                "error": "Directory not found"
            })
            .to_string();
        }
    };

    let valid_exts = [".png", ".jpg", ".jpeg", ".webp"];
    let mut files = Vec::new();

    if let Ok(entries) = fs::read_dir(&target_dir) {
        for entry in entries.flatten() {
            let fname = entry.file_name().to_string_lossy().to_string();
            let lower = fname.to_lowercase();
            if valid_exts.iter().any(|ext| lower.ends_with(ext)) && !fname.starts_with('.') {
                if filter_kw.is_empty() || lower.contains(filter_kw) {
                    let mtime = entry
                        .metadata()
                        .and_then(|m| m.modified())
                        .map(|t| {
                            t.duration_since(std::time::UNIX_EPOCH)
                                .map(|d| d.as_millis() as u64)
                                .unwrap_or(0)
                        })
                        .unwrap_or(0);
                    files.push((fname, mtime));
                }
            }
        }
    }

    if sort_by == "time" {
        files.sort_by(|a, b| b.1.cmp(&a.1));
    } else {
        files.sort_by(|a, b| natural_key(&a.0).cmp(&natural_key(&b.0)));
    }

    log_dev(&format!("  -> Found {} valid frames in {:?}", files.len(), target_dir));

    let mut metadata = serde_json::json!({
        "directory": dir_name,
        "type": "generic"
    });

    let models_json = target_dir.join("models.json");
    if models_json.is_file() {
        if let Ok(content) = fs::read_to_string(&models_json) {
            if let Ok(mut parsed) = serde_json::from_str::<serde_json::Value>(&content) {
                parsed["type"] = serde_json::json!("models");
                metadata = parsed;
            }
        }
    }

    let images: Vec<serde_json::Value> = files
        .iter()
        .enumerate()
        .map(|(idx, (fname, mtime))| {
            serde_json::json!({
                "filename": fname,
                "path": format!("/static/{}/{}", dir_name, fname),
                "index": idx,
                "mtime": mtime,
                "label": format!("Frame {}", idx + 1),
                "meta": fname,
                "extra": {}
            })
        })
        .collect();

    serde_json::json!({
        "success": true,
        "directory": dir_name,
        "count": images.len(),
        "images": images,
        "metadata": metadata
    })
    .to_string()
}

fn handle_export_video(host_dir: &Path, payload: &serde_json::Value) -> Result<String, String> {
    ensure_workspace_directories(host_dir);
    let start_time = Instant::now();

    let dir_name = payload
        .get("dir")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim();

    if dir_name.is_empty() {
        return Err("No directory specified".to_string());
    }

    let target_dir = match find_directory_path(host_dir, dir_name) {
        Some(p) => p,
        None => return Err("Directory not found".to_string()),
    };

    let static_dir = host_dir.join("static");
    let demos_dir = static_dir.join("demos");
    let _ = fs::create_dir_all(&demos_dir);

    let fps = payload
        .get("fps")
        .and_then(|v| v.as_u64())
        .unwrap_or(10)
        .clamp(1, 60);

    let pingpong = payload
        .get("pingpong")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    let loops = payload
        .get("loops")
        .and_then(|v| v.as_u64())
        .unwrap_or(1)
        .clamp(1, 10);

    let sort_by = payload
        .get("sort")
        .and_then(|v| v.as_str())
        .unwrap_or("name");

    let filter_kw = payload
        .get("filter")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_lowercase();

    let valid_exts = [".png", ".jpg", ".jpeg", ".webp"];
    let mut files: Vec<(String, u64)> = Vec::new();

    if let Ok(entries) = fs::read_dir(&target_dir) {
        for entry in entries.flatten() {
            let fname = entry.file_name().to_string_lossy().to_string();
            let lower = fname.to_lowercase();
            if valid_exts.iter().any(|ext| lower.ends_with(ext)) && !fname.starts_with('.') {
                if filter_kw.is_empty() || lower.contains(&filter_kw) {
                    let mtime = entry
                        .metadata()
                        .and_then(|m| m.modified())
                        .map(|t| {
                            t.duration_since(std::time::UNIX_EPOCH)
                                .map(|d| d.as_millis() as u64)
                                .unwrap_or(0)
                        })
                        .unwrap_or(0);
                    files.push((fname, mtime));
                }
            }
        }
    }

    if files.is_empty() {
        return Err("No valid image frames found".to_string());
    }

    if sort_by == "time" {
        files.sort_by(|a, b| b.1.cmp(&a.1));
    } else {
        files.sort_by(|a, b| natural_key(&a.0).cmp(&natural_key(&b.0)));
    }

    let total_avail = files.len();
    let mut start_frame = payload
        .get("start_frame")
        .and_then(|v| v.as_u64())
        .unwrap_or(1) as usize;
    let mut end_frame = payload
        .get("end_frame")
        .and_then(|v| v.as_u64())
        .unwrap_or(total_avail as u64) as usize;

    start_frame = start_frame.clamp(1, total_avail);
    end_frame = end_frame.clamp(1, total_avail);

    let mut image_paths: Vec<PathBuf> = Vec::new();
    let range_suffix;
    let is_reverse;

    if start_frame <= end_frame {
        is_reverse = false;
        range_suffix = format!("_f{}-to-f{}", start_frame, end_frame);
        for i in (start_frame - 1)..end_frame {
            image_paths.push(target_dir.join(&files[i].0));
        }
    } else {
        is_reverse = true;
        range_suffix = format!("_f{}-to-f{}_REV", start_frame, end_frame);
        let mut slice = Vec::new();
        for i in (end_frame - 1)..start_frame {
            slice.push(target_dir.join(&files[i].0));
        }
        slice.reverse();
        image_paths = slice;
    }

    if image_paths.is_empty() {
        return Err("Slice resulted in 0 frames".to_string());
    }

    // Ping-pong
    if pingpong && image_paths.len() > 2 {
        let middle: Vec<PathBuf> = image_paths[1..image_paths.len() - 1]
            .iter()
            .rev()
            .cloned()
            .collect();
        image_paths.extend(middle);
    }

    // Loops
    if loops > 1 {
        let base_slice = image_paths.clone();
        for _ in 1..loops {
            image_paths.extend(base_slice.clone());
        }
    }

    let total_frames = image_paths.len();
    let now = chrono_or_timestamp();
    let mode_suffix = if pingpong { "_pingpong" } else { "" };
    let filename = format!(
        "{}{}_{}fps{}{}_{}.mp4",
        dir_name, range_suffix, fps, mode_suffix, "", now
    );
    let output_path = demos_dir.join(&filename);

    let tmp_dir = std::env::temp_dir().join(format!("tauri_flipbook_{}", now));
    let _ = fs::create_dir_all(&tmp_dir);

    for (idx, src) in image_paths.iter().enumerate() {
        let dest = tmp_dir.join(format!("frame_{:06}.png", idx));
        #[cfg(unix)]
        {
            if std::os::unix::fs::symlink(src, &dest).is_err() {
                let _ = fs::copy(src, &dest);
            }
        }
        #[cfg(not(unix))]
        {
            let _ = fs::copy(src, &dest);
        }
    }

    let ffmpeg_bin = find_ffmpeg();
    let status = Command::new(&ffmpeg_bin)
        .arg("-y")
        .arg("-hide_banner")
        .arg("-loglevel")
        .arg("warning")
        .arg("-framerate")
        .arg(fps.to_string())
        .arg("-i")
        .arg(tmp_dir.join("frame_%06d.png"))
        .arg("-vf")
        .arg("scale=trunc(iw/2)*2:trunc(ih/2)*2")
        .arg("-c:v")
        .arg("libx264")
        .arg("-pix_fmt")
        .arg("yuv420p")
        .arg("-preset")
        .arg("fast")
        .arg("-crf")
        .arg("18")
        .arg(&output_path)
        .status();

    let _ = fs::remove_dir_all(&tmp_dir);

    match status {
        Ok(s) if s.success() => {
            let elapsed = start_time.elapsed().as_secs_f64();
            let file_size_mb = output_path
                .metadata()
                .map(|m| m.len() as f64 / (1024.0 * 1024.0))
                .unwrap_or(0.0);
            let duration = total_frames as f64 / fps as f64;

            Ok(serde_json::json!({
                "success": true,
                "filename": filename,
                "video_url": format!("/static/demos/{}", filename),
                "file_size_mb": (file_size_mb * 100.0).round() / 100.0,
                "fps": fps,
                "frames": total_frames,
                "duration": (duration * 100.0).round() / 100.0,
                "elapsed": (elapsed * 100.0).round() / 100.0,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "is_reverse": is_reverse
            })
            .to_string())
        }
        Ok(s) => Err(format!("FFmpeg failed with exit status {:?}", s.code())),
        Err(e) => Err(format!("Failed to execute FFmpeg: {}", e)),
    }
}

fn chrono_or_timestamp() -> String {
    use std::time::SystemTime;
    let dur = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default();
    format!("{:010}", dur.as_secs())
}

const INDEX_HTML: &str = include_str!("../../ui/index.html");

fn run_embedded_server(host_dir: PathBuf) -> u16 {
    let server = Server::http("127.0.0.1:0").expect("Failed to bind tiny_http server");
    let port = server.server_addr().to_ip().unwrap().port();
    log_dev(&format!("Server bound to http://127.0.0.1:{}", port));
    let host_arc = Arc::new(host_dir);

    std::thread::spawn(move || {
        for request in server.incoming_requests() {
            let host_clone = Arc::clone(&host_arc);
            std::thread::spawn(move || {
                process_http_request(request, &host_clone);
            });
        }
    });

    port
}

fn process_http_request(mut request: tiny_http::Request, host_arc: &Path) {
    let url_str = request.url().to_string();
    let parsed = Url::parse(&format!("http://127.0.0.1{}", url_str)).unwrap();
    let pathname = parsed.path().to_string();

    log_dev(&format!("HTTP Request: {} {}", request.method(), pathname));

    if pathname == "/" || pathname == "/index.html" {
        let response = Response::from_string(INDEX_HTML).with_header(
            Header::from_bytes(&b"Content-Type"[..], &b"text/html; charset=utf-8"[..]).unwrap(),
        );
        let _ = request.respond(response);
        return;
    }

    if pathname == "/api/directories" {
        let json = handle_directories(host_arc);
        let response = Response::from_string(json)
            .with_header(
                Header::from_bytes(&b"Content-Type"[..], &b"application/json"[..]).unwrap(),
            )
            .with_header(
                Header::from_bytes(&b"Access-Control-Allow-Origin"[..], &b"*"[..]).unwrap(),
            );
        let _ = request.respond(response);
        return;
    }

    if pathname == "/api/images" {
        let pairs: HashMap<_, _> = parsed.query_pairs().into_owned().collect();
        let dir_name = pairs.get("dir").cloned().unwrap_or_default();
        let sort_by = pairs.get("sort").cloned().unwrap_or_else(|| "name".to_string());
        let filter_kw = pairs.get("filter").cloned().unwrap_or_default().to_lowercase();

        let json = handle_images(host_arc, &dir_name, &sort_by, &filter_kw);
        let response = Response::from_string(json)
            .with_header(
                Header::from_bytes(&b"Content-Type"[..], &b"application/json"[..]).unwrap(),
            )
            .with_header(
                Header::from_bytes(&b"Access-Control-Allow-Origin"[..], &b"*"[..]).unwrap(),
            );
        let _ = request.respond(response);
        return;
    }

    if pathname == "/api/export_video" && request.method().as_str() == "POST" {
        let mut body = String::new();
        let _ = std::io::Read::read_to_string(&mut request.as_reader(), &mut body);
        let payload: serde_json::Value =
            serde_json::from_str(&body).unwrap_or(serde_json::Value::Null);

        match handle_export_video(host_arc, &payload) {
            Ok(json) => {
                let response = Response::from_string(json)
                    .with_header(
                        Header::from_bytes(&b"Content-Type"[..], &b"application/json"[..]).unwrap(),
                    )
                    .with_header(
                        Header::from_bytes(&b"Access-Control-Allow-Origin"[..], &b"*"[..]).unwrap(),
                    );
                let _ = request.respond(response);
            }
            Err(err) => {
                let err_json = serde_json::json!({ "success": false, "error": err }).to_string();
                let response = Response::from_string(err_json)
                    .with_status_code(StatusCode(400))
                    .with_header(
                        Header::from_bytes(&b"Content-Type"[..], &b"application/json"[..]).unwrap(),
                    )
                    .with_header(
                        Header::from_bytes(&b"Access-Control-Allow-Origin"[..], &b"*"[..]).unwrap(),
                    );
                let _ = request.respond(response);
            }
        }
        return;
    }

    // Static file serving: /static/...
    if pathname.starts_with("/static/") {
        let rel_path = pathname.trim_start_matches("/static/");
        let decoded = urlencoding_decode(rel_path);

        let parts: Vec<&str> = decoded.splitn(2, '/').collect();
        let file_path = if parts.len() == 2 {
            let (dir_name, fname) = (parts[0], parts[1]);
            if dir_name == "demos" {
                let p = host_arc.join("static").join("demos").join(fname);
                if p.is_file() {
                    Some(p)
                } else {
                    None
                }
            } else {
                find_directory_path(host_arc, dir_name).map(|d| d.join(fname))
            }
        } else {
            None
        };

        if let Some(path) = file_path {
            if path.is_file() {
                if let Ok(file) = fs::File::open(&path) {
                    let content_type = if decoded.ends_with(".png") {
                        "image/png"
                    } else if decoded.ends_with(".jpg") || decoded.ends_with(".jpeg") {
                        "image/jpeg"
                    } else if decoded.ends_with(".webp") {
                        "image/webp"
                    } else if decoded.ends_with(".mp4") {
                        "video/mp4"
                    } else {
                        "application/octet-stream"
                    };

                    let response = Response::from_file(file)
                        .with_header(
                            Header::from_bytes(&b"Content-Type"[..], content_type.as_bytes())
                                .unwrap(),
                        )
                        .with_header(
                            Header::from_bytes(&b"Access-Control-Allow-Origin"[..], &b"*"[..])
                                .unwrap(),
                        );
                    let _ = request.respond(response);
                    return;
                }
            }
        }
    }

    // 404 fallback
    log_dev(&format!("  -> 404 Not Found: {}", pathname));
    let response = Response::from_string("Not Found").with_status_code(StatusCode(404));
    let _ = request.respond(response);
}

fn urlencoding_decode(s: &str) -> String {
    url::form_urlencoded::parse(s.as_bytes())
        .map(|(k, _)| k.to_string())
        .collect::<Vec<_>>()
        .join("")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    log_dev("=== Tauri VideoMaker Studio Started ===");
    let host_dir = get_host_dir();
    ensure_workspace_directories(&host_dir);
    let port = run_embedded_server(host_dir);

    tauri::Builder::default()
        .setup(move |app| {
            let target_url = Url::parse(&format!("http://127.0.0.1:{}/", port)).unwrap();
            log_dev(&format!("setup() -> Creating WebviewWindow to: {}", target_url));
            let _win = tauri::WebviewWindowBuilder::new(
                app,
                "main",
                tauri::WebviewUrl::External(target_url),
            )
            .title("Tauri VideoMaker Studio [DEV LOGGING ACTIVE]")
            .inner_size(1400.0, 900.0)
            .resizable(true)
            .build()?;
            log_dev("setup() -> Window created successfully!");
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while building tauri application");
}
