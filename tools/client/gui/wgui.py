"""wgui.py - petit module d'automatisation GUI pour WoW 1.12.1 (ctypes pur, aucune dependance).
Fonctions : find_wow(), foreground(), capture(path, hwnd), click(...), key(...), type_text(...).
Les coordonnees de click() sont relatives a la zone client de la fenetre de jeu.
Garde-fou : ne cible que la fenetre d'un WoW.exe situe sous un dossier client_test.
"""
import ctypes, ctypes.wintypes as wt, struct, zlib, time, sys, os

user32 = ctypes.WinDLL('user32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    user32.SetProcessDPIAware()

user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]


def _exe_of(pid):
    """Chemin de l'exe ; si l'acces est refuse (cas observe pour WoW.exe), repli sur le nom via Toolhelp."""
    h = kernel32.OpenProcess(0x1000, False, pid)
    if h:
        buf = ctypes.create_unicode_buffer(520)
        n = wt.DWORD(520)
        kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
        kernel32.CloseHandle(h)
        return buf.value
    return _name_of(pid)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', wt.DWORD), ('cntUsage', wt.DWORD), ('th32ProcessID', wt.DWORD),
                ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wt.DWORD), ('cntThreads', wt.DWORD),
                ('th32ParentProcessID', wt.DWORD), ('pcPriClassBase', wt.LONG), ('dwFlags', wt.DWORD),
                ('szExeFile', ctypes.c_wchar * 260)]


def _name_of(pid):
    kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    snap = kernel32.CreateToolhelp32Snapshot(2, 0)
    e = PROCESSENTRY32W()
    e.dwSize = ctypes.sizeof(e)
    r = ''
    ok = kernel32.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        if e.th32ProcessID == pid:
            r = e.szExeFile
            break
        ok = kernel32.Process32NextW(snap, ctypes.byref(e))
    kernel32.CloseHandle(snap)
    # chemin inconnu : on suppose client_test (le lanceur refuse tout autre dossier ; WOW_PATH_ASSUMED)
    return ('C:/Wowlheim/client_test/' + r) if r else ''


def find_wow():
    """Retourne (hwnd, pid) de la fenetre WoW (client_test uniquement) ou (None, None)."""
    res = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, l):
        if not user32.IsWindowVisible(h):
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        exe = _exe_of(pid.value).lower()
        if exe.endswith('wow.exe') and 'client_test' in exe:
            cn = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(h, cn, 64)
            if cn.value.startswith('GxWindowClass'):
                res.append((h, pid.value))
        return True

    user32.EnumWindows(cb, 0)
    return res[0] if res else (None, None)


def client_rect(hwnd):
    r = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, r.right - r.left, r.bottom - r.top


def foreground(hwnd):
    user32.ShowWindow(hwnd, 9)
    user32.SetWindowPos(hwnd, wt.HWND(-1), 0, 0, 0, 0, 0x0003)  # HWND_TOPMOST, NOMOVE|NOSIZE (capture non masquee)
    user32.keybd_event(0x12, 0, 0, 0)  # astuce ALT pour autoriser SetForegroundWindow
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    return user32.GetForegroundWindow() == hwnd


def _write_png(path, w, h, bgra):
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        row = bgra[y * stride:(y + 1) * stride]
        rgb = bytearray(w * 3)
        rgb[0::3] = row[2::4]
        rgb[1::3] = row[1::4]
        rgb[2::3] = row[0::4]
        raw += b'\x00' + rgb

    def chunk(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)

    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + \
        chunk(b'IDAT', zlib.compress(bytes(raw), 6)) + chunk(b'IEND', b'')
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(png)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG), ('biPlanes', wt.WORD),
                ('biBitCount', wt.WORD), ('biCompression', wt.DWORD), ('biSizeImage', wt.DWORD),
                ('biXPelsPerMeter', wt.LONG), ('biYPelsPerMeter', wt.LONG), ('biClrUsed', wt.DWORD),
                ('biClrImportant', wt.DWORD)]


for _f in (gdi32.CreateCompatibleDC, gdi32.CreateCompatibleBitmap, gdi32.SelectObject):
    _f.restype = ctypes.c_void_p
user32.GetDC.restype = ctypes.c_void_p
user32.GetWindowDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wt.DWORD]
gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.UINT, wt.UINT, ctypes.c_void_p,
                            ctypes.c_void_p, wt.UINT]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
user32.ReleaseDC.argtypes = [wt.HWND, ctypes.c_void_p]
user32.GetDC.argtypes = [wt.HWND]
user32.GetWindowDC.argtypes = [wt.HWND]
user32.PrintWindow.argtypes = [wt.HWND, ctypes.c_void_p, wt.UINT]


def _nonblack(data, step=200):
    n = len(data) // step
    return sum(1 for i in range(0, len(data) - 3, step) if data[i] or data[i + 1] or data[i + 2]) / max(n, 1)


def capture_region(path, x, y, w, h):
    """Capture d'une zone de l'ecran (BitBlt depuis le DC du bureau) -> PNG. Retourne la fraction non noire."""
    sdc = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(sdc)
    bmp = gdi32.CreateCompatibleBitmap(sdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    gdi32.BitBlt(mdc, 0, 0, w, h, sdc, x, y, 0x00CC0020 | 0x40000000)
    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(bi)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    buf = (ctypes.c_ubyte * (w * h * 4))()
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(None, sdc)
    data = bytes(buf)
    _write_png(path, w, h, data)
    return _nonblack(data)


def capture(path, hwnd=None, whole_screen=False):
    if whole_screen or hwnd is None:
        return capture_region(path, 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    x, y, w, h = client_rect(hwnd)
    return capture_region(path, x, y, w, h)


def printwindow(path, hwnd):
    """Capture via PrintWindow(PW_RENDERFULLCONTENT) - pour comparer avec BitBlt."""
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    ww, wh = r.right - r.left, r.bottom - r.top
    wdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(wdc)
    bmp = gdi32.CreateCompatibleBitmap(wdc, ww, wh)
    gdi32.SelectObject(mdc, bmp)
    ok = user32.PrintWindow(hwnd, mdc, 2)
    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(bi)
    bi.biWidth = ww
    bi.biHeight = -wh
    bi.biPlanes = 1
    bi.biBitCount = 32
    buf = (ctypes.c_ubyte * (ww * wh * 4))()
    gdi32.GetDIBits(mdc, bmp, 0, wh, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, wdc)
    data = bytes(buf)
    _write_png(path, ww, wh, data)
    return ok, _nonblack(data)


# ---- entrees (SendInput) ----
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wt.LONG), ('dy', wt.LONG), ('mouseData', wt.DWORD), ('dwFlags', wt.DWORD),
                ('time', wt.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wt.WORD), ('wScan', wt.WORD), ('dwFlags', wt.DWORD), ('time', wt.DWORD),
                ('dwExtraInfo', ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [('type', wt.DWORD), ('u', _U)]


GUARD = None  # si defini : toute entree est refusee quand cette fenetre n'est pas au premier plan


def _send(*inputs):
    if GUARD and user32.GetForegroundWindow() != GUARD:
        raise RuntimeError('fenetre WoW perdue au premier plan : entree refusee')
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


EXT = (0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x21, 0x22, 0x23, 0x24, 0x6F, 0xA5)


def _kb(vk, up=False):
    sc = user32.MapVirtualKeyW(vk, 0)
    fl = 0x0008  # KEYEVENTF_SCANCODE
    if up:
        fl |= 0x0002
    if vk in EXT:
        fl |= 0x0001
    i = INPUT()
    i.type = 1
    i.u.ki = KEYBDINPUT(0, sc, fl, 0, 0)
    return i


def mouse_move(hwnd, cx, cy):
    x0, y0, w, h = client_rect(hwnd)
    user32.SetCursorPos(x0 + cx, y0 + cy)


def click(hwnd, cx, cy, button='left', double=False):
    mouse_move(hwnd, cx, cy)
    time.sleep(0.15)
    d, u = (0x0002, 0x0004) if button == 'left' else (0x0008, 0x0010)
    for _ in range(2 if double else 1):
        i1 = INPUT(); i1.type = 0; i1.u.mi = MOUSEINPUT(0, 0, 0, d, 0, 0)
        i2 = INPUT(); i2.type = 0; i2.u.mi = MOUSEINPUT(0, 0, 0, u, 0, 0)
        _send(i1); time.sleep(0.06); _send(i2); time.sleep(0.08)


VK = {'enter': 0x0D, 'tab': 0x09, 'esc': 0x1B, 'space': 0x20, 'back': 0x08, 'up': 0x26, 'down': 0x28,
      'left': 0x25, 'right': 0x27, 'shift': 0x10, 'ctrl': 0x11, 'alt': 0x12, 'delete': 0x2E, 'end': 0x23, 'home': 0x24}
for _n in range(12):
    VK['f%d' % (_n + 1)] = 0x70 + _n


def key(name, delay=0.06):
    vk = VK[name.lower()]
    _send(_kb(vk)); time.sleep(delay); _send(_kb(vk, True)); time.sleep(delay)


def hold(name, secs):
    vk = VK.get(name.lower()) or (user32.VkKeyScanW(ord(name)) & 0xff)
    _send(_kb(vk)); time.sleep(secs); _send(_kb(vk, True))


def type_text(text, delay=0.12):
    """Frappe via scancodes selon la disposition clavier courante (gere Maj/AltGr)."""
    for ch in text:
        r = user32.VkKeyScanW(ord(ch))
        if r == -1:
            raise ValueError('caractere non saisissable : %r' % ch)
        vk, st = r & 0xff, (r >> 8) & 0xff
        mods = []
        if st & 1: mods.append(0x10)
        if (st & 6) == 6: mods.append(0xA5)      # AltGr
        elif st & 2: mods.append(0x11)
        elif st & 4: mods.append(0x12)
        for m in mods: _send(_kb(m))
        _send(_kb(vk)); time.sleep(delay); _send(_kb(vk, True))
        for m in reversed(mods): _send(_kb(m, True))
        time.sleep(delay)


def wheel(hwnd, cx, cy, clicks):
    """Molette (clicks>0 vers le haut)."""
    mouse_move(hwnd, cx, cy)
    time.sleep(0.1)
    for _ in range(abs(clicks)):
        i = INPUT(); i.type = 0
        i.u.mi = MOUSEINPUT(0, 0, (120 if clicks > 0 else -120) & 0xffffffff, 0x0800, 0, 0)
        _send(i); time.sleep(0.05)


def drag(hwnd, x1, y1, x2, y2):
    mouse_move(hwnd, x1, y1); time.sleep(0.15)
    d = INPUT(); d.type = 0; d.u.mi = MOUSEINPUT(0, 0, 0, 0x0002, 0, 0)
    u = INPUT(); u.type = 0; u.u.mi = MOUSEINPUT(0, 0, 0, 0x0004, 0, 0)
    _send(d); time.sleep(0.2)
    for k in range(1, 11):
        mouse_move(hwnd, x1 + (x2 - x1) * k // 10, y1 + (y2 - y1) * k // 10); time.sleep(0.05)
    _send(u)


def ensure_fg(hwnd, tries=8):
    """Garde-fou : ne JAMAIS envoyer d'entrees si la fenetre WoW n'est pas au premier plan."""
    for _ in range(tries):
        if user32.GetForegroundWindow() == hwnd:
            return True
        foreground(hwnd)
        time.sleep(0.2)
    return user32.GetForegroundWindow() == hwnd
