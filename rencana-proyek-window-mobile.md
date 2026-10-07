# Rencana Proyek: Window Mobile Wrapper

Aplikasi desktop (Windows) yang mendeteksi semua jendela aplikasi yang terbuka, lalu membungkus jendela pilihan dalam bingkai berukuran HP.

## 1. Tujuan dan batasan

**Tujuan:** pengguna membuka aplikasi, melihat daftar jendela yang sedang terbuka, memilih satu, dan jendela itu tampil dalam bingkai HP (mis. 390×844) yang bisa dipindah dan dikembalikan seperti semula.

**Batasan yang sudah disepakati:**
- Layout "mobile" yang sungguhan hanya terjadi pada konten web (browser, Electron, PWA), karena situsnya sendiri yang menyesuaikan lebar layar. Aplikasi native hanya diperkecil dan dibungkus.
- Target awal: Windows 10/11.

## 2. Keputusan teknis

| Hal | Pilihan | Alasan |
|---|---|---|
| Kerangka aplikasi | Electron + TypeScript | UI bingkai HP paling mudah dibuat dengan HTML/CSS |
| Akses API Windows | `koffi` (FFI ke `user32.dll` dan `dwmapi.dll`) | Tanpa kompilasi native addon |
| Mode utama (MVP) | Resize jendela asli + bingkai buatan | Tab/jendela yang sama persis, input normal |
| Mode cadangan | Capture + forward input | Untuk aplikasi yang menolak di-resize |
| Mobile mode untuk Chrome | Pakai ulang ekstensi Mobile Tab lewat WebSocket lokal | Emulasi mobile hanya bisa dilakukan dari dalam browser |

Alternatif jika ingin lebih native: C# WPF dengan P/Invoke. Interop Win32-nya lebih nyaman, tapi UI bingkai lebih sulit dibuat.

## 3. Arsitektur singkat

```
┌─────────────────────────── Aplikasi Electron ───────────────────────────┐
│  Main process                                                          │
│   ├─ window-enumerator   EnumWindows, filter jendela valid             │
│   ├─ window-controller   SetWindowPos, simpan & pulihkan posisi asli   │
│   ├─ frame-sync          bingkai bergerak → jendela target ikut        │
│   └─ chrome-bridge       WebSocket lokal ke ekstensi Chrome            │
│  Renderer                                                              │
│   ├─ Picker UI           daftar jendela + pilih perangkat              │
│   └─ Frame UI            bingkai HP (frameless, transparan)            │
└────────────────────────────────────────────────────────────────────────┘
```

## 4. Fase pengerjaan

### Fase 0: Uji kelayakan teknis (1–2 hari)
Skrip kecil tanpa UI untuk memastikan fondasinya jalan.
- Daftar jendela dengan `EnumWindows`; ambil judul, PID, nama proses, dan ikon.
- Ubah ukuran dan posisi satu jendela dengan `SetWindowPos`.
- Coba pada Notepad, Chrome, VS Code, WhatsApp Desktop, dan satu aplikasi UWP (mis. Calculator).

**Selesai bila:** hasilnya tercatat per aplikasi (bisa di-resize atau tidak, ukuran minimum, perilaku DPI). Hasil ini menentukan daftar aplikasi yang didukung di MVP.

### Fase 1: MVP (1–2 minggu)
- **Picker:** daftar jendela dengan filter (hanya yang terlihat, berjudul, bukan *cloaked*/jendela sistem, bukan jendela aplikasi ini sendiri), tombol segarkan, dan pembaruan otomatis berkala.
- **Preset perangkat:** iPhone 15, iPhone SE, Pixel 8, Galaxy S23, plus ukuran kustom dan rotasi.
- **Bingkai:** jendela Electron tanpa border, transparan, sudut membulat, notch dan home indicator, selalu di atas.
- **Pemasangan:** jendela target diubah ukurannya dan diletakkan tepat di area layar bingkai.
- **Sinkron gerak:** saat bingkai digeser, jendela target ikut; saat jendela target diminimalkan atau ditutup, bingkai ikut menutup.
- **Pemulihan:** tombol Kembalikan dan penanganan saat aplikasi ditutup paksa (posisi asli disimpan ke disk).

**Selesai bila:** untuk aplikasi yang lolos Fase 0, pilih jendela → muncul dalam bingkai → kembalikan → posisi dan ukuran asli pulih.

### Fase 2: Mobile mode untuk browser (1 minggu)
- Aplikasi membuka WebSocket lokal (`127.0.0.1`) dan ekstensi Mobile Tab tersambung ke sana.
- Saat jendela Chrome dipilih, aplikasi meminta ekstensi menerapkan emulasi mobile (viewport, touch, User-Agent) dengan ukuran yang sama dengan bingkai.
- Pemetaan jendela ke tab aktifnya dilakukan lewat judul jendela dan `chrome.tabs`.

**Selesai bila:** jendela Chrome di dalam bingkai menampilkan versi mobile situsnya dan kembali normal saat dikembalikan.

> Catatan: Chrome versi baru membatasi opsi `--remote-debugging-port` pada profil bawaan, jadi jalur lewat ekstensi lebih aman daripada meluncurkan ulang Chrome dengan flag debug. Perlu diverifikasi pada versi Chrome yang Anda pakai.

### Fase 3: Mode capture untuk aplikasi yang menolak resize (1–2 minggu)
- Tangkap jendela target secara live (`desktopCapturer` Electron atau Windows Graphics Capture) dan tampilkan di dalam bingkai.
- Teruskan klik, scroll, dan ketikan ke jendela asli dengan pemetaan koordinat (`SendInput`/`PostMessage`).
- Jendela asli disembunyikan atau dipindah ke luar layar selama mode ini.

**Selesai bila:** aplikasi yang gagal di mode resize tetap bisa dipakai lewat bingkai, dengan input yang terasa wajar.

### Fase 4: Penyempurnaan dan rilis (1 minggu)
- Ikon tray, hotkey global (pasang/kembalikan), pengaturan tersimpan.
- Dukungan multi-monitor dan DPI per-monitor.
- Paket installer dengan `electron-builder`.

## 5. Risiko dan penanganan

| Risiko | Dampak | Penanganan |
|---|---|---|
| Aplikasi punya ukuran minimum jendela | Tidak bisa sekecil 390px | Deteksi di Fase 0; tandai "tidak didukung" atau arahkan ke mode capture |
| Jendela UWP/`ApplicationFrameHost` | Judul dan posisi tidak sesuai | Filter dengan `DWMWA_CLOAKED`; uji kasus per kasus |
| Jendela berhak admin (elevated) | Aplikasi biasa tidak bisa mengubahnya (UIPI) | Beri pesan jelas; opsi menjalankan aplikasi sebagai admin |
| DPI/multi-monitor | Posisi dan ukuran meleset | Jadikan aplikasi *per-monitor DPI aware*; uji di dua skala |
| Konten terproteksi (DRM, beberapa game) | Layar hitam saat capture | Kenali sebagai batasan; hanya mode resize yang berlaku |
| Aplikasi ditutup paksa saat jendela masih dimodifikasi | Jendela target tertinggal berukuran kecil | Simpan posisi asli ke disk dan pulihkan saat start berikutnya |
| Akses luas ke jendela pengguna | Risiko keamanan jika disalahgunakan | Semua lokal, tanpa jaringan keluar; WebSocket hanya `127.0.0.1` dengan token |

## 6. Struktur proyek yang diusulkan

```
window-mobile-wrapper/
├── package.json
├── src/
│   ├── main/
│   │   ├── index.ts              # titik masuk Electron
│   │   ├── win32.ts              # binding koffi (user32, dwmapi)
│   │   ├── window-enumerator.ts
│   │   ├── window-controller.ts
│   │   ├── frame-sync.ts
│   │   ├── chrome-bridge.ts      # WebSocket ke ekstensi
│   │   └── state-store.ts        # posisi asli, pengaturan
│   ├── renderer/
│   │   ├── picker/               # UI daftar jendela
│   │   └── frame/                # UI bingkai HP
│   └── shared/devices.ts         # preset perangkat
├── extension/                    # ekstensi Mobile Tab (dipakai ulang)
└── README.md
```

## 7. Keputusan yang perlu dari Anda

1. Apakah laptop Anda Windows 10/11? (Seluruh rencana ini mengasumsikan ya.)
2. Aplikasi apa saja yang paling ingin Anda bungkus? Daftar ini menentukan prioritas pengujian di Fase 0.
3. Setuju memakai Electron + TypeScript, atau lebih suka C#?

## 8. Langkah berikutnya

Mulai dari Fase 0: buat skrip uji yang mendaftar jendela dan mengubah ukurannya, lalu jalankan di laptop Anda dan kirim hasilnya. Dari hasil itu kita tahu aplikasi mana yang bisa didukung penuh sebelum membangun UI.
