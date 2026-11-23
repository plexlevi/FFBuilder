"""File-list and metadata panel workflow extracted from MainWindow."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHeaderView,
    QMenu,
    QMessageBox,
    QTreeWidgetItem,
)

from app.shared.i18n import trs
from app.gui_qt.main_window_parts import (
    build_metadata_columns,
    default_file_info_save_path,
    delete_files_by_rows,
    resolve_audio_analysis_request,
    resolve_current_file_info_text,
    resolve_file_rows_for_deletion,
    resolve_selected_file_for_open,
    resolve_selected_file_info,
    remove_paths_from_loudness_state,
)

_META_FIELDS = [
    ("Path", "path"),
    ("Size", "size"),
    ("Duration", "duration"),
    ("Title", "meta_title"),
    ("Date", "meta_date"),
    ("Encoder", "meta_encoder"),
    ("Comment", "meta_comment"),
    ("Resolution", "resolution"),
    ("Video BR", "video_bitrate"),
    ("FPS", "fps"),
    ("Field order", "field_order"),
    ("Aspect ratio", "aspect_ratio"),
    ("Video codec", "codec"),
    ("Profile", "profile"),
    ("Level", "level"),
    ("Bit depth", "bit_depth"),
    ("Pixel fmt", "color"),
    ("Color space", "color_space"),
    ("Color primaries", "color_primaries"),
    ("Color transfer", "color_transfer"),
    ("HDR", "hdr"),
    ("Video title", "video_title"),
    ("Video lang", "video_language"),
    ("Audio", "audio"),
    ("Audio BR", "audio_bitrate"),
    ("Audio Sample Rate", "audio_sample_rate"),
    ("Audio Bit Depth", "audio_bit_depth"),
    ("Audio Channels", "audio_channels"),
    ("Audio Layout", "audio_channel_layout"),
    ("Audio Language", "audio_language"),
    ("Audio Title", "audio_title"),
    ("Audio LUFS", "lufs"),
    ("Audio LRA", "lra"),
    ("Audio True Peak", "true_peak"),
    ("Audio Loudness Gate", "loudness_gate"),
    ("Container", "container_format"),
    ("Total BR", "bitrate"),
]

_LOUDNESS_KEYS = {"lufs", "lra", "true_peak", "loudness_gate"}


class FileMetadataMixin:
    def _update_clear_files_button(self) -> None:
        has_selection = bool(self.files_list_widget.selectedItems())
        self.clear_files_button.setEnabled(has_selection)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.files_list_widget and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                if self.files_list_widget.selectedItems():
                    self._delete_selected_file()
                return True
        return super().eventFilter(obj, event)

    def _on_clear_files(self) -> None:
        self.files.clear()
        self._manual_analysis_paths.clear()
        self._pending_metadata_paths.clear()
        self._pending_loudness_paths.clear()
        self._loudness_progress.clear()
        self.files_list_widget.clear()
        self._clear_selected_file_state()
        self._update_files_status_label()
        self._update_loudness_progress_bar()

    def _clear_selected_file_state(self) -> None:
        self.current_file_info = {}
        self.metadata_tree.clear()
        self._refresh_command()
        self._refresh_queue_controls()

    def _selected_media_paths(self) -> list[str]:
        rows = sorted({self.files_list_widget.row(it) for it in self.files_list_widget.selectedItems()})
        if not rows:
            current = self.files_list_widget.currentRow()
            if current >= 0:
                rows = [current]
        paths: list[str] = []
        for row in rows:
            if 0 <= row < len(self.files):
                path = str(self.files[row].get("path", "") or "").strip()
                if path:
                    paths.append(path)
        return paths

    def _open_audio_swap_dialog(self) -> None:
        paths = self._selected_media_paths()
        if not paths:
            QMessageBox.information(self, trs("Audio swap"), trs("Select at least one video."))
            return

        # Import lazily so application startup stays fast.
        from app.gui_qt.dialogs.audio_swap_dialog import AudioSwapDialog

        dlg = AudioSwapDialog(
            paths,
            ffmpeg_bin=self._ffmpeg_bin or "",
            ffprobe_bin=self._ffprobe_bin or "",
            output_format=self.output_format_combo.currentText().strip() or "mp4",
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.jobs:
            self._enqueue_audio_swap_jobs(dlg.jobs)

    def _show_file_context_menu(self, pos) -> None:
        row = self.files_list_widget.indexAt(pos).row()
        if row >= 0:
            already_selected = {
                self.files_list_widget.row(it)
                for it in self.files_list_widget.selectedItems()
            }
            if row not in already_selected:
                # In ExtendedSelection mode setCurrentRow changes the current item
                # but does NOT update the selection. Clear and re-select so that
                # _enqueue_current_file sees the right-clicked file in selectedItems().
                self.files_list_widget.clearSelection()
                self.files_list_widget.setCurrentRow(row)
                item = self.files_list_widget.item(row)
                if item is not None:
                    item.setSelected(True)

        multi = len(self.files_list_widget.selectedItems()) > 1

        menu = QMenu(self.files_list_widget)
        queue_action = menu.addAction(trs("Add to queue"))
        audio_swap_action = menu.addAction(trs("Audio swap..."))
        audio_swap_action.setEnabled(
            bool(self.files_list_widget.selectedItems()) or self.files_list_widget.currentRow() >= 0
        )
        menu.addSeparator()
        play_action = folder_action = audio_action = None
        if not multi:
            play_action = menu.addAction(trs("Play"))
            folder_action = menu.addAction(trs("Open folder"))
            menu.addSeparator()
        audio_action = menu.addAction(trs("Audio analysis"))
        save_chart_action = menu.addAction(trs("Save chart"))
        save_chart_action.setEnabled(
            bool(self.files_list_widget.selectedItems())
            or self.files_list_widget.currentRow() >= 0
        )
        menu.addSeparator()
        delete_action = menu.addAction(trs("Delete selected"))
        menu.addSeparator()
        clear_all_action = menu.addAction(trs("Clear all"))
        clear_all_action.setEnabled(bool(self.files))
        action = menu.exec(self.files_list_widget.mapToGlobal(pos))
        if action == queue_action:
            self._enqueue_current_file()
            self._show_queue_tab()
        elif action == audio_swap_action:
            self._open_audio_swap_dialog()
        elif action is not None and play_action is not None and action == play_action:
            self._play_selected_file()
        elif action is not None and folder_action is not None and action == folder_action:
            file_path = self.current_file_info.get("path", "")
            if file_path:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(file_path).parent)))
        elif action is not None and audio_action is not None and action == audio_action:
            self._run_audio_analysis_for_selection()
        elif action == save_chart_action:
            self._save_audio_graphs()
        elif action == delete_action:
            self._delete_selected_file()
        elif action == clear_all_action:
            self._on_clear_files()

    def _run_audio_analysis_for_selection(self) -> None:
        """Analyse the selected file, or all selected files in the background."""
        paths = self._selected_media_paths()
        if not paths:
            QMessageBox.information(self, trs("No file"), trs("Select a file first."))
            return
        if len(paths) == 1:
            self._open_audio_analysis()
            return

        ran_any = False
        for path in paths:
            info = next(
                (item for item in self.files if str(item.get("path", "")) == path),
                {"path": path, "filename": Path(path).name},
            )
            self._start_manual_audio_analysis(path, info)

    def _save_audio_graphs(self) -> None:
        """Save loudness graphs for all selected files into a chosen folder."""
        from app.gui_qt.dialogs.audio_analysis_dialog import get_all_cached_results

        paths = self._selected_media_paths()
        if not paths:
            QMessageBox.information(self, trs("No file"), trs("Select a file first."))
            return

        folder = QFileDialog.getExistingDirectory(
            self, trs("Save audio graphs"), str(Path.home() / "Desktop")
        )
        if not folder:
            return

        self._pending_graph_saves.clear()
        self._graph_save_total = len(paths)
        self._graph_save_done = 0
        self._graph_save_failed = 0
        used_names: set[str] = set()

        for path in paths:
            out_path = self._unique_graph_output_path(folder, path, used_names)
            cached = get_all_cached_results(path)
            if cached:
                if self._write_loudness_graph(cached[0], out_path):
                    self._graph_save_done += 1
                else:
                    self._graph_save_failed += 1
                continue

            info = next(
                (item for item in self.files if str(item.get("path", "")) == path), None
            )
            if info is None or not self._ffmpeg_bin or str(info.get("audio", "")) == "no audio":
                self._graph_save_failed += 1
                continue

            self._pending_graph_saves[path] = out_path
            started = self._start_manual_audio_analysis(path, info)
            if path in self._pending_graph_saves and not started:
                # The analysis could not start: count it as a failure.
                self._pending_graph_saves.pop(path, None)
                self._graph_save_failed += 1

        if self._pending_graph_saves:
            self._set_status(trs("Saving audio graphs..."), 0)
        else:
            self._finish_graph_saves()

    def _unique_graph_output_path(self, folder: str, media_path: str, used: set[str]) -> str:
        stem = Path(media_path).stem or "graph"
        candidate = Path(folder) / f"{stem}_loudnessGraph.png"
        counter = 2
        while str(candidate).lower() in used or candidate.exists():
            candidate = Path(folder) / f"{stem}_loudnessGraph_{counter}.png"
            counter += 1
        used.add(str(candidate).lower())
        return str(candidate)

    def _show_metadata_context_menu(self, pos) -> None:
        menu = QMenu(self.metadata_tree)
        copy_action = menu.addAction(trs("Copy full file info"))
        save_action = menu.addAction(trs("Save file info as TXT"))
        action = menu.exec(self.metadata_tree.mapToGlobal(pos))
        if action == copy_action:
            self._copy_current_file_info()
        elif action == save_action:
            self._save_current_file_info_txt()

    def _copy_current_file_info(self) -> None:
        resolved = resolve_current_file_info_text(self.current_file_info, _META_FIELDS, _LOUDNESS_KEYS)
        if resolved.get("error_text"):
            QMessageBox.information(self, str(resolved["error_title"]), str(resolved["error_text"]))
            return
        QApplication.clipboard().setText(str(resolved["text"]))
        self._set_status(trs("File info copied to clipboard"), 2500)

    def _save_current_file_info_txt(self) -> None:
        resolved = resolve_current_file_info_text(self.current_file_info, _META_FIELDS, _LOUDNESS_KEYS)
        if resolved.get("error_text"):
            QMessageBox.information(self, str(resolved["error_title"]), str(resolved["error_text"]))
            return

        input_path = str(self.current_file_info.get("path", "") or "").strip()
        default_path = default_file_info_save_path(input_path)

        path, _ = QFileDialog.getSaveFileName(
            self,
            trs("Save file info"),
            default_path,
            "Text file (*.txt)",
        )
        if not path:
            return

        try:
            Path(path).write_text(str(resolved["text"]), encoding="utf-8")
            self._set_status(trs("File info saved"), 2500)
        except Exception as exc:
            QMessageBox.critical(self, trs("Save error"), trs("Could not save file:\n{var}").replace("{var}", str(exc), 1))

    def _delete_selected_file(self) -> None:
        selected_rows = [self.files_list_widget.row(it) for it in self.files_list_widget.selectedItems()]
        rows = resolve_file_rows_for_deletion(
            selected_rows,
            self.files_list_widget.currentRow(),
            len(self.files),
        )
        if not rows:
            return

        for idx in rows:
            self.files_list_widget.takeItem(idx)
        delete_result = delete_files_by_rows(self.files, rows)
        remove_paths_from_loudness_state(
            self._pending_loudness_paths,
            self._loudness_progress,
            list(delete_result["removed_paths"]),
        )

        if not bool(delete_result["has_files"]):
            self._on_clear_files()
            return

        new_idx = int(delete_result["new_index"])
        self.files_list_widget.setCurrentRow(new_idx)
        self._on_file_selected(new_idx)
        self._update_files_status_label()
        self._update_loudness_progress_bar()

    def _play_selected_file(self) -> None:
        resolved = resolve_selected_file_for_open(self.files, self.files_list_widget.currentRow())
        if resolved.get("error_text"):
            QMessageBox.warning(self, str(resolved["error_title"]), str(resolved["error_text"]))
            return

        url = QUrl.fromLocalFile(str(resolved["path"]))
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, trs("Open error"), trs("Failed to open the video in the default player."))

    def _open_audio_analysis(self) -> None:
        request = resolve_audio_analysis_request(self.current_file_info, self._ffmpeg_bin, self._ffprobe_bin)
        if request.get("error_text"):
            QMessageBox.warning(self, str(request["error_title"]), str(request["error_text"]))
            return
        path = str(request["path"])

        from app.gui_qt.dialogs.audio_analysis_dialog import AudioAnalysisDialog

        dlg = AudioAnalysisDialog(path, ffmpeg_bin=self._ffmpeg_bin, ffprobe_bin=self._ffprobe_bin, parent=self)
        dlg.exec()

        patch = dlg.get_file_info_patch()
        if not patch:
            return

        idx = next((i for i, item in enumerate(self.files) if str(item.get("path", "")) == path), -1)
        if idx < 0:
            return

        updated = dict(self.files[idx])
        updated.update(patch)
        self.files[idx] = updated

        if self.files_list_widget.currentRow() == idx:
            self.current_file_info = updated
            self._render_metadata(updated)
            self._refresh_command()
            self._refresh_queue_controls()

    def _on_file_double_clicked(self, item) -> None:
        """Start the audio analysis in the background for the double-clicked file."""
        row = self.files_list_widget.row(item)
        if row < 0 or row >= len(self.files):
            return
        if self.files_list_widget.currentRow() != row:
            self.files_list_widget.setCurrentRow(row)
        info = self.files[row]
        file_path = str(info.get("path", "") or "").strip()
        if file_path:
            self._start_manual_audio_analysis(file_path, info)

    def _on_file_selected(self, idx: int) -> None:
        info = resolve_selected_file_info(self.files, idx)
        if info is None:
            self._clear_selected_file_state()
            return

        self.current_file_info = info
        self._render_metadata(info)
        self._refresh_output_path_from_input()
        self._refresh_command()
        self._refresh_queue_controls()

    def _render_metadata(self, info: dict) -> None:
        video_rows, audio_rows = build_metadata_columns(info, _META_FIELDS, _LOUDNESS_KEYS)
        self.metadata_tree.clear()

        # Left column: video/other data, right column: audio data.
        row_count = max(len(video_rows), len(audio_rows))
        for idx in range(row_count):
            video_pair = video_rows[idx] if idx < len(video_rows) else ("", "")
            audio_pair = audio_rows[idx] if idx < len(audio_rows) else ("", "")
            item = QTreeWidgetItem(
                [video_pair[0], video_pair[1], audio_pair[0], audio_pair[1]]
            )
            self.metadata_tree.addTopLevelItem(item)

        # Keep both halves at the same width: the field columns get a common
        # width, the value columns share the rest equally.
        header = self.metadata_tree.header()
        self.metadata_tree.resizeColumnToContents(0)
        self.metadata_tree.resizeColumnToContents(2)
        field_width = max(
            self.metadata_tree.columnWidth(0), self.metadata_tree.columnWidth(2)
        )
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.metadata_tree.setColumnWidth(0, field_width)
        self.metadata_tree.setColumnWidth(2, field_width)
