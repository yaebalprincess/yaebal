"""Windows sizing frame; caption controls are painted by the visible Qt bar."""
import os


def apply_frame(window, dark):
    if os.name != "nt" or window.windowHandle() is None or not window.isVisible():
        return
    import ctypes
    from ctypes import wintypes
    hwnd = int(window.winId())
    user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
    class Margins(ctypes.Structure):
        _fields_ = [(name, ctypes.c_int) for name in ("left", "right", "top", "bottom")]
    # A native caption painted behind the opaque Qt shell can disappear.
    # Keep the sizing frame/shadow; the client bar owns all three controls.
    dwm.DwmExtendFrameIntoClientArea(wintypes.HWND(hwnd), ctypes.byref(Margins(0, 0, 0, 0)))
    value = ctypes.c_int(bool(dark))
    dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 20, ctypes.byref(value), ctypes.sizeof(value))
    # COLORREF is BBGGRR. On older Windows these attributes are ignored safely.
    bg, fg = (0x251C1C, 0xFAF3F0) if dark else (0xFFFFFF, 0x493124)
    for attr, color in ((35, bg), (36, fg)):
        value = wintypes.DWORD(color)
        dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), attr, ctypes.byref(value), ctypes.sizeof(value))
    user32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0, 0x37)


def native_event(window, message):
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    msg = wintypes.MSG.from_address(int(message))
    user32 = ctypes.windll.user32
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.ScreenToClient.argtypes = [wintypes.HWND,ctypes.POINTER(wintypes.POINT)]
    if msg.message == 0x0083 and msg.wParam:  # WM_NCCALCSIZE
        rect = wintypes.RECT.from_address(msg.lParam)
        if user32.IsZoomed(msg.hWnd):
            # Retain the sizing border inset when maximized; never cover taskbar.
            dpi = int(window.devicePixelRatioF() * 96)
            metric = getattr(user32, "GetSystemMetricsForDpi", None)
            x = metric(32, dpi) + metric(92, dpi) if metric else user32.GetSystemMetrics(32) + user32.GetSystemMetrics(92)
            y = metric(33, dpi) + metric(92, dpi) if metric else user32.GetSystemMetrics(33) + user32.GetSystemMetrics(92)
            rect.left += x; rect.right -= x; rect.top += y; rect.bottom -= y
        return True, 0
    if msg.message == 0x0084:  # WM_NCHITTEST
        x, y = ctypes.c_short(msg.lParam & 0xffff).value, ctypes.c_short((msg.lParam >> 16) & 0xffff).value
        point = wintypes.POINT(x,y)
        user32.ScreenToClient(msg.hWnd,ctypes.byref(point))
        scale = window.devicePixelRatioF()
        px, py, width, height = point.x/scale, point.y/scale, window.width(), window.height()
        title = getattr(window, "titlebar", None)
        if title is not None and 0 <= py < title.height():
            from PyQt5.QtCore import QPoint
            child = window.childAt(QPoint(int(px),int(py)))
            # Controls remain clickable right up to the window's top/right edge.
            if child is not None and child is not title and child is not title.title:
                return True, 1  # HTCLIENT
        if not window.isMaximized() and not window.isFullScreen():
            edge = 6
            left, right, top, bottom = px < edge, px >= width-edge, py < edge, py >= height-edge
            hit = 13 if left and top else 14 if right and top else 16 if left and bottom else 17 if right and bottom else 10 if left else 11 if right else 12 if top else 15 if bottom else None
            if hit is not None:return True, hit
        if title is not None and 0 <= py < title.height():
            if child is title or child is title.title:return True, 2  # HTCAPTION
            return True, 1
    return None
