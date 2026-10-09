#!/usr/bin/env bash
# Buka Controller (Linux) - padanan Buka_Controller.bat
# Menjalankan server backend + GUI controller Flutter Mobile Studio.

set -u

ROOT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Error: python3 tidak ditemukan. Pasang dulu: sudo dnf install python3" >&2
  exit 1
fi

if ! command -v flutter >/dev/null 2>&1; then
  echo "Peringatan: 'flutter' tidak ada di PATH. Tambahkan flutter/bin ke PATH." >&2
fi

exec "$PYTHON" "$ROOT_DIR/core/app_server.py"
