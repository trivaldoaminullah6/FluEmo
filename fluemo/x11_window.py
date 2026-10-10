"""Akses jendela X11 untuk Linux tanpa dependensi pip.

Memakai libX11 lewat ctypes: mencari jendela Chrome hasil "flutter run -d chrome",
memindahkan/mengubah ukurannya, dan menutupnya. Padanan blok Win32 (user32) di
app_server.py.
"""

import ctypes
import ctypes.util
import os

MOBILE_WM_CLASS = "FlutterMobilePreview"
CONTROLLER_WM_CLASS = "FlutterController"
CONTROLLER_TITLE = "Flutter Controller"

_display_cache = None  # (lib, dpy)


class _XClassHint(ctypes.Structure):
    _fields_ = [("res_name", ctypes.c_void_p), ("res_class", ctypes.c_void_p)]


def _cstr(address):
    if not address:
        return ""
    return ctypes.string_at(address).decode("utf-8", "replace")


class _XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int),
        ("data", ctypes.c_long * 5),
    ]


class _XEvent(ctypes.Union):
    _fields_ = [
        ("type", ctypes.c_int),
        ("xclient", _XClientMessageEvent),
        ("pad", ctypes.c_long * 24),
    ]


def _load_library():
    path = ctypes.util.find_library("X11")
    if not path:
        return None
    lib = ctypes.CDLL(path)
    lib.XOpenDisplay.restype = ctypes.c_void_p
    lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    lib.XDefaultRootWindow.restype = ctypes.c_ulong
    lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    lib.XInternAtom.restype = ctypes.c_ulong
    lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.XGetWindowProperty.restype = ctypes.c_int
    lib.XGetWindowProperty.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long, ctypes.c_long,
        ctypes.c_int, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
    ]
    lib.XFree.argtypes = [ctypes.c_void_p]
    lib.XQueryTree.restype = ctypes.c_int
    lib.XQueryTree.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
        ctypes.POINTER(ctypes.c_uint),
    ]
    lib.XFetchName.restype = ctypes.c_int
    lib.XFetchName.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p)
    ]
    lib.XGetClassHint.restype = ctypes.c_int
    lib.XGetClassHint.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_XClassHint)
    ]
    lib.XMoveResizeWindow.restype = ctypes.c_int
    lib.XMoveResizeWindow.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint, ctypes.c_uint,
    ]
    lib.XSendEvent.restype = ctypes.c_int
    lib.XSendEvent.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.c_void_p
    ]
    lib.XFlush.argtypes = [ctypes.c_void_p]
    lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    return lib


def display():
    """Koneksi X11 aktif, atau None bila tidak tersedia."""
    global _display_cache
    if _display_cache is not None:
        return _display_cache
    if not os.environ.get("DISPLAY"):
        return None
    lib = _load_library()
    if not lib:
        return None
    dpy = lib.XOpenDisplay(os.environ["DISPLAY"].encode())
    if not dpy:
        return None
    _display_cache = (lib, dpy)
    return _display_cache


def _all_xids(lib, dpy):
    root = lib.XDefaultRootWindow(dpy)
    atom = lib.XInternAtom(dpy, b"_NET_CLIENT_LIST", False)
    actual_type = ctypes.c_ulong()
    actual_format = ctypes.c_int()
    nitems = ctypes.c_ulong()
    bytes_after = ctypes.c_ulong()
    data = ctypes.POINTER(ctypes.c_ubyte)()
    xids = []
    ok = lib.XGetWindowProperty(
        dpy, root, atom, 0, 4096, False, 0, ctypes.byref(actual_type),
        ctypes.byref(actual_format), ctypes.byref(nitems), ctypes.byref(bytes_after),
        ctypes.byref(data),
    )
    if ok == 0 and data:
        try:
            values = ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))
            xids = [values[i] for i in range(nitems.value)]
        finally:
            lib.XFree(data)
    if xids:
        return xids

    # Belum ada window manager (mis. dijalankan dari sesi tanpa WM): pakai anak root.
    root_return = ctypes.c_ulong()
    parent_return = ctypes.c_ulong()
    children = ctypes.POINTER(ctypes.c_ulong)()
    n_children = ctypes.c_uint()
    if lib.XQueryTree(dpy, root, ctypes.byref(root_return), ctypes.byref(parent_return),
                      ctypes.byref(children), ctypes.byref(n_children)):
        try:
            xids = [children[i] for i in range(n_children.value)]
        finally:
            lib.XFree(children)
    return xids


def window_info(xid):
    """(title, wm_class) sebuah jendela; kosong bila jendela sudah hilang."""
    conn = display()
    if not conn:
        return "", ""
    lib, dpy = conn

    title = ""
    name = ctypes.c_void_p()
    if lib.XFetchName(dpy, xid, ctypes.byref(name)) and name.value:
        title = _cstr(name.value)
        lib.XFree(name)

    if not title:
        atom = lib.XInternAtom(dpy, b"_NET_WM_NAME", False)
        actual_type = ctypes.c_ulong()
        actual_format = ctypes.c_int()
        nitems = ctypes.c_ulong()
        bytes_after = ctypes.c_ulong()
        data = ctypes.POINTER(ctypes.c_ubyte)()
        if lib.XGetWindowProperty(
            dpy, xid, atom, 0, 1024, False, 0, ctypes.byref(actual_type),
            ctypes.byref(actual_format), ctypes.byref(nitems), ctypes.byref(bytes_after),
            ctypes.byref(data),
        ) == 0 and data:
            try:
                title = ctypes.string_at(data, nitems.value).decode("utf-8", "replace")
            finally:
                lib.XFree(data)

    wm_class = ""
    hint = _XClassHint()
    if lib.XGetClassHint(dpy, xid, ctypes.byref(hint)):
        parts = [_cstr(hint.res_name), _cstr(hint.res_class)]
        wm_class = ".".join(p for p in parts if p).lower()
        for value in (hint.res_name, hint.res_class):
            if value:
                lib.XFree(value)  # XGetClassHint mengalokasikan string
    return title, wm_class


def find_controller():
    for xid in _all_xids(*display()):
        title, wm_class = window_info(xid)
        if CONTROLLER_WM_CLASS.lower() in wm_class or CONTROLLER_TITLE.lower() in title.lower():
            return xid
    return None


def find_mobile_window(controller_xid=None, exclude=None):
    """Jendela Chrome milik "flutter run -d chrome" (bukan jendela controller).

    Bila `exclude` diberikan (himpunan xid yang sudah ada sebelum peluncuran),
    pilih jendela baru yang belum ada di situ agar tidak salah menargetkan
    aplikasi lain yang juga dibuka lewat launcher ini.
    """
    conn = display()
    if not conn:
        return None
    exclude = exclude or ()
    candidates = []
    for xid in _all_xids(*conn):
        if controller_xid and xid == controller_xid:
            continue
        title, wm_class = window_info(xid)
        if CONTROLLER_WM_CLASS.lower() in wm_class or CONTROLLER_TITLE.lower() in title.lower():
            continue
        candidates.append((xid, title, wm_class))

    def pick(items):
        for xid, title, wm_class in items:
            if MOBILE_WM_CLASS.lower() in wm_class:
                return xid
        for xid, _, wm_class in items:
            if "chrom" in wm_class:
                return xid
        return None

    fresh = [c for c in candidates if c[0] not in exclude]
    if exclude:
        # Jangan pernah ambil jendela yang sudah ada sebelum peluncuran:
        # itu milik sesi "flutter run" lain (proyek lain).
        return pick(fresh)
    return pick(candidates)


def list_mobile_windows(controller_xid=None):
    """xid semua jendela Chrome yang dibuka launcher ini (untuk snapshot dasar)."""
    conn = display()
    if not conn:
        return set()
    found = set()
    for xid in _all_xids(*conn):
        if controller_xid and xid == controller_xid:
            continue
        title, wm_class = window_info(xid)
        if CONTROLLER_WM_CLASS.lower() in wm_class or CONTROLLER_TITLE.lower() in title.lower():
            continue
        if MOBILE_WM_CLASS.lower() in wm_class or "chrom" in wm_class:
            found.add(xid)
    return found


def resize(xid, w, h, x, y):
    conn = display()
    if not conn or not xid:
        return False
    lib, dpy = conn
    lib.XMoveResizeWindow(dpy, xid, int(x), int(y), int(w), int(h))
    lib.XSync(dpy, False)
    return True


def close(xid):
    """Kirim WM_DELETE_WINDOW ke jendela (padanan WM_CLOSE)."""
    conn = display()
    if not conn or not xid:
        return False
    lib, dpy = conn
    protocols = lib.XInternAtom(dpy, b"WM_PROTOCOLS", False)
    delete = lib.XInternAtom(dpy, b"WM_DELETE_WINDOW", False)
    event = _XEvent()
    event.xclient.type = 33  # ClientMessage
    event.xclient.send_event = 1
    event.xclient.window = xid
    event.xclient.message_type = protocols
    event.xclient.format = 32
    event.xclient.data[0] = delete
    event.xclient.data[1] = 0
    lib.XSendEvent(dpy, xid, False, 0, ctypes.byref(event))
    lib.XSync(dpy, False)
    return True
