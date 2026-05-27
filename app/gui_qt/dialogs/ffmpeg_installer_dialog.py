#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Qt FFmpeg installer dialog with live logs."""

from __future__ import annotations

import subprocess
import threading

from pathlib import Path

from PySide6.QtCore import QFile, QThread, Signal
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
)

from app.services.ffmpeg.manager import ensure_ffmpeg_with_callbacks
from app.shared.i18n import trs

_BREW_INSTALL_CMD = (
    '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
)


class _InstallerThread(QThread):
    """Runs ensure_ffmpeg_with_callbacks in a background thread."""

    log_signal: Signal = Signal(str)
    ask_signal: Signal = Signal(str)
    brew_signal: Signal = Signal()
    finished_signal: Signal = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ask_event = threading.Event()
        self._ask_result = False
        self._brew_event = threading.Event()
        self._brew_result = False

    def answer_ask(self, result: bool) -> None:
        self._ask_result = result
        self._ask_event.set()

    def answer_brew(self, result: bool) -> None:
        self._brew_result = result
        self._brew_event.set()

    def run(self) -> None:
        def log(msg: str) -> None:
            self.log_signal.emit(msg)

        def ask(question: str) -> bool:
            self._ask_event.clear()
            self.ask_signal.emit(question)
            self._ask_event.wait()
            return self._ask_result

        def open_terminal_brew() -> bool:
            self._brew_event.clear()
            self.brew_signal.emit()
            self._brew_event.wait()
            return self._brew_result

        try:
            result = ensure_ffmpeg_with_callbacks(
                log=log, ask=ask, open_terminal_brew=open_terminal_brew
            )
        except Exception as exc:
            result = {"ffmpeg": None, "ffprobe": None, "error": str(exc)}

        self.finished_signal.emit(result)


class FFmpegInstallerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(trs("FFmpeg installer"))
        self.resize(760, 500)
        self.result_data: dict = {"ffmpeg": None, "ffprobe": None, "error": trs("Not started")}
        self._thread: _InstallerThread | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        _ui_path = Path(__file__).parent.parent / "ui" / "ffmpeg_installer_dialog.ui"
        loader = QUiLoader()
        f = QFile(str(_ui_path))
        f.open(QFile.ReadOnly)
        w = loader.load(f, self)
        f.close()
        w.setStyleSheet("")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)

        self.log_text = w.findChild(QPlainTextEdit, "logText")
        self.progress = w.findChild(QProgressBar, "progressBar")
        self.start_button = w.findChild(QPushButton, "startButton")
        self.start_button.clicked.connect(self._run_install)
        self._close_buttons = w.findChild(QDialogButtonBox, "closeButtons")
        self._close_buttons.rejected.connect(self.reject)
        self._close_buttons.accepted.connect(self.accept)

    def _log(self, message: str) -> None:
        self.log_text.appendPlainText(message)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def _on_ask(self, question: str) -> None:
        """Main-thread slot: show dialog, then unblock the worker thread."""
        answer = QMessageBox.question(self, trs("FFmpeg installer"), question)
        if self._thread is not None:
            self._thread.answer_ask(answer == QMessageBox.Yes)

    def _on_brew(self) -> None:
        """Main-thread slot: open Terminal for Homebrew install, then ask if done."""
        osascript = (
            'tell application "Terminal"\n'
            f'    do script "{_BREW_INSTALL_CMD.replace(chr(34), chr(92) + chr(34))}"\n'
            '    activate\n'
            'end tell'
        )
        try:
            subprocess.Popen(["osascript", "-e", osascript])
            self._log(trs("Terminal opened — Homebrew installer is running."))
        except Exception as exc:
            self._log(trs("✗ Failed to open Terminal: {var}").replace("{var}", str(exc)))
            if self._thread is not None:
                self._thread.answer_brew(False)
            return

        answer = QMessageBox.question(
            self,
            trs("Homebrew installation"),
            trs("Has Homebrew installation in the Terminal completed?"),
        )
        if self._thread is not None:
            self._thread.answer_brew(answer == QMessageBox.Yes)

    def _on_finished(self, result: dict) -> None:
        self.result_data = result
        self.progress.setVisible(False)
        self.start_button.setEnabled(True)
        self._close_buttons.setEnabled(True)

        if result.get("ffmpeg") and result.get("ffprobe"):
            self._log(trs("Installation successful."))
            QMessageBox.information(self, "FFmpeg", trs("FFmpeg installation was successful."))
        else:
            self._log(trs("Installation failed: {var}").replace("{var}", str(result.get("error", trs("unknown error")))))
            QMessageBox.warning(self, "FFmpeg", trs("Installation failed."))

    def _run_install(self) -> None:
        self.start_button.setEnabled(False)
        self._close_buttons.setEnabled(False)
        self.progress.setVisible(True)
        self._log(trs("Starting installation..."))

        self._thread = _InstallerThread(self)
        self._thread.log_signal.connect(self._log)
        self._thread.ask_signal.connect(self._on_ask)
        self._thread.brew_signal.connect(self._on_brew)
        self._thread.finished_signal.connect(self._on_finished)
        self._thread.start()

    def closeEvent(self, event):
        """Prevent closing while installation is running."""
        if self._thread is not None and self._thread.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)


def run_ffmpeg_installer_dialog(parent=None) -> dict:
    dlg = FFmpegInstallerDialog(parent=parent)
    dlg.exec()
    return dlg.result_data