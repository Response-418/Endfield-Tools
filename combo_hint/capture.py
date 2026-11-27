"""Minimal game-window capture helpers (no extra dependencies beyond Pillow)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

u = ctypes.windll.user32


def client_rect(hwnd: int) -> tuple[int, int, int, int]:
    """Return the game window's CLIENT rect in screen coordinates.

    The combo bars sit in the client area, so the title bar must be excluded.
    """
    r = wintypes.RECT()
    u.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(r))
    pt = wintypes.POINT(0, 0)
    u.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(pt))
    return (pt.x, pt.y, pt.x + r.right, pt.y + r.bottom)


def is_foreground(hwnd: int) -> bool:
    """GDI capture only sees whatever is on screen -- require the game in front."""
    try:
        return int(u.GetForegroundWindow()) == int(hwnd)
    except Exception:
        return False
