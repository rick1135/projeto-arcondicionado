"""Posicionamento e acabamento Windows, com fallback para outros desktops.

Atributos oficiais DWM:
https://learn.microsoft.com/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute
"""

import ctypes
from ctypes import wintypes
import sys


def work_area(root=None):
    if sys.platform == "win32":
        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right, rect.bottom
    return (0, 0, root.winfo_screenwidth(), root.winfo_screenheight()-48) if root else (0, 0, 1920, 1032)


def apply_window_style(root):
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
        user32.GetAncestor.restype = wintypes.HWND
        hwnd = user32.GetAncestor(root.winfo_id(), 2)
        set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
        set_attribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
        set_attribute.restype = ctypes.c_long
        for attribute, value in ((20, 1), (33, 2), (34, 0x00333333)):
            setting = ctypes.c_int(value)
            set_attribute(hwnd, attribute, ctypes.byref(setting), ctypes.sizeof(setting))
        # Janelas override-redirect podem não receber o arredondamento DWM.
        # Recorta a moldura sem bordas com uma região GDI como fallback suave.
        if root.overrideredirect():
            gdi32 = ctypes.windll.gdi32
            gdi32.CreateRoundRectRgn.argtypes = (ctypes.c_int,)*6
            gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
            user32.SetWindowRgn.argtypes = (wintypes.HWND, wintypes.HRGN, wintypes.BOOL)
            region = gdi32.CreateRoundRectRgn(0, 0, root.winfo_width()+1, root.winfo_height()+1, 18, 18)
            if not user32.SetWindowRgn(hwnd, region, True):
                gdi32.DeleteObject.argtypes = (wintypes.HANDLE,)
                gdi32.DeleteObject(region)
    except (AttributeError, OSError):
        # Windows anterior ao 11 continua usando o fundo escuro e a borda Canvas.
        pass
