#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ffmpeg_manager.py — FFmpeg kezelő modul (FFBuilder)
==================================================
Megkeresi, telepíti vagy letölti az FFmpeg/FFprobe binárisokat.

Prioritási sorrend:
  1. Már telepített (PATH vagy ~/Documents/FFBuilder)
  2. Natív csomagkezelő (Homebrew / apt / dnf / pacman / winget / choco)
  3. Bináris letöltés → ~/Documents/FFBuilder/binaries/{platform}/

Futtatható önállóan:
    python ffmpeg_manager.py

Kimenet (stdout, JSON):
    {"ffmpeg": "/path/to/ffmpeg", "ffprobe": "/path/to/ffprobe"}
    vagy
    {"ffmpeg": null, "ffprobe": null, "error": "..."}
"""

import json
import os
import platform
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Konstansok
# ---------------------------------------------------------------------------

APP_DIR = Path.home() / "Documents" / "FFBuilder"

_PLATFORM = platform.system()  # 'Darwin' | 'Linux' | 'Windows'

_PLATFORM_FOLDER = {
    "Darwin":  "macos",
    "Linux":   "linux",
    "Windows": "windows",
}.get(_PLATFORM, "linux")

BIN_DIR = APP_DIR / "binaries" / _PLATFORM_FOLDER

_EXE = ".exe" if _PLATFORM == "Windows" else ""

# Letöltési URL-ek (fallback)
_DOWNLOAD_URLS = {
    "Darwin": {
        "ffmpeg":  "https://evermeet.cx/ffmpeg/ffmpeg-7.1.zip",
        "ffprobe": "https://evermeet.cx/ffmpeg/ffprobe-7.1.zip",
    },
    "Linux": {
        # Statikus build – amd64
        "ffmpeg":  "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
        "ffprobe": None,  # A tar.xz mindkét binárist tartalmazza
    },
    "Windows": {
        # gyan.dev essentials build
        "ffmpeg":  "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "ffprobe": None,  # Szintén együtt van a zip-ben
    },
}

_BINARY_CACHE: tuple[str | None, str | None] | None = None


# ---------------------------------------------------------------------------
# Keresés
# ---------------------------------------------------------------------------

def clear_binary_cache() -> None:
    """Invalidate cached ffmpeg/ffprobe discovery result."""
    global _BINARY_CACHE
    _BINARY_CACHE = None


def find_binaries(refresh: bool = False) -> tuple[str | None, str | None]:
    """
    Visszaadja az (ffmpeg_path, ffprobe_path) párt, vagy (None, None)-t.
    Keresési sorrend: BIN_DIR → system PATH
    """
    global _BINARY_CACHE

    if not refresh and _BINARY_CACHE is not None:
        return _BINARY_CACHE

    ffmpeg  = _find_binary("ffmpeg")
    ffprobe = _find_binary("ffprobe")
    _BINARY_CACHE = (ffmpeg, ffprobe)
    return _BINARY_CACHE


def _find_binary(name: str) -> str | None:
    # 1. Saját BIN_DIR
    candidate = BIN_DIR / (name + _EXE)
    if candidate.is_file():
        return str(candidate)

    # 2. System PATH
    found = shutil.which(name)
    if found:
        return found

    # 3. macOS GUI app launchnál a Homebrew PATH gyakran hiányzik.
    for known in _known_binary_locations(name):
        if os.path.isfile(known):
            return known

    # 4. Végső fallback: brew --prefix/bin/<name>
    if _PLATFORM == "Darwin":
        brew = _find_brew()
        if brew:
            try:
                prefix = subprocess.check_output([brew, "--prefix"], text=True).strip()
                brew_bin = os.path.join(prefix, "bin", name)
                if os.path.isfile(brew_bin):
                    return brew_bin
            except Exception:
                pass

    return None


def _known_binary_locations(name: str) -> list[str]:
    if _PLATFORM == "Darwin":
        return [
            f"/opt/homebrew/bin/{name}",
            f"/usr/local/bin/{name}",
            f"/opt/homebrew/opt/ffmpeg/bin/{name}",
            f"/usr/local/opt/ffmpeg/bin/{name}",
        ]
    return []


# ---------------------------------------------------------------------------
# Natív csomagkezelő
# ---------------------------------------------------------------------------

def _pkg_manager_install() -> bool:
    """
    Megpróbálja telepíteni az ffmpeg-et a natív csomagkezelőn keresztül.
    Visszaad True-t ha sikerült, False-t ha nem.
    """
    if _PLATFORM == "Darwin":
        return _install_macos()
    elif _PLATFORM == "Linux":
        return _install_linux()
    elif _PLATFORM == "Windows":
        return _install_windows()
    return False


def _pkg_manager_install_with_callbacks(log, ask, open_terminal_brew=None) -> bool:
    """
    GUI/egyéb felhasználói felülethez használható csomagkezelős telepítés.
    """
    if _PLATFORM == "Darwin":
        return _install_macos(log=log, ask=ask, open_terminal_brew=open_terminal_brew)
    elif _PLATFORM == "Linux":
        return _install_linux(log=log)
    elif _PLATFORM == "Windows":
        return _install_windows(log=log)
    return False


def _run_live(cmd: list, env=None, line_callback=None) -> int:
    """Futtat egy parancsot és valós időben streameli a kimenetet."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        for line in proc.stdout:
            text = line.rstrip()
            if line_callback:
                line_callback(text)
            else:
                print("  " + text, flush=True)
        proc.wait()
        return proc.returncode
    except FileNotFoundError:
        if line_callback:
            line_callback(f"Command not found: {cmd[0] if cmd else 'unknown'}")
        return -1
    except Exception as e:
        if line_callback:
            line_callback(f"Error: {e}")
        else:
            print(f"  Error: {e}")
        return -1


def _install_macos(log=None, ask=None, open_terminal_brew=None) -> bool:
    log = log or (lambda msg: print(msg))
    ask = ask or _ask

    # 1. Homebrew keresés
    brew = _find_brew()

    if not brew:
        log("  Homebrew not found.")

        if open_terminal_brew:
            # GUI mód: Terminal ablakban futtatja a user
            completed = open_terminal_brew()
            if not completed:
                log("  Homebrew telepítés kihagyva.")
                return False
            log("  Homebrew ellenőrzése...")
            brew = _find_brew()
            if not brew:
                log("  ✗ A brew nem található a telepítés után. Újraindítás szükséges lehet.")
                return False
        else:
            # CLI mód: beágyazottan próbáljuk (hagyományos terminál)
            if not ask("Install Homebrew now?"):
                log("  Homebrew install skipped by user.")
                return False
            log("  Installing Homebrew...")
            log("  Running as current user (no sudo prefix from this app).")
            rc = _run_live(
                [
                    "/bin/bash",
                    "-c",
                    '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
                ],
                line_callback=lambda line: log(f"  {line}"),
            )
            if rc != 0:
                log("  ✗ Homebrew installation failed.")
                return False
            brew = _find_brew()
            if not brew:
                log("  ✗ brew command not found after installation.")
                return False

    log(f"  brew install ffmpeg  ({brew})")
    rc = _run_live([brew, "install", "ffmpeg"], line_callback=lambda line: log(f"  {line}"))
    if rc == 0:
        log("  ✓ FFmpeg installed via Homebrew.")
        return True
    log("  ✗ brew install ffmpeg failed.")
    return False


def _find_brew() -> str | None:
    for candidate in [
        shutil.which("brew"),
        "/opt/homebrew/bin/brew",
        "/usr/local/bin/brew",
    ]:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _install_linux(log=None) -> bool:
    log = log or (lambda msg: print(msg))

    managers = [
        ("apt-get", ["sudo", "apt-get", "install", "-y", "ffmpeg"]),
        ("dnf",     ["sudo", "dnf",     "install", "-y", "ffmpeg"]),
        ("pacman",  ["sudo", "pacman",  "-S", "--noconfirm", "ffmpeg"]),
        ("zypper",  ["sudo", "zypper",  "install", "-y", "ffmpeg"]),
    ]
    for name, cmd in managers:
        if shutil.which(name):
            log(f"  Package manager: {name}")
            log(f"  Running: {' '.join(cmd)}")
            log("  (sudo may ask for your password)")
            rc = _run_live(cmd, line_callback=lambda line: log(f"  {line}"))
            if rc == 0:
                log("  ✓ FFmpeg installed.")
                return True
            log(f"  ✗ Failed (exit {rc}).")
            return False
    log("  ✗ No supported Linux package manager found.")
    return False


def _install_windows(log=None) -> bool:
    log = log or (lambda msg: print(msg))

    managers = [
        ("winget", ["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--silent"]),
        ("choco",  ["choco",  "install", "ffmpeg", "-y"]),
        ("scoop",  ["scoop",  "install", "ffmpeg"]),
    ]
    for name, cmd in managers:
        if shutil.which(name):
            log(f"  Package manager: {name}")
            log(f"  Running: {' '.join(cmd)}")
            rc = _run_live(cmd, line_callback=lambda line: log(f"  {line}"))
            if rc == 0:
                log("  ✓ FFmpeg installed.")
                return True
            log(f"  ✗ Failed (exit {rc}).")
            return False
    log("  ✗ No supported Windows package manager found (winget / choco / scoop).")
    return False


# ---------------------------------------------------------------------------
# Bináris letöltés (fallback)
# ---------------------------------------------------------------------------

def _download_binaries() -> bool:
    """Letölti és kicsomagolja az FFmpeg binárisokat a BIN_DIR-be."""
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    urls = _DOWNLOAD_URLS.get(_PLATFORM, {})

    if _PLATFORM == "Darwin":
        return _download_macos(urls)
    elif _PLATFORM == "Linux":
        return _download_linux(urls)
    elif _PLATFORM == "Windows":
        return _download_windows(urls)

    print("  ✗ Binary download not supported on this platform.")
    return False


def _download_file(url: str, dest: Path, log=None) -> bool:
    log = log or (lambda msg: print(msg))
    log(f"  Downloading: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Prefer curl — more reliable for large files
        curl = shutil.which("curl")
        if curl:
            rc = subprocess.run(
                [curl, "-fsSL", "-o", str(dest), url],
                timeout=300
            ).returncode
            if rc == 0:
                log(f"  Download complete: {dest.name}")
                return True

        # Fallback: urllib
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=120) as resp:
            with open(dest, "wb") as f:
                while chunk := resp.read(65536):
                    f.write(chunk)
        log(f"  Download complete: {dest.name}")
        return True
    except Exception as e:
        log(f"  ✗ Download error: {e}")
        return False


def _download_macos(urls: dict, log=None) -> bool:
    log = log or (lambda msg: print(msg))
    tmp = Path(tempfile.gettempdir())

    for name in ("ffmpeg", "ffprobe"):
        url = urls.get(name)
        if not url:
            continue
        zip_path = tmp / f"{name}.zip"
        if not _download_file(url, zip_path, log=log):
            return False
        log(f"  Extracting: {name}")
        with zipfile.ZipFile(zip_path, "r") as zf:
            # A zip tartalmaz egy egyszerű binárist, a nevét keressük meg
            members = [m for m in zf.namelist() if not m.endswith("/")]
            for member in members:
                extracted = BIN_DIR / name
                with zf.open(member) as src, open(extracted, "wb") as dst:
                    dst.write(src.read())
                extracted.chmod(0o755)
                break
        zip_path.unlink(missing_ok=True)

    return (BIN_DIR / "ffmpeg").is_file() and (BIN_DIR / "ffprobe").is_file()


def _download_linux(urls: dict) -> bool:
    url = urls.get("ffmpeg")
    if not url:
        return False
    tmp = Path(tempfile.gettempdir())
    archive = tmp / "ffmpeg-static.tar.xz"
    if not _download_file(url, archive):
        return False

    print("  Extracting (tar.xz)...")
    extract_dir = tmp / "ffmpeg_extract"
    extract_dir.mkdir(exist_ok=True)
    rc = subprocess.run(
        ["tar", "-xf", str(archive), "-C", str(extract_dir), "--strip-components=1"],
        timeout=120
    ).returncode
    if rc != 0:
        print("  ✗ Extraction failed.")
        return False

    for name in ("ffmpeg", "ffprobe"):
        src = extract_dir / name
        if src.is_file():
            dst = BIN_DIR / name
            shutil.copy2(src, dst)
            dst.chmod(0o755)

    archive.unlink(missing_ok=True)
    shutil.rmtree(extract_dir, ignore_errors=True)
    return (BIN_DIR / "ffmpeg").is_file() and (BIN_DIR / "ffprobe").is_file()


def _download_windows(urls: dict) -> bool:
    url = urls.get("ffmpeg")
    if not url:
        return False
    tmp = Path(tempfile.gettempdir())
    zip_path = tmp / "ffmpeg-win.zip"
    if not _download_file(url, zip_path):
        return False

    print("  Extracting (zip)...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in ("ffmpeg.exe", "ffprobe.exe"):
            matches = [m for m in zf.namelist() if m.endswith(f"bin/{name}")]
            if matches:
                with zf.open(matches[0]) as src, open(BIN_DIR / name, "wb") as dst:
                    dst.write(src.read())

    zip_path.unlink(missing_ok=True)
    return (BIN_DIR / "ffmpeg.exe").is_file() and (BIN_DIR / "ffprobe.exe").is_file()


# ---------------------------------------------------------------------------
# Segédfüggvények
# ---------------------------------------------------------------------------

def _ask(prompt: str) -> bool:
    """y/n question in terminal. Returns True for yes."""
    try:
        ans = input(prompt).strip().lower()
        return ans in ("y", "yes", "1")
    except (EOFError, KeyboardInterrupt):
        return False


def _print_result(ffmpeg: str | None, ffprobe: str | None):
    if ffmpeg:
        print(f"  ffmpeg  → {ffmpeg}")
    if ffprobe:
        print(f"  ffprobe → {ffprobe}")


# ---------------------------------------------------------------------------
# Fő logika
# ---------------------------------------------------------------------------

def ensure_ffmpeg() -> dict:
    """
    Biztosítja, hogy az FFmpeg elérhető legyen.
    Visszaad egy dict-et: {"ffmpeg": path, "ffprobe": path}
    """
    # 1. Már megvan?
    ffmpeg, ffprobe = find_binaries()
    if ffmpeg and ffprobe:
        print("✓ FFmpeg already available.")
        _print_result(ffmpeg, ffprobe)
        return {"ffmpeg": ffmpeg, "ffprobe": ffprobe}

    print("FFmpeg not found.")
    print(f"Install directory: {BIN_DIR}\n")

    # 2. Package manager
    print("--- Step 1: Native package manager ---")
    if _ask("Try to install via package manager? [y/n]: "):
        if _pkg_manager_install():
            clear_binary_cache()
            ffmpeg, ffprobe = find_binaries(refresh=True)
            if ffmpeg and ffprobe:
                _print_result(ffmpeg, ffprobe)
                return {"ffmpeg": ffmpeg, "ffprobe": ffprobe}
        print("  Package manager install failed.\n")
    else:
        print("  Skipped.\n")

    # 3. Binary download
    print("--- Step 2: Binary download ---")
    print(f"Destination: {BIN_DIR}")
    if _ask("Download binaries? [y/n]: "):
        if _download_binaries():
            clear_binary_cache()
            ffmpeg, ffprobe = find_binaries(refresh=True)
            if ffmpeg and ffprobe:
                print("✓ FFmpeg downloaded and ready.")
                _print_result(ffmpeg, ffprobe)
                return {"ffmpeg": ffmpeg, "ffprobe": ffprobe}
        print("  ✗ Download failed.\n")
    else:
        print("  Skipped.\n")

    # Failed
    msg = "FFmpeg could not be installed. Install manually: https://ffmpeg.org/download.html"
    print(f"✗ {msg}")
    return {"ffmpeg": None, "ffprobe": None, "error": msg}


def ensure_ffmpeg_with_callbacks(log, ask, open_terminal_brew=None) -> dict:
    """
    UI-barát FFmpeg telepítés.

    Paraméterek:
        log: callable(str) -> None
        ask: callable(str) -> bool  (igen/nem kérdés)
        open_terminal_brew: callable() -> bool  (GUI terminál megnyitás Homebrew-hoz)
    """
    ffmpeg, ffprobe = find_binaries()
    if ffmpeg and ffprobe:
        log("✓ FFmpeg already available.")
        log(f"  ffmpeg  -> {ffmpeg}")
        log(f"  ffprobe -> {ffprobe}")
        return {"ffmpeg": ffmpeg, "ffprobe": ffprobe}

    log("FFmpeg not found.")
    log(f"Install directory: {BIN_DIR}")
    log("")

    log("--- Step 1: Native package manager ---")
    log("Automatikus próbálkozás rendszer csomagkezelővel...")
    if _pkg_manager_install_with_callbacks(log=log, ask=ask, open_terminal_brew=open_terminal_brew):
        clear_binary_cache()
        ffmpeg, ffprobe = find_binaries(refresh=True)
        if ffmpeg and ffprobe:
            log(f"  ffmpeg  -> {ffmpeg}")
            log(f"  ffprobe -> {ffprobe}")
            return {"ffmpeg": ffmpeg, "ffprobe": ffprobe}
    log("  Package manager install failed.")
    log("")

    log("--- Step 2: Binary download ---")
    log(f"Destination: {BIN_DIR}")
    if ask("Letöltjük az FFmpeg binárisokat?"):
        if _download_binaries_with_log(log):
            clear_binary_cache()
            ffmpeg, ffprobe = find_binaries(refresh=True)
            if ffmpeg and ffprobe:
                log("✓ FFmpeg downloaded and ready.")
                log(f"  ffmpeg  -> {ffmpeg}")
                log(f"  ffprobe -> {ffprobe}")
                return {"ffmpeg": ffmpeg, "ffprobe": ffprobe}
        log("  ✗ Download failed.")
        log("")
    else:
        log("  Skipped.")
        log("")

    msg = "FFmpeg could not be installed. Install manually: https://ffmpeg.org/download.html"
    log(f"✗ {msg}")
    return {"ffmpeg": None, "ffprobe": None, "error": msg}


def _download_binaries_with_log(log) -> bool:
    """Letölti a binárisokat log callbackkel."""
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    urls = _DOWNLOAD_URLS.get(_PLATFORM, {})

    if _PLATFORM == "Darwin":
        return _download_macos(urls, log=log)
    elif _PLATFORM == "Linux":
        return _download_linux_with_log(urls, log=log)
    elif _PLATFORM == "Windows":
        return _download_windows_with_log(urls, log=log)

    log("  ✗ Binary download not supported on this platform.")
    return False


def _download_linux_with_log(urls: dict, log) -> bool:
    url = urls.get("ffmpeg")
    if not url:
        return False
    tmp = Path(tempfile.gettempdir())
    archive = tmp / "ffmpeg-static.tar.xz"
    if not _download_file(url, archive, log=log):
        return False

    log("  Extracting (tar.xz)...")
    extract_dir = tmp / "ffmpeg_extract"
    extract_dir.mkdir(exist_ok=True)
    rc = subprocess.run(
        ["tar", "-xf", str(archive), "-C", str(extract_dir), "--strip-components=1"],
        timeout=120
    ).returncode
    if rc != 0:
        log("  ✗ Extraction failed.")
        return False

    for name in ("ffmpeg", "ffprobe"):
        src = extract_dir / name
        if src.is_file():
            dst = BIN_DIR / name
            shutil.copy2(src, dst)
            dst.chmod(0o755)

    archive.unlink(missing_ok=True)
    shutil.rmtree(extract_dir, ignore_errors=True)
    return (BIN_DIR / "ffmpeg").is_file() and (BIN_DIR / "ffprobe").is_file()


def _download_windows_with_log(urls: dict, log) -> bool:
    url = urls.get("ffmpeg")
    if not url:
        return False
    tmp = Path(tempfile.gettempdir())
    zip_path = tmp / "ffmpeg-win.zip"
    if not _download_file(url, zip_path, log=log):
        return False

    log("  Extracting (zip)...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in ("ffmpeg.exe", "ffprobe.exe"):
            matches = [m for m in zf.namelist() if m.endswith(f"bin/{name}")]
            if matches:
                with zf.open(matches[0]) as src, open(BIN_DIR / name, "wb") as dst:
                    dst.write(src.read())

    zip_path.unlink(missing_ok=True)
    return (BIN_DIR / "ffmpeg.exe").is_file() and (BIN_DIR / "ffprobe.exe").is_file()


# ---------------------------------------------------------------------------
# Belépési pont
# ---------------------------------------------------------------------------

def main():
    print("=" * 50)
    print("FFmpeg Manager — FFBuilder")
    print(f"Platform : {_PLATFORM} ({_PLATFORM_FOLDER})")
    print(f"BIN_DIR  : {BIN_DIR}")
    print("=" * 50 + "\n")

    result = ensure_ffmpeg()

    print("\n" + "=" * 50)
    print("OUTPUT (JSON):")
    print("=" * 50)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 50)


if __name__ == "__main__":
    main()
