"""Pencarian executable Chrome/Chromium di Linux, macOS, dan Windows."""

import os
import shutil
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"

CHROME_CANDIDATES = (
    ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]
    if not IS_WINDOWS
    else [
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
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
