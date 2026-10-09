# fluemo

Runner Flutter web super ringan: pratinjau aplikasi Flutter di jendela Chrome **seukuran ponsel**, tanpa emulator dan tanpa Android Studio.

Satu perintah, tanpa konfigurasi:

```bash
pip install fluemo
cd proyek-flutter-ku
fluemo
```

`fluemo` mendeteksi proyek Flutter di folder saat ini, menjalankan `flutter run -d chrome` di latar belakang, membuka jendela controller, dan langsung mengembalikan terminal ke Anda.

## Instalasi (global, sekali per mesin)

`fluemo` dipasang **sekali per mesin**, bukan per proyek. Setelah itu Anda bisa memakainya dari folder proyek Flutter mana pun.

### Disarankan: pipx

```bash
pipx install fluemo
```

pipx memasang `fluemo` di lingkungan terisolasi miliknya dan menaruh executable di `~/.local/bin` (Linux/macOS) atau `%USERPROFILE%\.local\bin` (Windows). Cara ini tidak menyentuh Python sistem, jadi aman dari konflik paket dan dari proteksi PEP 668.

### Alternatif: pip

```bash
pip install --user fluemo      # Linux/macOS
py -m pip install --user fluemo   # Windows
```

Pastikan direktori script Python ada di `PATH`. Di Windows, centang **"Add Python to PATH"** saat memasang Python.

**Jangan** memasang `fluemo` di dalam virtualenv milik satu proyek: instalasi jadi terkurung di proyek itu dan tidak bisa dipanggil dari folder proyek lain. Bila terminal menolak `pip install fluemo` dengan `error: externally-managed-environment`, gunakan pipx atau tambahkan `--user`.

Cek hasilnya:

```bash
fluemo --version
```

### Syarat

- **Python 3.8+**
- **Flutter SDK** di `PATH` (`flutter --version` harus jalan)
- **Chrome atau Chromium**
  - Linux: `flatpak install --user flathub org.chromium.Chromium` atau `sudo dnf install chromium`
  - Windows: Chrome dari google.com, atau `winget install Google.Chrome`
- **zenity** (opsional, Linux) untuk dialog pemilih folder

## Pemakaian

```bash
cd proyek-flutter-ku
fluemo
```

Yang terjadi:

1. `fluemo` mencari `pubspec.yaml` di folder saat ini, lalu naik maksimum 5 level ke atas.
2. Server berjalan di latar belakang — terminal Anda langsung bebas, tetap bisa dipakai untuk perintah lain.
3. Jendela controller terbuka dengan tombol **Jalankan**, **Matikan**, **Muat ulang**, **Mulai ulang**, dan pemilih ukuran layar.
4. Aplikasi Flutter muncul di jendela Chrome terpisah yang dikunci seukuran perangkat pilihan (mis. iPhone 15 Pro Max atau iPad mini).

Stop semuanya dengan salah satu cara:

- klik **Keluar** di jendela controller, atau
- tutup jendela controller seperti jendela biasa — server ikut mati sendiri.

Keduanya mematikan `flutter run`, jendela aplikasi, jendela controller, dan server sekaligus.

Menjalankan `fluemo` lagi saat server masih hidup tidak memulai server kedua: perintah itu memakai instance yang sudah berjalan. Bila proyek di folder baru belum berjalan, proyek itu yang dijalankan; bila proyek lain sedang berjalan, proyek itu dibiarkan dan Anda diarahkan ke jendela controller yang ada.

## Keunggulan & Optimasi

- **Nol dependensi pip** — hanya standard library Python.
- **Satu implementasi launcher** untuk Linux, macOS, dan Windows.
- **Ringan** — UI controller adalah satu halaman HTML dengan CSS dan SVG inline: tanpa permintaan jaringan, tanpa framework.
- **Hot reload dan hot restart** diteruskan ke `flutter run` dari jendela controller.
- **Ukuran jendela presisi** — launcher menjalankan Chrome dalam mode aplikasi (`--app`) sehingga ukuran jendela sama dengan ukuran konten perangkat, bukan ukuran jendela ber-chrome.

## Struktur folder

```
fluemo/
  __init__.py      <-- versi paket
  __main__.py      <-- entry point `python -m fluemo`
  cli.py           <-- perintah `fluemo`: deteksi proyek, spawn/reuse server
  server.py        <-- server HTTP + API, pengelola proses flutter, jendela controller
  ui.py            <-- halaman controller (HTML + CSS + JS inline)
  launcher.py      <-- entry point `fluemo-launcher`; ukuran & posisi jendela ponsel
  browser.py       <-- pencarian Chrome/Chromium
  paths.py         <-- lokasi file runtime di ~/.fluemo
  x11_window.py    <-- kendali jendela X11 via ctypes (khusus Linux)
pyproject.toml
LICENSE
README.md
```

File runtime disimpan di `~/.fluemo/`: `config.json` (preset terakhir), `mobile_config.txt` (ukuran jendela aktif), `server.json` (pid & port server), `server.log`, `launcher_log.txt`, dan profil Chrome khusus controller.

## Pengembangan

```bash
python -m venv .venv
.venv/bin/pip install -e .          # Linux/macOS
.venv\Scripts\pip install -e .      # Windows
.venv/bin/fluemo --version
```

## Publikasi

```bash
python -m build
twine check dist/*
twine upload dist/*
```

`twine upload` membutuhkan token PyPI.

## Lisensi

MIT — lihat [LICENSE](LICENSE).
