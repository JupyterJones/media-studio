const { app, BrowserWindow } = require("electron");
const path = require("path");
const fs = require("fs");
const http = require("http");
const url = require("url");
const { spawn } = require("child_process");
const os = require("os");

// Linux GPU stability
app.commandLine.appendSwitch("disable-gpu-process-crash-limit");

let mainWindow = null;
let httpServer = null;

// Determine host directory (directory where the AppImage is run, or current working dir)
const hostDir = process.env.PORTABLE_EXECUTABLE_DIR || process.env.HOST_DIR || process.cwd();
const staticDir = path.join(hostDir, "static");
const demosDir = path.join(staticDir, "demos");

function naturalSort(a, b) {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
}

function findCandidateLocations() {
  const locs = [];
  const s1 = path.join(hostDir, "static");
  if (fs.existsSync(s1) && fs.statSync(s1).isDirectory()) locs.push(s1);
  if (fs.existsSync(hostDir) && fs.statSync(hostDir).isDirectory() && !locs.includes(hostDir)) locs.push(hostDir);
  return locs;
}

function findDirectoryPath(name) {
  for (const loc of findCandidateLocations()) {
    const p = path.join(loc, name);
    if (fs.existsSync(p) && fs.statSync(p).isDirectory()) return p;
  }
  return null;
}

// Auto-create static and novel_images* pattern
function ensureWorkspaceDirectories() {
  try {
    if (!fs.existsSync(staticDir)) {
      fs.mkdirSync(staticDir, { recursive: true });
    }
    if (!fs.existsSync(demosDir)) {
      fs.mkdirSync(demosDir, { recursive: true });
    }

    // Check if any novel_images* exists in hostDir or hostDir/static
    let hasNovel = false;
    for (const loc of findCandidateLocations()) {
      if (fs.existsSync(loc) && fs.statSync(loc).isDirectory()) {
        const entries = fs.readdirSync(loc);
        if (entries.some((f) => f.startsWith("novel_images") && fs.statSync(path.join(loc, f)).isDirectory())) {
          hasNovel = true;
          break;
        }
      }
    }

    if (!hasNovel) {
      const sampleNovel = path.join(staticDir, "novel_images-Appdemo");
      if (!fs.existsSync(sampleNovel)) {
        fs.mkdirSync(sampleNovel, { recursive: true });
      }

      // Copy sample frames if bundled inside AppImage
      const bundledSample = path.join(__dirname, "static", "novel_images-Appdemo");
      const fallbackSample = path.join(__dirname, "static", "novel_images0");
      const source = fs.existsSync(bundledSample) ? bundledSample : fallbackSample;

      if (fs.existsSync(source)) {
        for (const file of fs.readdirSync(source)) {
          const s = path.join(source, file);
          const d = path.join(sampleNovel, file);
          if (!fs.existsSync(d) && fs.statSync(s).isFile()) {
            fs.copyFileSync(s, d);
          }
        }
      }
    }
  } catch (err) {
    console.error("[Workspace Setup Error]", err);
  }
}

// Locate FFmpeg
function getFfmpegPath() {
  const localBin = path.join(__dirname, "../bin/ffmpeg");
  if (fs.existsSync(localBin)) return localBin;
  const appDirBin = path.join(__dirname, "../../bin/ffmpeg");
  if (fs.existsSync(appDirBin)) return appDirBin;
  const sysBin = "/usr/local/bin/ffmpeg";
  if (fs.existsSync(sysBin)) return sysBin;
  return "ffmpeg";
}

// API: Discover directories matching pattern novel_images*
function getDirectoriesData() {
  ensureWorkspaceDirectories();
  const validExts = [".png", ".jpg", ".jpeg", ".webp"];
  const list = [];
  const seen = new Set();

  try {
    for (const parent of findCandidateLocations()) {
      if (!fs.existsSync(parent) || !fs.statSync(parent).isDirectory()) continue;
      const entries = fs.readdirSync(parent);

      for (const name of entries) {
        if (!name.startsWith("novel_images") || seen.has(name)) continue;
        const fullPath = path.join(parent, name);
        if (!fs.statSync(fullPath).isDirectory()) continue;
        seen.add(name);

        const files = fs.readdirSync(fullPath).filter((f) => {
          const ext = path.extname(f).toLowerCase();
          return validExts.includes(ext) && !f.startsWith(".");
        });

        let type = "generic";
        let typeLabel = "Image Sequence";
        const modelsJson = path.join(fullPath, "models.json");

        if (fs.existsSync(modelsJson)) {
          type = "models";
          typeLabel = "Model Comparison";
        } else if (fs.existsSync(path.join(fullPath, "cfg.json"))) {
          type = "cfg";
          typeLabel = "CFG Sweep";
        } else if (fs.existsSync(path.join(fullPath, "slerp.json"))) {
          type = "slerp";
          typeLabel = "SLERP Morph";
        } else if (fs.existsSync(path.join(fullPath, "generations.json"))) {
          type = "generations";
          typeLabel = "Generations";
        }

        list.push({
          name: name,
          count: files.length,
          type: type,
          type_label: typeLabel,
        });
      }
    }
    list.sort((a, b) => naturalSort(a.name, b.name));
  } catch (err) {
    console.error("[getDirectoriesData Error]", err);
  }

  return { success: true, count: list.length, directories: list };
}

// API: Get frames for a specific directory
function getImagesData(dirName, sortBy = "name", filterPrefix = "") {
  ensureWorkspaceDirectories();
  const targetDir = findDirectoryPath(dirName);
  if (!targetDir) {
    return { success: false, error: "Directory not found" };
  }

  const validExts = [".png", ".jpg", ".jpeg", ".webp"];
  let files = fs.readdirSync(targetDir).filter((f) => {
    const ext = path.extname(f).toLowerCase();
    return validExts.includes(ext) && !f.startsWith(".");
  });

  if (filterPrefix) {
    const kw = filterPrefix.toLowerCase();
    files = files.filter((f) => f.toLowerCase().includes(kw));
  }

  if (sortBy === "time") {
    files.sort((a, b) => {
      return (
        fs.statSync(path.join(targetDir, b)).mtimeMs -
        fs.statSync(path.join(targetDir, a)).mtimeMs
      );
    });
  } else {
    files.sort(naturalSort);
  }

  let metadata = { directory: dirName, type: "generic" };
  const modelsJson = path.join(targetDir, "models.json");
  if (fs.existsSync(modelsJson)) {
    try {
      metadata = JSON.parse(fs.readFileSync(modelsJson, "utf8"));
      metadata.type = "models";
    } catch (e) {}
  }

  const images = files.map((f, idx) => {
    const filePath = path.join(targetDir, f);
    const mtime = fs.statSync(filePath).mtimeMs;
    return {
      filename: f,
      path: `/static/${dirName}/${encodeURIComponent(f)}`,
      index: idx,
      mtime: mtime,
      label: `Frame ${idx + 1}`,
      meta: f,
      extra: {},
    };
  });

  return {
    success: true,
    directory: dirName,
    count: images.length,
    images: images,
    metadata: metadata,
  };
}

// API: Export video using FFmpeg
function exportVideo(reqData) {
  return new Promise((resolve, reject) => {
    ensureWorkspaceDirectories();
    const dirName = (reqData.dir || "").trim();
    if (!dirName) return reject(new Error("No directory specified"));

    const targetDir = findDirectoryPath(dirName);
    if (!targetDir) return reject(new Error("Directory not found"));

    let fps = parseInt(reqData.fps) || 10;
    fps = Math.max(1, Math.min(60, fps));
    const pingpong = Boolean(reqData.pingpong);
    const loops = Math.max(1, Math.min(10, parseInt(reqData.loops) || 1));
    const sortBy = reqData.sort || "name";
    const filterKw = (reqData.filter || "").toLowerCase().trim();

    const validExts = [".png", ".jpg", ".jpeg", ".webp"];
    let rawFiles = fs.readdirSync(targetDir).filter((f) => {
      const ext = path.extname(f).toLowerCase();
      return validExts.includes(ext) && !f.startsWith(".");
    });

    if (filterKw) {
      rawFiles = rawFiles.filter((f) => f.toLowerCase().includes(filterKw));
    }
    if (rawFiles.length === 0) {
      return reject(new Error("No valid image frames found"));
    }

    if (sortBy === "time") {
      rawFiles.sort((a, b) => {
        return (
          fs.statSync(path.join(targetDir, b)).mtimeMs -
          fs.statSync(path.join(targetDir, a)).mtimeMs
        );
      });
    } else {
      rawFiles.sort(naturalSort);
    }

    let imagePaths = rawFiles.map((f) => path.join(targetDir, f));
    const totalAvail = imagePaths.length;

    // Start / End slicing
    let startFrame = parseInt(reqData.start_frame) || 1;
    let endFrame = parseInt(reqData.end_frame) || totalAvail;

    startFrame = Math.max(1, Math.min(totalAvail, startFrame));
    endFrame = Math.max(1, Math.min(totalAvail, endFrame));

    let rangeSuffix = "";
    let isReverse = false;

    if (startFrame <= endFrame) {
      imagePaths = imagePaths.slice(startFrame - 1, endFrame);
      rangeSuffix = `_f${startFrame}-to-f${endFrame}`;
    } else {
      isReverse = true;
      imagePaths = imagePaths.slice(endFrame - 1, startFrame).reverse();
      rangeSuffix = `_f${startFrame}-to-f${endFrame}_REV`;
    }

    if (imagePaths.length === 0) {
      return reject(new Error("Slice resulted in 0 frames"));
    }

    // Ping-Pong
    if (pingpong && imagePaths.length > 2) {
      const middleRev = imagePaths.slice(1, -1).reverse();
      imagePaths = imagePaths.concat(middleRev);
    }

    // Loops
    if (loops > 1) {
      let repeated = [];
      for (let i = 0; i < loops; i++) {
        repeated = repeated.concat(imagePaths);
      }
      imagePaths = repeated;
    }

    const totalFrames = imagePaths.length;
    const timestamp = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);
    const modeSuffix = pingpong ? "_pingpong" : "";
    const filename = `${dirName}${rangeSuffix}_${fps}fps${modeSuffix}_${timestamp}.mp4`;
    const outputPath = path.join(demosDir, filename);

    const tmpPrefix = path.join(os.tmpdir(), "electron_flipbook_");
    const tmpDir = fs.mkdtempSync(tmpPrefix);
    const startTime = Date.now();

    try {
      imagePaths.forEach((src, idx) => {
        const dest = path.join(tmpDir, `frame_${String(idx).padStart(6, "0")}.png`);
        try {
          fs.symlinkSync(src, dest);
        } catch (e) {
          fs.copyFileSync(src, dest);
        }
      });

      const ffmpegBin = getFfmpegPath();
      const ffmpegArgs = [
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-framerate",
        String(fps),
        "-i",
        path.join(tmpDir, "frame_%06d.png"),
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "fast",
        "-crf",
        "18",
        outputPath,
      ];

      const proc = spawn(ffmpegBin, ffmpegArgs);
      let stderr = "";
      proc.stderr.on("data", (d) => (stderr += d.toString()));

      proc.on("close", (code) => {
        // Clean temp dir
        try {
          fs.rmSync(tmpDir, { recursive: true, force: true });
        } catch (e) {}

        if (code !== 0) {
          return reject(new Error(`FFmpeg failed (${code}): ${stderr}`));
        }

        const elapsed = (Date.now() - startTime) / 1000;
        const fileSizeMb = fs.existsSync(outputPath)
          ? fs.statSync(outputPath).size / (1024 * 1024)
          : 0;
        const duration = totalFrames / fps;

        resolve({
          success: true,
          filename: filename,
          video_url: `/static/demos/${filename}`,
          file_size_mb: Math.round(fileSizeMb * 100) / 100,
          fps: fps,
          frames: totalFrames,
          duration: Math.round(duration * 100) / 100,
          elapsed: Math.round(elapsed * 100) / 100,
          start_frame: startFrame,
          end_frame: endFrame,
          is_reverse: isReverse,
        });
      });
    } catch (err) {
      try {
        fs.rmSync(tmpDir, { recursive: true, force: true });
      } catch (e) {}
      reject(err);
    }
  });
}

// Start built-in HTTP server
function startServer() {
  return new Promise((resolve) => {
    ensureWorkspaceDirectories();
    httpServer = http.createServer((req, res) => {
      const parsedUrl = url.parse(req.url, true);
      const pathname = parsedUrl.pathname;

      // Enable CORS & JSON headers
      res.setHeader("Access-Control-Allow-Origin", "*");

      if (pathname === "/" || pathname === "/index.html") {
        const indexPath = path.join(__dirname, "index.html");
        fs.readFile(indexPath, "utf8", (err, content) => {
          if (err) {
            res.writeHead(500);
            return res.end("Error loading index.html");
          }
          res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
          res.end(content);
        });
        return;
      }

      if (pathname === "/api/directories") {
        const data = getDirectoriesData();
        res.writeHead(200, { "Content-Type": "application/json" });
        return res.end(JSON.stringify(data));
      }

      if (pathname === "/api/images") {
        const dirName = parsedUrl.query.dir || "";
        const sortBy = parsedUrl.query.sort || "name";
        const filterPrefix = parsedUrl.query.filter || "";
        const data = getImagesData(dirName, sortBy, filterPrefix);
        res.writeHead(200, { "Content-Type": "application/json" });
        return res.end(JSON.stringify(data));
      }

      if (pathname === "/api/export_video" && req.method === "POST") {
        let body = "";
        req.on("data", (chunk) => (body += chunk));
        req.on("end", async () => {
          try {
            const reqData = JSON.parse(body || "{}");
            const result = await exportVideo(reqData);
            res.writeHead(200, { "Content-Type": "application/json" });
            res.end(JSON.stringify(result));
          } catch (err) {
            res.writeHead(200, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ success: false, error: err.message }));
          }
        });
        return;
      }

      // Serve static files
      if (pathname.startsWith("/static/")) {
        const rel = decodeURIComponent(pathname.slice("/static/".length));
        let filePath = path.join(staticDir, rel);

        if (!fs.existsSync(filePath)) {
          const parts = rel.split("/");
          if (parts.length >= 2) {
            const dirPart = parts[0];
            const filePart = parts.slice(1).join("/");
            const resolvedDir = findDirectoryPath(dirPart);
            if (resolvedDir) filePath = path.join(resolvedDir, filePart);
          }
        }

        if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
          const ext = path.extname(filePath).toLowerCase();
          const mimeTypes = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".mp4": "video/mp4",
            ".txt": "text/plain",
            ".json": "application/json",
          };
          const contentType = mimeTypes[ext] || "application/octet-stream";
          res.writeHead(200, { "Content-Type": contentType });
          return fs.createReadStream(filePath).pipe(res);
        } else {
          res.writeHead(404);
          return res.end("File Not Found");
        }
      }

      res.writeHead(404);
      res.end("Not Found");
    });

    // Listen on dynamic available port
    httpServer.listen(0, "127.0.0.1", () => {
      const port = httpServer.address().port;
      console.log(`[MediaStudio Electron] Internal server active on port ${port}`);
      resolve(port);
    });
  });
}

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 950,
    minHeight: 650,
    backgroundColor: "#0b0f19",
    title: "MediaStudio - Electron VideoMaker",
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.loadURL(`http://127.0.0.1:${port}`);

  mainWindow.on("closed", () => {
    mainWindow = null;
    if (httpServer) {
      httpServer.close();
    }
    app.quit();
  });
}

app.whenReady().then(async () => {
  const port = await startServer();
  createWindow(port);
});

app.on("window-all-closed", () => {
  if (httpServer) {
    httpServer.close();
  }
  app.quit();
});
