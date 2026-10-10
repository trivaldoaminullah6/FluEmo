"""CLI fluemo: jalankan server latar belakang + buka controller."""

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from . import paths

USAGE = """fluemo — runner Flutter web seukuran ponsel.

Pemakaian:
  cd <folder-proyek-flutter>
  fluemo

Opsi:
  -h, --help     tampilkan bantuan ini
  -V, --version  tampilkan versi
"""


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["_serve"]:
        from . import server

        server.main()
        return 0
    if args and args[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if args and args[0] in ("-V", "--version"):
        from . import __version__

        print(f"fluemo {__version__}")
        return 0
    return _run()


def _run() -> int:
    """Buka controller untuk proyek di cwd, pakai server yang sudah jalan bila ada."""
    paths.ensure_storage()
    project = _find_project()
    base = _running_server_url()

    if base:
        print(f"fluemo: server sudah jalan → {base}")
        if project:
            if _get_status(base) == "idle":
                _post(f"{base}/api/set_path?path={urllib.parse.quote(project)}")
                _post(f"{base}/api/start")
                print(f"fluemo: proyek  {project}")
            else:
                print(f"fluemo: proyek lain masih berjalan; kontrol lewat {base}")
        return 0

    _spawn_server()
    base = _wait_server(15.0)
    if not base:
        _print_log_tail()
        return 1

    if project:
        _post(f"{base}/api/set_path?path={urllib.parse.quote(project)}")
        if _get_status(base) == "idle":
            _post(f"{base}/api/start")
        print(f"fluemo: proyek  {project}")
    else:
        print("fluemo: proyek  (belum dipilih)")
    print(f"fluemo: controller → {base}")
    print(
        "fluemo: jalan di latar belakang. "
        "Tutup jendela controller atau klik Keluar untuk berhenti."
    )
    return 0


def _find_project() -> str:
    """Folder proyek Flutter: pubspec.yaml di cwd, atau naik maksimum 5 level."""
    current = os.getcwd()
    for _ in range(6):
        if os.path.exists(os.path.join(current, "pubspec.yaml")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return ""


def _running_server_url() -> str:
    """URL server fluemo yang sedang jalan, atau "" bila tidak ada."""
    try:
        with open(paths.SERVER_STATE_FILE, "r", encoding="utf-8") as f:
            info = json.load(f)
    except Exception:
        return ""
    url = info.get("url") or f"http://127.0.0.1:{info.get('port')}"
    try:
        with urllib.request.urlopen(f"{url}/api/state", timeout=1.5) as res:
            payload = json.loads(res.read().decode("utf-8"))
    except Exception:
        return ""
    return url if payload.get("fluemo") else ""


def _post(url: str) -> None:
    """POST tanpa menunggu isi respons; kegagalan diabaikan."""
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, data=b"", method="POST"), timeout=5
        ).read()
    except Exception:
        pass


def _get_status(base: str) -> str:
    """Status server: 'idle', 'running', ... atau "" bila tidak terbaca."""
    try:
        with urllib.request.urlopen(f"{base}/api/state", timeout=2) as res:
            return json.loads(res.read().decode("utf-8")).get("status", "")
    except Exception:
        return ""


def _wait_server(timeout: float) -> str:
    """Tunggu server.json hidup dan endpointnya menjawab."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        url = _running_server_url()
        if url:
            return url
        time.sleep(0.25)
    return ""


def _print_log_tail():
    """Tampilkan 15 baris terakhir log server saat server gagal hidup."""
    try:
        with open(paths.SERVER_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-15:]
    except Exception:
        return
    print("fluemo: server gagal start. Log terakhir:", file=sys.stderr)
    for line in lines:
        print("  " + line.rstrip("\n"), file=sys.stderr)


def _spawn_server() -> None:
    """Jalankan server fluemo terlepas dari terminal pemanggil."""
    log_handle = open(paths.SERVER_LOG_FILE, "a", encoding="utf-8")
    kwargs = dict(
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        cwd=os.getcwd(),
    )
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, "-m", "fluemo", "_serve"], **kwargs)
