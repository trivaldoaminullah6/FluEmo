#!/usr/bin/env bash
# ChromeMobileLauncher (Linux) - padanan ChromeMobileLauncher.cs
# Dipakai lewat env CHROME_EXECUTABLE oleh "flutter run -d chrome".
# Tugas: jalankan Chrome/Chromium dengan ukuran & posisi jendela ala smartphone,
#        touch event aktif, dan User-Agent mobile.

set -u

CORE_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
LOG_FILE="$CORE_DIR/launcher_log.txt"
CFG_FILE="$CORE_DIR/mobile_config.txt"

win_width=430
win_height=920
win_x=550
win_y=50
user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

if [ -f "$CFG_FILE" ]; then
  while IFS='=' read -r key value; do
    key="$(echo "$key" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
    value="$(echo "$value" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    case "$key" in
      width)  [[ "$value" =~ ^[0-9]+$ ]] && win_width="$value" ;;
      height) [[ "$value" =~ ^[0-9]+$ ]] && win_height="$value" ;;
      x)      [[ "$value" =~ ^-?[0-9]+$ ]] && win_x="$value" ;;
      y)      [[ "$value" =~ ^-?[0-9]+$ ]] && win_y="$value" ;;
      useragent) user_agent="$value" ;;
    esac
  done < "$CFG_FILE"
fi

# Cari browser: sistem dulu, lalu flatpak.
BROWSER=()
for candidate in google-chrome google-chrome-stable chromium chromium-browser; do
  if command -v "$candidate" >/dev/null 2>&1; then
    BROWSER=("$(command -v "$candidate")")
    break
  fi
done
if [ ${#BROWSER[@]} -eq 0 ] && command -v flatpak >/dev/null 2>&1; then
  for app_id in org.chromium.Chromium com.google.Chrome; do
    if flatpak info --user "$app_id" >/dev/null 2>&1 || flatpak info "$app_id" >/dev/null 2>&1; then
      BROWSER=(flatpak run "$app_id")
      break
    fi
  done
fi
if [ ${#BROWSER[@]} -eq 0 ]; then
  echo "Error: Google Chrome / Chromium tidak ditemukan!" >&2
  printf '[%s] ERROR: Chrome/Chromium not found\n' "$(date)" >> "$LOG_FILE"
  exit 1
fi

{
  printf '\n[%s] LAUNCH TRIGGERED. Args count: %s\n' "$(date)" "$#"
  i=0
  for a in "$@"; do
    printf '  arg[%s] = %s\n' "$i" "$a"
    i=$((i + 1))
  done
} >> "$LOG_FILE"

new_args=(--window-size="${win_width},${win_height}")
new_args+=(--window-position="${win_x},${win_y}")
new_args+=(--class=FlutterMobilePreview)
new_args+=(--touch-events=enabled)
new_args+=(--force-device-scale-factor=1)
new_args+=(--user-agent="$user_agent")
# Paksa X11 (via Xwayland) agar --window-size/--window-position berlaku.
new_args+=(--ozone-platform=x11)

target_url=""
for raw in "$@"; do
  case "$raw" in
    http://*|https://*|localhost:*|127.0.0.1:*) target_url="$raw" ;;
  esac
done
[ -n "$target_url" ] && new_args+=(--app="$target_url")

# Teruskan argumen flutter (profil, remote debugging, dsb) kecuali ukuran/posisi/URL.
for raw in "$@"; do
  case "$raw" in
    --window-size=*|--window-position=*|--app=*) continue ;;
    http://*|https://*) continue ;;
    *) new_args+=("$raw") ;;
  esac
done

printf 'Final command: "%s" %s\n' "${BROWSER[*]}" "${new_args[*]}" >> "$LOG_FILE"

exec "${BROWSER[@]}" "${new_args[@]}"
