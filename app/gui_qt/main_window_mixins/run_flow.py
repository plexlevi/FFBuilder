"""Run/process and command/output workflow extracted from MainWindow."""

from __future__ import annotations

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox, QVBoxLayout

from app.domain import cmd_macros
from app.gui_qt.dialogs.settings_dialog import SettingsDialog
from app.gui_qt.dialogs.visual_editor_dialog import VisualEditorWidget
from app.gui_qt.main_window_parts import (
    apply_finish_result_to_progress_bar,
    apply_queue_item_finish_state,
    apply_queue_item_progress,
    append_capped_text,
    ask_ebu_conflict,
    compute_output_path_with_suffix,
    confirm_run_command,
    expand_template_command,
    format_output_description,
    init_run_progress_display,
    is_process_running,
    normalized_output_format,
    resolve_process_finish_state,
    resolve_process_launch,
    resolve_stderr_progress_update,
    resolve_template_by_index,
    schedule_next_queue_start,
    set_line_edit_text_at_start,
    show_finish_error_dialog,
    template_output_extension,
    template_output_suffix,
    update_output_path_extension,
    validate_queue_snapshot,
)
from app.shared import settings as settings_manager
from app.shared.i18n import trs


class RunFlowMixin:
    def _start_command(self, command: str) -> None:
        launch = resolve_process_launch(command, self._ffmpeg_bin)
        if launch.get("error"):
            QMessageBox.critical(self, trs("Command error"), str(launch["error"]))
            return

        program = launch.get("program")
        arguments = launch.get("arguments")
        if not program or arguments is None:
            return

        self._process = QProcess(self)
        self._process.setProgram(str(program))
        self._process.setArguments([str(arg) for arg in arguments])
        self._process.setProcessChannelMode(QProcess.SeparateChannels)
        self._process.readyReadStandardError.connect(self._on_process_stderr)
        self._process.readyReadStandardOutput.connect(self._on_process_stdout)
        self._process.finished.connect(self._on_process_finished)
        self._process.start()

    def _refresh_output_path_from_input(self) -> None:
        if not self.current_file_info:
            return
        input_path = self.current_file_info.get("path", "")
        if not input_path:
            return
        suffix = ""
        tmpl = resolve_template_by_index(self._template_manager.templates, self._current_template_idx)
        if tmpl is not None:
            suffix = template_output_suffix(tmpl)

        path = self._compute_output_path(input_path, suffix)
        set_line_edit_text_at_start(self.output_path_line, path)

    def _compute_output_path(self, input_path: str, template_suffix: str = "") -> str:
        fmt = normalized_output_format(self.output_format_combo.currentText(), "mp4")
        suffix = settings_manager.get_output_suffix(template_suffix)
        return compute_output_path_with_suffix(input_path, fmt, suffix)

    def _on_output_format_changed(self) -> None:
        desc = self.output_format_combo.currentData() or ""
        self.format_desc_label.setText(format_output_description(desc))

        fmt = normalized_output_format(self.output_format_combo.currentText(), "mp4")
        current_output = self.output_path_line.text().strip()
        if current_output:
            updated_output = update_output_path_extension(current_output, fmt)
            if updated_output != current_output:
                set_line_edit_text_at_start(self.output_path_line, updated_output)
        else:
            self._refresh_output_path_from_input()
        self._refresh_command()

    def _on_browse_output(self) -> None:
        fmt = normalized_output_format(self.output_format_combo.currentText(), "mp4")
        path, _ = QFileDialog.getSaveFileName(
            self,
            trs("Output file"),
            self.output_path_line.text().strip(),
            f"*.{fmt}",
        )
        if path:
            set_line_edit_text_at_start(self.output_path_line, path)

    def _open_visual_editor(self) -> None:
        if self._ve_dialog is not None and self._ve_dialog.isVisible():
            self._ve_dialog.close()
            return

        input_path = str(self.current_file_info.get("path", "") or "")
        output_path = self.output_path_line.text().strip()
        output_format = self.output_format_combo.currentText().strip() or "mp4"
        initial_cmd = self.command_preview.toPlainText()

        dlg = QDialog(self, Qt.WindowType.Window)
        dlg.setWindowTitle(trs("Visual editor"))
        dlg.resize(780, 680)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        ve = VisualEditorWidget(
            input_path=input_path,
            output_path=output_path,
            output_format=output_format,
            initial_command=initial_cmd,
            parent=dlg,
        )
        ve.command_changed.connect(self.command_preview.setPlainText)
        layout.addWidget(ve)

        parent_geo = self.frameGeometry()
        target_x = parent_geo.x() + (parent_geo.width() - dlg.width()) // 2
        target_y = parent_geo.y() + (parent_geo.height() - dlg.height()) // 2
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            max_x = avail.right() - dlg.width() + 1
            max_y = avail.bottom() - dlg.height() + 1
            target_x = max(avail.left(), min(target_x, max_x))
            target_y = max(avail.top(), min(target_y, max_y))
        dlg.move(target_x, target_y)

        dlg.finished.connect(self._on_ve_dialog_closed)
        self._ve_dialog = dlg
        self.visual_editor_button.setText(trs("◀ Close"))
        dlg.show()

    def _on_ve_dialog_closed(self) -> None:
        self._ve_dialog = None
        self.visual_editor_button.setText(trs("Visual editor..."))

    def _refresh_command(self) -> None:
        if self.builder_tabs.currentIndex() == 0:
            template = resolve_template_by_index(self._template_manager.templates, self._current_template_idx)
            if template is not None:
                cmd = expand_template_command(
                    template,
                    input_path=str(self.current_file_info.get("path", "") or ""),
                    output_path=self.output_path_line.text().strip(),
                    fallback_fmt=normalized_output_format(self.output_format_combo.currentText(), "mp4"),
                    ffprobe_bin=self._ffprobe_bin or "",
                )
                self.command_preview.setPlainText(cmd)

    def _expand_internal_macros(self, cmd: str) -> str:
        input_path = str(self.current_file_info.get("path", "") or "")
        return cmd_macros.expand_map_all(cmd, input_path, self._ffprobe_bin or "")

    def _apply_template(self) -> None:
        tmpl = resolve_template_by_index(self._template_manager.templates, self._current_template_idx)
        if tmpl is not None:
            tmpl_ext = template_output_extension(tmpl)
            if tmpl_ext:
                self.output_format_combo.setCurrentText(tmpl_ext)

            if self.current_file_info:
                set_line_edit_text_at_start(
                    self.output_path_line,
                    self._compute_output_path(
                        str(self.current_file_info.get("path", "") or ""),
                        template_output_suffix(tmpl),
                    ),
                )

            settings_manager.save_settings(
                {
                    "last_used_preset_name": tmpl.get("name", "")
                }
            )
        self._refresh_command()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(parent=self)
        dlg.check_updates_requested.connect(self.check_for_updates_manual)
        dlg.exec()
        if dlg.reset_layout_requested:
            self.main_h_splitter.setSizes([320, 820])
            self.main_v_splitter.setSizes([560, 260])
            self.files_meta_splitter.setSizes([300, 240])
            self.templates_details_splitter.setSizes([260, 260])
        self._apply_saved_layout()
        self._refresh_output_path_from_input()
        self._refresh_command()
        self._refresh_queue_controls()
        if self.current_file_info:
            self._render_metadata(self.current_file_info)

    def _copy_command(self) -> None:
        cmd = self.command_preview.toPlainText().strip()
        if not cmd:
            return
        QApplication.clipboard().setText(cmd)
        self._set_status(trs("✅ Copied to clipboard"), 2500)

    def _validate_current_preview_command(self) -> None:
        command = self.command_preview.toPlainText().strip()
        input_path = str(self.current_file_info.get("path", "") or "")
        output_path = self.output_path_line.text().strip()
        if not output_path and input_path:
            suffix = ""
            tmpl = resolve_template_by_index(self._template_manager.templates, self._current_template_idx)
            if tmpl is not None:
                suffix = template_output_suffix(tmpl)
            output_path = self._compute_output_path(input_path, suffix)

        validation_error = validate_queue_snapshot(command, input_path, output_path)
        if validation_error:
            QMessageBox.warning(self, trs("Command check"), validation_error)
            self._set_status(trs("⚠️ Command check failed"), 3500)
            return

        QMessageBox.information(self, trs("Command check"), trs("The command appears to be executable."))
        self._set_status(trs("✅ Command OK"), 2500)

    def _run_command(self) -> None:
        if is_process_running(self._process):
            self._user_stopped = True
            self._process.kill()
            self._set_status(trs("⛔ Stopped"))
            return

        command = self.command_preview.toPlainText().strip()
        if not command:
            QMessageBox.warning(self, trs("Empty command"), trs("The command field is empty."))
            return

        if self._pending_loudness_paths:
            choice = ask_ebu_conflict(self, len(self._pending_loudness_paths))
            if choice == "cancel":
                return
            elif choice == "wait":
                self._auto_run_command = command
                return
            else:
                self._cancel_loudness_analysis()

        if not confirm_run_command(self, command):
            return

        self._execute_run(command)

    def _execute_run(self, command: str) -> None:
        """Elindítja az FFmpeg folyamatot a megadott paranccsal."""
        self._run_duration_seconds = float(self.current_file_info.get("__duration_seconds", 0.0) or 0.0)
        self._stderr_buffer = ""
        self._stdout_buffer = ""
        self._eta_estimator.reset()
        init_run_progress_display(self.run_progress, self._run_duration_seconds)

        self._set_status(trs("⏳ Running..."))
        self.run_command_button.setText(trs("■ Stop"))
        self._user_stopped = False
        self._start_command(command)

    def _cancel_loudness_analysis(self) -> None:
        """Elveti a folyamatban lévő EBU elemzés eredményeit és elrejti a progress bart."""
        self._pending_loudness_paths.clear()
        self._loudness_progress.clear()
        self._auto_run_command = None
        self._update_loudness_progress_bar()

    def _on_process_stderr(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        self._stderr_buffer = append_capped_text(self._stderr_buffer, data, 12000)

        self._apply_process_progress_update(self._stderr_buffer)

    def _on_process_stdout(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._stdout_buffer = append_capped_text(self._stdout_buffer, data, 12000)
        self._apply_process_progress_update(self._stdout_buffer)

    def _apply_process_progress_update(self, source_text: str) -> None:
        progress_update = resolve_stderr_progress_update(
            source_text,
            self._run_duration_seconds,
            self._eta_estimator,
        )
        self._run_duration_seconds = float(progress_update["run_duration_seconds"])
        if bool(progress_update.get("should_reset_progress")):
            self.run_progress.setProperty("maximum", 100)
            self.run_progress.setProperty("value", 0)

        if progress_update.get("status_text"):
            self._set_status(str(progress_update["status_text"]))

        pct = progress_update.get("progress_percent")
        if pct is None:
            return
        self.run_progress.setProperty("maximum", 100)
        self.run_progress.setProperty("value", int(pct))

        if self._queue_active_item is not None:
            apply_queue_item_progress(self._queue_active_item, float(pct))
            self._refresh_queue_view()

    def _on_process_finished(self, exit_code: int, _status) -> None:
        queue_item = self._queue_active_item
        self._queue_active_item = None
        self.run_command_button.setText(trs("Run"))

        if queue_item is not None:
            queue_result = apply_queue_item_finish_state(queue_item, exit_code, self._user_stopped)
            self._set_status(queue_result["status_text"], int(queue_result["timeout_ms"]))
            if queue_result.get("play_sound"):
                self._play_notification_sound(str(queue_result["play_sound"]))

            self._save_queue_state()
            self._refresh_queue_view()

            if bool(queue_result.get("start_next_queue")):
                QTimer.singleShot(0, self._start_next_queue_item)
            else:
                self._refresh_queue_controls()
            return

        finish_result = resolve_process_finish_state(
            exit_code,
            self._user_stopped,
            self._queue_pending_start,
            self._stderr_buffer,
        )
        self._queue_pending_start = bool(finish_result["queue_pending_start"])
        self._set_status(str(finish_result["status_text"]), int(finish_result["timeout_ms"]))
        apply_finish_result_to_progress_bar(self.run_progress, finish_result)
        if finish_result.get("play_sound"):
            self._play_notification_sound(str(finish_result["play_sound"]))
        show_finish_error_dialog(self, finish_result)
        if schedule_next_queue_start(
            finish_result.get("start_next_delay_ms"),
            self._start_next_queue_item,
        ):
            return
