"""Conversion log tab mixin for MainWindow."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from app.shared import conversion_log
from app.shared.i18n import trs

_STATUS_COLORS = {
    "success": "#4caf50",
    "error":   "#f44336",
    "stopped": "#ff9800",
}

_STATUS_LABEL_KEYS = {
    "success": "Success",
    "error":   "Error",
    "stopped": "Stopped",
}


_ENTRY_ROLE = Qt.ItemDataRole.UserRole + 1


class LogTabMixin:
    def _build_log_panel(self) -> None:
        self._log_status_label: QLabel = self._w(QLabel, "logStatusLabel")

        self._log_delete_button: QPushButton = self._w(QPushButton, "logDeleteButton")
        self._log_delete_button.setEnabled(False)
        self._log_delete_button.clicked.connect(self._log_delete_selected)

        self._log_tree: QTreeWidget = self._w(QTreeWidget, "logTreeWidget")
        self._log_tree.setRootIsDecorated(False)
        self._log_tree.setAlternatingRowColors(True)
        header = self._log_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._log_tree.itemSelectionChanged.connect(self._on_log_selection_changed)
        self._log_tree.itemDoubleClicked.connect(self._log_show_detail)
        self._log_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._log_tree.customContextMenuRequested.connect(self._show_log_context_menu)
        self._log_tree.installEventFilter(self)

        self._refresh_log_view()

    def _refresh_log_view(self) -> None:
        if not hasattr(self, "_log_tree"):
            return
        self._log_tree.clear()
        entries = conversion_log.read_entries()
        total = len(entries)
        for i, entry in enumerate(reversed(entries)):
            original_idx = total - 1 - i
            item = QTreeWidgetItem()
            item.setText(0, entry.get("ts", ""))
            item.setText(1, Path(entry.get("input", "")).name)
            item.setText(2, Path(entry.get("output", "")).name)
            status = entry.get("status", "")
            label_key = _STATUS_LABEL_KEYS.get(status, status.capitalize())
            item.setText(3, trs(label_key))
            item.setData(0, Qt.ItemDataRole.UserRole, original_idx)
            item.setData(0, _ENTRY_ROLE, entry)
            color = _STATUS_COLORS.get(status)
            if color:
                item.setForeground(3, QColor(color))
            self._log_tree.addTopLevelItem(item)

        if total == 0:
            self._log_status_label.setText(trs("No conversions logged"))
        else:
            self._log_status_label.setText(
                trs("{var} entries logged").replace("{var}", str(total))
            )
        self._log_delete_button.setEnabled(False)

    def _on_log_selection_changed(self) -> None:
        self._log_delete_button.setEnabled(bool(self._log_tree.selectedItems()))

    def _log_delete_selected(self) -> None:
        selected = self._log_tree.selectedItems()
        if not selected:
            return
        indices = [item.data(0, Qt.ItemDataRole.UserRole) for item in selected]
        conversion_log.delete_entries(indices)
        self._refresh_log_view()

    def _log_clear_all(self) -> None:
        if not conversion_log.read_entries():
            return
        reply = QMessageBox.question(
            self,
            trs("Clear log"),
            trs("Delete all log entries?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            conversion_log.clear_all()
            self._refresh_log_view()

    def _show_log_context_menu(self, pos) -> None:
        menu = QMenu(self._log_tree)
        has_entries = self._log_tree.topLevelItemCount() > 0
        has_selection = bool(self._log_tree.selectedItems())

        delete_action = menu.addAction(trs("Delete selected"))
        delete_action.setEnabled(has_selection)
        menu.addSeparator()
        clear_action = menu.addAction(trs("Clear all"))
        clear_action.setEnabled(has_entries)

        action = menu.exec(self._log_tree.mapToGlobal(pos))
        if action == delete_action:
            self._log_delete_selected()
        elif action == clear_action:
            self._log_clear_all()

    def eventFilter(self, obj, event: QEvent) -> bool:
        if obj is self._log_tree and event.type() == QEvent.Type.KeyPress:
            key = event.key()  # type: ignore[attr-defined]
            if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self._log_delete_selected()
                return True
        return super().eventFilter(obj, event)

    def _log_show_detail(self, item: QTreeWidgetItem, _col: int) -> None:
        entry: dict = item.data(0, _ENTRY_ROLE) or {}
        console_out = str(entry.get("console_output", "")).strip()

        dlg = QDialog(self)
        dlg.setWindowTitle(trs("FFmpeg output"))
        dlg.resize(700, 450)
        layout = QVBoxLayout(dlg)

        info_label = QLabel(
            f"<b>{Path(entry.get('input', '')).name}</b>  →  "
            f"{Path(entry.get('output', '')).name}  "
            f"[{entry.get('ts', '')}]"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        text_edit = QPlainTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(console_out if console_out else trs("No FFmpeg output recorded."))
        layout.addWidget(text_edit)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton(trs("Copy"))
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(console_out))
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        close_btn = QPushButton(trs("Close"))
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dlg.exec()

    def append_conversion_log(
        self, input_path: str, output_path: str, status: str, exit_code: int,
        console_output: str = "",
    ) -> None:
        conversion_log.append_entry(input_path, output_path, status, exit_code, console_output)
        self._refresh_log_view()
