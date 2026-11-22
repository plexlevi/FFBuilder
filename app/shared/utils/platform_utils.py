"""Cross-platform helpers for FFBuilder."""

import platform
from typing import Literal, TypedDict


PlatformType = Literal["windows", "macos", "linux"]


class PlatformInfo(TypedDict):
    system: PlatformType
    folder: str


def get_platform_info() -> PlatformInfo:
    system = platform.system().lower()
    if system == "darwin":
        return {"system": "macos", "folder": "macos"}
    if system == "windows":
        return {"system": "windows", "folder": "windows"}
    return {"system": "linux", "folder": "linux"}


def is_windows() -> bool:
    return platform.system().lower() == "windows"


def is_macos() -> bool:
    return platform.system().lower() == "darwin"


def is_linux() -> bool:
    return platform.system().lower() == "linux"
