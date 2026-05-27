#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Template editor dialog for Qt UI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile, Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app.gui_qt.dialogs._modal_backdrop import exec_with_backdrop
from app.gui_qt.dialogs.visual_editor_dialog import VisualEditorWidget
from app.shared.i18n import trs


class TemplateEditorDialog(QDialog):
    def __init__(self, template: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(trs("New template") if template is None else trs("Edit template"))
        self.resize(760, 560)
        self._template = template or {}
        self._ve_dialog: QDialog | None = None
        self._build_ui()
        self._load_values()
        self.finished.connect(self._close_active_help)

    def exec(self) -> int:
        return exec_with_backdrop(self)

    def _build_ui(self) -> None:
        _ui_path = Path(__file__).parent.parent / "ui" / "template_editor_dialog.ui"
        loader = QUiLoader()
        f = QFile(str(_ui_path))
        f.open(QFile.ReadOnly)
        w = loader.load(f, self)
        f.close()
        w.setStyleSheet("")

        self.name_edit = w.findChild(QLineEdit, "nameEdit")
        self.desc_edit = w.findChild(QPlainTextEdit, "descEdit")
        self.cmd_edit = w.findChild(QPlainTextEdit, "cmdEdit")
        self.suffix_edit = w.findChild(QLineEdit, "suffixEdit")
        self.ext_edit = w.findChild(QLineEdit, "extEdit")
        save_btn = w.findChild(QPushButton, "saveButton")
        close_btn = w.findChild(QPushButton, "closeButton")
        self._ve_toggle_btn = w.findChild(QPushButton, "visualEditorButton")

        save_btn.clicked.connect(self._validate_accept)
        close_btn.clicked.connect(self.reject)
        self._ve_toggle_btn.clicked.connect(self._open_visual_editor)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)

    def _load_values(self) -> None:
        self.name_edit.setText(str(self._template.get("name", "")))
        self.desc_edit.setPlainText(str(self._template.get("desc", "")))
        self.cmd_edit.setPlainText(str(self._template.get("cmd", "")))
        self.suffix_edit.setText(str(self._template.get("output_suffix", "")))
        self.ext_edit.setText(str(self._template.get("output_extension", "")))

    def _validate_accept(self) -> None:
        name = self.name_edit.text().strip()
        cmd = self.cmd_edit.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, trs("Missing field"), trs("Name is required."))
            return
        if not cmd:
            QMessageBox.warning(self, trs("Missing field"), trs("Command is required."))
            return
        self.accept()

    def values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "desc": self.desc_edit.toPlainText().strip(),
            "cmd": self.cmd_edit.toPlainText().strip(),
            "output_suffix": self.suffix_edit.text().strip(),
            "output_extension": self.ext_edit.text().strip().lstrip(".").lower(),
        }

    # ------------------------------------------------------------------
    # Visual editor
    # ------------------------------------------------------------------

    def _open_visual_editor(self) -> None:
        if self._ve_dialog is not None and self._ve_dialog.isVisible():
            self._ve_dialog.close()
            return

        ext = self.ext_edit.text().strip().lstrip(".").lower() or "mp4"
        dlg = QDialog(self, Qt.WindowType.Window)
        dlg.setWindowTitle(trs("Visual editor"))
        dlg.resize(780, 680)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        ve = VisualEditorWidget(output_format=ext, initial_command=self.cmd_edit.toPlainText(), parent=dlg)
        ve.command_changed.connect(self.cmd_edit.setPlainText)
        layout.addWidget(ve)

        geo = self.geometry()
        dlg.move(geo.right() + 10, geo.top())

        dlg.finished.connect(self._close_active_help)
        dlg.finished.connect(self._on_ve_dialog_closed)
        self._ve_dialog = dlg
        self._ve_toggle_btn.setText(trs("◀ Close"))
        dlg.show()

    def _close_active_help(self) -> None:
        """Close the help dialog inside the visual editor if one is open."""
        if self._ve_dialog is None:
            return
        try:
            ve = self._ve_dialog.findChild(VisualEditorWidget)
            if ve is not None and ve._active_help_dlg is not None:
                ve._active_help_dlg.reject()
        except RuntimeError:
            pass

    def _on_ve_dialog_closed(self) -> None:
        self._ve_dialog = None
        self._ve_toggle_btn.setText(trs("Visual editor..."))