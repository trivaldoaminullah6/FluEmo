"""Lokasi file runtime fluemo (~/.fluemo)."""

import os

STORAGE_DIR = os.path.join(os.path.expanduser("~"), ".fluemo")
CONFIG_FILE = os.path.join(STORAGE_DIR, "config.json")
MOBILE_CONFIG_FILE = os.path.join(STORAGE_DIR, "mobile_config.txt")
LAUNCHER_LOG_FILE = os.path.join(STORAGE_DIR, "launcher_log.txt")
SERVER_LOG_FILE = os.path.join(STORAGE_DIR, "server.log")
SERVER_STATE_FILE = os.path.join(STORAGE_DIR, "server.json")
CONTROLLER_PROFILE_DIR = os.path.join(STORAGE_DIR, "controller_profile")


def ensure_storage():
    """Buat direktori penyimpanan bila belum ada."""
    os.makedirs(CONTROLLER_PROFILE_DIR, exist_ok=True)
    return STORAGE_DIR
