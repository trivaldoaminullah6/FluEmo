"""Launcher Chrome seukuran ponsel untuk `flutter run -d chrome`.

Modul ini punya dua peran:

- `command()` mengembalikan path executable `fluemo-launcher`, nilai yang dipakai
  sebagai `CHROME_EXECUTABLE`.
- `main()` adalah entry point `fluemo-launcher`: menerima argumen Chrome dari
  Flutter, menambahkan ukuran/posisi jendela ponsel, lalu menjalankan browser.

Satu implementasi untuk Linux, macOS, dan Windows; tanpa dependensi pip.
"""

import os
import shutil
import site
import subprocess
import sys
import sysconfig

from . import browser, paths

DEFAULT_WIDTH = 430
DEFAULT_HEIGHT = 920
DEFAULT_X = 550
DEFAULT_Y = 50
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)
URL_PREFIXES = ("http://", "https://", "localhost:", "127.0.0.1:")


def command() -> str:
    """Path executable launcher yang dipakai sebagai CHROME_EXECUTABLE."""
    name = "fluemo-launcher.exe" if os.name == "nt" else "fluemo-launcher"
    candidates = []

    # 1. PATH: menangani pipx dan `pip install --user`.
    found = shutil.which("fluemo-launcher")
    if found:
        candidates.append(found)

    # 2. Sebelah interpreter: menangani venv biasa.
    candidates.append(os.path.join(os.path.dirname(sys.executable), name))

    # 3. Direktori skrip menurut sysconfig (dan base pengguna untuk --user).
    scripts = sysconfig.get_path("scripts")
    if scripts:
        candidates.append(os.path.join(scripts, name))
    candidates.append(
        os.path.join(
            site.getuserbase(), "Scripts" if os.name == "nt" else "bin", name
        )
    )

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    raise RuntimeError(
        "fluemo-launcher tidak ditemukan. Pasang ulang paket: "
        "pip install --force-reinstall fluemo"
    )


def _read_mobile_config():
    """Baca mobile_config.txt (key=value). Nilai tidak valid diabaikan."""
    cfg = {
        "width": DEFAULT_WIDTH,
        "height": DEFAULT_HEIGHT,
        "x": DEFAULT_X,
        "y": DEFAULT_Y,
        "useragent": DEFAULT_USER_AGENT,
    }
    if not os.path.exists(paths.MOBILE_CONFIG_FILE):
        return cfg
    try:
        with open(paths.MOBILE_CONFIG_FILE, "r", encoding="utf-8") as f:
            for raw_line in f:
                if "=" not in raw_line:
                    continue
                key, _, value = raw_line.partition("=")
                key = key.strip().lower()
                value = value.strip()
                if key in ("width", "height", "x", "y"):
                    number = int(value)
                    if key in ("width", "height") and number <= 0:
                        continue
                    cfg[key] = number
                elif key == "useragent" and value:
                    cfg["useragent"] = value
    except Exception:
        pass
    return cfg


def _log(line):
    try:
        with open(paths.LAUNCHER_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _build_args(argv, cfg):
    """Susun argumen Chrome: ukuran ponsel dulu, lalu argumen Flutter yang relevan."""
    args = [
        f"--window-size={cfg['width']},{cfg['height']}",
        f"--window-position={cfg['x']},{cfg['y']}",
        "--class=FlutterMobilePreview",
        "--touch-events=enabled",
        "--force-device-scale-factor=1",
        f"--user-agent={cfg['useragent']}",
    ]
    if os.name != "nt":
        # Paksa X11 (via Xwayland) agar --window-size/--window-position berlaku.
        args.append("--ozone-platform=x11")

    target_url = ""
    for raw in argv:
        if raw.startswith(URL_PREFIXES):
            target_url = raw
            break
    if target_url:
        args.append(f"--app={target_url}")

    for raw in argv:
        if raw.startswith(("--window-size=", "--window-position=", "--app=")):
            continue
        if raw.startswith(URL_PREFIXES):
            continue
        args.append(raw)
    return args


def main() -> int:
    cfg = _read_mobile_config()
    chrome_cmd = browser.find_chrome_command()
    if not chrome_cmd:
        print("Error: Google Chrome / Chromium tidak ditemukan!", file=sys.stderr)
        _log("ERROR: Chrome/Chromium not found")
        return 1

    # Flutter memanggil `<CHROME_EXECUTABLE> --version` saat verbose; teruskan apa adanya.
    if "--version" in sys.argv[1:]:
        return subprocess.run([*chrome_cmd, *sys.argv[1:]]).returncode

    argv = sys.argv[1:]
    args = _build_args(argv, cfg)

    _log(f"\nLAUNCH TRIGGERED. Args count: {len(argv)}")
    for index, raw in enumerate(argv):
        _log(f"  arg[{index}] = {raw}")
    _log('Final command: "%s" %s' % (" ".join(chrome_cmd), " ".join(args)))

    result = subprocess.run([*chrome_cmd, *args])
    _log(f"Exit code: {result.returncode}")
    return result.returncode
