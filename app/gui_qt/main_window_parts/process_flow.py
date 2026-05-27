"""Runtime flow helpers for command launch, process lifecycle and status UI."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.shared.i18n import trs


def _is_ffmpeg_program(program: str) -> bool:
    name = Path(program).name.lower()
    return name in {"ffmpeg", "ffmpeg.exe"}


def validate_queue_snapshot(command: str, input_path: str, output_path: str) -> str | None:
    cmd = (command or "").strip()
    if not cmd:
        return trs("The command is empty.")

    if re.search(r"\{[^}]+\}", cmd):
        return trs("The command has unresolved placeholders (e.g. {input} or {output}).")

    try:
        args = shlex.split(cmd)
    except ValueError as exc:
        return trs("The command could not be parsed: {var}").replace("{var}", str(exc))

    if not args:
        return trs("The command is not executable.")

    lowered = [part.lower() for part in args]
    if "-i" not in lowered:
        return trs("The command does not contain an input file (-i).")

    try:
        i_idx = lowered.index("-i")
        if i_idx + 1 >= len(args):
            return trs("No input file specified after -i.")
        command_input = str(args[i_idx + 1]).strip()
        if command_input.startswith("-"):
            return trs("Non-file argument after -i.")
    except Exception:
        return trs("Could not verify the input file.")

    input_clean = command_input
    if not input_clean:
        input_clean = (input_path or "").strip()

    if not input_clean:
        return trs("No input file selected.")

    if not Path(input_clean).exists():
        return trs("Input file not found: {var}").replace("{var}", input_clean)

    positional = [arg for arg in args[1:] if not str(arg).startswith("-")]
    command_output = positional[-1].strip() if positional else ""
    if not command_output:
        command_output = (output_path or "").strip()
    if not command_output:
        return trs("Output path is empty.")

    return None


def resolve_process_launch(command: str, ffmpeg_bin: str | None) -> dict[str, Any]:
    try:
        args = shlex.split(command)
    except ValueError as exc:
        return {"error": str(exc), "program": None, "arguments": None}

    if not args:
        return {"error": None, "program": None, "arguments": None}

    program = args[0]
    if program in {"ffmpeg", "ffmpeg.exe"} and ffmpeg_bin:
        program = ffmpeg_bin

    if _is_ffmpeg_program(str(program)):
        lowered = [str(part).lower() for part in args[1:]]
        if "-progress" not in lowered:
            # Force machine-readable progress output regardless of loglevel.
            args = [args[0], "-progress", "pipe:1", *args[1:]]

    return {
        "error": None,
        "program": program,
        "arguments": args[1:],
    }


def confirm_run_command(parent: QWidget, command: str) -> bool:
    dlg = QDialog(parent)
    dlg.setWindowTitle(trs("Run confirmation"))
    dlg.resize(720, 380)

    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel(trs("Are you sure you want to run this command?")))

    preview = QPlainTextEdit()
    preview.setReadOnly(True)
    preview.setPlainText(command)
    layout.addWidget(preview)

    buttons = QDialogButtonBox()
    no_btn = buttons.addButton(trs("No"), QDialogButtonBox.RejectRole)
    yes_btn = buttons.addButton(trs("Yes"), QDialogButtonBox.AcceptRole)
    no_btn.clicked.connect(dlg.reject)
    yes_btn.clicked.connect(dlg.accept)
    layout.addWidget(buttons)

    yes_btn.setDefault(True)
    preview.setFocus()
    return dlg.exec() == QDialog.Accepted


def ask_ebu_conflict(parent: QWidget, pending_count: int) -> str:
    """Return one of: 'wait', 'continue', 'cancel'."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(trs("EBU analysis in progress"))
    dlg.setModal(True)
    layout = QVBoxLayout(dlg)
    layout.setSpacing(12)
    layout.addWidget(QLabel(trs("EBU analysis still running ({var} files).\nWhat would you like to do?").replace("{var}", str(pending_count))))

    wait_btn = QPushButton(trs("⏳  Wait for analysis"))
    cont_btn = QPushButton(trs("▶  Continue without analysis"))
    cancel_btn = QPushButton(trs("Cancel"))
    for btn in (wait_btn, cont_btn, cancel_btn):
        layout.addWidget(btn)
    wait_btn.clicked.connect(lambda: dlg.done(1))
    cont_btn.clicked.connect(lambda: dlg.done(2))
    cancel_btn.clicked.connect(lambda: dlg.done(0))

    res = dlg.exec()
    if res == 1:
        return "wait"
    if res == 2:
        return "continue"
    return "cancel"


def clear_status_display(progress_bar: QProgressBar) -> None:
    progress_bar.setFormat("")
    progress_bar.setVisible(False)


def set_status_display(progress_bar: QProgressBar, clear_timer: QTimer, text: str, timeout_ms: int = 0) -> None:
    progress_bar.setFormat(text)
    progress_bar.setVisible(True)
    clear_timer.stop()
    if timeout_ms > 0:
        clear_timer.start(timeout_ms)


def init_run_progress_display(progress_bar: QProgressBar, duration_seconds: float) -> None:
    if duration_seconds > 0:
        progress_bar.setProperty("maximum", 100)
        progress_bar.setProperty("value", 0)
    else:
        progress_bar.setProperty("maximum", 0)
        progress_bar.setProperty("value", 0)
    progress_bar.setVisible(True)


def resolve_process_finish_state(
    exit_code: int,
    user_stopped: bool,
    queue_pending_start: bool,
    stderr_buffer: str,
) -> dict[str, Any]:
    if exit_code == 0:
        return {
            "status_text": trs("✅ Conversion complete"),
            "timeout_ms": 5000,
            "progress_max": 100,
            "progress_value": 100,
            "play_sound": "success",
            "queue_pending_start": False if queue_pending_start else queue_pending_start,
            "start_next_delay_ms": 500 if queue_pending_start else None,
            "error_title": None,
            "error_text": None,
        }

    if user_stopped:
        return {
            "status_text": trs("⛔ Stopped"),
            "timeout_ms": 4000,
            "progress_max": 100,
            "progress_value": 0,
            "play_sound": None,
            "queue_pending_start": False,
            "start_next_delay_ms": None,
            "error_title": None,
            "error_text": None,
        }

    err_tail = stderr_buffer[-1800:].strip()
    return {
        "status_text": trs("❌ Error code: {var}").replace("{var}", str(exit_code)),
        "timeout_ms": 8000,
        "progress_max": 100,
        "progress_value": None,
        "play_sound": "error",
        "queue_pending_start": queue_pending_start,
        "start_next_delay_ms": None,
        "error_title": trs("FFmpeg error") if err_tail else None,
        "error_text": (trs("Error code: {var}").replace("{var}", str(exit_code)) + f"\n\n{err_tail}") if err_tail else None,
    }


def apply_finish_result_to_progress_bar(progress_bar: QProgressBar, finish_result: dict[str, Any]) -> None:
    progress_bar.setProperty("maximum", int(finish_result["progress_max"]))
    if finish_result.get("progress_value") is not None:
        progress_bar.setProperty("value", int(finish_result["progress_value"]))


def show_finish_error_dialog(parent: QWidget, finish_result: dict[str, Any]) -> None:
    if finish_result.get("error_text"):
        QMessageBox.critical(
            parent,
            str(finish_result["error_title"]),
            str(finish_result["error_text"]),
        )


def schedule_next_queue_start(start_next_delay_ms: int | None, callback: Callable[[], None]) -> bool:
    if start_next_delay_ms is None:
        return False
    QTimer.singleShot(int(start_next_delay_ms), callback)
    return True


def is_process_running(process: QProcess | None) -> bool:
    return process is not None and process.state() != QProcess.NotRunning
