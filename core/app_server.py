import os
import sys
import time
import json
import shutil
import signal
import threading
import subprocess
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    # DPI Awareness
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
else:
    import ctypes

    ctypes.windll = None  # type: ignore[attr-defined]

    class _Unavailable:
        """Stub agar pemanggilan API Windows di Linux tidak melempar AttributeError."""

        def __getattr__(self, name):
            def _noop(*_args, **_kwargs):
                return 0

            return _noop

    user32 = _Unavailable()
    kernel32 = _Unavailable()

PORT = int(os.environ.get("FLUEMO_PORT", "7890"))
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CORE_DIR)

# Penyimpanan profil & konfigurasi (Windows: %USERPROFILE%, Linux: $HOME)
STORAGE_HOME = os.environ.get("USERPROFILE") or os.path.expanduser("~")
C_STORAGE_DIR = os.path.join(STORAGE_HOME, ".flutter_mobile_studio")
CHROME_PROFILE_DIR = os.path.join(C_STORAGE_DIR, "controller_profile")
os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(C_STORAGE_DIR, "config.json")

CHROME_CANDIDATES = (
    ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]
    if not IS_WINDOWS
    else [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
)
FLATPAK_CHROME_IDS = ["org.chromium.Chromium", "com.google.Chrome"]


def find_chrome_command():
    """Kembalikan list argumen untuk menjalankan Chrome/Chromium, atau None bila tidak ada."""
    for candidate in CHROME_CANDIDATES:
        path = shutil.which(candidate) or (candidate if os.path.exists(candidate) else None)
        if path:
            return [path]
    if not IS_WINDOWS and shutil.which("flatpak"):
        for app_id in FLATPAK_CHROME_IDS:
            for scope in (["--user"], []):
                res = subprocess.run(
                    ["flatpak", "info", *scope, app_id], capture_output=True, text=True
                )
                if res.returncode == 0:
                    return ["flatpak", "run", *scope, app_id]
    return None


def find_flutter_executable():
    candidates = [
        r"F:\flutter\bin\flutter.bat",
        r"C:\flutter\bin\flutter.bat",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c

    if IS_WINDOWS:
        try:
            res = subprocess.run("where flutter.bat", capture_output=True, text=True, shell=True)
            lines = res.stdout.strip().splitlines()
            if lines and os.path.exists(lines[0].strip()):
                return lines[0].strip()
        except Exception:
            pass
        return "flutter.bat"

    found = shutil.which("flutter")
    if found:
        return found
    for c in (
        os.path.expanduser("~/development/flutter/bin/flutter"),
        os.path.expanduser("~/flutter/bin/flutter"),
        "/opt/flutter/bin/flutter",
        "/usr/local/flutter/bin/flutter",
    ):
        if os.path.exists(c):
            return c
    return "flutter"


FLUTTER_BAT = find_flutter_executable()
LAUNCHER_EXE = os.path.join(
    CORE_DIR, "chrome_mobile_launcher.exe" if IS_WINDOWS else "chrome_mobile_launcher.sh"
)

# ---------------------------------------------------------------- X11 (Linux)
# Di Linux, pencarian & pemindahan jendela memakai libX11 via ctypes (lihat x11_window.py).
# Tidak ada dependensi pip, murni pustaka sistem.
import x11_window as x11_window


def _linux_controller_xid():
    return x11_window.find_controller()


def _linux_find_window():
    """Padanan find_flutter_chrome_hwnd() untuk Linux."""
    return x11_window.find_mobile_window(
        controller_xid=_linux_controller_xid(), exclude=_mobile_window_baseline
    )


def _linux_snapshot_mobile_windows():
    """Catat jendela mobile yang sudah ada agar peluncuran berikutnya tak salah sasaran."""
    return x11_window.list_mobile_windows(controller_xid=_linux_controller_xid())


def _linux_resize_window(xid, w, h, x, y):
    return x11_window.resize(xid, w, h, x, y)


def _linux_close_window(xid):
    return x11_window.close(xid)


def _linux_window_alive(xid):
    return bool(x11_window.window_info(xid)[0])


# State Aplikasi
state = {
    "project_path": "",
    "project_error": "",
    "status": "idle", # "idle", "starting", "running", "reload", "restart"
    "active_preset": "mobile1",
    "presets": {
        "mobile1": {"name": "iPhone 15 Pro Max", "w": 430, "h": 932},
        "mobile2": {"name": "Pixel 8 Pro",       "w": 448, "h": 998},
        "tab1":    {"name": "iPad mini (A17)",   "w": 744, "h": 1133},
        "tab2":    {"name": 'iPad Air 11"',      "w": 820, "h": 1180},
    },
    "logs": []
}

flutter_proc = None
controller_hwnd = None
cached_flutter_hwnd = None
_mobile_window_baseline = frozenset()

def load_saved_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("active_preset") in state["presets"]:
                    state["active_preset"] = data["active_preset"]
        except Exception:
            pass

load_saved_config()

def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "project_path": "", # Selalu reset agar input awal bersih
                "active_preset": state["active_preset"]
            }, f, indent=2)
    except Exception:
        pass

def validate_project_dir(path):
    """Simpan path apa adanya di project_path, isi project_error bila tidak valid. True bila valid."""
    state["project_path"] = path or ""
    if not path:
        state["project_error"] = "Belum ada folder proyek dipilih."
        return False
    if not os.path.isdir(path):
        state["project_error"] = f"Folder tidak ditemukan: {path}"
        return False
    if not os.path.exists(os.path.join(path, "pubspec.yaml")):
        state["project_error"] = "Folder ini tidak punya pubspec.yaml. Pilih folder proyek Flutter."
        return False
    state["project_error"] = ""
    return True

def add_log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    state["logs"].append(line)
    if len(state["logs"]) > 35: # Ringan di memori RAM
        state["logs"] = state["logs"][-35:]

def update_mobile_config(w, h):
    cfg_path = os.path.join(CORE_DIR, "mobile_config.txt")
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(f"width={w + 16}\n")
            f.write(f"height={h + 39}\n")
            f.write("x=410\n")
            f.write("y=40\n")
    except Exception:
        pass

def find_flutter_chrome_hwnd():
    global cached_flutter_hwnd

    if not IS_WINDOWS:
        if cached_flutter_hwnd and _linux_window_alive(cached_flutter_hwnd):
            return cached_flutter_hwnd
        return _linux_find_window()

    # Cek cache validitas jendela sebelumnya untuk hemat CPU
    if cached_flutter_hwnd and user32.IsWindow(cached_flutter_hwnd) and user32.IsWindowVisible(cached_flutter_hwnd):
        return cached_flutter_hwnd

    targets = []
    def enum_cb(h, lp):
        if not user32.IsWindowVisible(h):
            return True
        if controller_hwnd and h == controller_hwnd:
            return True

        length = user32.GetWindowTextLengthW(h)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(h, buff, length + 1)
            title = buff.value
            if "Flutter Controller" in title:
                return True

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            h_proc = kernel32.OpenProcess(0x1000, False, pid.value)
            is_chrome = False
            if h_proc:
                name_buf = ctypes.create_unicode_buffer(512)
                size = wintypes.DWORD(512)
                if kernel32.QueryFullProcessImageNameW(h_proc, 0, name_buf, ctypes.byref(size)):
                    if "chrome.exe" in name_buf.value.lower():
                        is_chrome = True
                kernel32.CloseHandle(h_proc)

            if is_chrome:
                targets.append(h)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

    if targets:
        cached_flutter_hwnd = targets[0]
        return cached_flutter_hwnd
    return None

def resize_flutter_chrome(preset_id):
    preset = state["presets"].get(preset_id)
    if not preset:
        return False
    state["active_preset"] = preset_id
    save_config()
    update_mobile_config(preset["w"], preset["h"])

    hwnd = find_flutter_chrome_hwnd()
    if hwnd:
        total_w = preset["w"] + 16
        total_h = preset["h"] + 39
        if IS_WINDOWS:
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            user32.SetWindowPos(hwnd, 0, 410, 40, total_w, total_h, SWP_NOZORDER | SWP_NOACTIVATE)
        else:
            _linux_resize_window(hwnd, total_w, total_h, 410, 40)
        add_log(f"Ukuran: {preset['name']} ({preset['w']}×{preset['h']})")
        return True
    else:
        add_log(f"Preset dipilih: {preset['name']}")
        return False

def run_flutter_background():
    global flutter_proc, cached_flutter_hwnd, _mobile_window_baseline
    project = state["project_path"]
    if not project or not os.path.exists(os.path.join(project, "pubspec.yaml")):
        state["status"] = "idle"
        add_log("Error: Folder proyek tidak valid!")
        return

    p = state["presets"][state["active_preset"]]
    update_mobile_config(p["w"], p["h"])

    if not IS_WINDOWS:
        # Jendela app yang sudah terbuka bukan milik peluncuran ini.
        _mobile_window_baseline = frozenset(_linux_snapshot_mobile_windows())

    env = os.environ.copy()
    env["CHROME_EXECUTABLE"] = LAUNCHER_EXE

    state["status"] = "starting"
    add_log(f"Build: {os.path.basename(project)}...")

    # Watchdog: Begitu jendela Chrome render di layar, langsung ubah status ke 'running'
    def window_watchdog():
        for _ in range(40):
            time.sleep(1)
            if state["status"] == "starting":
                hwnd = find_flutter_chrome_hwnd()
                if hwnd:
                    state["status"] = "running"
                    add_log("Aplikasi siap & berjalan!")
                    resize_flutter_chrome(state["active_preset"])
                    break
            elif state["status"] != "starting":
                break

    threading.Thread(target=window_watchdog, daemon=True).start()

    try:
        cmd = (
            ["cmd.exe", "/c", FLUTTER_BAT, "run", "-d", "chrome"]
            if IS_WINDOWS
            else [FLUTTER_BAT, "run", "-d", "chrome"]
        )
        proc = subprocess.Popen(
            cmd,
            cwd=project,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=not IS_WINDOWS,
        )
        flutter_proc = proc

        for line in proc.stdout:
            l = line.strip()
            if l:
                add_log(l)
                lower_l = l.lower()

                # Deteksi transisi status BERJALAN dari log
                if any(k in lower_l for k in [
                    "to hot reload",
                    "devtools",
                    "http://localhost:",
                    "http://127.0.0.1:",
                    "debug service on chrome",
                    "syncing files to device chrome",
                    "is available at"
                ]):
                    if state["status"] != "running" and state["status"] not in ["reload", "restart"]:
                        state["status"] = "running"
                        add_log("Berjalan!")
                        time.sleep(1)
                        resize_flutter_chrome(state["active_preset"])

                elif "reloaded" in lower_l or "hot reload" in lower_l:
                    state["status"] = "running"

                elif "restarted application" in lower_l or "hot restart" in lower_l:
                    state["status"] = "running"

        proc.wait()
        add_log("Flutter berhenti.")
    except Exception as e:
        add_log(f"Error: {e}")
    finally:
        flutter_proc = None
        cached_flutter_hwnd = None
        state["status"] = "idle"

def stop_flutter_process():
    global flutter_proc, cached_flutter_hwnd
    add_log("Menghentikan aplikasi...")
    state["status"] = "idle"

    if flutter_proc:
        pid = flutter_proc.pid
        try:
            if flutter_proc.stdin:
                flutter_proc.stdin.write("q\n")
                flutter_proc.stdin.flush()
        except Exception:
            pass

        def force_cleanup():
            time.sleep(0.3)
            if not IS_WINDOWS:
                # flutter run + Chrome launcher hidup di process group sendiri
                # (start_new_session=True), jadi aman dimatikan sekaligus.
                try:
                    pgid = os.getpgid(pid)
                except Exception:
                    return
                if pgid == os.getpgid(0):
                    return
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(pgid, sig)
                    except Exception:
                        pass
                    time.sleep(0.7)
                return
            try:
                subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, capture_output=True)
            except Exception:
                pass
            try:
                subprocess.run("taskkill /F /IM dart.exe", shell=True, capture_output=True)
            except Exception:
                pass
            try:
                subprocess.run("taskkill /F /IM chrome_mobile_launcher.exe", shell=True, capture_output=True)
            except Exception:
                pass

        threading.Thread(target=force_cleanup, daemon=True).start()
        flutter_proc = None

    hwnd = find_flutter_chrome_hwnd()
    if hwnd:
        if IS_WINDOWS:
            try:
                user32.PostMessageW(hwnd, 0x0010, 0, 0) # WM_CLOSE
            except Exception:
                pass
        else:
            _linux_close_window(hwnd)
    cached_flutter_hwnd = None
    add_log("Aplikasi dimatikan.")

def trigger_hot_reload():
    global flutter_proc
    state["status"] = "reload"
    add_log("Hot Reload (r)...")

    if flutter_proc and flutter_proc.stdin:
        try:
            flutter_proc.stdin.write("r\n")
            flutter_proc.stdin.flush()
        except Exception as e:
            add_log(f"Err: {e}")

    def revert():
        time.sleep(2.0)
        if state["status"] == "reload":
            state["status"] = "running"
    threading.Thread(target=revert, daemon=True).start()

def trigger_hot_restart():
    global flutter_proc
    state["status"] = "restart"
    add_log("Hot Restart (R)...")

    if flutter_proc and flutter_proc.stdin:
        try:
            flutter_proc.stdin.write("R\n")
            flutter_proc.stdin.flush()
        except Exception as e:
            add_log(f"Err: {e}")

    def revert():
        time.sleep(2.5)
        if state["status"] == "restart":
            state["status"] = "running"
    threading.Thread(target=revert, daemon=True).start()

def pick_folder_dialog():
    initial = state["project_path"] or (os.path.expanduser("~") if not IS_WINDOWS else "C:\\")
    folder = None
    if IS_WINDOWS:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="Pilih Folder Flutter", initialdir=initial)
        root.destroy()
    else:
        for dialog in (
            ["zenity", "--file-selection", "--directory", "--title=Pilih Folder Flutter",
             f"--filename={initial}/"],
            ["kdialog", "--getexistingdirectory", initial],
        ):
            if not shutil.which(dialog[0]):
                continue
            res = subprocess.run(dialog, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                folder = res.stdout.strip()
                break
            return None
    if not folder:
        return None
    if validate_project_dir(folder):
        save_config()
        add_log(f"Proyek: {os.path.basename(folder)}")
        return folder
    add_log(state["project_error"])
    return None

# ULTRA-RINGAN: Pure embedded CSS & inline SVG. 0 network request, 100% offline, < 15MB RAM!
HTML_PAGE = """<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <title>Flutter Controller</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      height: 100%;
      overflow: hidden !important;
      user-select: none;
      background-color: #020617;
      color: #f1f5f9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      font-size: 12px;
    }
    .app-container {
      height: 100%;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 10px;
      gap: 8px;
    }
    /* Card Styles */
    .card {
      background: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 12px;
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .card-title {
      font-size: 10px;
      font-weight: 700;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    /* Header */
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 6px;
      border-bottom: 1px solid #1e293b;
    }
    .header-title { font-size: 12px; font-weight: 800; color: #fff; letter-spacing: 0.5px; }
    .header-sub { font-size: 9.5px; color: #64748b; }
    /* Status Badge */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 10px;
      border-radius: 9999px;
      font-size: 10px;
      font-weight: 800;
      border: 1px solid transparent;
      transition: all 0.2s ease;
    }
    .badge-idle { background: #0f172a; border-color: #334155; color: #94a3b8; }
    .badge-starting { background: #451a03; border-color: #d97706; color: #fbbf24; }
    .badge-running { background: #022c22; border-color: #059669; color: #34d399; }
    .badge-reload { background: #431407; border-color: #ea580c; color: #fb923c; }
    .badge-restart { background: #082f49; border-color: #0284c7; color: #38bdf8; }
    .dot { width: 7px; height: 7px; border-radius: 50%; }
    .dot-idle { background: #64748b; }
    .dot-starting { background: #f59e0b; animation: pulse 1s infinite; }
    .dot-running { background: #10b981; animation: pulse 1.5s infinite; }
    .dot-reload { background: #f97316; animation: pulse 0.8s infinite; }
    .dot-restart { background: #0ea5e9; animation: pulse 0.8s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.85); } }

    /* Inputs */
    .input-row { display: flex; gap: 6px; align-items: center; }
    .text-input {
      flex: 1;
      background: #020617;
      border: 1px solid #1e293b;
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 11px;
      color: #cbd5e1;
      font-family: monospace;
      outline: none;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .text-input:focus { border-color: #0ea5e9; }
    .btn-browse {
      background: #1e293b;
      border: 1px solid #334155;
      color: #e2e8f0;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: background 0.15s;
    }
    .btn-browse:hover { background: #334155; }

    /* Button Grid */
    .btn-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
    .action-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 8px 10px;
      border-radius: 10px;
      font-size: 11px;
      font-weight: 700;
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.15s ease;
    }
    .action-btn:active { transform: scale(0.97); }
    .btn-start-active { background: #059669; color: #fff; box-shadow: 0 2px 6px rgba(5,150,105,0.3); }
    .btn-start-active:hover { background: #10b981; }
    .btn-stop-active { background: #e11d48; color: #fff; box-shadow: 0 2px 6px rgba(225,29,72,0.3); }
    .btn-stop-active:hover { background: #f43f5e; }
    .btn-reload-active { background: #d97706; color: #fff; box-shadow: 0 2px 6px rgba(217,119,6,0.3); }
    .btn-reload-active:hover { background: #f59e0b; }
    .btn-reset-active { background: #0284c7; color: #fff; box-shadow: 0 2px 6px rgba(2,132,199,0.3); }
    .btn-reset-active:hover { background: #0ea5e9; }
    .btn-disabled {
      background: #020617 !important;
      border-color: #1e293b !important;
      color: #475569 !important;
      box-shadow: none !important;
      cursor: not-allowed !important;
      transform: none !important;
    }

    /* Preset Grid */
    .preset-header { display: flex; justify-content: space-between; align-items: center; }
    .preset-active-label { color: #38bdf8; font-weight: 800; font-family: monospace; font-size: 10px; }
    .preset-btn {
      background: #020617;
      border: 1px solid #1e293b;
      border-radius: 10px;
      padding: 8px 10px;
      text-align: left;
      cursor: pointer;
      transition: all 0.15s;
    }
    .preset-btn:hover { border-color: #334155; }
    .preset-btn-selected {
      border: 2px solid #38bdf8 !important;
      background: rgba(8, 47, 73, 0.4) !important;
      box-shadow: 0 2px 8px rgba(56, 189, 248, 0.2);
    }
    .preset-name { font-weight: 700; color: #f1f5f9; display: flex; align-items: center; gap: 5px; font-size: 11px; }
    .preset-dim { font-size: 9.5px; color: #64748b; margin-top: 2px; }

    /* Log Box */
    .log-box {
      flex: 1;
      background: #000;
      border: 1px solid #1e293b;
      border-radius: 8px;
      padding: 8px;
      font-family: Consolas, monospace;
      font-size: 10px;
      color: #94a3b8;
      overflow-y: auto;
      line-height: 1.35;
      min-height: 0;
    }
    .log-box::-webkit-scrollbar { width: 4px; }
    .log-box::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 2px; }
    .log-line { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

    /* Footer */
    .footer {
      display: flex;
      justify-content: center;
      align-items: center;
      border-top: 1px solid #0f172a;
      padding-top: 2px;
      font-size: 10.5px;
      color: #475569;
      font-weight: 600;
    }

    svg { vertical-align: middle; fill: currentColor; }
  </style>
</head>
<body>
  <div class="app-container">

    <!-- 1. Header -->
    <div class="header">
      <div>
        <div class="header-title">FLUTTER CONTROLLER</div>
        <div class="header-sub">Mobile Runner (Ultra Ringan)</div>
      </div>
      <div id="statusBadge" class="badge badge-idle">
        <span id="statusDot" class="dot dot-idle"></span>
        <span id="statusText">IDLE</span>
      </div>
    </div>

    <!-- 2. Proyek Picker -->
    <div class="card">
      <div class="card-title">PROYEK FLUTTER</div>
      <div class="input-row">
        <input type="text" id="projectPathInput" onchange="onManualPathInput(this.value)"
          class="text-input" placeholder="Pilih folder proyek Flutter...">
        <button onclick="browseProject()" class="btn-browse">
          <svg width="12" height="12" viewBox="0 0 24 24"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>
          <span>Pilih</span>
        </button>
      </div>
    </div>

    <!-- 3. Kontrol Aksi -->
    <div class="card">
      <div class="card-title">KONTROL EKSEKUSI</div>
      <div class="btn-grid">
        <button id="btnStart" onclick="startFlutter()" class="action-btn btn-start-active">
          <svg width="11" height="11" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
          <span>Jalankan</span>
        </button>
        <button id="btnStop" onclick="stopFlutter()" class="action-btn btn-disabled" disabled>
          <svg width="11" height="11" viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg>
          <span>Matikan</span>
        </button>
        <button id="btnReload" onclick="triggerReload()" class="action-btn btn-disabled" disabled>
          <svg width="11" height="11" viewBox="0 0 24 24"><path d="M7 2v11h3v9l7-12h-4l4-8z"/></svg>
          <span>Reload (r)</span>
        </button>
        <button id="btnReset" onclick="triggerRestart()" class="action-btn btn-disabled" disabled>
          <svg width="11" height="11" viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
          <span>Reset (R)</span>
        </button>
      </div>
    </div>

    <!-- 4. Preset Ukuran Layar -->
    <div class="card">
      <div class="preset-header">
        <div class="card-title">UKURAN LAYAR</div>
        <div id="activePresetBadge" class="preset-active-label">iPhone 15 Pro</div>
      </div>
      <div class="btn-grid">
        <div onclick="setPreset('mobile1')" id="p-mobile1" class="preset-btn preset-btn-selected">
          <div class="preset-name">
            <svg width="11" height="11" viewBox="0 0 24 24" style="color:#38bdf8"><path d="M17 1.01L7 1c-1.1 0-2 .9-2 2v18c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V3c0-1.1-.9-1.99-2-1.99zM17 19H7V5h10v14z"/></svg>
            <span>iPhone 15 Pro</span>
          </div>
          <div class="preset-dim">430 × 932 px</div>
        </div>

        <div onclick="setPreset('mobile2')" id="p-mobile2" class="preset-btn">
          <div class="preset-name">
            <svg width="11" height="11" viewBox="0 0 24 24" style="color:#34d399"><path d="M6 18c0 .55.45 1 1 1h1v3.5c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5V19h2v3.5c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5V19h1c.55 0 1-.45 1-1V8H6v10zM3.5 8C2.67 8 2 8.67 2 9.5v7c0 .83.67 1.5 1.5 1.5S5 17.33 5 16.5v-7C5 8.67 4.33 8 3.5 8zm17 0c-.83 0-1.5.67-1.5 1.5v7c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5v-7c0-.83-.67-1.5-1.5-1.5z"/></svg>
            <span>Pixel 8 Pro</span>
          </div>
          <div class="preset-dim">440 × 960 px</div>
        </div>

        <div onclick="setPreset('tab1')" id="p-tab1" class="preset-btn">
          <div class="preset-name">
            <svg width="11" height="11" viewBox="0 0 24 24" style="color:#c084fc"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-1 14H6V6h12v11z"/></svg>
            <span>iPad Mini</span>
          </div>
          <div class="preset-dim">800 × 1080 px</div>
        </div>

        <div onclick="setPreset('tab2')" id="p-tab2" class="preset-btn">
          <div class="preset-name">
            <svg width="11" height="11" viewBox="0 0 24 24" style="color:#f472b6"><path d="M21 4H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm-2 12H5V8h14v8z"/></svg>
            <span>iPad Air</span>
          </div>
          <div class="preset-dim">920 × 1240 px</div>
        </div>
      </div>
    </div>

    <!-- 5. Output Log -->
    <div class="card" style="flex:1; min-height:0;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div class="card-title">OUTPUT LOG</div>
        <span onclick="clearLogs()" style="font-size:9.5px; color:#64748b; cursor:pointer;">Bersihkan</span>
      </div>
      <div id="logBox" class="log-box"><div>Ready.</div></div>
    </div>

    <!-- 6. Footer -->
    <div class="footer">
      <span>© VallDev</span>
    </div>

  </div>

  <script>
    let activePreset = "mobile1";
    let pollTimer = null;

    async function fetchState() {
      try {
        const res = await fetch("/api/state");
        const data = await res.json();

        const inputEl = document.getElementById("projectPathInput");
        if (document.activeElement !== inputEl) {
          inputEl.value = data.project_path || "";
          inputEl.title = data.project_path || "";
        }

        const badge = document.getElementById("statusBadge");
        const dot = document.getElementById("statusDot");
        const statusText = document.getElementById("statusText");

        const btnStart = document.getElementById("btnStart");
        const btnStop = document.getElementById("btnStop");
        const btnReload = document.getElementById("btnReload");
        const btnReset = document.getElementById("btnReset");

        if (data.status === "running") {
          badge.className = "badge badge-running";
          dot.className = "dot dot-running";
          statusText.textContent = "BERJALAN";

          btnStart.disabled = true;
          btnStart.className = "action-btn btn-disabled";

          btnStop.disabled = false;
          btnStop.className = "action-btn btn-stop-active";

          btnReload.disabled = false;
          btnReload.className = "action-btn btn-reload-active";

          btnReset.disabled = false;
          btnReset.className = "action-btn btn-reset-active";

        } else if (data.status === "starting") {
          badge.className = "badge badge-starting";
          dot.className = "dot dot-starting";
          statusText.textContent = "BUILD / PROSES";

          btnStart.disabled = true;
          btnStart.className = "action-btn btn-disabled";

          btnStop.disabled = false;
          btnStop.className = "action-btn btn-stop-active";

          btnReload.disabled = false;
          btnReload.className = "action-btn btn-reload-active";

          btnReset.disabled = false;
          btnReset.className = "action-btn btn-reset-active";

        } else if (data.status === "reload") {
          badge.className = "badge badge-reload";
          dot.className = "dot dot-reload";
          statusText.textContent = "RELOAD";

          btnReload.disabled = true;
          btnReload.className = "action-btn btn-disabled";

        } else if (data.status === "restart") {
          badge.className = "badge badge-restart";
          dot.className = "dot dot-restart";
          statusText.textContent = "RESTART";

          btnReset.disabled = true;
          btnReset.className = "action-btn btn-disabled";

        } else {
          // IDLE
          badge.className = "badge badge-idle";
          dot.className = "dot dot-idle";
          statusText.textContent = "IDLE";

          btnStart.disabled = false;
          btnStart.className = "action-btn btn-start-active";

          btnStop.disabled = true;
          btnStop.className = "action-btn btn-disabled";

          btnReload.disabled = true;
          btnReload.className = "action-btn btn-disabled";

          btnReset.disabled = true;
          btnReset.className = "action-btn btn-disabled";
        }

        activePreset = data.active_preset;
        const presetNames = { mobile1: "iPhone 15 Pro", mobile2: "Pixel 8 Pro", tab1: "iPad Mini", tab2: "iPad Air" };
        document.getElementById("activePresetBadge").textContent = presetNames[activePreset] || activePreset;

        ["mobile1", "mobile2", "tab1", "tab2"].forEach(pid => {
          const el = document.getElementById("p-" + pid);
          if (el) {
            el.className = pid === activePreset ? "preset-btn preset-btn-selected" : "preset-btn";
          }
        });

        const logBox = document.getElementById("logBox");
        const shouldScroll = logBox.scrollHeight - logBox.scrollTop <= logBox.clientHeight + 30;
        logBox.innerHTML = data.logs.map(l => `<div class="log-line">${escapeHtml(l)}</div>`).join("");
        if (shouldScroll) {
          logBox.scrollTop = logBox.scrollHeight;
        }

        // Adaptive polling interval untuk hemat CPU/baterai
        const nextDelay = (data.status === "starting" || data.status === "reload" || data.status === "restart") ? 600 : 900;
        clearTimeout(pollTimer);
        pollTimer = setTimeout(fetchState, nextDelay);

      } catch (e) {
        clearTimeout(pollTimer);
        pollTimer = setTimeout(fetchState, 1500);
      }
    }

    function escapeHtml(t) {
      return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    async function browseProject() {
      await fetch("/api/browse", { method: "POST" });
      fetchState();
    }

    async function onManualPathInput(path) {
      if (path && path.trim()) {
        await fetch("/api/set_path?path=" + encodeURIComponent(path.trim()), { method: "POST" });
        fetchState();
      }
    }

    async function startFlutter() {
      const p = document.getElementById("projectPathInput").value;
      if (!p || p.trim() === "") {
        alert("Silakan pilih folder proyek Flutter terlebih dahulu!");
        return;
      }
      await fetch("/api/start", { method: "POST" });
      fetchState();
    }

    async function stopFlutter() {
      await fetch("/api/stop", { method: "POST" });
      fetchState();
    }

    async function triggerReload() {
      await fetch("/api/reload", { method: "POST" });
      fetchState();
    }

    async function triggerRestart() {
      await fetch("/api/restart", { method: "POST" });
      fetchState();
    }

    async function setPreset(pid) {
      await fetch("/api/resize?preset=" + pid, { method: "POST" });
      fetchState();
    }

    async function clearLogs() {
      await fetch("/api/clear_logs", { method: "POST" });
      fetchState();
    }

    fetchState();
  </script>
</body>
</html>
"""

class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif parsed.path == "/api/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(json.dumps(state).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/api/browse":
            threading.Thread(target=pick_folder_dialog, daemon=True).start()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        elif parsed.path == "/api/set_path":
            manual_path = params.get("path", [""])[0]
            if validate_project_dir(manual_path):
                add_log(f"Path: {os.path.basename(manual_path)}")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        elif parsed.path == "/api/start":
            if state["project_error"] or not validate_project_dir(state["project_path"]):
                body = json.dumps({"status": "error", "error": state["project_error"]}).encode("utf-8")
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif state["status"] == "idle":
                threading.Thread(target=run_flutter_background, daemon=True).start()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"busy"}')

        elif parsed.path == "/api/stop":
            stop_flutter_process()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        elif parsed.path == "/api/reload":
            trigger_hot_reload()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        elif parsed.path == "/api/restart":
            trigger_hot_restart()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        elif parsed.path == "/api/resize":
            pid = params.get("preset", ["mobile1"])[0]
            resize_flutter_chrome(pid)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        elif parsed.path == "/api/clear_logs":
            state["logs"] = []
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

def start_http_server():
    server = HTTPServer(("127.0.0.1", PORT), RequestHandler)
    server.serve_forever()

def write_initial_chrome_preferences():
    pref_dir = os.path.join(CHROME_PROFILE_DIR, "Default")
    os.makedirs(pref_dir, exist_ok=True)
    pref_file = os.path.join(pref_dir, "Preferences")
    prefs = {}
    if os.path.exists(pref_file):
        try:
            with open(pref_file, "r", encoding="utf-8") as f:
                prefs = json.load(f)
        except Exception:
            pass

    prefs.setdefault("browser", {})
    prefs["browser"]["window_placement"] = {
        "top": 40,
        "left": 30,
        "bottom": 780,
        "right": 390,
        "maximized": False
    }

    try:
        with open(pref_file, "w", encoding="utf-8") as f:
            json.dump(prefs, f)
    except Exception:
        pass

def launch_controller_window():
    global controller_hwnd
    url = f"http://127.0.0.1:{PORT}"

    write_initial_chrome_preferences()

    chrome_cmd = find_chrome_command()
    if not chrome_cmd:
        add_log("Chrome/Chromium tidak ditemukan. Buka manual: " + url)
        print(f"Chrome/Chromium tidak ditemukan. Buka manual: {url}")
        return

    cmd = [
        *chrome_cmd,
        f"--user-data-dir={CHROME_PROFILE_DIR}",
        f"--app={url}",
        f"--class={x11_window.CONTROLLER_WM_CLASS}",
        "--window-size=360,740",
        "--window-position=30,40",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if not IS_WINDOWS:
        # Paksa X11 (via Xwayland) agar ukuran/posisi jendela bisa diatur.
        cmd.append("--ozone-platform=x11")
    subprocess.Popen(cmd)

    time.sleep(1)
    if not IS_WINDOWS:
        for _ in range(20):
            controller_hwnd = _linux_controller_xid()
            if controller_hwnd:
                return
            time.sleep(0.5)
        return

    def enum_cb(h, lp):
        if user32.IsWindowVisible(h):
            length = user32.GetWindowTextLengthW(h)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, buff, length + 1)
                if "Flutter Controller" in buff.value:
                    global controller_hwnd
                    controller_hwnd = h
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

if __name__ == "__main__":
    t_server = threading.Thread(target=start_http_server, daemon=True)
    t_server.start()

    print(f"Controller Aktif: http://127.0.0.1:{PORT}")
    launch_controller_window()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Selesai.")
