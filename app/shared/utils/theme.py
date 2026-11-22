#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Theme manager local to FFBuilder."""

import subprocess
from typing import Optional

from .platform_utils import is_linux, is_macos, is_windows


LIGHT = {
    "bg": "#f0f0f0",
    "bg_widget": "#ffffff",
    "bg_canvas": "#e8e8e8",
    "bg_timeline": "#d0d0d0",
    "bg_input": "#ffffff",
    "fg": "#1a1a1a",
    "fg_secondary": "#555555",
    "fg_disabled": "#999999",
    "fg_title": "#2c3e50",
    "status_ok": "#2e7d32",
    "status_error": "#c62828",
    "status_warning": "#e65100",
    "status_info": "#1565c0",
    "border": "#cccccc",
    "hover": "#d8d8d8",
    "press": "#c0c0c0",
    "button_face": "#f5f5f5",
    "button_fg": "#1a1a1a",
    "highlight": "#fffde7",
    "video_bg": "#000000",
    "drag_preview_bg": "#e0e0e0",
}

DarkPalette = dict[str, str]

DARK: DarkPalette = {
    "bg": "#2b2b2b",
    "bg_widget": "#3c3c3c",
    "bg_canvas": "#3c3c3c",
    "bg_timeline": "#4a4a4a",
    "bg_input": "#3c3c3c",
    "fg": "#e0e0e0",
    "fg_secondary": "#aaaaaa",
    "fg_disabled": "#666666",
    "fg_title": "#c8d8e8",
    "status_ok": "#66bb6a",
    "status_error": "#ef5350",
    "status_warning": "#ffa726",
    "status_info": "#42a5f5",
    "border": "#555555",
    "hover": "#4a4a4a",
    "press": "#5a5a5a",
    "button_face": "#3c3c3c",
    "button_fg": "#e0e0e0",
    "highlight": "#3c3a00",
    "video_bg": "#000000",
    "drag_preview_bg": "#4a4a4a",
}


_cached_dark_mode: Optional[bool] = None


def is_dark_mode() -> bool:
    global _cached_dark_mode
    if _cached_dark_mode is not None:
        return _cached_dark_mode

    if is_macos():
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            _cached_dark_mode = result.stdout.strip().lower() == "dark"
            return _cached_dark_mode
        except Exception:
            pass
    elif is_windows():
        try:
            import winreg

            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(
                registry,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            _cached_dark_mode = value == 0
            return _cached_dark_mode
        except Exception:
            pass
    elif is_linux():
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            _cached_dark_mode = "dark" in result.stdout.strip().lower()
            return _cached_dark_mode
        except Exception:
            pass

    _cached_dark_mode = False
    return False


def get_colors() -> dict:
    return DARK if is_dark_mode() else LIGHT


def invalidate_cache() -> None:
    global _cached_dark_mode
    _cached_dark_mode = None


# ---------------------------------------------------------------------------
# System accent colour
# Call init_accent() in main() BEFORE app.setStyleSheet() so Qt hasn't
# desaturated the palette yet.  get_accent() returns (hex, r, g, b).
# ---------------------------------------------------------------------------
_accent_hex: str = "#007AFF"
_accent_rgb: tuple[int, int, int] = (0, 122, 255)


def init_accent(raw_colour) -> None:  # raw_colour: QColor
    """Persist the vivid system accent colour before any stylesheet is applied."""
    global _accent_hex, _accent_rgb
    h, s, v, _ = raw_colour.getHsvF()
    from PySide6.QtGui import QColor
    vivid = QColor.fromHsvF(h, 1.0, max(0.88, v))
    _accent_hex = vivid.name()
    _accent_rgb = (vivid.red(), vivid.green(), vivid.blue())


def get_accent() -> tuple[str, int, int, int]:
    """Return (hex, r, g, b) of the vivid system accent colour."""
    r, g, b = _accent_rgb
    return _accent_hex, r, g, b
