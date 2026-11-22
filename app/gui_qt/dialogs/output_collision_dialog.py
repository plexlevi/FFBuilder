#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Overwrite-conflict dialog for output files."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QWidget

from app.gui_qt.main_window_parts.template_output_helpers import find_available_output_path
from app.shared.i18n import trs

OVERWRITE = "overwrite"
RENAME = "rename"
SKIP = "skip"


def ask_output_collision(
    parent: QWidget,
    output_path: str,
    *,
    queue_mode: bool = False,
    label: str = "",
    reserved: Iterable[str] = (),
) -> tuple[str, str]:
    """Ask what to do when *output_path* already exists.

    Returns ``(OVERWRITE, output_path)``, ``(RENAME, suggested_path)`` or
    ``(SKIP, "")``. Closing the dialog is treated as skip/cancel.
    """
    suggested = find_available_output_path(output_path, reserved)

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(trs("Output file exists"))
    box.setTextFormat(Qt.TextFormat.PlainText)

    text = trs("The output file already exists:")
    if label:
        text = f"{label}\n\n{text}"
    box.setText(text)

    info = f"{output_path}\n\n{trs('New name:')} {suggested}"
    if queue_mode:
        info += "\n\n" + trs("This item will be skipped if you choose Skip.")
    box.setInformativeText(info)

    overwrite_button = box.addButton(trs("Overwrite"), QMessageBox.ButtonRole.DestructiveRole)
    rename_button = box.addButton(trs("Create new name"), QMessageBox.ButtonRole.AcceptRole)
    skip_text = trs("Skip") if queue_mode else trs("Cancel")
    skip_button = box.addButton(skip_text, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(rename_button)
    box.setEscapeButton(skip_button)

    box.exec()
    clicked = box.clickedButton()
    if clicked is overwrite_button:
        return OVERWRITE, output_path
    if clicked is rename_button:
        return RENAME, suggested
    return SKIP, ""
