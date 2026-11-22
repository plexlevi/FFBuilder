"""Cross-platform sound playback helpers for FFBuilder."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .platform_utils import is_linux, is_macos, is_windows
from .subprocess_utils import popen_hidden_subprocess


def play_sound(sound_path: str) -> Optional[object]:
    """Play a sound file asynchronously if the platform supports it."""
    path = Path(sound_path)
    if not path.exists():
        return None

    try:
        if is_windows():
            import winsound

            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            return True
        if is_macos():
            return popen_hidden_subprocess(["afplay", str(path)])
        if is_linux():
            try:
                return popen_hidden_subprocess(["aplay", str(path)])
            except FileNotFoundError:
                try:
                    return popen_hidden_subprocess(["paplay", str(path)])
                except FileNotFoundError:
                    return None
        return None
    except Exception:
        return None
