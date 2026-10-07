# Flutter Mobile Studio (Runner Ringan Pengganti Emulator)

Aplikasi desktop controller ultra-ringan untuk menjalankan proyek Flutter langsung ke Google Chrome dengan format tampilan smartphone/tablet tanpa menggunakan emulator Android yang berat.

## Keunggulan & Optimasi
- **RAM < 200 MB** (Emulator Android biasa memakan 4–8 GB RAM).
- **0% CPU saat idle** dengan pemuatan style murni tanpa dependensi compiler eksternal.
- **100% Offline Ready** (Tanpa CDN eksternal, aset SVG tertanam).
- **Dukungan Hot Reload (`r`) dan Hot Restart (`R`)** secara instan.
- **Ukuran Layar Lega**: Pilihan preset iPhone 15 Pro, Pixel 8 Pro, iPad Mini, iPad Air.

## Struktur Folder
```text
Mobile_Screen/
├── Buka_Controller.bat        <-- Shortcut utama sekali klik untuk menjalankan
├── README.md                  <-- Dokumentasi proyek
└── core/                      <-- Mesin inti aplikasi
    ├── app_server.py          <-- Server backend & GUI Controller
    ├── chrome_mobile_launcher.exe <-- Launcher interceptor ukuran layar Chrome
    ├── ChromeMobileLauncher.cs    <-- Source code C# launcher
    └── mobile_config.txt      <-- Konfigurasi koordinat jendela
```

## Cara Menjalankan
1. Klik ganda pada `Buka_Controller.bat`.
2. Klik tombol **Pilih** atau ketik path folder proyek Flutter Anda.
3. Klik **Jalankan** untuk memulai Flutter.
4. Gunakan tombol **Reload (r)**, **Reset (R)**, dan **Matikan** sesuai kebutuhan.
5. Klik preset ukuran layar untuk mengubah ukuran jendela pengujian secara langsung.
