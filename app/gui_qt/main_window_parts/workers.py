"""Background worker classes used by the main window."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

_log = logging.getLogger(__name__)

from app.services.media.file_info_service import extract_info
from app.services.media.hardware_detector import HardwareDetector
from app.services.update.checker import fetch_latest_release, is_newer_version
from app.services.update.installer import download_and_install_release


class _LoudnessWorkerSignals(QObject):
    finished = Signal(str, dict)
    progress = Signal(str, float)


class _MetadataWorkerSignals(QObject):
    finished = Signal(str, dict)


class _MetadataWorker(QRunnable):
    def __init__(self, file_path: str, ffprobe_bin: str, ffmpeg_bin: str) -> None:
        super().__init__()
        self._file_path = file_path
        self._ffprobe_bin = ffprobe_bin
        self._ffmpeg_bin = ffmpeg_bin
        self.signals = _MetadataWorkerSignals()

    def run(self) -> None:
        try:
            info = extract_info(self._file_path, self._ffprobe_bin, ffmpeg=self._ffmpeg_bin, include_loudness=False)
        except Exception as exc:
            info = {
                "path": self._file_path,
                "filename": Path(self._file_path).name,
                "error": str(exc),
            }
        self.signals.finished.emit(self._file_path, info)


class _HardwareStatusWorkerSignals(QObject):
    finished = Signal(str)


class _HardwareStatusWorker(QRunnable):
    def __init__(self, ffmpeg_bin: str | None) -> None:
        super().__init__()
        self._ffmpeg_bin = ffmpeg_bin
        self.signals = _HardwareStatusWorkerSignals()

    def run(self) -> None:
        try:
            profile = HardwareDetector(ffmpeg_path=self._ffmpeg_bin).detect(probe_encoders=False)
            gpu_names = ", ".join(gpu.name for gpu in profile.gpus) or "Unknown GPU"
            rec = profile.recommended
            if rec.hwaccel:
                text = f"{gpu_names} -> {rec.label}"
            else:
                text = f"{gpu_names} -> CPU encoding"
            self.signals.finished.emit(text)
        except Exception:
            self.signals.finished.emit("Hardware detection unavailable")


class _LoudnessWorker(QRunnable):
    def __init__(self, file_path: str, base_info: dict, ffmpeg_bin: str, ffprobe_bin: str) -> None:
        super().__init__()
        self._file_path = file_path
        self._base_info = dict(base_info)
        self._ffmpeg_bin = ffmpeg_bin
        self._ffprobe_bin = ffprobe_bin
        self.signals = _LoudnessWorkerSignals()

    def run(self) -> None:
        from app.gui_qt.dialogs.audio_analysis_dialog import (
            _AudioAnalysisWorker, _RESULT_CACHE, _PENDING_PATHS, _cache_key, build_file_info_patch,
        )
        inner = _AudioAnalysisWorker(self._file_path, self._ffmpeg_bin, self._ffprobe_bin)
        # Progress forwarding to the main-window progress bar.
        inner.signals.progress.connect(
            lambda pct: self.signals.progress.emit(self._file_path, pct / 100.0)
        )
        try:
            result = inner._analyze()
        except Exception:
            _PENDING_PATHS.discard(self._file_path)
            self.signals.finished.emit(self._file_path, dict(self._base_info))
            return
        _RESULT_CACHE[_cache_key(self._file_path)] = result
        _PENDING_PATHS.discard(self._file_path)
        enriched = dict(self._base_info)
        enriched.update(build_file_info_patch(result))
        self.signals.finished.emit(self._file_path, enriched)


class _UpdateCheckWorkerSignals(QObject):
    finished = Signal(dict)


class _UpdateCheckWorker(QRunnable):
    def __init__(self, repo: str, current_version: str) -> None:
        super().__init__()
        self.setAutoDelete(False)  # Prevent Qt from deleting the C++ object before Python GC
        self._repo = repo
        self._current_version = current_version
        self.signals = _UpdateCheckWorkerSignals()

    def run(self) -> None:
        _log.debug("[UpdateCheck] Worker started – repo=%s current=%s", self._repo, self._current_version)
        try:
            payload = fetch_latest_release(self._repo, timeout_sec=10.0)
            _log.debug("[UpdateCheck] fetch_latest_release returned: ok=%s error=%s latest=%s",
                       payload.get("ok"), payload.get("error"), payload.get("latest_version"))
            if not payload.get("ok"):
                self.signals.finished.emit(payload)
                return

            latest_version = str(payload.get("latest_version", ""))
            payload["current_version"] = self._current_version
            payload["update_available"] = is_newer_version(self._current_version, latest_version)
            _log.debug("[UpdateCheck] update_available=%s (current=%s latest=%s)",
                       payload["update_available"], self._current_version, latest_version)
            self.signals.finished.emit(payload)
        except Exception as exc:
            _log.exception("[UpdateCheck] Unhandled exception in worker – signal will still fire")
            self.signals.finished.emit({"ok": False, "error": f"Unhandled exception: {exc}"})


class _UpdateInstallWorkerSignals(QObject):
    finished = Signal(dict)


class _UpdateInstallWorker(QRunnable):
    def __init__(self, dmg_url: str, dmg_name: str) -> None:
        super().__init__()
        self.setAutoDelete(False)  # Prevent Qt from deleting the C++ object before Python GC
        self._dmg_url = dmg_url
        self._dmg_name = dmg_name
        self.signals = _UpdateInstallWorkerSignals()

    def run(self) -> None:
        result = download_and_install_release(self._dmg_url, self._dmg_name)
        self.signals.finished.emit(result)
