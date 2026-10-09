"""Halaman controller fluemo: satu blok HTML+CSS+JS tanpa aset eksternal."""

HTML_PAGE = """<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <title>Flutter Controller</title>
  <script>window.__INITIAL_STATE__ = __STATE_JSON__;</script>
  <style>
    :root {
      --bg: #020617;
      --surface: #0f172a;
      --surface-2: #1e293b;
      --line: #1e293b;
      --line-strong: #64748b;
      --text: #f1f5f9;
      --text-dim: #94a3b8;
      --text-disabled: #7d8ca3;
      --accent: #38bdf8;
      --accent-soft: #0c2136;
      --ok: #047857;
      --ok-hover: #065f46;
      --danger: #b91c1c;
      --danger-hover: #991b1b;
      --danger-soft: #450a0a;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      height: 100%;
      overflow: hidden !important;
      user-select: none;
      background-color: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", Arial, sans-serif;
      font-size: 12px;
    }
    .app-container {
      height: 100%;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 8px;
      gap: 6px;
      overflow-y: auto;
    }
    /* Card Styles */
    .card {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 8px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .card-title {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-dim);
    }
    /* Header */
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--line);
    }
    .header-title { font-size: 13px; font-weight: 700; color: var(--text); }
    .header-sub { font-size: 11px; color: var(--text-dim); }
    /* Status Badge */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
      border: 1px solid var(--line-strong);
      color: var(--text-dim);
      background: var(--surface);
    }
    .badge-starting { background: #451a03; border-color: #d97706; color: #fbbf24; }
    .badge-running { background: #022c22; border-color: #059669; color: #34d399; }
    .badge-reload { background: #431407; border-color: #ea580c; color: #fdba74; }
    .badge-restart { background: #082f49; border-color: #0284c7; color: var(--accent); }
    .badge-offline { background: var(--danger-soft); border-color: #dc2626; color: #fca5a5; }
    .dot { width: 7px; height: 7px; border-radius: 50%; flex: none; }
    .dot-idle { background: var(--text-dim); }
    .dot-starting { background: #f59e0b; }
    .dot-running { background: #10b981; }
    .dot-reload { background: #f97316; }
    .dot-restart { background: var(--accent); }
    .dot-offline { background: #f87171; }

    /* Inputs */
    .input-row { display: flex; gap: 6px; align-items: center; }
    .text-input {
      flex: 1;
      min-height: 44px;
      background: var(--bg);
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 12px;
      color: var(--text);
      font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .text-input:focus { border-color: var(--accent); }
    .text-input::placeholder { color: var(--text-dim); }
    .btn-browse {
      background: var(--surface-2);
      border: 1px solid var(--line-strong);
      color: var(--text);
      padding: 8px 12px;
      min-height: 44px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: background 0.15s;
    }
    .btn-browse:hover { background: #334155; }

    /* Button Grid */
    .btn-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
    .action-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 8px 10px;
      min-height: 44px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      border: 1px solid transparent;
      transition: background 0.15s ease, border-color 0.15s ease;
    }
    /* Warna mengikuti arti aksi, bukan dekorasi: Jalankan = ok, Matikan = bahaya,
       Reload/Reset = netral karena keduanya hanya mengulang proses yang sama. */
    .btn-start-active { background: var(--ok); color: #fff; }
    .btn-start-active:hover { background: var(--ok-hover); }
    .btn-stop-active { background: var(--danger); color: #fff; }
    .btn-stop-active:hover { background: var(--danger-hover); }
    .btn-neutral-active { background: var(--surface-2); border-color: var(--line-strong); color: var(--text); }
    .btn-neutral-active:hover { background: #334155; }
    .btn-disabled {
      background: var(--bg) !important;
      border-color: var(--line) !important;
      color: var(--text-disabled) !important;
      cursor: not-allowed !important;
    }
    .btn-quit {
      background: #7f1d1d;
      border: 1px solid #b91c1c;
      color: #fecaca;
      border-radius: 10px;
      padding: 4px 10px;
      font-size: 10px;
      font-weight: 800;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .btn-quit:hover { background: #991b1b; }
    .btn-quit:active { transform: scale(0.97); }

    /* Preset Grid */
    .preset-header { display: flex; justify-content: space-between; align-items: center; }
    .preset-btn {
      display: flex;
      flex-direction: column;
      justify-content: flex-start;
      gap: 2px;
      width: 100%;
      min-height: 56px;
      background: var(--bg);
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      padding: 8px 10px;
      text-align: left;
      font: inherit;
      color: inherit;
      cursor: pointer;
      transition: background 0.15s, border-color 0.15s;
    }
    .preset-btn:hover { border-color: var(--accent); }
    .preset-btn-selected { border-color: var(--accent) !important; background: var(--accent-soft) !important; }
    .preset-name { font-weight: 700; color: var(--text); display: flex; align-items: center; gap: 5px; font-size: 12px; }
    .preset-dim { font-size: 11px; color: var(--text-dim); margin-top: 2px; }

    /* Log Box */
    .card-log { flex: 1; min-height: 170px; }
    .log-box {
      flex: 1;
      background: var(--bg);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
      font-size: 11px;
      color: var(--text-dim);
      overflow-y: auto;
      line-height: 1.45;
      min-height: 72px;
      user-select: text;
    }
    .log-box::-webkit-scrollbar { width: 4px; }
    .log-box::-webkit-scrollbar-thumb { background: var(--line-strong); border-radius: 2px; }
    .log-line { white-space: pre-wrap; word-break: break-word; }

    /* Footer */
    .footer {
      display: flex;
      justify-content: center;
      align-items: center;
      padding-top: 2px;
      font-size: 11px;
      color: var(--text-dim);
    }

    .link-btn {
      display: inline-flex;
      align-items: center;
      min-height: 44px;
      background: none;
      border: 0;
      padding: 0 6px;
      font: inherit;
      font-size: 11px;
      color: var(--text-dim);
      cursor: pointer;
      text-decoration: underline;
      text-underline-offset: 3px;
    }
    .link-btn:hover:not(:disabled) { color: var(--text); }
    .link-btn:disabled { color: var(--text-disabled); cursor: not-allowed; text-decoration: none; }
    .field-hint { font-size: 11px; color: var(--text-dim); }
    .field-hint.is-error { color: #fca5a5; }
    .log-empty { font-size: 11px; color: var(--text-dim); }
    .log-empty[hidden] { display: none; }
    .visually-hidden {
      position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
      overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
    }

    svg { vertical-align: middle; fill: currentColor; }
    .icon-slot { width: 16px; height: 16px; display: inline-flex; align-items: center; justify-content: center; flex: none; }

    :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

    @media (prefers-reduced-motion: reduce) {
      * { transition: none !important; animation: none !important; }
    }
  </style>
</head>
<body>
  <div class="app-container">

    <!-- 1. Header -->
    <div class="header">
      <div>
        <h1 class="header-title">Flutter Controller</h1>
        <p class="header-sub">Pratinjau Flutter di layar ponsel</p>
      </div>
      <div style="display:flex; align-items:center; gap:6px;">
        <div id="statusBadge" class="badge" role="status" aria-live="polite">
          <span id="statusDot" class="dot dot-idle" aria-hidden="true"></span>
          <span id="statusText">Menunggu</span>
        </div>
        <button type="button" id="btnQuit" onclick="quitApp()" class="btn-quit" title="Matikan server dan tutup semua jendela">
          <span class="icon-slot" aria-hidden="true"><svg width="11" height="11" viewBox="0 0 24 24"><path d="M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42C17.99 7.86 19 9.81 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.19 1.01-4.14 2.58-5.42L6.17 5.17C4.23 6.82 3 9.26 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z"/></svg></span>
          <span>Keluar</span>
        </button>
      </div>
    </div>

    <!-- 2. Proyek Picker -->
    <div class="card">
      <h2 class="card-title">Folder proyek</h2>
      <div class="input-row">
        <label class="visually-hidden" for="projectPathInput">Folder proyek Flutter</label>
        <input type="text" id="projectPathInput" onchange="onManualPathInput(this.value)"
          class="text-input" placeholder="Belum ada folder dipilih" spellcheck="false">
        <button type="button" onclick="browseProject()" class="btn-browse">
          <span class="icon-slot" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg></span>
          <span>Pilih</span>
        </button>
      </div>
      <p id="projectHint" class="field-hint">Pilih folder yang berisi pubspec.yaml.</p>
    </div>

    <!-- 3. Kontrol Aksi -->
    <div class="card">
      <h2 class="card-title">Kontrol</h2>
      <div class="btn-grid">
        <button type="button" id="btnStart" onclick="startFlutter()" class="action-btn btn-start-active">
          <span class="icon-slot" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></span>
          <span>Jalankan</span>
        </button>
        <button type="button" id="btnStop" onclick="stopFlutter()" class="action-btn btn-disabled" disabled>
          <span class="icon-slot" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg></span>
          <span>Matikan</span>
        </button>
        <button type="button" id="btnReload" onclick="triggerReload()" class="action-btn btn-disabled" disabled>
          <span class="icon-slot" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg></span>
          <span>Muat ulang</span>
        </button>
        <button type="button" id="btnReset" onclick="triggerRestart()" class="action-btn btn-disabled" disabled>
          <span class="icon-slot" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24"><path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg></span>
          <span>Mulai ulang</span>
        </button>
      </div>
    </div>

    <!-- 4. Preset Ukuran Layar -->
    <div class="card">
      <div class="preset-header">
        <h2 class="card-title" id="presetGroupLabel">Ukuran layar</h2>
      </div>
      <div class="btn-grid" id="presetGrid" role="group" aria-labelledby="presetGroupLabel"></div>
    </div>

    <!-- 5. Output Log -->
    <div class="card card-log">
      <div class="preset-header">
        <h2 class="card-title">Output log</h2>
        <button type="button" id="btnClearLogs" onclick="clearLogs()" class="link-btn" disabled>Bersihkan</button>
      </div>
      <div id="logBox" class="log-box" role="log" aria-live="polite" aria-relevant="additions" tabindex="0"></div>
      <p id="logEmpty" class="log-empty">Belum ada output. Tekan Jalankan untuk memulai build.</p>
    </div>

    <!-- 6. Footer -->
    <div class="footer">
      <span>fluemo v__VERSION__</span>
    </div>

  </div>

  <script>
    const STATUS = {
      idle:     { label: "Menunggu",    badge: "badge",                dot: "dot dot-idle" },
      starting: { label: "Membangun",   badge: "badge badge-starting", dot: "dot dot-starting" },
      running:  { label: "Berjalan",    badge: "badge badge-running",  dot: "dot dot-running" },
      reload:   { label: "Muat ulang",  badge: "badge badge-reload",   dot: "dot dot-reload" },
      restart:  { label: "Mulai ulang", badge: "badge badge-restart",  dot: "dot dot-restart" },
      offline:  { label: "Server mati", badge: "badge badge-offline",  dot: "dot dot-offline" },
    };
    const ENABLED = {
      idle:     { start: true,  stop: false, reload: false, reset: false },
      starting: { start: false, stop: true,  reload: true,  reset: true },
      running:  { start: false, stop: true,  reload: true,  reset: true },
      reload:   { start: false, stop: true,  reload: false, reset: true },
      restart:  { start: false, stop: true,  reload: true,  reset: false },
      offline:  { start: false, stop: false, reload: false, reset: false },
    };
    const BUTTONS = {
      start:  { on: "action-btn btn-start-active",  off: "action-btn btn-disabled" },
      stop:   { on: "action-btn btn-stop-active",   off: "action-btn btn-disabled" },
      reload: { on: "action-btn btn-neutral-active", off: "action-btn btn-disabled" },
      reset:  { on: "action-btn btn-neutral-active", off: "action-btn btn-disabled" },
    };

    let pollTimer = null;

    function el(id) { return document.getElementById(id); }

    const PRESET_ICONS = {
      mobile: '<svg width="14" height="14" viewBox="0 0 24 24"><path d="M17 1.01L7 1c-1.1 0-2 .9-2 2v18c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V3c0-1.1-.9-1.99-2-1.99zM17 19H7V5h10v14z"/></svg>',
      tablet: '<svg width="14" height="14" viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-1 14H6V6h12v11z"/></svg>'
    };
    let renderedPresets = null;

    function renderPresets(presets) {
      const signature = JSON.stringify(presets);
      if (signature === renderedPresets) return;
      renderedPresets = signature;
      const grid = el("presetGrid");
      grid.innerHTML = Object.keys(presets).map(id => {
        const p = presets[id];
        return `<button type="button" aria-pressed="false" id="p-${id}" class="preset-btn">
          <span class="preset-name"><span class="icon-slot" aria-hidden="true">${p.w >= 700 ? PRESET_ICONS.tablet : PRESET_ICONS.mobile}</span><span>${p.name}</span></span>
          <span class="preset-dim">${p.w} x ${p.h} px</span>
        </button>`;
      }).join("");
      grid.querySelectorAll(".preset-btn").forEach(node => {
        node.addEventListener("click", () => setPreset(node.id.slice(2)));
      });
    }

    function applyPreset(presetId) {
      document.querySelectorAll("#presetGrid .preset-btn").forEach(node => {
        const on = node.id === "p-" + presetId;
        node.classList.toggle("preset-btn-selected", on);
        node.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }

    function applyStatus(status) {
      const s = STATUS[status] || STATUS.idle;
      const e = ENABLED[status] || ENABLED.idle;
      el("statusBadge").className = s.badge;
      el("statusDot").className = s.dot;
      el("statusText").textContent = s.label;
      for (const key of Object.keys(BUTTONS)) {
        const node = el("btn" + key[0].toUpperCase() + key.slice(1));
        node.disabled = !e[key];
        node.className = e[key] ? BUTTONS[key].on : BUTTONS[key].off;
      }
    }

    function setHint(text, isError) {
      const hint = el("projectHint");
      hint.textContent = text;
      hint.classList.toggle("is-error", Boolean(isError));
    }

    let renderedLogs = [];

    function logLine(text) {
      const div = document.createElement("div");
      div.className = "log-line";
      div.textContent = text;
      return div;
    }

    function renderLogs(logs) {
      const box = el("logBox");
      el("logEmpty").hidden = logs.length > 0;
      el("btnClearLogs").disabled = logs.length === 0;

      if (logs.length === renderedLogs.length && logs.every((l, i) => l === renderedLogs[i])) return;
      const shouldScroll = box.scrollHeight - box.scrollTop <= box.clientHeight + 30;
      const isAppend = logs.length > renderedLogs.length && renderedLogs.every((l, i) => l === logs[i]);
      if (isAppend) {
        // Tempel hanya baris baru: DOM lama tetap utuh, jadi seleksi teks tidak hilang saat polling.
        logs.slice(renderedLogs.length).forEach(l => box.appendChild(logLine(l)));
      } else {
        box.replaceChildren(...logs.map(logLine));
      }
      renderedLogs = logs.slice();
      if (shouldScroll) box.scrollTop = box.scrollHeight;
    }

    function applyState(data) {
      renderPresets(data.presets || {});
      const input = el("projectPathInput");
      if (document.activeElement !== input) {
        input.value = data.project_path || "";
        input.title = data.project_path || "";
      }
      if (data.project_error) {
        setHint(data.project_error, true);
      } else if (!data.project_path) {
        setHint("Pilih folder yang berisi pubspec.yaml.", false);
      } else {
        setHint("pubspec.yaml ditemukan. Proyek siap dijalankan.", false);
      }

      applyStatus(data.status);
      applyPreset(data.active_preset);
      renderLogs(data.logs || []);
    }

    function setOffline() {
      applyStatus("offline");
      setHint("Controller tidak menjawab. Tutup jendela ini lalu jalankan ulang fluemo.", true);
      el("logEmpty").hidden = el("logBox").childElementCount > 0;
    }

    async function fetchState() {
      let delay = 1000;
      try {
        const res = await fetch("/api/state", { cache: "no-store" });
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();
        applyState(data);
        delay = (data.status === "starting" || data.status === "reload" || data.status === "restart") ? 600 : 900;
      } catch (e) {
        setOffline();
        delay = 1500;
      }
      clearTimeout(pollTimer);
      pollTimer = setTimeout(fetchState, delay);
    }

    async function post(path, body) {
      try {
        await fetch(path, { method: "POST", body });
      } catch (e) {
        setOffline();
      }
      clearTimeout(pollTimer);
      pollTimer = setTimeout(fetchState, 150);
    }

    function browseProject() { post("/api/browse"); }

    function onManualPathInput(path) {
      if (path && path.trim()) post("/api/set_path?path=" + encodeURIComponent(path.trim()));
    }

    function startFlutter() {
      const p = el("projectPathInput").value;
      if (!p || p.trim() === "") {
        setHint("Pilih folder proyek Flutter dulu sebelum menjalankan.", true);
        el("projectPathInput").focus();
        return;
      }
      post("/api/start");
    }

    function stopFlutter() { post("/api/stop"); }
    function triggerReload() { post("/api/reload"); }
    function triggerRestart() { post("/api/restart"); }
    function setPreset(pid) { post("/api/resize?preset=" + encodeURIComponent(pid)); }
    function clearLogs() { post("/api/clear_logs"); }

    async function quitApp() {
      if (!confirm("Matikan server, hentikan flutter run, dan tutup semua jendela?")) return;
      try {
        await fetch("/api/quit", { method: "POST" });
      } catch (e) {}
      window.close();
    }

    if (window.__INITIAL_STATE__) applyState(window.__INITIAL_STATE__);
    fetchState();
  </script>
</body>
</html>
"""
