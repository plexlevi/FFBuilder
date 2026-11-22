#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Audio swap dialog: replace or extend the audio tracks of selected videos."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.domain.audio_swap import (
    AUDIO_CODEC_AAC,
    AUDIO_CODEC_COPY,
    VIDEO_PROFILE_COPY,
    VIDEO_PROFILES,
    AudioSlot,
    AudioSwapJob,
    build_audio_swap_command,
    copy_codec_compatible,
    slot_for_track,
    validate_audio_swap_job,
)
from app.gui_qt.dialogs._modal_backdrop import exec_with_backdrop
from app.gui_qt.main_window_parts.template_output_helpers import (
    compute_output_path_with_suffix,
)
from app.services.media.audio_track_service import (
    AudioTrackInfo,
    MediaProbeResult,
    probe_media,
)
from app.shared import settings as settings_manager
from app.shared.i18n import trs


_AUDIO_FILTER = (
    "Media files (*.wav *.mp3 *.m4a *.aac *.flac *.aiff *.aif *.ogg *.opus "
    "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.wmv *.ts *.m2ts);;All files (*.*)"
)

_AUDIO_CODECS: list[tuple[str, str]] = [
    (AUDIO_CODEC_COPY, "Copy"),
    (AUDIO_CODEC_AAC, "AAC"),
    ("ac3", "AC3"),
    ("pcm_s24le", "PCM 24-bit"),
    ("libmp3lame", "MP3"),
    ("libopus", "Opus"),
]

_CHANNEL_OPTIONS: list[tuple[str, int | None]] = [
    ("Keep original", None),
    ("Mono", 1),
    ("Stereo", 2),
    ("5.1", 6),
]

_SAMPLE_RATE_OPTIONS: list[tuple[str, int | None]] = [
    ("Keep original", None),
    ("44100 Hz", 44100),
    ("48000 Hz", 48000),
    ("96000 Hz", 96000),
]

_BITRATES = ["96k", "128k", "160k", "192k", "256k", "320k", "384k", "448k", "512k"]


class _TargetListWidget(QListWidget):
    """Target list that accepts media files dragged from Finder."""

    files_dropped = None  # replaced with a bound callback by the dialog

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths and callable(self.files_dropped):
            self.files_dropped(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class _TrackPickerDialog(QDialog):
    """Pick one or more audio tracks from a media file."""

    def __init__(self, path: str, tracks: list[AudioTrackInfo], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(trs("Select audio tracks"))
        self.resize(560, 340)
        self._tracks = tracks

        layout = QVBoxLayout(self)
        header = QLabel(Path(path).name)
        header.setWordWrap(True)
        layout.addWidget(header)

        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for track in tracks:
            item = QListWidgetItem(f"{track.audio_index + 1}. {track.short_label()}")
            item.setData(Qt.ItemDataRole.UserRole, track.audio_index)
            self.list_widget.addItem(item)
        if tracks:
            self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_tracks(self) -> list[AudioTrackInfo]:
        rows = sorted({self.list_widget.row(item) for item in self.list_widget.selectedItems()})
        return [self._tracks[row] for row in rows if 0 <= row < len(self._tracks)]


class AudioSwapDialog(QDialog):
    """Per-video audio track assignment dialog."""

    def __init__(
        self,
        targets: list[str],
        *,
        ffmpeg_bin: str = "",
        ffprobe_bin: str = "",
        output_format: str = "mp4",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.jobs: list[dict] = []
        self._targets = list(dict.fromkeys(str(t) for t in targets if t))
        self._ffmpeg_bin = ffmpeg_bin or "ffmpeg"
        self._ffprobe_bin = ffprobe_bin or ""
        self._jobs: dict[str, list[AudioSlot]] = {path: [] for path in self._targets}
        self._probes: dict[str, MediaProbeResult] = {}
        self._durations: dict[str, float] = {}
        self._invalid_targets: list[str] = []
        self._loading = False
        self._default_format = output_format if output_format in ("mp4", "mkv", "mov") else "mp4"

        self.setWindowTitle(trs("Audio swap"))
        self.setMinimumSize(820, 560)
        self.resize(1040, 760)
        self._build_ui()
        self._probe_targets()
        self._populate_targets()
        self._update_summary()
        if self._targets:
            self.targets_list.setCurrentRow(0)

    def exec(self) -> int:
        return exec_with_backdrop(self)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        intro = QLabel(
            trs(
                "Choose the output audio tracks for each video. Drag audio files "
                "onto the target list, or use the buttons to add audio tracks."
            )
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.invalid_label = QLabel("", self)
        self.invalid_label.setWordWrap(True)
        self.invalid_label.setVisible(False)
        root.addWidget(self.invalid_label)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Left: target videos
        left = QGroupBox(trs("Target videos"), splitter)
        left.setMinimumWidth(270)
        left_layout = QVBoxLayout(left)
        self.targets_list = _TargetListWidget(left)
        self.targets_list.setMinimumWidth(230)
        self.targets_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.targets_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.targets_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.targets_list.currentRowChanged.connect(self._on_target_changed)
        self.targets_list.itemSelectionChanged.connect(self._on_target_selection_changed)
        self.targets_list.files_dropped = self._on_files_dropped
        left_layout.addWidget(self.targets_list, 1)
        self.add_to_all_check = QCheckBox(trs("All targets"), left)
        self.add_to_all_check.setToolTip(trs("Apply to all target videos"))
        left_layout.addWidget(self.add_to_all_check)
        splitter.addWidget(left)

        # Right: tracks + track settings
        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        tracks_group = QGroupBox(trs("Output audio tracks"), right)
        tracks_layout = QVBoxLayout(tracks_group)
        self.slots_list = QListWidget(tracks_group)
        self.slots_list.currentRowChanged.connect(self._on_slot_selected)
        tracks_layout.addWidget(self.slots_list, 1)

        track_buttons = QHBoxLayout()
        self.add_audio_button = QPushButton(trs("Add audio..."), tracks_group)
        self.add_original_button = QPushButton(trs("Original track"), tracks_group)
        self.remove_slot_button = QPushButton(trs("Remove"), tracks_group)
        self.move_up_button = QPushButton("▲", tracks_group)
        self.move_up_button.setToolTip(trs("Move up"))
        self.move_down_button = QPushButton("▼", tracks_group)
        self.move_down_button.setToolTip(trs("Move down"))
        self.add_audio_button.clicked.connect(self._add_audio_files)
        self.add_original_button.clicked.connect(self._add_original_tracks)
        self.remove_slot_button.clicked.connect(self._remove_slot)
        self.move_up_button.clicked.connect(lambda: self._move_slot(-1))
        self.move_down_button.clicked.connect(lambda: self._move_slot(1))
        track_buttons.addWidget(self.add_audio_button)
        track_buttons.addWidget(self.add_original_button)
        track_buttons.addStretch(1)
        track_buttons.addWidget(self.remove_slot_button)
        track_buttons.addWidget(self.move_up_button)
        track_buttons.addWidget(self.move_down_button)
        tracks_layout.addLayout(track_buttons)

        settings_group = QGroupBox(trs("Track settings"), right)
        form = QFormLayout(settings_group)
        self.source_label = QLabel("—")
        self.source_label.setWordWrap(True)
        form.addRow(trs("Source"), self.source_label)

        self.codec_combo = QComboBox(settings_group)
        for codec, label in _AUDIO_CODECS:
            self.codec_combo.addItem(trs(label), codec)
        form.addRow(trs("Codec"), self.codec_combo)

        self.bitrate_combo = QComboBox(settings_group)
        self.bitrate_combo.setEditable(True)
        self.bitrate_combo.addItems(_BITRATES)
        form.addRow(trs("Bitrate"), self.bitrate_combo)

        self.channels_combo = QComboBox(settings_group)
        for label, value in _CHANNEL_OPTIONS:
            self.channels_combo.addItem(trs(label), value)
        form.addRow(trs("Channels"), self.channels_combo)

        self.sample_rate_combo = QComboBox(settings_group)
        for label, value in _SAMPLE_RATE_OPTIONS:
            self.sample_rate_combo.addItem(trs(label), value)
        form.addRow(trs("Sample rate"), self.sample_rate_combo)

        self.normalize_check = QCheckBox(trs("Loudness normalization (EBU R128, -18 LUFS)"), settings_group)
        form.addRow("", self.normalize_check)

        self.language_edit = QLineEdit(settings_group)
        self.language_edit.setPlaceholderText("hun")
        form.addRow(trs("Language"), self.language_edit)

        self.title_edit = QLineEdit(settings_group)
        form.addRow(trs("Title"), self.title_edit)

        self.default_check = QCheckBox(trs("Default track"), settings_group)
        form.addRow("", self.default_check)

        right_splitter = QSplitter(Qt.Orientation.Vertical, right)
        right_splitter.addWidget(tracks_group)
        right_splitter.addWidget(settings_group)
        right_splitter.setSizes([300, 320])
        right_layout.addWidget(right_splitter, 1)
        splitter.addWidget(right)
        splitter.setSizes([320, 700])
        root.addWidget(splitter, 1)

        video_group = QGroupBox(trs("Video and output"), self)
        video_layout = QVBoxLayout(video_group)
        video_row = QHBoxLayout()
        self.copy_radio = QRadioButton(trs("Copy video (no re-encode)"), video_group)
        self.convert_radio = QRadioButton(trs("Convert video"), video_group)
        self.copy_radio.setChecked(True)
        self.profile_combo = QComboBox(video_group)
        for key, profile in VIDEO_PROFILES.items():
            if key == VIDEO_PROFILE_COPY:
                continue
            self.profile_combo.addItem(trs(profile.label), key)
        self.profile_combo.setEnabled(False)
        self.copy_radio.toggled.connect(self._on_video_mode_changed)
        video_row.addWidget(self.copy_radio)
        video_row.addWidget(self.convert_radio)
        video_row.addWidget(self.profile_combo, 1)
        video_layout.addLayout(video_row)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel(trs("Output format"), video_group))
        self.format_combo = QComboBox(video_group)
        for fmt in ("mp4", "mkv", "mov"):
            self.format_combo.addItem(fmt, fmt)
        self.format_combo.setCurrentText(self._default_format)
        output_row.addWidget(self.format_combo)
        self.fit_check = QCheckBox(trs("Fit audio to video length"), video_group)
        self.fit_check.setChecked(True)
        output_row.addWidget(self.fit_check)
        self.subtitles_check = QCheckBox(trs("Keep subtitles"), video_group)
        output_row.addWidget(self.subtitles_check)
        output_row.addStretch(1)
        video_layout.addLayout(output_row)

        output_hint = QLabel(
            trs("Output files are written next to the source video using the current naming settings.")
        )
        output_hint.setWordWrap(True)
        video_layout.addWidget(output_hint)
        root.addWidget(video_group)

        footer = QHBoxLayout()
        self.summary_label = QLabel("", self)
        footer.addWidget(self.summary_label, 1)
        cancel_button = QPushButton(trs("Cancel"), self)
        self.add_to_queue_button = QPushButton(trs("Add to queue"), self)
        self.add_to_queue_button.setDefault(True)
        cancel_button.clicked.connect(self.reject)
        self.add_to_queue_button.clicked.connect(self._add_to_queue)
        footer.addWidget(cancel_button)
        footer.addWidget(self.add_to_queue_button)
        root.addLayout(footer)

        for widget in (
            self.codec_combo, self.bitrate_combo, self.channels_combo,
            self.sample_rate_combo, self.normalize_check, self.language_edit,
            self.title_edit, self.default_check,
        ):
            self._connect_slot_widget(widget)

    def _connect_slot_widget(self, widget) -> None:
        if isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self._on_slot_field_changed)
            if widget.isEditable():
                widget.currentTextChanged.connect(self._on_slot_field_changed)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(self._on_slot_field_changed)
        elif isinstance(widget, QCheckBox):
            widget.toggled.connect(self._on_slot_field_changed)

    # ------------------------------------------------------------------ probing

    def _probe_targets(self) -> None:
        if not self._targets:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for path in list(self._targets):
                probe = probe_media(path, self._ffprobe_bin)
                if not probe.has_video:
                    self._invalid_targets.append(Path(path).name)
                    self._targets.remove(path)
                    self._jobs.pop(path, None)
                    continue
                self._probes[path] = probe
                self._durations[path] = float(probe.duration)
        finally:
            QApplication.restoreOverrideCursor()

        if self._invalid_targets:
            self.invalid_label.setText(
                trs("Only video files can be targets. Skipped:")
                + " "
                + ", ".join(self._invalid_targets)
            )
            self.invalid_label.setVisible(True)

    def _populate_targets(self) -> None:
        self._loading = True
        try:
            self.targets_list.clear()
            for path in self._targets:
                probe = self._probes.get(path)
                track_count = len(probe.audio_tracks) if probe is not None else 0
                assigned_count = len(self._jobs.get(path, []))
                item = QListWidgetItem(self._target_label(path, track_count, assigned_count))
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(path)
                if track_count == 0:
                    item.setToolTip(f"{path}\n{trs('No audio track found in the selected file.')}")
                self.targets_list.addItem(item)
        finally:
            self._loading = False

    def _target_label(self, path: str, track_count: int, assigned_count: int) -> str:
        name = Path(path).name
        if assigned_count > 0:
            assigned_text = trs("{var} assigned").replace("{var}", str(assigned_count), 1)
            return f"{name} — {assigned_text}"
        if track_count <= 0:
            return f"{name} — {trs('no audio')}"
        tracks_text = trs("{var} audio track(s)").replace("{var}", str(track_count), 1)
        return f"{name} — {tracks_text}"

    # ------------------------------------------------------------------ target helpers

    def _current_target(self) -> str:
        item = self.targets_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else ""

    def _selected_targets(self) -> list[str]:
        if self.add_to_all_check.isChecked():
            return list(self._targets)
        paths = [str(item.data(Qt.ItemDataRole.UserRole)) for item in self.targets_list.selectedItems()]
        if not paths:
            current = self._current_target()
            if current:
                paths = [current]
        return list(dict.fromkeys(path for path in paths if path))

    def _target_audio_tracks(self, target: str) -> list[AudioTrackInfo]:
        probe = self._probes.get(target)
        if probe is None:
            return []
        return list(probe.audio_tracks)

    def _refresh_target_item(self, target: str) -> None:
        for row in range(self.targets_list.count()):
            item = self.targets_list.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole)) != target:
                continue
            probe = self._probes.get(target)
            track_count = len(probe.audio_tracks) if probe is not None else 0
            assigned_count = len(self._jobs.get(target, []))
            item.setText(self._target_label(target, track_count, assigned_count))
            return

    def _on_target_changed(self, _row: int) -> None:
        self._refresh_slots_list()

    def _on_target_selection_changed(self) -> None:
        has_targets = bool(self._selected_targets())
        self.add_audio_button.setEnabled(has_targets)
        self.add_original_button.setEnabled(has_targets)

    # ------------------------------------------------------------------ slot list

    def _refresh_slots_list(self) -> None:
        target = self._current_target()
        slots = self._jobs.get(target, [])
        previous_row = self.slots_list.currentRow()
        self._loading = True
        try:
            self.slots_list.clear()
            for index, slot in enumerate(slots):
                self.slots_list.addItem(QListWidgetItem(self._slot_label(index, slot)))
        finally:
            self._loading = False

        if slots:
            row = previous_row if 0 <= previous_row < len(slots) else 0
            self.slots_list.setCurrentRow(row)
        else:
            self._on_slot_selected(-1)
        self._update_summary()

    def _slot_label(self, index: int, slot: AudioSlot) -> str:
        name = slot.source_label or Path(slot.source_path).name or "?"
        if slot.is_original:
            name = f"{name} ({trs('Original')})"
        details: list[str] = []
        if slot.codec == AUDIO_CODEC_COPY:
            details.append(trs("Copy"))
            if slot.source_codec:
                details.append(slot.source_codec.upper())
        else:
            details.append(slot.codec.upper())
            if slot.bitrate:
                details.append(slot.bitrate)
        if slot.normalize:
            details.append("R128")
        if slot.language:
            details.append(slot.language)
        if slot.is_default:
            details.append(trs("Default"))
        return f"{index + 1}. {name} · " + " · ".join(details)

    def _on_slot_selected(self, row: int) -> None:
        target = self._current_target()
        slots = self._jobs.get(target, [])
        slot = slots[row] if 0 <= row < len(slots) else None
        self._load_slot_into_form(slot)
        has_slot = slot is not None
        self.remove_slot_button.setEnabled(has_slot)
        self.move_up_button.setEnabled(has_slot and row > 0)
        self.move_down_button.setEnabled(has_slot and row < len(slots) - 1)

    def _load_slot_into_form(self, slot: AudioSlot | None) -> None:
        self._loading = True
        try:
            enabled = slot is not None
            for widget in (
                self.source_label, self.codec_combo, self.bitrate_combo,
                self.channels_combo, self.sample_rate_combo, self.normalize_check,
                self.language_edit, self.title_edit, self.default_check,
            ):
                widget.setEnabled(enabled)
            if slot is None:
                self.source_label.setText("—")
                return

            source = slot.source_label or Path(slot.source_path).name
            if slot.source_codec:
                source = f"{source} · {slot.source_codec.upper()}"
            if slot.is_original:
                source = f"{source} ({trs('Original')})"
            self.source_label.setText(source)
            self._set_combo_data(self.codec_combo, slot.codec)
            self.bitrate_combo.setCurrentText(slot.bitrate or "")
            self._set_combo_data(self.channels_combo, slot.channels)
            self._set_combo_data(self.sample_rate_combo, slot.sample_rate)
            self.normalize_check.setChecked(bool(slot.normalize))
            self.language_edit.setText(slot.language or "")
            self.title_edit.setText(slot.title or "")
            self.default_check.setChecked(bool(slot.is_default))
            self._update_codec_dependent_fields()
        finally:
            self._loading = False

    @staticmethod
    def _set_combo_data(combo: QComboBox, value) -> None:
        if value is None:
            combo.setCurrentIndex(0)
            return
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.isEditable():
            combo.setCurrentText(str(value))

    def _on_slot_field_changed(self, *_args) -> None:
        if self._loading:
            return
        target = self._current_target()
        slots = self._jobs.get(target, [])
        row = self.slots_list.currentRow()
        if not (0 <= row < len(slots)):
            return
        slot = slots[row]

        codec = str(self.codec_combo.currentData() or AUDIO_CODEC_AAC)
        slot.codec = codec
        slot.bitrate = self.bitrate_combo.currentText().strip()
        slot.channels = self.channels_combo.currentData()
        slot.sample_rate = self.sample_rate_combo.currentData()
        slot.normalize = bool(self.normalize_check.isChecked()) and codec != AUDIO_CODEC_COPY
        slot.language = self.language_edit.text().strip()
        slot.title = self.title_edit.text().strip()
        slot.is_default = bool(self.default_check.isChecked())

        if slot.is_default:
            for other_index, other in enumerate(slots):
                if other_index != row:
                    other.is_default = False
        elif slots and not any(other.is_default for other in slots):
            # Keep exactly one default when the last one is unchecked.
            slot.is_default = True
            self.default_check.setChecked(True)

        if codec == AUDIO_CODEC_COPY and self.normalize_check.isChecked():
            self._loading = True
            self.normalize_check.setChecked(False)
            self._loading = False
            slot.normalize = False

        self._update_codec_dependent_fields()
        self.slots_list.item(row).setText(self._slot_label(row, slot))
        self._update_summary()

    def _update_codec_dependent_fields(self) -> None:
        codec = str(self.codec_combo.currentData() or AUDIO_CODEC_AAC)
        is_copy = codec == AUDIO_CODEC_COPY
        self.bitrate_combo.setEnabled(not is_copy)
        self.channels_combo.setEnabled(not is_copy)
        self.sample_rate_combo.setEnabled(not is_copy)
        self.normalize_check.setEnabled(not is_copy)

    # ------------------------------------------------------------------ add/remove

    def _add_audio_files(self) -> None:
        if not self._selected_targets():
            QMessageBox.information(self, trs("Audio swap"), trs("Select at least one video."))
            return
        start_dir = str(settings_manager.get_settings().get("last_open_dir", "") or "")
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            trs("Add audio..."),
            start_dir,
            _AUDIO_FILTER,
        )
        if paths:
            settings_manager.save_settings({"last_open_dir": str(Path(paths[0]).parent)})
            self._add_source_paths(paths)

    def _on_files_dropped(self, paths: list[str]) -> None:
        self._add_source_paths(paths)

    def _add_source_paths(self, paths: list[str]) -> None:
        targets = self._selected_targets()
        if not targets:
            QMessageBox.information(self, trs("Audio swap"), trs("Select at least one video."))
            return

        missing: list[str] = []
        added_any = False
        output_format = self._current_output_format()
        for path in paths:
            probe = probe_media(path, self._ffprobe_bin)
            tracks = list(probe.audio_tracks)
            if not tracks:
                missing.append(Path(path).name)
                continue

            selected = tracks
            if len(tracks) > 1:
                picker = _TrackPickerDialog(path, tracks, self)
                if not picker.exec():
                    continue
                selected = picker.selected_tracks()
            if not selected:
                continue

            for target in targets:
                is_original = Path(target).resolve() == Path(path).resolve()
                for track in selected:
                    default_codec = None
                    if is_original:
                        default_codec = (
                            AUDIO_CODEC_COPY
                            if copy_codec_compatible(track.codec, output_format)
                            else AUDIO_CODEC_AAC
                        )
                    slot = slot_for_track(
                        track,
                        is_original=is_original,
                        default_codec=default_codec,
                    )
                    self._jobs[target].append(slot)
                self._ensure_default_track(target)
                self._refresh_target_item(target)
            added_any = True

        if missing:
            QMessageBox.warning(
                self,
                trs("Audio swap"),
                trs("No audio track found in the selected file.") + "\n" + "\n".join(missing),
            )
        if added_any:
            self._refresh_slots_list()

    def _add_original_tracks(self) -> None:
        targets = self._selected_targets()
        if not targets:
            QMessageBox.information(self, trs("Audio swap"), trs("Select at least one video."))
            return

        missing: list[str] = []
        added_any = False
        output_format = self._current_output_format()
        for target in targets:
            tracks = self._target_audio_tracks(target)
            if not tracks:
                missing.append(Path(target).name)
                continue

            selected = tracks
            if len(tracks) > 1:
                picker = _TrackPickerDialog(target, tracks, self)
                if not picker.exec():
                    continue
                selected = picker.selected_tracks()

            existing = {
                (slot.source_audio_index, bool(slot.is_original))
                for slot in self._jobs.get(target, [])
            }
            for track in selected:
                key = (track.audio_index, True)
                if key in existing:
                    continue
                default_codec = (
                    AUDIO_CODEC_COPY
                    if copy_codec_compatible(track.codec, output_format)
                    else AUDIO_CODEC_AAC
                )
                self._jobs[target].append(
                    slot_for_track(track, is_original=True, default_codec=default_codec)
                )
                existing.add(key)
            self._ensure_default_track(target)
            self._refresh_target_item(target)
            added_any = True

        if missing:
            QMessageBox.warning(
                self,
                trs("Audio swap"),
                trs("The selected video has no audio track.") + "\n" + "\n".join(missing),
            )
        if added_any:
            self._refresh_slots_list()

    def _ensure_default_track(self, target: str) -> None:
        slots = self._jobs.get(target, [])
        if slots and not any(slot.is_default for slot in slots):
            slots[0].is_default = True

    def _remove_slot(self) -> None:
        target = self._current_target()
        slots = self._jobs.get(target, [])
        row = self.slots_list.currentRow()
        if not (0 <= row < len(slots)):
            return
        slots.pop(row)
        self._ensure_default_track(target)
        self._refresh_target_item(target)
        self._refresh_slots_list()

    def _move_slot(self, delta: int) -> None:
        target = self._current_target()
        slots = self._jobs.get(target, [])
        row = self.slots_list.currentRow()
        new_row = row + delta
        if not (0 <= row < len(slots) and 0 <= new_row < len(slots)):
            return
        slots[row], slots[new_row] = slots[new_row], slots[row]
        self._refresh_slots_list()
        self.slots_list.setCurrentRow(new_row)

    # ------------------------------------------------------------------ output

    def _on_video_mode_changed(self, _checked: bool = False) -> None:
        self.profile_combo.setEnabled(self.convert_radio.isChecked())

    def _update_summary(self) -> None:
        total_tracks = sum(len(slots) for slots in self._jobs.values())
        video_count = sum(1 for slots in self._jobs.values() if slots)
        if total_tracks <= 0:
            text = trs("No audio tracks assigned.")
        else:
            text = (
                trs("{var} videos, {var} audio tracks")
                .replace("{var}", str(video_count), 1)
                .replace("{var}", str(total_tracks), 1)
            )
        self.summary_label.setText(text)
        self.add_to_queue_button.setEnabled(total_tracks > 0)

    def _output_suffix(self) -> str | None:
        return settings_manager.get_output_suffix("_audio")

    def _current_output_format(self) -> str:
        return str(self.format_combo.currentData() or self._default_format)

    def _add_to_queue(self) -> None:
        output_format = str(self.format_combo.currentData() or self._default_format)
        video_profile = (
            VIDEO_PROFILE_COPY if self.copy_radio.isChecked()
            else str(self.profile_combo.currentData() or VIDEO_PROFILE_COPY)
        )
        suffix = self._output_suffix()

        jobs: list[AudioSwapJob] = []
        errors: list[str] = []
        for target in self._targets:
            slots = self._jobs.get(target, [])
            if not slots:
                continue
            output_path = compute_output_path_with_suffix(target, output_format, suffix)
            if Path(output_path).resolve() == Path(target).resolve():
                output_path = str(
                    Path(target).with_name(f"{Path(target).stem}_audio.{output_format}")
                )
            job = AudioSwapJob(
                target_path=target,
                output_path=output_path,
                slots=slots,
                video_profile=video_profile,
                keep_subtitles=self.subtitles_check.isChecked(),
                fit_duration=self.fit_check.isChecked(),
                target_duration=self._durations.get(target, 0.0),
                output_format=output_format,
                ffmpeg_bin=self._ffmpeg_bin,
            )
            error = validate_audio_swap_job(job)
            if error:
                errors.append(f"{Path(target).name}: {trs(error)}")
            else:
                jobs.append(job)

        if errors:
            QMessageBox.warning(self, trs("Audio swap"), "\n".join(errors))
            return
        if not jobs:
            QMessageBox.information(self, trs("Audio swap"), trs("No audio tracks assigned."))
            return

        output_paths = [job.output_path for job in jobs]
        if len(set(output_paths)) != len(output_paths):
            QMessageBox.warning(self, trs("Audio swap"), trs("Two jobs would write the same output file."))
            return

        built: list[dict] = []
        for job in jobs:
            try:
                command = build_audio_swap_command(job)
            except Exception as exc:
                QMessageBox.warning(self, trs("Audio swap"), str(exc))
                return
            built.append(
                {
                    "label": Path(job.target_path).name,
                    "input_path": job.target_path,
                    "output_path": job.output_path,
                    "command": command,
                    "duration_seconds": job.target_duration,
                }
            )

        self.jobs = built
        self.accept()
