#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Download and install updates from a DMG on macOS."""

from __future__ import annotations

import plistlib
import shlex
import ssl
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


def _stream_to_file(req: urllib.request.Request, destination: Path, timeout_sec: float) -> None:
    """Stream response to disk in chunks; avoids loading the entire file into RAM."""
    def _write_chunks(resp, out):
        while chunk := resp.read(65536):
            out.write(chunk)

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            with destination.open("wb") as out:
                _write_chunks(resp, out)
    except urllib.error.URLError as exc:
        reason = exc.reason
        cert_error = isinstance(reason, ssl.SSLCertVerificationError)
        if not cert_error and isinstance(reason, ssl.SSLError):
            cert_error = "CERTIFICATE_VERIFY_FAILED" in str(reason)
        if not cert_error:
            raise

        # Fallback for Python environments where system CA chain is not configured.
        insecure_ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=timeout_sec, context=insecure_ctx) as resp:
            with destination.open("wb") as out:
                _write_chunks(resp, out)


def _download_to_path(url: str, destination: Path) -> None:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "FFBuilder-Updater",
        },
    )
    _stream_to_file(req, destination, timeout_sec=120)


def download_release_dmg(download_url: str, file_name: str = "") -> Path:
    downloads_dir = Path.home() / "Downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    if file_name.strip():
        safe_name = Path(file_name.strip()).name
    else:
        parsed = urlparse(download_url)
        safe_name = Path(parsed.path).name or "FFBuilder-update.dmg"
    if not safe_name.lower().endswith(".dmg"):
        safe_name += ".dmg"

    destination = downloads_dir / safe_name
    _download_to_path(download_url, destination)
    return destination


def _attach_dmg(dmg_path: Path) -> list[str]:
    proc = subprocess.run(
        ["hdiutil", "attach", str(dmg_path), "-nobrowse", "-plist"],
        capture_output=True,
        check=True,
    )
    data = plistlib.loads(proc.stdout)
    mounts: list[str] = []
    for entity in data.get("system-entities", []):
        if not isinstance(entity, dict):
            continue
        mount_point = entity.get("mount-point")
        if isinstance(mount_point, str) and mount_point:
            mounts.append(mount_point)
    return mounts


def _detach_mount(mount_point: str) -> None:
    subprocess.run(["hdiutil", "detach", mount_point, "-quiet"], capture_output=True)


def _escape_for_osascript(shell_command: str) -> str:
    return shell_command.replace("\\", "\\\\").replace('"', '\\"')


def install_app_from_dmg(dmg_path: Path) -> tuple[bool, str, str]:
    mounts: list[str] = []
    try:
        mounts = _attach_dmg(dmg_path)
        if not mounts:
            return False, "", "Nem sikerült csatolni a DMG-t."

        source_app: Path | None = None
        for mount in mounts:
            mount_path = Path(mount)
            apps = list(mount_path.glob("*.app"))
            if apps:
                source_app = apps[0]
                break

        if source_app is None:
            return False, "", "Nem található .app a DMG-ben."

        destination = Path("/Applications") / source_app.name

        # First try direct copy (works if user has write permission).
        direct = subprocess.run(
            ["ditto", str(source_app), str(destination)],
            capture_output=True,
            text=True,
        )
        if direct.returncode != 0:
            # Fallback with elevation prompt.
            cmd = f"ditto {shlex.quote(str(source_app))} {shlex.quote(str(destination))}"
            osa_cmd = _escape_for_osascript(cmd)
            elevated = subprocess.run(
                ["osascript", "-e", f'do shell script "{osa_cmd}" with administrator privileges'],
                capture_output=True,
                text=True,
            )
            if elevated.returncode != 0:
                err = elevated.stderr.strip() or elevated.stdout.strip() or "Telepítés sikertelen."
                return False, "", err

        return True, str(destination), "Sikeres frissítés"
    except Exception as exc:
        return False, "", str(exc)
    finally:
        for mount in mounts:
            _detach_mount(mount)


def download_and_install_release(download_url: str, file_name: str = "") -> dict:
    try:
        dmg_path = download_release_dmg(download_url, file_name)
    except Exception as exc:
        return {"ok": False, "error": f"Letöltési hiba: {exc}"}

    ok, app_path, message = install_app_from_dmg(dmg_path)
    if not ok:
        return {"ok": False, "error": message, "dmg_path": str(dmg_path)}

    return {
        "ok": True,
        "app_path": app_path,
        "dmg_path": str(dmg_path),
        "message": message,
    }
