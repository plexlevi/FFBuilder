"""Queue panel and queue execution workflow extracted from MainWindow."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from app.gui_qt.main_window_parts import (
    _ConversionQueueItem,
    apply_invalid_queue_item_state,
    expand_template_command,
    get_next_waiting_queue_item,
    init_run_progress_display,
    is_process_running,
    normalized_output_format,
    queue_has_error_items,
    resolve_template_by_index,
    template_output_suffix,
    validate_queue_snapshot,
)
from app.shared import settings as settings_manager
from app.shared.i18n import trs

_QUEUE_SETTINGS_KEY = "conversion_queue_items"


class QueueFlowMixin:
    def _build_queue_panel(self) -> None:
        self._queue_status_label = self._w(QLabel, "queueStatusLabel")
        self._queue_clear_button = self._w(QPushButton, "queueClearButton")
        self._queue_clear_button.clicked.connect(self._clear_queue)

        self._queue_start_button = self._w(QPushButton, "queueStartButton")
        self._queue_start_button.clicked.connect(self._start_queue)

        self._queue_stop_button = self._w(QPushButton, "queueStopButton")
        self._queue_stop_button.clicked.connect(self._stop_queue)

        self._queue_tree_widget = self._w(QTreeWidget, "queueTreeWidget")
        self._queue_tree_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._queue_tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self._queue_tree_widget.customContextMenuRequested.connect(self._show_queue_context_menu)
        self._queue_tree_widget.itemSelectionChanged.connect(self._refresh_queue_controls)
        self._queue_tree_widget.itemDoubleClicked.connect(self._edit_queue_item_command)
        self._queue_tree_widget.model().rowsMoved.connect(self._on_queue_rows_moved)

        self._refresh_queue_view()
        self._refresh_queue_controls()

    def _save_queue_state(self) -> None:
        serialized: list[dict] = []
        for item in self._queue_items:
            status = item.status
            if status == "Running":
                status = "Waiting"
            serialized.append(
                {
                    "queue_id": int(item.queue_id),
                    "label": str(item.label),
                    "input_path": str(item.input_path),
                    "output_path": str(item.output_path),
                    "command": str(item.command),
                    "duration_seconds": float(item.duration_seconds),
                    "status": status,
                    "progress": float(max(0.0, min(1.0, item.progress))),
                    "exit_code": item.exit_code,
                }
            )
        settings_manager.save_settings({_QUEUE_SETTINGS_KEY: serialized})

    def _load_queue_state(self) -> None:
        settings = settings_manager.get_settings()
        raw = settings.get(_QUEUE_SETTINGS_KEY, [])
        if not isinstance(raw, list):
            return

        loaded: list[_ConversionQueueItem] = []
        max_id = 0
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            command = str(entry.get("command", "") or "").strip()
            label = str(entry.get("label", "") or "").strip()
            if not command or not label:
                continue

            try:
                queue_id = int(entry.get("queue_id", 0) or 0)
            except Exception:
                queue_id = 0
            if queue_id <= 0:
                queue_id = max_id + 1

            status = str(entry.get("status", "Waiting") or "Waiting")
            if status == "Running":
                status = "Waiting"

            item = _ConversionQueueItem(
                queue_id=queue_id,
                label=label,
                input_path=str(entry.get("input_path", "") or ""),
                output_path=str(entry.get("output_path", "") or ""),
                command=command,
                duration_seconds=float(entry.get("duration_seconds", 0.0) or 0.0),
                status=status,
                progress=float(max(0.0, min(1.0, float(entry.get("progress", 0.0) or 0.0)))),
                exit_code=entry.get("exit_code"),
            )
            loaded.append(item)
            max_id = max(max_id, queue_id)

        self._queue_items = loaded
        self._queue_next_id = max(max_id + 1, 1)
        self._refresh_queue_view()

    def _on_queue_rows_moved(self, *_args) -> None:
        if self._queue_tree_widget is None or self._queue_active_item is not None:
            self._refresh_queue_view()
            return

        ordered_ids: list[int] = []
        for idx in range(self._queue_tree_widget.topLevelItemCount()):
            item = self._queue_tree_widget.topLevelItem(idx)
            value = item.data(0, Qt.ItemDataRole.UserRole)
            if value is None:
                continue
            ordered_ids.append(int(value))

        if not ordered_ids:
            return

        id_to_item = {item.queue_id: item for item in self._queue_items}
        reordered = [id_to_item[qid] for qid in ordered_ids if qid in id_to_item]
        if len(reordered) != len(self._queue_items):
            missing = [item for item in self._queue_items if item.queue_id not in ordered_ids]
            reordered.extend(missing)
        self._queue_items = reordered
        self._save_queue_state()
        self._refresh_queue_controls()

    def _current_queue_item(self) -> _ConversionQueueItem | None:
        if self._queue_tree_widget is None:
            return None
        item = self._queue_tree_widget.currentItem()
        if item is None:
            return None
        queue_id = item.data(0, Qt.ItemDataRole.UserRole)
        if queue_id is None:
            return None
        return next((queue_item for queue_item in self._queue_items if queue_item.queue_id == int(queue_id)), None)

    def _refresh_queue_controls(self) -> None:
        waiting_count = sum(1 for item in self._queue_items if item.status == "Waiting")
        active = self._queue_active_item is not None

        if self._queue_status_label is not None:
            n = len(self._queue_items)
            self._queue_status_label.setProperty("i18n_template", "{var} tasks, of which {var} waiting")
            self._queue_status_label.setProperty("i18n_args", [n, waiting_count])
            _tmpl = trs("{var} tasks, of which {var} waiting")
            _status_text = _tmpl.replace("{var}", str(n), 1).replace("{var}", str(waiting_count), 1)
            self._queue_status_label.setText(_status_text)

        if self._queue_start_button is not None:
            self._queue_start_button.setEnabled(waiting_count > 0 and not active)
        if self._queue_stop_button is not None:
            self._queue_stop_button.setEnabled(active)
        if self._queue_tree_widget is not None:
            mode = QAbstractItemView.NoDragDrop if active else QAbstractItemView.InternalMove
            self._queue_tree_widget.setDragDropMode(mode)
        if self._queue_clear_button is not None:
            self._queue_clear_button.setEnabled(bool(self._queue_items) and not active)

    def _refresh_queue_view(self) -> None:
        if self._queue_tree_widget is None:
            return

        selected_id = None
        current = self._queue_tree_widget.currentItem()
        if current is not None:
            selected_id = current.data(0, Qt.ItemDataRole.UserRole)

        self._queue_tree_widget.clear()
        for queue_item in self._queue_items:
            row = QTreeWidgetItem([
                queue_item.label,
                queue_item.output_path,
                trs(queue_item.status),
                f"{int(max(0.0, min(1.0, queue_item.progress)) * 100)}%",
            ])
            row.setData(0, Qt.ItemDataRole.UserRole, queue_item.queue_id)
            self._queue_tree_widget.addTopLevelItem(row)

        if selected_id is not None:
            for idx in range(self._queue_tree_widget.topLevelItemCount()):
                item = self._queue_tree_widget.topLevelItem(idx)
                if item.data(0, Qt.ItemDataRole.UserRole) == selected_id:
                    self._queue_tree_widget.setCurrentItem(item)
                    break

        self._refresh_queue_controls()

    def _enqueue_current_file(self) -> None:
        selected_rows = sorted(
            {self.files_list_widget.row(it) for it in self.files_list_widget.selectedItems()}
        )
        if not selected_rows:
            if not self.current_file_info:
                QMessageBox.warning(self, trs("No file"), trs("Select a file first."))
                return
            selected_rows = [self.files_list_widget.currentRow()]

        current_row = self.files_list_widget.currentRow()
        self._refresh_command()

        added_items: list[_ConversionQueueItem] = []
        failed: list[str] = []

        for row in selected_rows:
            if row < 0 or row >= len(self.files):
                continue
            file_info = self.files[row]
            input_path = str(file_info.get("path", "") or "")

            if row == current_row:
                command = self.command_preview.toPlainText().strip()
                output_path = self.output_path_line.text().strip()
            elif self.builder_tabs.currentIndex() == 0:
                tmpl = resolve_template_by_index(self._template_manager.templates, self._current_template_idx)
                if tmpl is not None:
                    t_suffix = template_output_suffix(tmpl)
                    output_path = self._compute_output_path(input_path, t_suffix)
                    command = expand_template_command(
                        tmpl,
                        input_path=input_path,
                        output_path=output_path,
                        fallback_fmt=normalized_output_format(self.output_format_combo.currentText(), "mp4"),
                        ffprobe_bin=self._ffprobe_bin or "",
                    )
                else:
                    command = ""
                    output_path = ""
            else:
                command = ""
                output_path = ""

            if not command:
                failed.append(Path(input_path).name if input_path else f"#{row + 1}")
                continue

            if not output_path and input_path:
                suffix = ""
                tmpl = resolve_template_by_index(self._template_manager.templates, self._current_template_idx)
                if tmpl is not None:
                    suffix = template_output_suffix(tmpl)
                output_path = self._compute_output_path(input_path, suffix)

            validation_error = validate_queue_snapshot(command, input_path, output_path)
            if validation_error:
                failed.append(Path(input_path).name if input_path else f"#{row + 1}")
                continue

            label = str(file_info.get("filename", Path(input_path).name) or Path(input_path).name)
            queue_item = _ConversionQueueItem(
                queue_id=self._queue_next_id,
                label=label,
                input_path=input_path,
                output_path=output_path,
                command=command,
                duration_seconds=float(file_info.get("__duration_seconds", 0.0) or 0.0),
            )
            self._queue_next_id += 1
            self._queue_items.append(queue_item)
            added_items.append(queue_item)

        if not added_items:
            if failed:
                QMessageBox.warning(self, trs("Failed to add to queue"), "\n".join(failed))
            return

        self._save_queue_state()
        self._refresh_queue_view()

        if self._queue_tree_widget is not None:
            last_id = added_items[-1].queue_id
            for idx in range(self._queue_tree_widget.topLevelItemCount()):
                item = self._queue_tree_widget.topLevelItem(idx)
                if item.data(0, Qt.ItemDataRole.UserRole) == last_id:
                    self._queue_tree_widget.setCurrentItem(item)
                    break

        n = len(added_items)
        if n == 1:
            self._set_status(trs("Added to queue: {var}").replace("{var}", added_items[0].label, 1), 2500)
        else:
            msg = trs("{var} files added to queue").replace("{var}", str(n), 1)
            if failed:
                msg += " " + trs("({var} failed)").replace("{var}", str(len(failed)), 1)
            self._set_status(msg, 2500)

    def _edit_queue_item_command(self, tree_item: QTreeWidgetItem) -> None:
        queue_id = tree_item.data(0, Qt.ItemDataRole.UserRole)
        queue_item = next((q for q in self._queue_items if q.queue_id == queue_id), None)
        if queue_item is None:
            return
        if self._queue_active_item is not None and queue_item.queue_id == self._queue_active_item.queue_id:
            QMessageBox.information(self, trs("Edit"), trs("This task is currently running and cannot be edited."))
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(trs("Edit command – {var}").replace("{var}", queue_item.label, 1))
        dlg.setMinimumWidth(700)
        layout = QVBoxLayout(dlg)

        editor = QPlainTextEdit()
        editor.setPlainText(queue_item.command)
        editor.setFont(self.font())
        layout.addWidget(editor)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_command = editor.toPlainText().strip()
            if new_command and new_command != queue_item.command:
                queue_item.command = new_command
                self._save_queue_state()
                self._set_status(trs("Command updated: {var}").replace("{var}", queue_item.label, 1), 2500)

    def _show_queue_context_menu(self, pos) -> None:
        if self._queue_tree_widget is None:
            return
        selected = self._queue_tree_widget.selectedItems()
        if not selected:
            return

        active = self._queue_active_item is not None
        active_id = self._queue_active_item.queue_id if active else None
        selected_ids = {it.data(0, Qt.ItemDataRole.UserRole) for it in selected}
        multi = len(selected) > 1

        can_delete = active_id not in selected_ids

        menu = QMenu(self._queue_tree_widget)
        edit_action = None
        folder_action = None
        if not multi:
            edit_action = menu.addAction(trs("Edit"))
            edit_action.setEnabled(not active)
        output_action = menu.addAction(trs("Change output path..."))
        output_action.setEnabled(can_delete)
        menu.addSeparator()
        if not multi:
            folder_action = menu.addAction(trs("Open folder"))
        menu.addSeparator()
        delete_action = menu.addAction(trs("Delete selected"))
        delete_action.setEnabled(can_delete)

        action = menu.exec(self._queue_tree_widget.mapToGlobal(pos))
        if action is None:
            return
        if edit_action is not None and action == edit_action:
            self._edit_queue_item_command(selected[0])
        elif action == output_action:
            self._change_queue_output_path(selected)
        elif folder_action is not None and action == folder_action:
            qid = selected[0].data(0, Qt.ItemDataRole.UserRole)
            queue_item = next((q for q in self._queue_items if q.queue_id == int(qid)), None)
            if queue_item and queue_item.input_path:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(queue_item.input_path).parent)))
        elif action == delete_action:
            self._remove_selected_queue_item()

    def _change_queue_output_path(self, tree_items: list) -> None:
        if not tree_items:
            return
        first_item = next(
            (q for q in self._queue_items
             if q.queue_id == tree_items[0].data(0, Qt.ItemDataRole.UserRole)),
            None,
        )
        start_dir = str(Path(first_item.output_path).parent) if first_item else ""
        new_dir = QFileDialog.getExistingDirectory(
            self, trs("Select output folder"), start_dir
        )
        if not new_dir:
            return
        selected_ids = {it.data(0, Qt.ItemDataRole.UserRole) for it in tree_items}
        for item in self._queue_items:
            if item.queue_id in selected_ids:
                old_output = item.output_path
                new_output = str(Path(new_dir) / Path(old_output).name)
                item.output_path = new_output
                if old_output in item.command:
                    item.command = item.command.replace(old_output, new_output)
        self._save_queue_state()
        self._refresh_queue_view()
        self._set_status(trs("Output path updated ({var} items)").replace("{var}", str(len(selected_ids)), 1), 2500)

    def _remove_selected_queue_item(self) -> None:
        if self._queue_tree_widget is None:
            return
        active_id = self._queue_active_item.queue_id if self._queue_active_item else None
        ids_to_remove = {
            it.data(0, Qt.ItemDataRole.UserRole)
            for it in self._queue_tree_widget.selectedItems()
        } - ({active_id} if active_id is not None else set())
        if not ids_to_remove:
            return
        self._queue_items = [item for item in self._queue_items if item.queue_id not in ids_to_remove]
        self._save_queue_state()
        self._refresh_queue_view()
        self._refresh_queue_controls()

    def _clear_queue(self) -> None:
        if self._queue_active_item is not None:
            return
        self._queue_items.clear()
        self._save_queue_state()
        self._refresh_queue_view()

    def _start_queue(self) -> None:
        if self._queue_active_item is not None:
            return
        if is_process_running(self._process):
            self._queue_pending_start = True
            self._set_status(trs("⏳ Queue will start after conversion..."), 6000)
            return
        self._start_next_queue_item()

    def _stop_queue(self) -> None:
        if not is_process_running(self._process):
            return
        self._user_stopped = True
        self._process.kill()

    def _start_next_queue_item(self) -> None:
        if is_process_running(self._process):
            return

        next_item = get_next_waiting_queue_item(self._queue_items)
        if next_item is None:
            self._queue_active_item = None
            self._refresh_queue_controls()
            has_errors = queue_has_error_items(self._queue_items)
            if not has_errors:
                self._play_notification_sound("success")
            return

        self._start_queue_item(next_item)

    def _start_queue_item(self, queue_item: _ConversionQueueItem) -> None:
        validation_error = validate_queue_snapshot(queue_item.command, queue_item.input_path, queue_item.output_path)
        if validation_error:
            invalid_result = apply_invalid_queue_item_state(queue_item, validation_error)
            self._set_status(str(invalid_result["status_text"]), int(invalid_result["timeout_ms"]))
            self._save_queue_state()
            self._refresh_queue_view()
            QTimer.singleShot(0, self._start_next_queue_item)
            return

        self._queue_active_item = queue_item
        queue_item.status = "Running"
        queue_item.progress = 0.0
        self._run_duration_seconds = max(0.0, float(queue_item.duration_seconds))
        self._stderr_buffer = ""
        self._eta_estimator.reset()
        init_run_progress_display(self.run_progress, self._run_duration_seconds)

        self._set_status(f"⏳ Sor fut: {queue_item.label}")
        self.run_command_button.setText("■ Stop")
        self._user_stopped = False
        self._save_queue_state()
        self._refresh_queue_view()

        self._start_command(queue_item.command)
