#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Settings dialog for Qt UI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile, Signal
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QPushButton,
    QCheckBox,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
)

from app.shared import settings as settings_manager
from app.shared.i18n import available_languages, get_language, set_language, apply_language_to_app, trs

_LANG_DISPLAY: dict[str, str] = {
    "en": "English",
    "hu": "Magyar",
}


class SettingsDialog(QDialog):
    check_updates_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(trs("⚙  Settings"))
        self.setModal(True)
        self.resize(520, 390)

        self._settings = settings_manager.get_settings()
        self._reset_layout_requested = False
        self._is_loading_values = False
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        _ui_path = Path(__file__).parent.parent / "ui" / "settings_dialog.ui"
        loader = QUiLoader()
        f = QFile(str(_ui_path))
        f.open(QFile.ReadOnly)
        w = loader.load(f, self)
        f.close()
        w.setStyleSheet("")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)

        self.template_radio = w.findChild(QRadioButton, "templateRadio")
        self.custom_radio = w.findChild(QRadioButton, "customRadio")
        self.custom_suffix_edit = w.findChild(QLineEdit, "customSuffixEdit")
        self.numbering_radio = w.findChild(QRadioButton, "numberingRadio")
        self.example_label = w.findChild(QLabel, "exampleLabel")
        self.success_sound_check = w.findChild(QCheckBox, "successSoundCheck")
        self.error_sound_check = w.findChild(QCheckBox, "errorSoundCheck")
        self.auto_apply_preset_check = w.findChild(QCheckBox, "autoApplyPresetCheck")
        self.save_panes_check = w.findChild(QCheckBox, "savePanesCheck")
        self.auto_ebu_check = w.findChild(QCheckBox, "autoEbuCheck")
        self.auto_update_check = w.findChild(QCheckBox, "autoUpdateCheck")
        self.check_updates_button = w.findChild(QPushButton, "checkUpdatesButton")
        self.reset_layout_button = w.findChild(QPushButton, "resetLayoutButton")
        self.language_combo = w.findChild(QComboBox, "languageCombo")
        self._populate_language_combo()

        self.reset_layout_button.clicked.connect(self._request_layout_reset)
        self.check_updates_button.clicked.connect(self.check_updates_requested.emit)
        self.language_combo.currentIndexChanged.connect(self._on_settings_changed)
        self.template_radio.toggled.connect(self._update_example)
        self.custom_radio.toggled.connect(self._update_example)
        self.numbering_radio.toggled.connect(self._update_example)
        self.custom_suffix_edit.textChanged.connect(self._update_example)
        self.template_radio.toggled.connect(self._on_settings_changed)
        self.custom_radio.toggled.connect(self._on_settings_changed)
        self.numbering_radio.toggled.connect(self._on_settings_changed)
        self.custom_suffix_edit.textChanged.connect(self._on_settings_changed)
        self.success_sound_check.toggled.connect(self._on_settings_changed)
        self.error_sound_check.toggled.connect(self._on_settings_changed)
        self.save_panes_check.toggled.connect(self._on_settings_changed)
        self.auto_apply_preset_check.toggled.connect(self._on_settings_changed)
        self.auto_ebu_check.toggled.connect(self._on_settings_changed)
        self.auto_update_check.toggled.connect(self._on_settings_changed)

    def _load_values(self) -> None:
        self._is_loading_values = True
        mode = self._settings.get("output_naming_mode", "template")
        if mode == "custom":
            self.custom_radio.setChecked(True)
        elif mode == "numbering":
            self.numbering_radio.setChecked(True)
        else:
            self.template_radio.setChecked(True)

        self.custom_suffix_edit.setText(str(self._settings.get("custom_suffix", "_converted")))
        self.success_sound_check.setChecked(bool(self._settings.get("sound_on_success", True)))
        self.error_sound_check.setChecked(bool(self._settings.get("sound_on_error", True)))
        self.save_panes_check.setChecked(bool(self._settings.get("save_pane_sizes", False)))
        self.auto_apply_preset_check.setChecked(bool(self._settings.get("auto_apply_last_preset", True)))
        self.auto_ebu_check.setChecked(bool(self._settings.get("auto_ebu_analysis", True)))
        self.auto_update_check.setChecked(bool(self._settings.get("auto_check_updates", True)))
        current_lang = get_language()
        for i in range(self.language_combo.count()):
            if self.language_combo.itemData(i) == current_lang:
                self.language_combo.setCurrentIndex(i)
                break
        self._is_loading_values = False
        self._update_example()

    def _request_layout_reset(self) -> None:
        self._reset_layout_requested = True
        settings_manager.save_settings(
            {
                "splitter_main_horizontal": "320,820",
                "splitter_main_vertical": "560,260",
                "splitter_files_metadata": "300,240",
                "splitter_templates_details": "260,260",
                "window_size": "1140x760",
            }
        )

    def _populate_language_combo(self) -> None:
        self.language_combo.clear()
        for code in available_languages():
            label = _LANG_DISPLAY.get(code, code.upper())
            self.language_combo.addItem(label, userData=code)

    @property
    def reset_layout_requested(self) -> bool:
        return self._reset_layout_requested

    def _update_example(self) -> None:
        self.custom_suffix_edit.setEnabled(self.custom_radio.isChecked())
        if self.template_radio.isChecked():
            self.example_label.setText(f"{trs('Example:')} video_h264.mp4")
        elif self.custom_radio.isChecked():
            suffix = self.custom_suffix_edit.text().strip() or "_converted"
            self.example_label.setText(f"{trs('Example:')} video{suffix}.mp4")
        else:
            self.example_label.setText(f"{trs('Example:')} video_001.mp4, video_002.mp4")

    def _on_settings_changed(self) -> None:
        if self._is_loading_values:
            return
        self._save_settings()

    def _save_settings(self) -> None:
        mode = "template"
        if self.custom_radio.isChecked():
            mode = "custom"
        elif self.numbering_radio.isChecked():
            mode = "numbering"

        selected_lang = self.language_combo.currentData() or "en"
        lang_changed = selected_lang != get_language()

        settings_manager.save_settings(
            {
                "output_naming_mode": mode,
                "custom_suffix": self.custom_suffix_edit.text().strip() or "_converted",
                "sound_on_success": self.success_sound_check.isChecked(),
                "sound_on_error": self.error_sound_check.isChecked(),
                "save_pane_sizes": self.save_panes_check.isChecked(),
                "auto_apply_last_preset": self.auto_apply_preset_check.isChecked(),
                "auto_ebu_analysis": self.auto_ebu_check.isChecked(),
                "auto_check_updates": self.auto_update_check.isChecked(),
            }
        )
        if lang_changed:
            set_language(selected_lang)
            apply_language_to_app()