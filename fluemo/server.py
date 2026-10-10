import os
import sys
import time
import json
import shutil
import signal
import threading
import subprocess
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

from . import __version__, browser, launcher, paths
from .ui import HTML_PAGE

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

PORT_RANGE = range(
    int(os.environ.get("FLUEMO_PORT", "7890")),
    int(os.environ.get("FLUEMO_PORT", "7890")) + 10,
)

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
LAUNCHER_CMD = ""

# ---------------------------------------------------------------- X11 (Linux)
# Di Linux, pencarian & pemindahan jendela memakai libX11 via ctypes (lihat x11_window.py).
# Tidak ada dependensi pip, murni pustaka sistem.
if not IS_WINDOWS:
    from . import x11_window

    CONTROLLER_WM_CLASS = x11_window.CONTROLLER_WM_CLASS
else:
    # Hanya dipakai untuk argumen --class Chrome; di Windows nilainya diabaikan
    # tetapi argumennya tetap harus berbentuk string.
    CONTROLLER_WM_CLASS = "FlutterController"


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
    "logs": [],
    "fluemo": True,
}

flutter_proc = None
controller_hwnd = None
cached_flutter_hwnd = None
_mobile_window_baseline = frozenset()
_shutting_down = False

def load_saved_config():
    if os.path.exists(paths.CONFIG_FILE):
        try:
            with open(paths.CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("active_preset") in state["presets"]:
                    state["active_preset"] = data["active_preset"]
        except Exception:
            pass

load_saved_config()

def save_config():
    try:
        with open(paths.CONFIG_FILE, "w", encoding="utf-8") as f:
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
    cfg_path = paths.MOBILE_CONFIG_FILE
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
    if LAUNCHER_CMD:
        env["CHROME_EXECUTABLE"] = LAUNCHER_CMD

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
        popen_kwargs = {}
        if not IS_WINDOWS:
            # Process group sendiri supaya killpg mematikan flutter + anak-anaknya.
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(
            cmd,
            cwd=project,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **popen_kwargs,
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

def _kill_flutter_tree(pid):
    """Bunuh flutter run beserta anak-anaknya (dart, launcher, Chrome)."""
    if IS_WINDOWS:
        # Membunuh pohon proses.
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
            )
        except Exception:
            pass
        return
    # flutter run + launcher hidup di process group sendiri
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
            _kill_flutter_tree(pid)

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

class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            payload = json.dumps(state).replace("<", "\\u003c").replace("&", "\\u0026")
            page = HTML_PAGE.replace("__STATE_JSON__", payload, 1).replace(
                "__VERSION__", __version__, 1
            ).encode("utf-8")
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

        elif parsed.path == "/api/quit":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            threading.Thread(target=shutdown_everything, daemon=True).start()

        elif parsed.path == "/api/clear_logs":
            state["logs"] = []
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

def _bind_server():
    """Bind ke port pertama yang bebas di PORT_RANGE."""
    last_error = None
    for port in PORT_RANGE:
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), RequestHandler)
        except OSError as exc:
            last_error = exc
    print(
        f"fluemo: port {PORT_RANGE.start}-{PORT_RANGE.stop - 1} semuanya terpakai",
        file=sys.stderr,
    )
    raise SystemExit(1) from last_error


def _write_server_state(port):
    """Catat pid/port server supaya `fluemo` berikutnya bisa menemukannya."""
    try:
        with open(paths.SERVER_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"pid": os.getpid(), "port": port, "url": f"http://127.0.0.1:{port}"},
                f,
                indent=2,
            )
    except Exception:
        pass


def _remove_server_state():
    """Hapus server.json hanya bila milik proses ini."""
    try:
        with open(paths.SERVER_STATE_FILE, "r", encoding="utf-8") as f:
            info = json.load(f)
        if info.get("pid") != os.getpid():
            return
        os.remove(paths.SERVER_STATE_FILE)
    except Exception:
        pass


def _close_controller_windows():
    """Tutup jendela controller tanpa bergantung pada user."""
    if IS_WINDOWS:
        if controller_hwnd:
            try:
                user32.PostMessageW(controller_hwnd, 0x0010, 0, 0) # WM_CLOSE
            except Exception:
                pass
        return
    try:
        xid = x11_window.find_controller()
        if xid:
            x11_window.close(xid)
    except Exception:
        pass


def shutdown_everything():
    """Matikan flutter, tutup jendela controller, hapus server.json, keluar."""
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True

    pid = flutter_proc.pid if flutter_proc else None
    _close_controller_windows()
    _remove_server_state()
    if pid:
        # Bunuh sebelum keluar: os._exit() menghentikan thread pendamping
        # `force_cleanup()` tanpa memberinya kesempatan jalan.
        try:
            _kill_flutter_tree(pid)
        except Exception:
            pass
    os._exit(0)


def _controller_window_alive():
    if IS_WINDOWS:
        if not controller_hwnd:
            return False
        return bool(user32.IsWindow(controller_hwnd)) and bool(
            user32.IsWindowVisible(controller_hwnd)
        )
    return x11_window.find_controller() is not None


def _controller_watchdog():
    """Keluar sendiri bila jendela controller ditutup user; tidak menutup apa pun
    bila jendela controller memang tidak pernah berhasil dibuka."""
    if not controller_hwnd:
        return
    while True:
        time.sleep(2)
        if not _controller_window_alive():
            shutdown_everything()


def _install_signal_handlers():
    def _handle(_signum, _frame):
        shutdown_everything()

    signal.signal(signal.SIGINT, _handle)
    if not IS_WINDOWS:
        signal.signal(signal.SIGTERM, _handle)


def write_initial_chrome_preferences():
    pref_dir = os.path.join(paths.CONTROLLER_PROFILE_DIR, "Default")
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

def launch_controller_window(port):
    global controller_hwnd
    url = f"http://127.0.0.1:{port}"

    write_initial_chrome_preferences()

    chrome_cmd = browser.find_chrome_command()
    if not chrome_cmd:
        add_log("Chrome/Chromium tidak ditemukan. Buka manual: " + url)
        print(f"Chrome/Chromium tidak ditemukan. Buka manual: {url}")
        return

    cmd = [
        *chrome_cmd,
        f"--user-data-dir={paths.CONTROLLER_PROFILE_DIR}",
        f"--app={url}",
        f"--class={CONTROLLER_WM_CLASS}",
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

def main():
    paths.ensure_storage()
    global LAUNCHER_CMD
    try:
        LAUNCHER_CMD = launcher.command()
    except RuntimeError as exc:
        LAUNCHER_CMD = ""
        add_log(f"{exc} Ukuran jendela ponsel tidak aktif.")

    server = _bind_server()
    _write_server_state(server.server_address[1])
    _install_signal_handlers()
    launch_controller_window(server.server_address[1])
    threading.Thread(target=_controller_watchdog, daemon=True).start()
    print(f"fluemo: controller → http://127.0.0.1:{server.server_address[1]}", flush=True)
    server.serve_forever()
