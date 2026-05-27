#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Visual FFmpeg parameter editor dialog."""

from __future__ import annotations

import shlex

from pathlib import Path

from PySide6.QtCore import QFile, QObject, Qt, QUrl, Signal, QEvent, QTimer
from PySide6.QtGui import QDesktopServices, QPalette
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication,
    QAbstractScrollArea,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.gui_qt.dialogs._modal_backdrop import exec_with_backdrop

from app.domain.ffmpeg_params import PARAM_SECTIONS, refresh_param_descriptions
from app.domain import cmd_macros
from app.shared.utils.theme import get_accent, is_dark_mode
from app.shared.i18n import get_language, trs


def _sys_accent() -> tuple[str, int, int, int]:
    """Return (hex, r, g, b) of the vivid system accent colour."""
    return get_accent()


def _quote_if_needed(s: str) -> str:
    return cmd_macros.quote_if_needed(s)


class _ComboBoxWheelGuard(QObject):
    """Block accidental wheel value changes but keep parent scrolling working."""

    def eventFilter(self, watched, event):  # type: ignore[override]
        if isinstance(watched, QComboBox) and event.type() == QEvent.Type.Wheel:
            if watched.view().isVisible():
                return super().eventFilter(watched, event)

            parent = watched.parentWidget()
            while parent is not None and not isinstance(parent, QAbstractScrollArea):
                parent = parent.parentWidget()
            if isinstance(parent, QAbstractScrollArea):
                QApplication.sendEvent(parent.viewport(), event)
                return True

            event.accept()
            return True
        return super().eventFilter(watched, event)


# ---------------------------------------------------------------------------
# Per-parameter FFmpeg documentation URLs → trac.ffmpeg.org wiki
# ---------------------------------------------------------------------------
_TRAC = "https://trac.ffmpeg.org/wiki"
_DOC_URLS: dict[str, str] = {
    # ── Seeking / trimming ────────────────────────────────────────────────
    "-ss":            _TRAC + "/Seeking#Seekingwithssinput",
    "-to":            _TRAC + "/Seeking#Seekingwithssinput",
    "-t":             _TRAC + "/Seeking#Seekingwithssinput",
    "-itsoffset":     _TRAC + "/Seeking",
    # ── H.264 encoding ────────────────────────────────────────────────────
    "-c:v":           _TRAC + "/Encode/H.264",
    "-crf":           _TRAC + "/Encode/H.264#crf",
    "-preset":        _TRAC + "/Encode/H.264#Preset",
    "-profile:v":     _TRAC + "/Encode/H.264#Profile",
    "-refs":          _TRAC + "/Encode/H.264#Compatibility",
    "-bf":            _TRAC + "/Encode/H.264#Compatibility",
    "-tune":          _TRAC + "/Encode/H.264#Tune",
    "-g":             _TRAC + "/Encode/H.264",
    "-level":         _TRAC + "/Encode/H.264#Compatibility",
    "-pass":          _TRAC + "/Encode/H.264#Two-Passencoding",
    # ── Bitrate / quality control ─────────────────────────────────────────
    "-b:v":           _TRAC + "/Encode/H.264#ConstrainedEncoding",
    "-maxrate":       _TRAC + "/Encode/H.264#ConstrainedEncoding",
    "-minrate":       _TRAC + "/Encode/H.264#ConstrainedEncoding",
    "-bufsize":       _TRAC + "/Encode/H.264#ConstrainedEncoding",
    "-qscale:v":      _TRAC + "/Encode/H.264",
    # ── Audio ─────────────────────────────────────────────────────────────
    "-c:a":           _TRAC + "/Encode/HighQualityAudio",
    "-b:a":           _TRAC + "/Encode/HighQualityAudio#Bitrate",
    "-ar":            _TRAC + "/Encode/HighQualityAudio",
    "-q:a":           _TRAC + "/Encode/HighQualityAudio",
    "-profile:a":     _TRAC + "/Encode/HighQualityAudio",
    "-ac":            _TRAC + "/AudioChannelManipulation",
    "-sample_fmt":    _TRAC + "/AudioChannelManipulation",
    "-vol":           _TRAC + "/AudioVolume",
    "-af":            _TRAC + "/FilteringGuide#Filteringtutorial",
    "-c:s":           _TRAC + "/SubtitleEncoding",
    # ── Video filters / scaling / framerate ──────────────────────────────
    "-vf":            _TRAC + "/FilteringGuide#Filteringtutorial",
    "-r":             _TRAC + "/ChangingFrameRate",
    "-s":             _TRAC + "/Scaling#Options",
    # ── Hardware acceleration ─────────────────────────────────────────────
    "-hwaccel":       _TRAC + "/HWAccelIntro",
    # ── Stream mapping ────────────────────────────────────────────────────
    "-map":           _TRAC + "/Map",
    "-map_metadata":  _TRAC + "/Map",
    # ── Metadata ─────────────────────────────────────────────────────────
    "-metadata":      _TRAC + "/AddingMetadata",
    # ── HDR / colour ─────────────────────────────────────────────────────
    "-color_range":            _TRAC + "/HDR#MasteringMetadata",
    "-color_primaries":        _TRAC + "/HDR#MasteringMetadata",
    "-color_trc":              _TRAC + "/HDR#MasteringMetadata",
    "-colorspace":             _TRAC + "/HDR#MasteringMetadata",
    "-chroma_sample_location": _TRAC + "/HDR#MasteringMetadata",
    "-master_display":         _TRAC + "/HDR#MasteringMetadata",
    "-max_cll":                _TRAC + "/HDR#ContentLightLevel",
}


def _doc_url_for(key: str) -> str:
    """Return the most specific trac.ffmpeg.org wiki URL for the given option key."""
    return _DOC_URLS.get(key, _TRAC)


def _desc_to_html(text: str) -> str:
    """Convert structured FFmpeg parameter description to HTML for QTextBrowser.

    Handles:
      - ALL-CAPS section headers ending with ':' → bold styled paragraph
      - Lines starting with whitespace → <pre> block (monospace, preserves alignment)
      - Regular paragraph lines → <p> with word-wrap, adjacent lines joined
    """
    import html as _hl

    def _is_header(s: str) -> bool:
        if not s.endswith(":") or len(s) > 80:
            return False
        alpha = [c for c in s if c.isalpha()]
        return bool(alpha) and sum(1 for c in alpha if c.isupper()) / len(alpha) >= 0.75

    lines = text.split("\n")
    out: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Blank line → small spacer
        if not stripped:
            out.append('<p style="margin:0;font-size:4pt;line-height:100%;"> </p>')
            i += 1
            continue

        # Section header (e.g. "FORMÁTUM:", "AJÁNLOTT ÉRTÉKEK:")
        if _is_header(stripped):
            out.append(
                '<p style="margin:10px 0 2px 0;font-size:10pt;font-weight:bold;'
                'letter-spacing:0.4px;color:rgba(190,205,220,0.9);">'
                f"{_hl.escape(stripped)}</p>"
            )
            i += 1
            continue

        # Indented block (table rows / code examples) → monospace <pre>
        if line and line[0] in (" ", "\t"):
            block: list[str] = []
            while i < len(lines) and lines[i] and lines[i][0] in (" ", "\t"):
                block.append(lines[i].rstrip())
                i += 1
            raw = _hl.escape("\n".join(block))
            out.append(
                '<pre style="margin:2px 0 2px 2px;padding:0;'
                "font-family:Menlo,Consolas,'Courier New',monospace;"
                'font-size:10.5pt;background:transparent;white-space:pre;">'
                f"{raw}</pre>"
            )
            continue

        # Regular paragraph – collect adjacent non-special lines, join with space
        para: list[str] = []
        while i < len(lines):
            ln = lines[i]
            s = ln.strip()
            if not s or (ln and ln[0] in (" ", "\t")) or _is_header(s):
                break
            para.append(_hl.escape(s))
            i += 1
        out.append(
            '<p style="margin:2px 0 3px 0;font-size:12pt;">'
            f'{" ".join(para)}</p>'
        )

    return "".join(out)


class _ParamHelpDialog(QDialog):
    """Styled FFmpeg parameter help with clickable examples and a manual link."""

    def __init__(
        self,
        key: str,
        desc: str,
        examples: list[str],
        editor: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(key)
        self.setMinimumWidth(420)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._editor = editor

        self.setMinimumWidth(460)
        self.setMaximumHeight(540)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(8)

        # ── Header (pinned, always visible) ───────────────────────────────
        key_lbl = QLabel(key)
        _ah, _ar, _ag, _ab = _sys_accent()
        key_lbl.setStyleSheet(
            f"font-size: 26px; font-weight: bold; color: {_ah}; letter-spacing: 1px;"
        )
        outer.addWidget(key_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(128,128,128,0.25);")
        outer.addWidget(sep)

        # ── Scrollable body (description + example chips) ─────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body_w = QWidget()
        body_layout = QVBoxLayout(body_w)
        body_layout.setContentsMargins(0, 4, 4, 4)
        body_layout.setSpacing(8)

        if desc:
            desc_browser = QTextBrowser()
            desc_browser.setFrameShape(QFrame.Shape.NoFrame)
            desc_browser.setOpenExternalLinks(False)
            desc_browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            desc_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            desc_browser.setHtml(_desc_to_html(desc))
            desc_browser.setStyleSheet(
                "QTextBrowser { background: transparent; border: none; }"
            )
            # Make the rendered document area transparent too (palette Base).
            from PySide6.QtGui import QPalette as _QPalette
            _pal = desc_browser.palette()
            _pal.setColor(_QPalette.ColorRole.Base, Qt.GlobalColor.transparent)
            desc_browser.setPalette(_pal)
            # Size the browser to its full document height so the parent
            # scroll area handles scrolling instead of the browser itself.
            desc_browser.document().setTextWidth(420)
            _dh = int(desc_browser.document().size().height())
            desc_browser.setFixedHeight(_dh + 6)
            body_layout.addWidget(desc_browser)

        if examples:
            ex_hdr = QLabel(trs("Examples – click to insert:"))
            ex_hdr.setStyleSheet(
                "font-size: 11pt; color: rgba(150,160,175,0.85); margin-top: 4px;"
            )
            body_layout.addWidget(ex_hdr)

            chips_w = QWidget()
            chips_layout = QHBoxLayout(chips_w)
            chips_layout.setContentsMargins(0, 0, 0, 0)
            chips_layout.setSpacing(6)
            for ex_val in examples:
                btn = QPushButton(ex_val)
                _ah, _ar, _ag, _ab = _sys_accent()
                btn.setStyleSheet(
                    "QPushButton {"
                    "  font-size: 11pt;"
                    "  padding: 3px 12px; border-radius: 10px;"
                    f"  background: rgba({_ar},{_ag},{_ab},0.14); color: {_ah};"
                    f"  border: 1px solid rgba({_ar},{_ag},{_ab},0.30);"
                    "}"
                    f"QPushButton:hover {{ background: rgba({_ar},{_ag},{_ab},0.30); }}"
                    f"QPushButton:pressed {{ background: rgba({_ar},{_ag},{_ab},0.45); }}"
                )
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(
                    lambda _ch=False, v=ex_val: self._fill_and_close(v)
                )
                chips_layout.addWidget(btn)
            chips_layout.addStretch(1)
            body_layout.addWidget(chips_w)

        if not desc and not examples:
            no_desc = QLabel(trs("No description available for this parameter."))
            no_desc.setStyleSheet(
                "font-size: 11pt; color: rgba(160,170,185,0.6); font-style: italic;"
            )
            no_desc.setWordWrap(True)
            body_layout.addWidget(no_desc)

        body_layout.addStretch(1)
        scroll.setWidget(body_w)
        outer.addWidget(scroll, 1)

        # ── Footer: docs link (pinned, always visible) ────────────────────
        outer.addSpacing(4)
        footer = QHBoxLayout()
        docs_btn = QPushButton(trs("📖  Open FFmpeg Wiki"))
        docs_btn.setStyleSheet(
            "QPushButton {"
            "  font-size: 11pt; padding: 5px 14px; border-radius: 8px;"
            "  background: transparent; border: 1px solid rgba(128,128,128,0.25);"
            "  color: rgba(160,170,185,0.9);"
            "}"
            "QPushButton:hover { background: rgba(128,128,128,0.10); }"
        )
        docs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _url = _doc_url_for(key)
        docs_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(_url))
        )
        footer.addStretch(1)
        footer.addWidget(docs_btn)
        outer.addLayout(footer)

    def _fill_and_close(self, value: str) -> None:
        if self._editor is not None:
            if hasattr(self._editor, "setText"):
                self._editor.setText(value)  # type: ignore[attr-defined]
            elif hasattr(self._editor, "setCurrentText"):
                self._editor.setCurrentText(value)  # type: ignore[attr-defined]
        self.accept()


class VisualEditorWidget(QWidget):
    """Self-contained visual FFmpeg parameter editor widget.

    Can be embedded directly into any layout.  Emits ``command_changed``
    whenever the generated FFmpeg command changes.
    """

    command_changed = Signal(str)

    def __init__(
        self,
        input_path: str = "",
        output_path: str = "",
        output_format: str = "mp4",
        initial_command: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._input_path = input_path
        self._output_path = output_path
        self._output_format = output_format
        self._combo_wheel_guard = _ComboBoxWheelGuard(self)

        # Keep parameter descriptions in sync with current UI language.
        refresh_param_descriptions(get_language())

        self._param_enabled: dict[str, QCheckBox] = {}
        self._param_inputs: dict[str, QWidget] = {}
        self._param_types: dict[str, str] = {}
        self._param_indicators: dict[str, QFrame] = {}
        self._param_badges: dict[str, QLabel] = {}
        self._param_help_buttons: dict[str, QPushButton] = {}
        self._active_help_dlg: QDialog | None = None

        self._build_ui()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        if initial_command.strip():
            self.apply_command(initial_command)

    @staticmethod
    def _param_display_name(param: dict) -> str:
        """Return a compact, human-readable parameter name for row labels."""
        label = str(param.get("label", "")).strip()
        if label:
            return label

        desc = str(param.get("desc", ""))
        first_line = ""
        for line in desc.splitlines():
            line = line.strip()
            if line:
                first_line = line
                break

        if first_line:
            for sep in (" — ", " - "):
                if sep in first_line:
                    first_line = first_line.split(sep, 1)[0].strip()
                    break
            return first_line[:48].rstrip()

        return str(param.get("key", "")).strip()

    def set_paths(
        self,
        input_path: str,
        output_path: str,
        output_format: str = "mp4",
    ) -> None:
        """Update the paths used when building the command."""
        self._input_path = input_path
        self._output_path = output_path
        self._output_format = output_format
        self._refresh_preview()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        _ui_path = Path(__file__).parent.parent / "ui" / "visual_editor_dialog.ui"
        loader = QUiLoader()
        f = QFile(str(_ui_path))
        f.open(QFile.ReadOnly)
        w = loader.load(f, self)
        f.close()
        w.setStyleSheet("")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)

        self._preview = w.findChild(QPlainTextEdit, "previewTextEdit")
        button_box = w.findChild(QDialogButtonBox, "buttonBox")
        button_box.hide()

        container = w.findChild(QWidget, "paramsContainer")
        container_layout = container.layout()

        # Global column width for key badge column.
        key_col_width = 0
        metrics = self.fontMetrics()
        for section in PARAM_SECTIONS:
            for param in section["params"]:
                key_col_width = max(key_col_width, metrics.horizontalAdvance(param["key"]))
        key_col_width += 16

        self._editor_row_height = max(28, self.fontMetrics().height() + 10)

        for section in PARAM_SECTIONS:
            group = QGroupBox(trs(section["title"]))
            grid = QGridLayout(group)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(2)
            grid.setContentsMargins(4, 10, 4, 4)
            grid.setColumnMinimumWidth(2, key_col_width)
            grid.setColumnStretch(1, 0)  # checkbox column (narrow)
            grid.setColumnStretch(2, 0)  # key badge column
            grid.setColumnStretch(3, 1)  # editor column (flexible)
            for row_idx, param in enumerate(section["params"]):
                enabled, editor = self._add_param_to_grid(param, grid, row_idx)
                key = param["key"]
                self._param_enabled[key] = enabled
                self._param_inputs[key] = editor
                self._param_types[key] = param["type"]
            container_layout.addWidget(group)

        container_layout.addStretch(1)

        # Prevent accidental parameter changes from wheel scrolling.
        for combo in self.findChildren(QComboBox):
            combo.installEventFilter(self._combo_wheel_guard)

        self._apply_dynamic_colors()
        self._refresh_preview()

    def _add_param_to_grid(self, param: dict, grid: QGridLayout, row: int) -> tuple:
        """Add one parameter row into a QGridLayout for proper column alignment."""
        key = param["key"]
        ptype = param["type"]
        is_enabled = bool(param.get("enabled_default", False))

        # Col 0: accent indicator bar
        _ah, _ar, _ag, _ab = _sys_accent()
        _on = f"QFrame#rowIndicator {{ background: {_ah}; border-radius: 1px; }}"
        _off = "QFrame#rowIndicator { background: transparent; }"
        indicator = QFrame()
        indicator.setObjectName("rowIndicator")
        indicator.setFixedWidth(3)
        indicator.setStyleSheet(_on if is_enabled else _off)
        self._param_indicators[key] = indicator
        grid.addWidget(indicator, row, 0, Qt.AlignmentFlag.AlignVCenter)

        # Col 1: enable/disable checkbox (no text)
        enabled = QCheckBox(self._param_display_name(param))
        enabled.setChecked(is_enabled)
        enabled.setToolTip(key)
        grid.addWidget(enabled, row, 1, Qt.AlignmentFlag.AlignVCenter)

        # Col 2: monospace key badge
        badge = QLabel(key)
        _ah, _ar, _ag, _ab = _sys_accent()
        badge.setStyleSheet(
            "QLabel { font-size: 11pt; "
            f"color: {_ah}; background: rgba({_ar},{_ag},{_ab},0.12); "
            "border-radius: 3px; padding: 0px 4px; }"
        )
        badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._param_badges[key] = badge
        grid.addWidget(
            badge,
            row,
            2,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        # Col 3: editor widget
        editor = None
        if ptype == "combo":
            _cb = QComboBox()
            _cb.addItems(list(param.get("options", [])))
            _cb.setCurrentText(str(param.get("default", "")))
            _cb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            _cb.setMinimumHeight(getattr(self, "_editor_row_height", 28))
            _cb.installEventFilter(self._combo_wheel_guard)
            _cb.currentTextChanged.connect(self._refresh_preview)
            _cb.currentTextChanged.connect(lambda _t, chk=enabled: chk.setChecked(True))
            grid.addWidget(_cb, row, 3)
            editor = _cb
        elif ptype == "entry":
            _le = QLineEdit(str(param.get("default", "")))
            _le.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            _le.setMinimumHeight(getattr(self, "_editor_row_height", 28))
            _ph = str(param.get("placeholder", "")).strip()
            if _ph:
                _le.setPlaceholderText(_ph)
            _le.textChanged.connect(self._refresh_preview)
            _le.textChanged.connect(lambda _t, chk=enabled: chk.setChecked(True))
            grid.addWidget(_le, row, 3)
            editor = _le
        else:
            _sp = QWidget()
            _sp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            grid.addWidget(_sp, row, 3)

        # Col 4: help button (always shown)
        _hb = QPushButton("?")
        _hb.setFixedSize(24, 24)
        _hb.setToolTip(trs("Help and FFmpeg documentation"))
        _ah, _ar, _ag, _ab = _sys_accent()
        _hb.setStyleSheet(
            "QPushButton {"
            "  padding: 0px; margin: 0px;"
            "  border-radius: 12px;"
            f"  background: rgba({_ar},{_ag},{_ab},0.14);"
            f"  color: {_ah};"
            f"  border: 1px solid rgba({_ar},{_ag},{_ab},0.35);"
            "  font-weight: bold;"
            "  font-size: 12pt;"
            "}"
            f"QPushButton:hover {{ background: rgba({_ar},{_ag},{_ab},0.28); }}"
            f"QPushButton:pressed {{ background: rgba({_ar},{_ag},{_ab},0.45); }}"
        )
        _hb.clicked.connect(
            lambda _ch=False, p=param, e=editor: self._show_help(p, e)
        )
        self._param_help_buttons[key] = _hb
        grid.addWidget(_hb, row, 4, Qt.AlignmentFlag.AlignVCenter)

        def _toggle(state: int, bar=indicator, on=_on, off=_off) -> None:
            bar.setStyleSheet(on if bool(state) else off)

        enabled.stateChanged.connect(self._refresh_preview)
        enabled.stateChanged.connect(_toggle)
        enabled.stateChanged.connect(self._apply_dynamic_colors)
        return enabled, editor

    def _apply_dynamic_colors(self, *_args) -> None:
        """Refresh accent-coloured controls when system appearance/accent changes."""
        _ah, _ar, _ag, _ab = _sys_accent()
        indicator_on = f"QFrame#rowIndicator {{ background: {_ah}; border-radius: 1px; }}"
        indicator_off = "QFrame#rowIndicator { background: transparent; }"
        checkbox_text = "#f2f6ff" if is_dark_mode() else "#1b1f24"
        checkbox_border = "rgba(255,255,255,0.92)" if is_dark_mode() else "rgba(35,35,35,0.72)"

        for key, indicator in self._param_indicators.items():
            box = self._param_enabled.get(key)
            indicator.setStyleSheet(indicator_on if (box and box.isChecked()) else indicator_off)

        checkbox_style = (
            f"QCheckBox {{ color: {checkbox_text}; }}"
            "QCheckBox::indicator {"
            "  width: 14px;"
            "  height: 14px;"
            "  border-radius: 3px;"
            f"  border: 1px solid {checkbox_border};"
            "  background: transparent;"
            "}"
            "QCheckBox::indicator:unchecked:hover {"
            "  background: rgba(255,255,255,0.08);"
            "}"
            "QCheckBox::indicator:checked {"
            f"  background: {_ah};"
            f"  border: 1px solid {_ah};"
            "}"
        )
        for checkbox in self._param_enabled.values():
            checkbox.setStyleSheet(checkbox_style)

        badge_fg = "#f5f9ff" if is_dark_mode() else "#1b1f24"
        badge_style = (
            "QLabel { font-size: 11pt; "
            f"color: {badge_fg}; "
            f"background: rgba({_ar},{_ag},{_ab},0.26); "
            f"border: 1px solid rgba({_ar},{_ag},{_ab},0.75); "
            "border-radius: 3px; padding: 1px 5px; }"
        )
        for badge in self._param_badges.values():
            badge.setStyleSheet(badge_style)

        help_style = (
            "QPushButton {"
            "  padding: 0px; margin: 0px;"
            "  border-radius: 12px;"
            f"  background: rgba({_ar},{_ag},{_ab},0.24);"
            f"  color: {badge_fg};"
            f"  border: 1px solid rgba({_ar},{_ag},{_ab},0.85);"
            "  font-weight: bold;"
            "  font-size: 12pt;"
            "}"
            f"QPushButton:hover {{ background: rgba({_ar},{_ag},{_ab},0.36); }}"
            f"QPushButton:pressed {{ background: rgba({_ar},{_ag},{_ab},0.50); }}"
        )
        for help_btn in self._param_help_buttons.values():
            help_btn.setStyleSheet(help_style)

    def _on_system_theme_changed(self) -> None:
        from app.shared.utils.theme import init_accent, invalidate_cache

        app = QApplication.instance()
        if app is None:
            return
        init_accent(app.palette().color(QPalette.ColorRole.Highlight))
        invalidate_cache()
        self._apply_dynamic_colors()

    def eventFilter(self, watched, event):
        app = QApplication.instance()
        if watched is app and event.type() in {
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.ThemeChange,
        }:
            QTimer.singleShot(0, self._on_system_theme_changed)
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def apply_command(self, cmd: str) -> None:
        """Pre-fill widgets by parsing an existing FFmpeg command string."""
        try:
            tokens = shlex.split(cmd)
        except ValueError:
            tokens = cmd.split()

        # Start clean: uncheck everything
        for box in self._param_enabled.values():
            box.setChecked(False)

        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in ("ffmpeg", "{input}", "{output}"):
                i += 1
                continue
            if token == "-i":
                i += 2  # skip -i and its argument
                continue

            if token in self._param_enabled:
                ptype = self._param_types.get(token)
                self._param_enabled[token].setChecked(True)
                if ptype in ("combo", "entry") and i + 1 < len(tokens):
                    value = tokens[i + 1]
                    widget = self._param_inputs.get(token)
                    if widget is not None:
                        if ptype == "combo":
                            widget.setCurrentText(value)  # type: ignore[attr-defined]
                        else:
                            widget.setText(value)  # type: ignore[attr-defined]
                    i += 2
                    continue

            i += 1

        self._refresh_preview()

    def _show_help(self, param: dict, editor: QWidget | None) -> None:
        dlg = _ParamHelpDialog(
            key=str(param["key"]),
            desc=str(param.get("desc", "")),
            examples=list(param.get("examples", [])),
            editor=editor,
            parent=self.parentWidget() or self,
        )
        self._active_help_dlg = dlg
        exec_with_backdrop(dlg)
        self._active_help_dlg = None

    def _is_on(self, key: str) -> bool:
        box = self._param_enabled.get(key)
        return bool(box and box.isChecked())

    def _get_param_value(self, key: str) -> str:
        widget = self._param_inputs.get(key)
        ptype = self._param_types.get(key)
        if widget is None:
            return ""
        if ptype == "combo":
            return str(widget.currentText()).strip()  # type: ignore[attr-defined]
        if ptype == "entry":
            return str(widget.text()).strip()  # type: ignore[attr-defined]
        return ""

    # ------------------------------------------------------------------
    # Command building
    # ------------------------------------------------------------------

    def build_command(self) -> str:
        parts: list[str] = ["ffmpeg"]

        if self._is_on("-y"):
            parts.append("-y")

        if self._is_on("-hwaccel") and (v := self._get_param_value("-hwaccel")):
            parts += ["-hwaccel", v]

        if self._is_on("-re"):
            parts.append("-re")

        if self._is_on("-stream_loop") and (v := self._get_param_value("-stream_loop")):
            parts += ["-stream_loop", v]

        if self._is_on("-itsoffset") and (v := self._get_param_value("-itsoffset")):
            parts += ["-itsoffset", _quote_if_needed(v)]

        for key in ("-ss", "-to", "-t"):
            if self._is_on(key) and (v := self._get_param_value(key)):
                parts += [key, _quote_if_needed(v)]

        parts += ["-i", _quote_if_needed(self._input_path or "{input}")]

        _pre_input = {"-y", "-hwaccel", "-re", "-stream_loop", "-itsoffset", "-ss", "-to", "-t"}
        for section in PARAM_SECTIONS:
            for param in section["params"]:
                key = param["key"]
                if key in _pre_input:
                    continue
                if not self._is_on(key):
                    continue
                if param["type"] == "flag":
                    parts.append(key)
                else:
                    value = self._get_param_value(key)
                    if value:
                        parts += [key, _quote_if_needed(value)]

        fmt = self._output_format or "mp4"
        parts.append(_quote_if_needed(self._output_path or f"{{output}}.{fmt}"))
        return " ".join(parts)

    def _refresh_preview(self) -> None:
        cmd = self.build_command()
        self._preview.setPlainText(cmd)
        self.command_changed.emit(cmd)

    def get_command(self) -> str:
        """Return the currently built FFmpeg command."""
        return self.build_command()


class VisualEditorDialog(QDialog):
    """Dialog wrapper around :class:`VisualEditorWidget`."""

    def __init__(
        self,
        input_path: str = "",
        output_path: str = "",
        output_format: str = "mp4",
        initial_command: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        from app.shared.i18n import get_language
        refresh_param_descriptions(get_language())
        self.setWindowTitle(trs("Visual editor"))
        self.resize(900, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 10)
        layout.setSpacing(6)

        self._widget = VisualEditorWidget(
            input_path=input_path,
            output_path=output_path,
            output_format=output_format,
            initial_command=initial_command,
            parent=self,
        )
        layout.addWidget(self._widget)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_command(self) -> str:
        """Return the built FFmpeg command from the embedded widget."""
        return self._widget.get_command()
