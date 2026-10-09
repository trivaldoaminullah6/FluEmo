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
  <script>window.__INITIAL_STATE__ = __STATE_JSON__;</script>
  <style>
    :root {
      --bg: #020617;
      --surface: #0f172a;
      --surface-2: #1e293b;
      --line: #1e293b;
      --line-strong: #64748b;
      --text: #f1f5f9;
      --text-dim: #94a3b8;
      --text-disabled: #7d8ca3;
      --accent: #38bdf8;
      --accent-soft: #0c2136;
      --ok: #047857;
      --ok-hover: #065f46;
      --danger: #b91c1c;
      --danger-hover: #991b1b;
      --danger-soft: #450a0a;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      height: 100%;
      overflow: hidden !important;
      user-select: none;
      background-color: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", Arial, sans-serif;
      font-size: 12px;
    }
    .app-container {
      height: 100%;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 8px;
      gap: 6px;
      overflow-y: auto;
    }
    /* Card Styles */
    .card {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 8px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .card-title {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-dim);
    }
    /* Header */
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--line);
    }
    .header-title { font-size: 13px; font-weight: 700; color: var(--text); }
    .header-sub { font-size: 11px; color: var(--text-dim); }
    /* Status Badge */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
      border: 1px solid var(--line-strong);
      color: var(--text-dim);
      background: var(--surface);
    }
    .badge-starting { background: #451a03; border-color: #d97706; color: #fbbf24; }
    .badge-running { background: #022c22; border-color: #059669; color: #34d399; }
    .badge-reload { background: #431407; border-color: #ea580c; color: #fdba74; }
    .badge-restart { background: #082f49; border-color: #0284c7; color: var(--accent); }
    .badge-offline { background: var(--danger-soft); border-color: #dc2626; color: #fca5a5; }
    .dot { width: 7px; height: 7px; border-radius: 50%; flex: none; }
    .dot-idle { background: var(--text-dim); }
    .dot-starting { background: #f59e0b; }
    .dot-running { background: #10b981; }
    .dot-reload { background: #f97316; }
    .dot-restart { background: var(--accent); }
    .dot-offline { background: #f87171; }

    /* Inputs */
    .input-row { display: flex; gap: 6px; align-items: center; }
    .text-input {
      flex: 1;
      min-height: 44px;
      background: var(--bg);
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 12px;
      color: var(--text);
      font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .text-input:focus { border-color: var(--accent); }
    .text-input::placeholder { color: var(--text-dim); }
    .btn-browse {
      background: var(--surface-2);
      border: 1px solid var(--line-strong);
      color: var(--text);
      padding: 8px 12px;
      min-height: 44px;
      border-radius: 8px;
      font-size: 12px;
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
      min-height: 44px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      border: 1px solid transparent;
      transition: background 0.15s ease, border-color 0.15s ease;
    }
    /* Warna mengikuti arti aksi, bukan dekorasi: Jalankan = ok, Matikan = bahaya,
       Reload/Reset = netral karena keduanya hanya mengulang proses yang sama. */
    .btn-start-active { background: var(--ok); color: #fff; }
    .btn-start-active:hover { background: var(--ok-hover); }
    .btn-stop-active { background: var(--danger); color: #fff; }
    .btn-stop-active:hover { background: var(--danger-hover); }
    .btn-neutral-active { background: var(--surface-2); border-color: var(--line-strong); color: var(--text); }
    .btn-neutral-active:hover { background: #334155; }
    .btn-disabled {
      background: var(--bg) !important;
      border-color: var(--line) !important;
      color: var(--text-disabled) !important;
      cursor: not-allowed !important;
    }

    /* Preset Grid */
    .preset-header { display: flex; justify-content: space-between; align-items: center; }
    .preset-btn {
      display: flex;
      flex-direction: column;
      justify-content: flex-start;
      gap: 2px;
      width: 100%;
      min-height: 56px;
      background: var(--bg);
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      padding: 8px 10px;
      text-align: left;
      font: inherit;
      color: inherit;
      cursor: pointer;
      transition: background 0.15s, border-color 0.15s;
    }
    .preset-btn:hover { border-color: var(--accent); }
    .preset-btn-selected { border-color: var(--accent) !important; background: var(--accent-soft) !important; }
    .preset-name { font-weight: 700; color: var(--text); display: flex; align-items: center; gap: 5px; font-size: 12px; }
    .preset-dim { font-size: 11px; color: var(--text-dim); margin-top: 2px; }

    /* Log Box */
    .card-log { flex: 1; min-height: 170px; }
    .log-box {
      flex: 1;
      background: var(--bg);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
      font-size: 11px;
      color: var(--text-dim);
      overflow-y: auto;
      line-height: 1.45;
      min-height: 72px;
      user-select: text;
    }
    .log-box::-webkit-scrollbar { width: 4px; }
    .log-box::-webkit-scrollbar-thumb { background: var(--line-strong); border-radius: 2px; }
    .log-line { white-space: pre-wrap; word-break: break-word; }

    /* Footer */
    .footer {
      display: flex;
      justify-content: center;
      align-items: center;
      padding-top: 2px;
      font-size: 11px;
      color: var(--text-dim);
    }

    .link-btn {
      display: inline-flex;
      align-items: center;
      min-height: 44px;
      background: none;
      border: 0;
      padding: 0 6px;
      font: inherit;
      font-size: 11px;
      color: var(--text-dim);
      cursor: pointer;
      text-decoration: underline;
      text-underline-offset: 3px;
    }
    .link-btn:hover:not(:disabled) { color: var(--text); }
    .link-btn:disabled { color: var(--text-disabled); cursor: not-allowed; text-decoration: none; }
    .field-hint { font-size: 11px; color: var(--text-dim); }
    .field-hint.is-error { color: #fca5a5; }
    .log-empty { font-size: 11px; color: var(--text-dim); }
    .log-empty[hidden] { display: none; }
    .visually-hidden {
      position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
      overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
    }

    svg { vertical-align: middle; fill: currentColor; }
    .icon-slot { width: 16px; height: 16px; display: inline-flex; align-items: center; justify-content: center; flex: none; }

    :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

    @media (prefers-reduced-motion: reduce) {
      * { transition: none !important; animation: none !important; }
    }
  </style>
</head>
<body>
  <div class="app-container">

    <!-- 1. Header -->
    <div class="header">
      <div>
        <h1 class="header-title">Flutter Controller</h1>
        <p class="header-sub">Pratinjau Flutter di layar ponsel</p>
      </div>
      <div id="statusBadge" class="badge" role="status" aria-live="polite">
        <span id="statusDot" class="dot dot-idle" aria-hidden="true"></span>
        <span id="statusText">Menunggu</span>
      </div>
    </div>

    <!-- 2. Proyek Picker -->
    <div class="card">
      <h2 class="card-title">Folder proyek</h2>
      <div class="input-row">
        <label class="visually-hidden" for="projectPathInput">Folder proyek Flutter</label>
        <input type="text" id="projectPathInput" onchange="onManualPathInput(this.value)"
          class="text-input" placeholder="Belum ada folder dipilih" spellcheck="false">
        <button type="button" onclick="browseProject()" class="btn-browse">
          <span class="icon-slot" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg></span>
          <span>Pilih</span>
        </button>
      </div>
      <p id="projectHint" class="field-hint">Pilih folder yang berisi pubspec.yaml.</p>
    </div>

    <!-- 3. Kontrol Aksi -->
    <div class="card">
      <h2 class="card-title">Kontrol</h2>
      <div class="btn-grid">
        <button type="button" id="btnStart" onclick="startFlutter()" class="action-btn btn-start-active">
          <span class="icon-slot" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></span>
          <span>Jalankan</span>
        </button>
        <button type="button" id="btnStop" onclick="stopFlutter()" class="action-btn btn-disabled" disabled>
          <span class="icon-slot" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg></span>
          <span>Matikan</span>
        </button>
        <button type="button" id="btnReload" onclick="triggerReload()" class="action-btn btn-disabled" disabled>
          <span class="icon-slot" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg></span>
          <span>Muat ulang</span>
        </button>
        <button type="button" id="btnReset" onclick="triggerRestart()" class="action-btn btn-disabled" disabled>
          <span class="icon-slot" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24"><path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg></span>
          <span>Mulai ulang</span>
        </button>
      </div>
    </div>

    <!-- 4. Preset Ukuran Layar -->
    <div class="card">
      <div class="preset-header">
        <h2 class="card-title" id="presetGroupLabel">Ukuran layar</h2>
      </div>
      <div class="btn-grid" id="presetGrid" role="group" aria-labelledby="presetGroupLabel"></div>
    </div>

    <!-- 5. Output Log -->
    <div class="card card-log">
      <div class="preset-header">
        <h2 class="card-title">Output log</h2>
        <button type="button" id="btnClearLogs" onclick="clearLogs()" class="link-btn" disabled>Bersihkan</button>
      </div>
      <div id="logBox" class="log-box" role="log" aria-live="polite" aria-relevant="additions" tabindex="0"></div>
      <p id="logEmpty" class="log-empty">Belum ada output. Tekan Jalankan untuk memulai build.</p>
    </div>

    <!-- 6. Footer -->
    <div class="footer">
      <span>© VallDev</span>
    </div>

  </div>

  <script>
    const STATUS = {
      idle:     { label: "Menunggu",    badge: "badge",                dot: "dot dot-idle" },
      starting: { label: "Membangun",   badge: "badge badge-starting", dot: "dot dot-starting" },
      running:  { label: "Berjalan",    badge: "badge badge-running",  dot: "dot dot-running" },
      reload:   { label: "Muat ulang",  badge: "badge badge-reload",   dot: "dot dot-reload" },
      restart:  { label: "Mulai ulang", badge: "badge badge-restart",  dot: "dot dot-restart" },
      offline:  { label: "Server mati", badge: "badge badge-offline",  dot: "dot dot-offline" },
    };
    const ENABLED = {
      idle:     { start: true,  stop: false, reload: false, reset: false },
      starting: { start: false, stop: true,  reload: true,  reset: true },
      running:  { start: false, stop: true,  reload: true,  reset: true },
      reload:   { start: false, stop: true,  reload: false, reset: true },
      restart:  { start: false, stop: true,  reload: true,  reset: false },
      offline:  { start: false, stop: false, reload: false, reset: false },
    };
    const BUTTONS = {
      start:  { on: "action-btn btn-start-active",  off: "action-btn btn-disabled" },
      stop:   { on: "action-btn btn-stop-active",   off: "action-btn btn-disabled" },
      reload: { on: "action-btn btn-neutral-active", off: "action-btn btn-disabled" },
      reset:  { on: "action-btn btn-neutral-active", off: "action-btn btn-disabled" },
    };

    let pollTimer = null;

    function el(id) { return document.getElementById(id); }

    const PRESET_ICONS = {
      mobile: '<svg width="14" height="14" viewBox="0 0 24 24"><path d="M17 1.01L7 1c-1.1 0-2 .9-2 2v18c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V3c0-1.1-.9-1.99-2-1.99zM17 19H7V5h10v14z"/></svg>',
      tablet: '<svg width="14" height="14" viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-1 14H6V6h12v11z"/></svg>'
    };
    let renderedPresets = null;

    function renderPresets(presets) {
      const signature = JSON.stringify(presets);
      if (signature === renderedPresets) return;
      renderedPresets = signature;
      const grid = el("presetGrid");
      grid.innerHTML = Object.keys(presets).map(id => {
        const p = presets[id];
        return `<button type="button" aria-pressed="false" id="p-${id}" class="preset-btn">
          <span class="preset-name"><span class="icon-slot" aria-hidden="true">${p.w >= 700 ? PRESET_ICONS.tablet : PRESET_ICONS.mobile}</span><span>${p.name}</span></span>
          <span class="preset-dim">${p.w} x ${p.h} px</span>
        </button>`;
      }).join("");
      grid.querySelectorAll(".preset-btn").forEach(node => {
        node.addEventListener("click", () => setPreset(node.id.slice(2)));
      });
    }

    function applyPreset(presetId) {
      document.querySelectorAll("#presetGrid .preset-btn").forEach(node => {
        const on = node.id === "p-" + presetId;
        node.classList.toggle("preset-btn-selected", on);
        node.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }

    function applyStatus(status) {
      const s = STATUS[status] || STATUS.idle;
      const e = ENABLED[status] || ENABLED.idle;
      el("statusBadge").className = s.badge;
      el("statusDot").className = s.dot;
      el("statusText").textContent = s.label;
      for (const key of Object.keys(BUTTONS)) {
        const node = el("btn" + key[0].toUpperCase() + key.slice(1));
        node.disabled = !e[key];
        node.className = e[key] ? BUTTONS[key].on : BUTTONS[key].off;
      }
    }

    function setHint(text, isError) {
      const hint = el("projectHint");
      hint.textContent = text;
      hint.classList.toggle("is-error", Boolean(isError));
    }

    let renderedLogs = [];

    function logLine(text) {
      const div = document.createElement("div");
      div.className = "log-line";
      div.textContent = text;
      return div;
    }

    function renderLogs(logs) {
      const box = el("logBox");
      el("logEmpty").hidden = logs.length > 0;
      el("btnClearLogs").disabled = logs.length === 0;

      if (logs.length === renderedLogs.length && logs.every((l, i) => l === renderedLogs[i])) return;
      const shouldScroll = box.scrollHeight - box.scrollTop <= box.clientHeight + 30;
      const isAppend = logs.length > renderedLogs.length && renderedLogs.every((l, i) => l === logs[i]);
      if (isAppend) {
        // Tempel hanya baris baru: DOM lama tetap utuh, jadi seleksi teks tidak hilang saat polling.
        logs.slice(renderedLogs.length).forEach(l => box.appendChild(logLine(l)));
      } else {
        box.replaceChildren(...logs.map(logLine));
      }
      renderedLogs = logs.slice();
      if (shouldScroll) box.scrollTop = box.scrollHeight;
    }

    function applyState(data) {
      renderPresets(data.presets || {});
      const input = el("projectPathInput");
      if (document.activeElement !== input) {
        input.value = data.project_path || "";
        input.title = data.project_path || "";
      }
      if (data.project_error) {
        setHint(data.project_error, true);
      } else if (!data.project_path) {
        setHint("Pilih folder yang berisi pubspec.yaml.", false);
      } else {
        setHint("pubspec.yaml ditemukan. Proyek siap dijalankan.", false);
      }

      applyStatus(data.status);
      applyPreset(data.active_preset);
      renderLogs(data.logs || []);
    }

    function setOffline() {
      applyStatus("offline");
      setHint("Controller tidak menjawab. Tutup jendela ini lalu jalankan ulang Buka_Controller.", true);
      el("logEmpty").hidden = el("logBox").childElementCount > 0;
    }

    async function fetchState() {
      let delay = 1000;
      try {
        const res = await fetch("/api/state", { cache: "no-store" });
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();
        applyState(data);
        delay = (data.status === "starting" || data.status === "reload" || data.status === "restart") ? 600 : 900;
      } catch (e) {
        setOffline();
        delay = 1500;
      }
      clearTimeout(pollTimer);
      pollTimer = setTimeout(fetchState, delay);
    }

    async function post(path, body) {
      try {
        await fetch(path, { method: "POST", body });
      } catch (e) {
        setOffline();
      }
      clearTimeout(pollTimer);
      pollTimer = setTimeout(fetchState, 150);
    }

    function browseProject() { post("/api/browse"); }

    function onManualPathInput(path) {
      if (path && path.trim()) post("/api/set_path?path=" + encodeURIComponent(path.trim()));
    }

    function startFlutter() {
      const p = el("projectPathInput").value;
      if (!p || p.trim() === "") {
        setHint("Pilih folder proyek Flutter dulu sebelum menjalankan.", true);
        el("projectPathInput").focus();
        return;
      }
      post("/api/start");
    }

    function stopFlutter() { post("/api/stop"); }
    function triggerReload() { post("/api/reload"); }
    function triggerRestart() { post("/api/restart"); }
    function setPreset(pid) { post("/api/resize?preset=" + encodeURIComponent(pid)); }
    function clearLogs() { post("/api/clear_logs"); }

    if (window.__INITIAL_STATE__) applyState(window.__INITIAL_STATE__);
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
            payload = json.dumps(state).replace("<", "\\u003c").replace("&", "\\u0026")
            page = HTML_PAGE.replace("__STATE_JSON__", payload, 1).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(page)
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
