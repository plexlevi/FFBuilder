#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Qt main window for FFBuilder."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer, QThreadPool
from app.gui_qt.ui.ui_main_window import Ui_MainWindow
from app.shared.i18n import trs, tr
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTreeWidget,
)

from app.domain import cmd_macros
from app.services.ffmpeg.manager import find_binaries
from app.gui_qt.main_window_mixins import (
    FileMetadataMixin,
    QueueFlowMixin,
    RunFlowMixin,
    ShellMixin,
    TemplateCategoryMixin,
    UiWiringMixin,
)
from app.gui_qt.main_window_parts import (
    _ConversionQueueItem,
    _EtaEstimator,
    _HardwareStatusWorker,
    _LoudnessWorker,
    _MetadataWorker,
    clear_status_display,
    resolve_notification_sound_path,
    set_status_display,
)
from app.shared import settings as settings_manager
from app.shared.version import app_window_title
from app.shared.utils.sound_utils import play_sound
from app.templates.template_repository import TemplateManager

_ROOT_DIR = Path(__file__).resolve().parents[2]

def _quote_if_needed(value: str) -> str:
    return cmd_macros.quote_if_needed(value)


class MainWindow(
    UiWiringMixin,
    FileMetadataMixin,
    QueueFlowMixin,
    RunFlowMixin,
    ShellMixin,
    TemplateCategoryMixin,
    QMainWindow,
):
    """Qt main window for FFBuilder."""

    def __init__(self, effective_version: str | None = None) -> None:
        super().__init__()
        self._ui = Ui_MainWindow()
        self._ui.setupUi(self)
        self.setWindowTitle(app_window_title())
        # Make the status bar content widget fill the full width dynamically
        self._ui.statusbar.addPermanentWidget(self._ui.statusBarContentWidget, 1)

        self._effective_version: str = effective_version or APP_VERSION

        self.files: list[dict] = []
        self.current_file_info: dict = {}
        self._template_manager = TemplateManager()
        self._current_template_idx: int | None = None
        self._process: QProcess | None = None
        self._ffmpeg_bin, self._ffprobe_bin = find_binaries()
        self._layout_save_timer = QTimer()
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.timeout.connect(self._save_layout_settings)
        self._status_clear_timer = QTimer()
        self._status_clear_timer.setSingleShot(True)
        self._status_clear_timer.timeout.connect(self._on_status_clear_timer)
        self._applying_template_move = False
        self._user_stopped = False
        self._run_duration_seconds = 0.0
        self._stderr_buffer = ""
        self._eta_estimator = _EtaEstimator()
        self._thread_pool = QThreadPool.globalInstance()
        self._hardware_status_worker: _HardwareStatusWorker | None = None
        self._queue_items: list[_ConversionQueueItem] = []
        self._queue_active_item: _ConversionQueueItem | None = None
        self._queue_next_id = 1
        self._queue_tree_widget: QTreeWidget | None = None
        self._queue_status_label: QLabel | None = None
        self._queue_start_button: QPushButton | None = None
        self._queue_stop_button: QPushButton | None = None
        self._queue_clear_button: QPushButton | None = None
        self._pending_loudness_paths: set[str] = set()
        self._loudness_progress: dict[str, float] = {}
        self._auto_run_command: str | None = None
        self._queue_pending_start: bool = False
        self._pending_metadata_paths: set[str] = set()
        self._update_check_in_progress = False
        self._update_install_in_progress = False
        self._update_check_forced = False
        self._update_check_retries_left = 2
        self._update_check_worker: _UpdateCheckWorker | None = None
        self._update_install_worker: _UpdateInstallWorker | None = None

        self._wire_widgets()
        self._build_queue_panel()
        self._load_queue_state()
        self._apply_theme_palette()
        self._apply_platform_icons()
        app_widget = QApplication.instance()
        if app_widget is not None:
            app_widget.styleHints().colorSchemeChanged.connect(self._on_system_theme_changed)
            app_widget.installEventFilter(self)
        self._populate_output_formats()
        self._load_templates()
        self._update_hardware_status()
        self._apply_saved_layout()
        self._refresh_command()
        self.installEventFilter(self)
        self.setAcceptDrops(True)

        # audio_analysis_dialog-ot előre importáljuk a főszálon, hogy a
        # _LoudnessWorker háttérszál ne futassa először az importot.
        QTimer.singleShot(0, self._prewarm_imports)
        QTimer.singleShot(1400, self._maybe_check_for_updates)

    def _update_hardware_status(self) -> None:
        self.hardware_status_label.setProperty("_i18n_text", "Detecting hardware...")
        self.hardware_status_label.setText(trs("Detecting hardware..."))
        worker = _HardwareStatusWorker(ffmpeg_bin=self._ffmpeg_bin)
        worker.signals.finished.connect(self._on_hardware_status_ready)
        self._hardware_status_worker = worker
        self._thread_pool.start(worker)

    def _on_hardware_status_ready(self, text: str) -> None:
        self.hardware_status_label.setProperty("_i18n_text", text)
        self.hardware_status_label.setText(trs(text))
        self._hardware_status_worker = None

    def _on_browse_files(self) -> None:
        start_dir = settings_manager.get_settings().get("last_open_dir", "") or ""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            trs("Open file(s)"),
            start_dir,
            "Media files (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v *.mpeg *.mpg *.mp3 *.wav *.ogg *.aac *.flac *.m4a *.wma);;All files (*.*)",
        )
        if not paths:
            return
        settings_manager.save_settings({"last_open_dir": str(Path(paths[0]).parent)})
        self._load_files(paths)

    def _load_files(self, paths: list[str]) -> None:
        if not self._ffprobe_bin:
            # The installer may have completed after window initialization.
            self.refresh_binary_paths()

        if not self._ffprobe_bin:
            QMessageBox.warning(self, trs("FFprobe missing"), trs("ffprobe not found, file metadata cannot be loaded."))
            return

        known_paths = {str(item.get("path", "")) for item in self.files}
        new_paths = [path for path in paths if path not in known_paths]
        if not new_paths:
            return

        for path in new_paths:
            info = self._minimal_info(path, loading=True)
            self.files.append(info)
            self.files_list_widget.addItem(info.get("filename", Path(path).name))
            self._start_metadata_load(path)

        self._update_files_status_label()
        if self.files:
            self.files_list_widget.setCurrentRow(len(self.files) - 1)

    def _minimal_info(self, path: str, loading: bool = False) -> dict:
        size_text = "unknown"
        try:
            size_bytes = os.path.getsize(path)
            if size_bytes < 1024 ** 3:
                size_text = f"{size_bytes / 1024 ** 2:.1f} MB"
            else:
                size_text = f"{size_bytes / 1024 ** 3:.2f} GB"
        except OSError:
            pass

        info = {
            "path": path,
            "filename": Path(path).name,
            "size": size_text,
        }
        if loading:
            info["__loading__"] = True
        return info

    def _start_metadata_load(self, file_path: str) -> None:
        if not file_path or not self._ffprobe_bin:
            return
        if file_path in self._pending_metadata_paths:
            return

        self._pending_metadata_paths.add(file_path)
        worker = _MetadataWorker(file_path, self._ffprobe_bin, self._ffmpeg_bin)
        worker.signals.finished.connect(self._on_metadata_load_finished)
        self._thread_pool.start(worker)

    def _on_metadata_load_finished(self, file_path: str, info: dict) -> None:
        self._pending_metadata_paths.discard(file_path)

        idx = next((i for i, item in enumerate(self.files) if str(item.get("path", "")) == file_path), -1)
        if idx < 0:
            return

        info.pop("__loading__", None)
        self.files[idx] = info

        if self.files_list_widget.currentRow() == idx:
            self.current_file_info = info
            self._render_metadata(info)
            self._refresh_output_path_from_input()
            self._refresh_command()
            self._refresh_queue_controls()

        if settings_manager.get_settings().get("auto_ebu_analysis", True):
            self._start_loudness_analysis(file_path, info)

    def _start_loudness_analysis(self, file_path: str, base_info: dict) -> None:
        if not self._ffmpeg_bin or not file_path:
            return
        if str(base_info.get("audio", "")) == "no audio":
            return
        if file_path in self._pending_loudness_paths:
            return

        # Ha a teljes audió analízis dialógus már lefutott erre a fájlra,
        # nincs szükség külön LoudnessWorker-re — az eredményt a cache-ből vesszük.
        try:
            from app.gui_qt.dialogs.audio_analysis_dialog import get_cached_result
            cached = get_cached_result(file_path)
            if cached is not None:
                enriched = dict(base_info)
                enriched.update({
                    "lufs": cached.integrated,
                    "lra": cached.loudness_range,
                    "true_peak": cached.true_peak_max,
                    "loudness_gate": "N/A",
                })
                self._on_loudness_analysis_finished(file_path, enriched)
                return
        except Exception:
            pass

        from app.gui_qt.dialogs.audio_analysis_dialog import _PENDING_PATHS
        _PENDING_PATHS.add(file_path)
        self._pending_loudness_paths.add(file_path)
        self._loudness_progress[file_path] = 0.0
        self._update_files_status_label()
        self._update_loudness_progress_bar()
        worker = _LoudnessWorker(file_path, base_info, self._ffmpeg_bin, self._ffprobe_bin)
        worker.signals.progress.connect(self._on_loudness_analysis_progress)
        worker.signals.finished.connect(self._on_loudness_analysis_finished)
        self._thread_pool.start(worker)

    def _on_loudness_analysis_progress(self, file_path: str, progress: float) -> None:
        if file_path not in self._pending_loudness_paths:
            return
        self._loudness_progress[file_path] = max(0.0, min(1.0, float(progress)))
        self._update_loudness_progress_bar()

    def _on_loudness_analysis_finished(self, file_path: str, enriched_info: dict) -> None:
        self._pending_loudness_paths.discard(file_path)
        self._loudness_progress.pop(file_path, None)

        idx = next((i for i, item in enumerate(self.files) if str(item.get("path", "")) == file_path), -1)
        if idx >= 0:
            self.files[idx] = enriched_info
            if self.files_list_widget.currentRow() == idx:
                self.current_file_info = enriched_info
                self._render_metadata(enriched_info)
                self._refresh_command()

        self._update_files_status_label()
        self._update_loudness_progress_bar()

        if not self._pending_loudness_paths and self._auto_run_command:
            cmd = self._auto_run_command
            self._auto_run_command = None
            self._execute_run(cmd)

    def _update_loudness_progress_bar(self) -> None:
        pending = list(self._pending_loudness_paths)
        if not pending:
            self.loudness_progress_bar.setRange(0, 100)
            self.loudness_progress_bar.setVisible(False)
            self.loudness_progress_bar.setValue(0)
            self.loudness_progress_bar.setFormat(trs("EBU: %p%"))
            return

        avg = sum(self._loudness_progress.get(path, 0.0) for path in pending) / float(len(pending))
        pct = int(max(0.0, min(1.0, avg)) * 100)
        self.loudness_progress_bar.setVisible(True)
        self.loudness_progress_bar.setTextVisible(True)
        if pct <= 0:
            self.loudness_progress_bar.setRange(0, 0)
            self.loudness_progress_bar.setFormat(trs("EBU analysis ({var} files): %p%").replace("{var}", str(len(pending))))
        else:
            self.loudness_progress_bar.setRange(0, 100)
            self.loudness_progress_bar.setValue(pct)
            self.loudness_progress_bar.setFormat(trs("EBU analysis ({var} files): %p%").replace("{var}", str(len(pending))))

    def _update_files_status_label(self) -> None:
        file_count = len(self.files)
        if file_count <= 0:
            self.files_status_label.setText(trs("No files loaded"))
            return
        self.files_status_label.setText(trs("{var} files loaded").replace("{var}", str(file_count)))

    def _on_status_clear_timer(self) -> None:
        clear_status_display(self.run_progress)

    def _set_status(self, text: str, timeout_ms: int = 0) -> None:
        set_status_display(self.run_progress, self._status_clear_timer, text, timeout_ms)

    def _play_notification_sound(self, kind: str) -> None:
        settings = settings_manager.get_settings()
        sound_path = resolve_notification_sound_path(_ROOT_DIR, kind, settings)
        if sound_path:
            play_sound(sound_path)

