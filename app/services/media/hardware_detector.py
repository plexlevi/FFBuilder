#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Local hardware detection for FFBuilder."""

import json
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional


def _run_fast(cmd: list[str], timeout: float = 2.0) -> str:
    """Run a quick command and return stdout or empty string on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


@dataclass
class GpuInfo:
    vendor: str
    name: str


@dataclass
class HwaccelOption:
    label: str
    hwaccel: str
    encoder_h264: str
    encoder_hevc: str
    encoder_av1: Optional[str]
    priority: int
    available: bool = False


@dataclass
class HardwareProfile:
    os: str
    gpus: List[GpuInfo]
    recommended: HwaccelOption
    all_options: List[HwaccelOption]
    ffmpeg_path: Optional[str]


def _detect_gpus_windows() -> List[GpuInfo]:
    gpus: List[GpuInfo] = []

    # Fast path on most Windows machines.
    wmic_out = _run_fast(["wmic", "path", "win32_VideoController", "get", "Name", "/value"], timeout=2.5)
    if wmic_out:
        for line in wmic_out.splitlines():
            if not line.lower().startswith("name="):
                continue
            name = line.split("=", 1)[-1].strip()
            if name:
                gpus.append(GpuInfo(vendor=_classify_vendor(name), name=name))

    if gpus:
        return gpus

    # Fallback where wmic is unavailable.
    ps_out = _run_fast(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name",
        ],
        timeout=4.0,
    )
    if ps_out:
        for line in ps_out.splitlines():
            name = line.strip()
            if name:
                gpus.append(GpuInfo(vendor=_classify_vendor(name), name=name))

    return gpus


def _detect_gpus_macos() -> List[GpuInfo]:
    gpus: List[GpuInfo] = []

    # Apple Silicon fast path: integrated GPU tracks SoC model and sysctl is very fast.
    if platform.machine().lower() in ("arm64", "aarch64"):
        cpu_brand = _run_fast(["sysctl", "-n", "machdep.cpu.brand_string"], timeout=1.5)
        if cpu_brand:
            gpus.append(GpuInfo(vendor="apple", name=cpu_brand))
            return gpus

    # Intel/discrete fallback: still lighter than full-detail profiler calls.
    out = _run_fast(["system_profiler", "SPDisplaysDataType", "-json", "-detailLevel", "mini"], timeout=4.0)
    if out:
        try:
            data = json.loads(out)
            for entry in data.get("SPDisplaysDataType", []):
                name = entry.get("sppci_model") or entry.get("_name") or ""
                if name:
                    gpus.append(GpuInfo(vendor=_classify_vendor(name), name=name))
        except Exception:
            pass

    if gpus:
        return gpus

    # Last resort: SoC/chip name from hardware profile.
    hw_out = _run_fast(["system_profiler", "SPHardwareDataType", "-json", "-detailLevel", "mini"], timeout=3.5)
    if hw_out:
        try:
            hw_data = json.loads(hw_out)
            hw_items = hw_data.get("SPHardwareDataType", [])
            if hw_items and hw_items[0].get("chip_type"):
                chip = str(hw_items[0]["chip_type"]).strip()
                if chip:
                    gpus.append(GpuInfo(vendor="apple", name=chip))
        except Exception:
            pass

    return gpus


def _detect_gpus_linux() -> List[GpuInfo]:
    gpus: List[GpuInfo] = []
    lspci_cmd = shutil.which("lspci")
    if lspci_cmd:
        try:
            result = subprocess.run([lspci_cmd, "-nn"], capture_output=True, text=True, timeout=10)
            for line in result.stdout.splitlines():
                lower = line.lower()
                if any(keyword in lower for keyword in ("vga compatible", "3d controller", "display controller")):
                    match = re.search(r"\[([^\]]+)\]", line)
                    name = match.group(1) if match else line.split(":", 1)[-1].strip()
                    gpus.append(GpuInfo(vendor=_classify_vendor(name), name=name))
        except Exception:
            pass
    return gpus


def _classify_vendor(name: str) -> str:
    lower = name.lower()
    if any(keyword in lower for keyword in ("nvidia", "geforce", "quadro", "rtx", "gtx", "tesla")):
        return "nvidia"
    if any(keyword in lower for keyword in ("amd", "radeon", "rx ", "vega", "rdna", "navi")):
        return "amd"
    if any(keyword in lower for keyword in ("intel", "iris", "uhd", "hd graphics", "arc ")):
        return "intel"
    if any(keyword in lower for keyword in ("apple", " m1", " m2", " m3", " m4", "apple m")):
        return "apple"
    return "unknown"


def _build_candidate_options(os_name: str, gpus: List[GpuInfo]) -> List[HwaccelOption]:
    vendors = {gpu.vendor for gpu in gpus}
    options: List[HwaccelOption] = []

    if "nvidia" in vendors or os_name in ("windows", "linux"):
        options.append(HwaccelOption("NVIDIA NVENC (CUDA)", "cuda", "h264_nvenc", "hevc_nvenc", "av1_nvenc", 10))
    if os_name == "macos":
        options.append(HwaccelOption("Apple VideoToolbox", "videotoolbox", "h264_videotoolbox", "hevc_videotoolbox", None, 11))
    if "intel" in vendors or os_name in ("windows", "linux"):
        options.append(HwaccelOption("Intel QuickSync (QSV)", "qsv", "h264_qsv", "hevc_qsv", "av1_qsv", 20))
    if os_name == "windows" and ("amd" in vendors or not vendors):
        options.append(HwaccelOption("AMD AMF (D3D11VA)", "d3d11va", "h264_amf", "hevc_amf", "av1_amf", 15))
    if os_name == "linux" and ("amd" in vendors or not vendors):
        options.append(HwaccelOption("AMD/Intel VAAPI", "vaapi", "h264_vaapi", "hevc_vaapi", None, 16))

    options.append(HwaccelOption("Szoftveres kódolás (CPU)", "", "libx264", "libx265", "libsvtav1", 100))
    return sorted(options, key=lambda option: option.priority)


def _get_available_encoders(ffmpeg_path: str) -> set[str]:
    try:
        result = subprocess.run([ffmpeg_path, "-encoders", "-v", "quiet"], capture_output=True, text=True, timeout=8)
        encoders = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and re.match(r"^[V.][A.][S.][X.][B.][D.]$", parts[0]):
                encoders.add(parts[1])
        return encoders
    except Exception:
        return set()


def _mark_available_options(
    options: List[HwaccelOption],
    available_encoders: set[str],
    probe_encoders: bool,
) -> None:
    for option in options:
        if option.hwaccel == "":
            option.available = True
        elif not probe_encoders:
            # Fast startup mode: rely on platform/vendor heuristics.
            option.available = True
        else:
            option.available = option.encoder_h264 in available_encoders


class HardwareDetector:
    def __init__(self, ffmpeg_path: Optional[str] = None):
        self._ffmpeg_path = ffmpeg_path

    def detect(self, probe_encoders: bool = False) -> HardwareProfile:
        os_name = self._get_os()
        gpus = self._detect_gpus(os_name)
        ffmpeg = self._find_ffmpeg()
        available_encoders = _get_available_encoders(ffmpeg) if (probe_encoders and ffmpeg) else set()
        candidates = _build_candidate_options(os_name, gpus)
        _mark_available_options(candidates, available_encoders, probe_encoders=probe_encoders)
        available = [option for option in candidates if option.available]
        recommended = available[0] if available else candidates[-1]
        return HardwareProfile(os=os_name, gpus=gpus, recommended=recommended, all_options=candidates, ffmpeg_path=ffmpeg)

    def _get_os(self) -> str:
        system_name = platform.system().lower()
        if system_name == "darwin":
            return "macos"
        if system_name == "windows":
            return "windows"
        return "linux"

    def _detect_gpus(self, os_name: str) -> List[GpuInfo]:
        if os_name == "windows":
            return _detect_gpus_windows()
        if os_name == "macos":
            return _detect_gpus_macos()
        return _detect_gpus_linux()

    def _find_ffmpeg(self) -> Optional[str]:
        if self._ffmpeg_path:
            return self._ffmpeg_path
        found = shutil.which("ffmpeg")
        if found:
            return found
        folder_map = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}
        system_name = platform.system()
        folder = folder_map.get(system_name, "linux")
        extension = ".exe" if system_name == "Windows" else ""
        from pathlib import Path

        candidate = Path.home() / "Documents" / "FFBuilder" / "binaries" / folder / f"ffmpeg{extension}"
        if candidate.exists():
            return str(candidate)
        return None
