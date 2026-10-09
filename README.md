# Flutter Mobile Studio (Runner Ringan Pengganti Emulator)

Aplikasi desktop controller ultra-ringan untuk menjalankan proyek Flutter langsung ke Google Chrome dengan format tampilan smartphone/tablet tanpa menggunakan emulator Android yang berat.

## Keunggulan & Optimasi
- **RAM < 200 MB** (Emulator Android biasa memakan 4–8 GB RAM).
- **0% CPU saat idle** dengan pemuatan style murni tanpa dependensi compiler eksternal.
- **100% Offline Ready** (Tanpa CDN eksternal, aset SVG tertanam).
- **Dukungan Hot Reload (`r`) dan Hot Restart (`R`)** secara instan.
- **Ukuran Layar Lega**: Pilihan preset iPhone 15 Pro Max, Pixel 8 Pro, iPad mini (A17), iPad Air 11".

## Struktur Folder
```text
FluEmo/
├── Buka_Controller.bat        <-- Shortcut Windows
├── Buka_Controller.sh         <-- Shortcut Linux/macOS
├── README.md                  <-- Dokumentasi proyek
└── core/                      <-- Mesin inti aplikasi
    ├── app_server.py          <-- Server backend & GUI Controller
    ├── chrome_mobile_launcher.exe <-- Launcher Windows (interceptor ukuran layar)
    ├── ChromeMobileLauncher.cs    <-- Source code C# launcher Windows
    ├── chrome_mobile_launcher.sh  <-- Launcher Linux (padanan .exe)
    ├── x11_window.py          <-- Kontrol jendela X11 (Linux)
    └── mobile_config.txt      <-- Konfigurasi koordinat jendela
```

## Cara Menjalankan (Windows)
1. Klik ganda pada `Buka_Controller.bat`.
2. Klik tombol **Pilih** atau ketik path folder proyek Flutter Anda.
3. Klik **Jalankan** untuk memulai Flutter.
4. Gunakan tombol **Muat ulang (r)**, **Mulai ulang (R)**, dan **Matikan** sesuai kebutuhan.
5. Klik preset ukuran layar untuk mengubah ukuran jendela pengujian secara langsung.

## Cara Menjalankan (Linux / Fedora)
1. Pastikan `flutter` ada di `PATH`:
   ```bash
   export PATH="$HOME/development/flutter/bin:$PATH"
   flutter --version
   ```
2. Pasang Chrome/Chromium (pilih salah satu):
   ```bash
   # Chromium dari Flathub (tanpa sudo)
   flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
   flatpak install --user flathub org.chromium.Chromium

   # atau via dnf (butuh sudo, aktifkan repo RPM Fusion bila belum):
   sudo dnf install chromium
   ```
3. Pasang `zenity` untuk dialog pemilihan folder (opsional; tombol **Pilih**):
   ```bash
   sudo dnf install zenity
   ```
4. Jalankan controller:
   ```bash
   ./Buka_Controller.sh
   ```
   Controller terbuka di jendela Chrome mode `--app` pada `http://127.0.0.1:7890`.

### Catatan Linux
- Ukuran/posisi jendela diatur lewat libX11. Chrome/Chromium dipaksa jalan sebagai klien X11 (via Xwayland) supaya `--window-size` dan resize preset benar-benar berlaku.
- Cara lain: jalankan sesi Xorg dari layar login bila ingin X11 native.
- Preset mengubah ukuran jendela app yang **baru diluncurkan** controller ini; jendela `flutter run` lain tidak diganggu.
- Gratis dependensi Python tambahan: hanya `python3` standard library.
