"""Run/process and command/output workflow extracted from MainWindow."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox, QVBoxLayout

from app.domain import cmd_macros
from app.gui_qt.dialogs.settings_dialog import SettingsDialog
from app.gui_qt.dialogs.visual_editor_dialog import VisualEditorWidget, build_default_visual_command
from app.gui_qt.main_window_parts import (
    apply_finish_result_to_progress_bar,
    apply_queue_item_finish_state,
    append_capped_text,
    ask_ebu_conflict,
    compute_output_path_with_suffix,
    confirm_run_command,
    expand_template_command,
    extract_command_input_path,
    extract_command_output_path,
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
from app.shared.utils.theme import get_accent


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
        
        # START the periodic progress update timer
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(500)  # Update every 500ms
        self._timer_progress_update_slot = lambda: self._timer_progress_handler()
        self._progress_timer.timeout.connect(self._timer_progress_update_slot)
        self._progress_timer.start()

    def _timer_progress_handler(self) -> None:
        """Timer callback handler for periodic progress updates."""
        # Only update if we have duration and process is running
        if not hasattr(self, "_run_duration_seconds") or self._run_duration_seconds <= 0:
            return
        if not self._process or self._process.state() != QProcess.ProcessState.Running:
            self._progress_timer.stop()
            return
        
        # Parse FFmpeg output to calculate progress
        data = self._stderr_buffer
        progress_update = resolve_stderr_progress_update(
            data,
            self._run_duration_seconds,
            self._eta_estimator,
        )
        
        # Update progress bar from parsed FFmpeg output
        if progress_update.get("progress_percent") is not None:
            clamped_pct = max(0.0, min(100.0, float(progress_update["progress_percent"])))
            self.run_progress.setProperty("maximum", 100)
            self.run_progress.setProperty("value", int(clamped_pct))

    def _refresh_output_path_from_input(self) -> None:
        if not self.current_file_info:
            return
        input_path = self.current_file_info.get("path", "")
        if not input_path:
            return
        suffix = ""
        tmpl = self._active_template()
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
            self._refresh_command()

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

    def _active_template(self) -> dict | None:
        """Az aktív (betöltött) preset, vagy None, ha nincs aktív preset."""
        return self._active_preset

    def _command_is_manual(self) -> bool:
        """True, ha a parancsot kézzel szerkesztették (a parancs az elsődleges)."""
        return bool(self._command_manual)

    def _set_command_text(self, text: str) -> None:
        if self.command_preview.toPlainText() == text:
            return
        self._command_updating = True
        try:
            self.command_preview.setPlainText(text)
        finally:
            self._command_updating = False

    def _on_command_text_edited(self) -> None:
        """Kézi szerkesztés: a preset inaktívvá válik, a parancs lesz az elsődleges."""
        if self._command_updating or self._command_manual:
            return
        self._command_manual = True
        self._update_command_mode_visual()

    def _update_command_mode_visual(self) -> None:
        """Vizuális visszajelzés, amíg a preset aktív (félkövér + akcentus keret)."""
        preset_active = self._active_preset is not None and not self._command_manual

        font = self.command_preview.font()
        font.setBold(preset_active)
        self.command_preview.setFont(font)

        if preset_active:
            accent, _r, _g, _b = get_accent()
            self.command_preview.setStyleSheet(
                "QPlainTextEdit#commandPreviewTextEdit {"
                f" border: 1px solid {accent};"
                " border-radius: 6px; padding-left: 4px; }"
            )
        else:
            self.command_preview.setStyleSheet("")

    def _remap_command_text(self, text: str, input_path: str, output_path: str) -> str:
        """A parancsban csak a be- és kimeneti útvonalakat cseréli ki."""
        old_input = extract_command_input_path(text) or self._command_input_snapshot
        old_output = extract_command_output_path(text) or self._command_output_snapshot
        if old_input and input_path and old_input != input_path:
            text = cmd_macros.replace_path(text, old_input, input_path)
        if old_output and output_path and old_output != output_path:
            text = cmd_macros.replace_path(text, old_output, output_path)
        return text

    def _refresh_command(self) -> None:
        if self.builder_tabs.currentIndex() != 0 and not self._command_manual:
            return

        input_path = str(self.current_file_info.get("path", "") or "")
        output_path = self.output_path_line.text().strip()

        if self._command_manual:
            # Kézzel szerkesztett parancs: csak az útvonalak frissülnek.
            cmd = self._remap_command_text(
                self.command_preview.toPlainText(), input_path, output_path
            )
        else:
            template = self._active_template()
            if template is None:
                return
            cmd = expand_template_command(
                template,
                input_path=input_path,
                output_path=output_path,
                fallback_fmt=normalized_output_format(self.output_format_combo.currentText(), "mp4"),
                ffprobe_bin=self._ffprobe_bin or "",
            )

        self._set_command_text(cmd_macros.ensure_overwrite_flag(cmd))
        self._command_input_snapshot = input_path
        self._command_output_snapshot = output_path

    def _prepare_run_command(self, command: str) -> str | None:
        """Normalize ``-y`` and resolve an existing output file before running."""
        command = cmd_macros.ensure_overwrite_flag(command).strip()
        if not command:
            return None
        self._set_command_text(command)

        output_path = extract_command_output_path(command) or self.output_path_line.text().strip()
        if not output_path or not Path(output_path).exists():
            return command

        from app.gui_qt.dialogs.output_collision_dialog import (
            OVERWRITE,
            RENAME,
            ask_output_collision,
        )

        choice, new_path = ask_output_collision(self, output_path)
        if choice == RENAME and new_path:
            set_line_edit_text_at_start(self.output_path_line, new_path)
            command = cmd_macros.replace_path(command, output_path, new_path)
            self._set_command_text(command)
            self._command_output_snapshot = new_path
            return command
        if choice != OVERWRITE:
            return None
        return command

    def _expand_internal_macros(self, cmd: str) -> str:
        input_path = str(self.current_file_info.get("path", "") or "")
        return cmd_macros.expand_map_channel(cmd, input_path, self._ffprobe_bin or "")

    def _apply_template(self) -> None:
        """A kijelölt sablon betöltése (dupla klikk vagy induló auto-apply)."""
        tmpl = resolve_template_by_index(self._template_manager.templates, self._current_template_idx)
        if tmpl is None:
            return

        self._active_preset = tmpl
        self._command_manual = False

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
        self._update_command_mode_visual()

    def _reset_command_to_default(self) -> None:
        """Replace the command with the visual editor's default parameter set."""
        input_path = str(self.current_file_info.get("path", "") or "")
        output_path = self.output_path_line.text().strip()
        output_format = normalized_output_format(
            self.output_format_combo.currentText(), "mp4"
        )
        command = build_default_visual_command(
            input_path=input_path,
            output_path=output_path,
            output_format=output_format,
        )

        self._active_preset = None
        self._command_manual = True
        self._command_input_snapshot = input_path
        self._command_output_snapshot = output_path
        self._set_command_text(cmd_macros.ensure_overwrite_flag(command))
        self._update_command_mode_visual()
        self._set_status(trs("Default state restored"), 2500)

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
        self._apply_console_visibility()
        if self.current_file_info:
            self._render_metadata(self.current_file_info)

    def _copy_command(self) -> None:
        cmd = cmd_macros.ensure_overwrite_flag(self.command_preview.toPlainText().strip())
        if not cmd:
            return
        self._set_command_text(cmd)
        QApplication.clipboard().setText(cmd)
        self._set_status(trs("✅ Copied to clipboard"), 2500)

    def _validate_current_preview_command(self) -> None:
        command = self.command_preview.toPlainText().strip()
        input_path = str(self.current_file_info.get("path", "") or "")
        output_path = self.output_path_line.text().strip()
        if not output_path and input_path:
            suffix = ""
            tmpl = self._active_template()
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

        command = cmd_macros.ensure_overwrite_flag(self.command_preview.toPlainText().strip())
        if not command:
            QMessageBox.warning(self, trs("Empty command"), trs("The command field is empty."))
            return
        self._set_command_text(command)

        if self._pending_loudness_paths:
            choice = ask_ebu_conflict(self, len(self._pending_loudness_paths))
            if choice == "cancel":
                return
            elif choice == "wait":
                self._auto_run_command = command
                return
            else:
                self._cancel_loudness_analysis()

        prepared = self._prepare_run_command(command)
        if prepared is None:
            return
        self._execute_run(prepared)

    def _execute_run(self, command: str) -> None:
        """Elindítja az FFmpeg folyamatot a megadott paranccsal."""
        self._run_duration_seconds = float(self.current_file_info.get("__duration_seconds", 0.0) or 0.0)
        self._stderr_buffer = ""
        self._stdout_buffer = ""
        self._ffmpeg_full_log = f"$ {command}\n\n"
        self._eta_estimator.reset()
        self._clear_ffmpeg_console()
        init_run_progress_display(self.run_progress, self._run_duration_seconds)

        self._run_active_filename = Path(str(self.current_file_info.get("path", "") or "")).name
        status = trs("⏳ Running...")
        if self._run_active_filename:
            status = f"{status} ({self._run_active_filename})"
        self._set_status(status)
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
        self._ffmpeg_full_log += data
        self._append_ffmpeg_console(data)
        # Only update status text, not progress bar (timer is the primary source)
        self._apply_process_progress_update(self._stderr_buffer, update_progress_bar=False)

    def _on_process_stdout(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._stdout_buffer = append_capped_text(self._stdout_buffer, data, 12000)
        # Only update status text, not progress bar (timer is the primary source)
        self._apply_process_progress_update(self._stdout_buffer, update_progress_bar=False)

    def _apply_process_progress_update(self, source_text: str, update_progress_bar: bool = True) -> None:
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
            status = str(progress_update["status_text"])
            if self._run_active_filename:
                status = f"{status} ({self._run_active_filename})"
            self._set_status(status)

        # Only update progress bar if requested
        if update_progress_bar:
            pct = progress_update.get("progress_percent")
            if pct is None:
                return
            self.run_progress.setProperty("maximum", 100)
            self.run_progress.setProperty("value", int(pct))

    def _on_process_finished(self, exit_code: int, _status) -> None:
        """Handle FFmpeg process completion (blocking mode)."""
        # Stop the periodic progress update timer
        self._progress_timer.stop()
        
        queue_item = self._queue_active_item
        self._queue_active_item = None
        self._run_active_filename = ""
        self.run_command_button.setText(trs("Run"))

        if queue_item is not None:
            queue_result = apply_queue_item_finish_state(queue_item, exit_code, self._user_stopped)
            _q_status = "success" if exit_code == 0 else ("stopped" if self._user_stopped else "error")
            self.append_conversion_log(queue_item.input_path, queue_item.output_path, _q_status, exit_code, self._ffmpeg_full_log)
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

        _r_status = "success" if exit_code == 0 else ("stopped" if self._user_stopped else "error")
        _r_input = str(self.current_file_info.get("path", "") or "")
        _r_output = self.output_path_line.text().strip()
        self.append_conversion_log(_r_input, _r_output, _r_status, exit_code, self._ffmpeg_full_log)

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

    # ------------------------------------------------------------------ console

    def _append_ffmpeg_console(self, text: str) -> None:
        """Append raw FFmpeg output to the console widget (no-op when hidden)."""
        if not hasattr(self, "ffmpeg_console") or not self.ffmpeg_console.isVisible():
            return
        cursor = self.ffmpeg_console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.ffmpeg_console.setTextCursor(cursor)
        self.ffmpeg_console.insertPlainText(text)
        self.ffmpeg_console.ensureCursorVisible()

    def _clear_ffmpeg_console(self) -> None:
        if hasattr(self, "ffmpeg_console"):
            self.ffmpeg_console.clear()

    def _apply_console_visibility(self) -> None:
        if hasattr(self, "ffmpeg_console"):
            show = bool(settings_manager.get_settings().get("show_ffmpeg_console", False))
            self.ffmpeg_console.setVisible(show)
