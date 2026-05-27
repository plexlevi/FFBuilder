"""Cross-platform subprocess helpers for FFBuilder."""

import platform
import subprocess


def get_subprocess_startup_info():
    startupinfo = None
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo


def run_hidden_subprocess(command, **kwargs):
    startupinfo = get_subprocess_startup_info()
    if startupinfo:
        kwargs["startupinfo"] = startupinfo
    if kwargs.get("text") and "encoding" not in kwargs:
        kwargs["encoding"] = "utf-8"
        kwargs.setdefault("errors", "replace")
    return subprocess.run(command, **kwargs)


def popen_hidden_subprocess(command, **kwargs):
    startupinfo = get_subprocess_startup_info()
    if startupinfo:
        kwargs["startupinfo"] = startupinfo
    if (kwargs.get("text") or kwargs.get("universal_newlines")) and "encoding" not in kwargs:
        kwargs["encoding"] = "utf-8"
        kwargs.setdefault("errors", "replace")
        if kwargs.get("universal_newlines"):
            kwargs["text"] = True
            kwargs.pop("universal_newlines", None)
    return subprocess.Popen(command, **kwargs)
