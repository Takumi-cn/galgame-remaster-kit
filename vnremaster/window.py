"""Read-only Windows window enumeration and client-area capture.

This is the capture side of a display experiment: find a visible window,
verify its client size, and grab the client pixels currently on screen. It is
deliberately read-only; it does not inject, hook, or modify another process.
BitBlt reads the screen, so an occluded window is captured as occluded; pass
``bring_to_front=True`` (or move it manually) before capturing.

The module imports cleanly on non-Windows systems; calling an OS function
raises :class:`WindowError` there.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

__all__ = [
    "WindowError",
    "WindowInfo",
    "capture_client",
    "client_origin",
    "find_window",
    "list_windows",
    "save_capture",
]


class WindowError(RuntimeError):
    """A window could not be found or captured."""


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    class_name: str
    title: str
    width: int
    height: int
    visible: bool

    @property
    def area(self) -> int:
        return self.width * self.height

    def matches(
        self,
        *,
        pid: int | None = None,
        class_name: str | None = None,
        title_contains: str | None = None,
        min_size: tuple[int, int] = (1, 1),
        visible_only: bool = True,
    ) -> bool:
        if visible_only and not self.visible:
            return False
        if pid is not None and self.pid != pid:
            return False
        if class_name is not None and self.class_name != class_name:
            return False
        if title_contains is not None and title_contains not in self.title:
            return False
        return self.width >= min_size[0] and self.height >= min_size[1]


def _win():
    if os.name != "nt":
        raise WindowError("window enumeration/capture is only available on Windows")
    import ctypes
    import ctypes.wintypes as wt

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        user32.SetProcessDPIAware()
    return ctypes, wt, user32, gdi32


def list_windows(
    *,
    visible_only: bool = True,
    min_size: tuple[int, int] = (1, 1),
) -> list[WindowInfo]:
    """Enumerate top-level windows and return their client geometry."""
    ctypes, wt, user32, _gdi32 = _win()
    results: list[WindowInfo] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def callback(hwnd, _lparam):
        if visible_only and not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buffer, 256)
        rect = wt.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width < min_size[0] or height < min_size[1]:
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        results.append(
            WindowInfo(
                hwnd=int(hwnd),
                pid=int(pid.value),
                class_name=class_buffer.value,
                title=title.value,
                width=width,
                height=height,
                visible=bool(user32.IsWindowVisible(hwnd)),
            )
        )
        return True

    user32.EnumWindows(callback, 0)
    return results


def find_window(
    *,
    pid: int | None = None,
    class_name: str | None = None,
    title_contains: str | None = None,
    min_size: tuple[int, int] = (1, 1),
    visible_only: bool = True,
) -> WindowInfo | None:
    """Return the largest matching window, or ``None``."""
    candidates = [
        window
        for window in list_windows(visible_only=visible_only, min_size=min_size)
        if window.matches(
            pid=pid,
            class_name=class_name,
            title_contains=title_contains,
            min_size=min_size,
            visible_only=visible_only,
        )
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda window: window.area)


def client_origin(hwnd: int) -> tuple[int, int]:
    """Return the screen coordinates of a window's client-area origin."""
    ctypes, wt, user32, _gdi32 = _win()
    point = wt.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        raise WindowError(f"ClientToScreen failed for hwnd {hwnd}")
    return int(point.x), int(point.y)


def capture_client(hwnd: int, *, bring_to_front: bool = False) -> Image.Image:
    """Capture the client area of *hwnd* and return an RGB image."""
    ctypes, wt, user32, gdi32 = _win()
    if not user32.IsWindow(hwnd):
        raise WindowError(f"window does not exist: {hwnd}")

    rect = wt.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise WindowError(f"GetClientRect failed for hwnd {hwnd}")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise WindowError(f"window has an empty client area: {width}x{height}")

    if bring_to_front:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)

    origin_x, origin_y = client_origin(hwnd)
    screen_dc = user32.GetDC(0)
    if not screen_dc:
        raise WindowError("GetDC(0) failed")
    memory_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    if not memory_dc or not bitmap:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory_dc:
            gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(0, screen_dc)
        raise WindowError("failed to create a compatible device context")
    old_bitmap = gdi32.SelectObject(memory_dc, bitmap)

    class BitmapInfoHeader(ctypes.Structure):
        _fields_ = [
            ("biSize", wt.DWORD),
            ("biWidth", wt.LONG),
            ("biHeight", wt.LONG),
            ("biPlanes", wt.WORD),
            ("biBitCount", wt.WORD),
            ("biCompression", wt.DWORD),
            ("biSizeImage", wt.DWORD),
            ("biXPelsPerMeter", wt.LONG),
            ("biYPelsPerMeter", wt.LONG),
            ("biClrUsed", wt.DWORD),
            ("biClrImportant", wt.DWORD),
        ]

    try:
        if not gdi32.BitBlt(
            memory_dc, 0, 0, width, height, screen_dc, origin_x, origin_y, 0x00CC0020
        ):
            raise WindowError("BitBlt failed")
        header = BitmapInfoHeader()
        header.biSize = ctypes.sizeof(BitmapInfoHeader)
        header.biWidth = width
        header.biHeight = -height  # top-down
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0
        buffer = ctypes.create_string_buffer(width * height * 4)
        copied = gdi32.GetDIBits(
            memory_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0
        )
        if copied == 0:
            raise WindowError("GetDIBits failed")
        return Image.frombuffer(
            "RGBA", (width, height), buffer, "raw", "BGRA", 0, 1
        ).convert("RGB")
    finally:
        gdi32.SelectObject(memory_dc, old_bitmap)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(0, screen_dc)


def save_capture(hwnd: int, path: str | Path, *, bring_to_front: bool = False) -> Path:
    image = capture_client(hwnd, bring_to_front=bring_to_front)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return target
