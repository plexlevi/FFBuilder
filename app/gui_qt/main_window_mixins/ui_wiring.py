"""UI widget lookup and signal wiring extracted from MainWindow."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QAbstractScrollArea,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from app.gui_qt.main_window_parts import _CategoryDropFilter, _install_splitter_dots
from app.shared import settings as settings_manager
from app.shared.i18n import trs


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


class UiWiringMixin:
    def _w(self, cls, name: str):
        widget = self.findChild(cls, name)
        if widget is None:
            raise RuntimeError(f"Missing widget: {name}")
        return widget

    def _build_conversion_tab(self) -> None:
        """Create the first tab: files/metadata + compact preset selector + output."""
        self.conversion_tab = QWidget()
        self.conversion_tab.setObjectName("conversionTab")
        conversion_layout = QHBoxLayout(self.conversion_tab)
        conversion_layout.setContentsMargins(0, 0, 0, 0)
        conversion_layout.setSpacing(0)

        self.conversion_splitter = QSplitter(Qt.Orientation.Horizontal, self.conversion_tab)
        self.conversion_splitter.setObjectName("conversionSplitter")
        conversion_layout.addWidget(self.conversion_splitter)

        # Move the existing file + metadata pane into the conversion tab.
        self._ui.leftPaneWidget.setParent(self.conversion_tab)
        self.conversion_splitter.addWidget(self._ui.leftPaneWidget)

        right_panel = QWidget(self.conversion_splitter)
        right_panel.setObjectName("conversionRightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        preset_group = QGroupBox(trs("Preset"), right_panel)
        preset_layout = QVBoxLayout(preset_group)
        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox(preset_group)
        self.preset_combo.setObjectName("presetComboBox")
        self.preset_combo.setMinimumContentsLength(18)
        self.preset_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.preset_combo.view().setMinimumWidth(420)
        self.load_preset_button = QPushButton(trs("Load preset"), preset_group)
        self.load_preset_button.setObjectName("loadPresetButton")
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(self.load_preset_button)
        preset_layout.addLayout(preset_row)

        self.conversion_preset_desc = QLabel("", preset_group)
        self.conversion_preset_desc.setWordWrap(True)
        preset_layout.addWidget(self.conversion_preset_desc)
        right_layout.addWidget(preset_group)

        # The output settings belong to the conversion workflow, not to template management.
        self._ui.verticalLayout_5.removeWidget(self._ui.outputGroupBox)
        self._ui.outputGroupBox.setParent(right_panel)
        right_layout.addWidget(self._ui.outputGroupBox)
        right_layout.addStretch(1)

        self.conversion_splitter.addWidget(right_panel)
        self.conversion_splitter.setSizes([480, 420])

        self.builder_tabs.insertTab(0, self.conversion_tab, trs("Conversion"))
        self.builder_tabs.setCurrentIndex(0)

        self.preset_combo.currentIndexChanged.connect(self._on_preset_combo_changed)
        self.preset_combo.activated.connect(lambda _idx: self._load_selected_preset())
        self.load_preset_button.clicked.connect(self._load_selected_preset)

        # File metadata should be readable; the template list can be a bit smaller.
        template_font = QFont("Tuffy", 12)
        self.categories_list.setFont(template_font)
        self.templates_list.setFont(template_font)
        self.files_list_widget.setFont(QFont("Tuffy", 12))
        self.metadata_tree.setFont(QFont("Tuffy", 12))
        self.files_meta_splitter.setSizes([200, 320])

    def _update_conversion_panel_visibility(self, index: int | None = None) -> None:
        """Show the command preview/status bar only on the Conversion tab."""
        if index is None:
            index = self.builder_tabs.currentIndex()
        conversion_index = self.builder_tabs.indexOf(self.conversion_tab)
        is_conversion = index == conversion_index

        preview = self._ui.bottomPreviewWidget
        if is_conversion:
            if not preview.isVisible():
                preview.setVisible(True)
                sizes = getattr(self, "_bottom_preview_sizes", None)
                if sizes:
                    self.main_v_splitter.setSizes(sizes)
            self._ui.statusbar.setVisible(True)
            self._apply_console_visibility()
            return

        if preview.isVisible():
            self._bottom_preview_sizes = self.main_v_splitter.sizes()
        preview.setVisible(False)
        self._ui.statusbar.setVisible(False)
        if hasattr(self, "ffmpeg_console"):
            self.ffmpeg_console.setVisible(False)

    def _wire_widgets(self) -> None:
        self.hardware_status_label = self._w(QLabel, "hardwareStatusLabel")
        self.settings_button = self._w(QPushButton, "settingsButton")
        self.browse_files_button = self._w(QPushButton, "browseFilesButton")
        self.clear_files_button = self._w(QPushButton, "clearFilesButton")
        self.files_list_widget = self._w(QListWidget, "filesListWidget")
        self.metadata_tree = self._w(QTreeWidget, "metadataTreeWidget")
        self.files_status_label = self._w(QLabel, "statusFilesLabel")
        self.loudness_progress_bar = self._w(QProgressBar, "statusEbuProgressBar")

        self.output_format_combo = self._w(QComboBox, "outputFormatComboBox")
        self.format_desc_label = self._w(QLabel, "formatDescriptionLabel")
        self.output_path_line = self._w(QLineEdit, "outputPathLineEdit")
        self.browse_output_button = self._w(QPushButton, "browseOutputButton")

        self.builder_tabs = self._w(QTabWidget, "builderTabWidget")
        self.main_h_splitter = self._w(QSplitter, "mainHSplitter")
        self.main_v_splitter = self._w(QSplitter, "mainVSplitter")
        self.files_meta_splitter = self._w(QSplitter, "filesMetaSplitter")
        self.templates_details_splitter = self._w(QSplitter, "templatesDetailsSplitter")
        self.templates_list = self._w(QListWidget, "templatesListWidget")
        self.template_desc_label = self._w(QLabel, "templateDescriptionLabel")
        self.new_template_button = self._w(QPushButton, "newTemplateButton")

        self.cat_template_splitter = self._w(QSplitter, "catTemplateSplitter")
        self.categories_list = self._w(QListWidget, "categoriesListWidget")
        self.cat_template_splitter.setSizes([130, 220])

        self._build_conversion_tab()

        self._splitter_dots: list = []
        for _spl in (
            self.main_h_splitter,
            self.main_v_splitter,
            self.conversion_splitter,
            self.files_meta_splitter,
            self.templates_details_splitter,
            self.cat_template_splitter,
        ):
            self._splitter_dots.extend(_install_splitter_dots(_spl))

        self.command_preview = self._w(QPlainTextEdit, "commandPreviewTextEdit")
        self.command_preview.textChanged.connect(self._on_command_text_edited)

        self.preview_title_label = self._w(QLabel, "previewTitleLabel")
        self.reset_command_button = QPushButton(trs("Default state"), self._ui.bottomPreviewWidget)
        self.reset_command_button.setObjectName("resetCommandButton")
        self.reset_command_button.setProperty("_i18n_text", "Default state")
        self.reset_command_button.setToolTip(trs("Restore the default command."))
        self.reset_command_button.setProperty(
            "_i18n_toolTip", "Restore the default command."
        )
        self.reset_command_button.setAutoDefault(False)
        self.reset_command_button.setDefault(False)
        self.reset_command_button.clicked.connect(self._reset_command_to_default)

        self.preview_header_layout = QHBoxLayout()
        self.preview_header_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_header_layout.addWidget(self.preview_title_label)
        self.preview_header_layout.addStretch(1)
        self.preview_header_layout.addWidget(self.reset_command_button)
        self._ui.verticalLayout_8.removeWidget(self.preview_title_label)
        self._ui.verticalLayout_8.insertLayout(0, self.preview_header_layout)
        self.copy_command_button = self._w(QPushButton, "copyCommandButton")
        self.run_command_button = self._w(QPushButton, "runCommandButton")
        self.run_command_button.setDefault(False)
        self.run_command_button.setAutoDefault(False)
        self._apply_accent_styles()
        self.clear_command_button = self._w(QPushButton, "clearCommandButton")
        self.run_progress = self._w(QProgressBar, "statusRunProgressBar")
        self.browse_files_button.clicked.connect(self._on_browse_files)
        self.clear_files_button.clicked.connect(self._delete_selected_file)
        self.clear_files_button.setEnabled(False)
        self.files_list_widget.currentRowChanged.connect(self._on_file_selected)
        self.files_list_widget.itemSelectionChanged.connect(self._update_clear_files_button)
        self.files_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files_list_widget.customContextMenuRequested.connect(self._show_file_context_menu)
        self.files_list_widget.installEventFilter(self)

        self.metadata_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.metadata_tree.customContextMenuRequested.connect(self._show_metadata_context_menu)
        self.settings_button.clicked.connect(self._open_settings)

        self.output_format_combo.currentIndexChanged.connect(self._on_output_format_changed)
        self.output_path_line.textChanged.connect(self._refresh_command)
        self.browse_output_button.clicked.connect(self._on_browse_output)

        self.templates_list.currentRowChanged.connect(self._on_template_selected)
        self.templates_list.itemDoubleClicked.connect(self._on_template_double_clicked)
        self.categories_list.currentRowChanged.connect(self._on_category_selected)
        self.categories_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.categories_list.customContextMenuRequested.connect(self._show_category_context_menu)
        self.new_template_button.clicked.connect(self._new_template)

        self.visual_editor_button = self._w(QPushButton, "visualEditorButton")
        self.visual_editor_button.clicked.connect(self._open_visual_editor)
        self._ve_dialog: QDialog | None = None

        self.builder_tabs.currentChanged.connect(lambda _idx: self._refresh_command())
        self.builder_tabs.currentChanged.connect(self._update_conversion_panel_visibility)
        self.templates_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.templates_list.customContextMenuRequested.connect(self._show_template_context_menu)
        self.templates_list.model().rowsMoved.connect(self._on_template_rows_moved)

        self._cat_drop_filter = _CategoryDropFilter(
            self.categories_list,
            self.templates_list,
            self._on_template_dropped_on_category,
        )

        self.main_h_splitter.splitterMoved.connect(self._on_splitter_changed)
        self.main_v_splitter.splitterMoved.connect(self._on_splitter_changed)
        self.conversion_splitter.splitterMoved.connect(self._on_splitter_changed)
        self.files_meta_splitter.splitterMoved.connect(self._on_splitter_changed)
        self.templates_details_splitter.splitterMoved.connect(self._on_splitter_changed)

        self.copy_command_button.clicked.connect(self._copy_command)
        self.clear_command_button.clicked.connect(self.command_preview.clear)
        self.run_command_button.clicked.connect(self._run_command)

        # Guard against accidental parameter changes caused by scrolling.
        self._combo_wheel_guard = _ComboBoxWheelGuard(self)
        for combo in self.findChildren(QComboBox):
            combo.installEventFilter(self._combo_wheel_guard)

        self.loudness_progress_bar.setVisible(False)
        self.run_progress.setVisible(False)

        self.ffmpeg_console = self._w(QPlainTextEdit, "ffmpegConsoleTextEdit")
        _console_font = QFont()
        _console_font.setFamilies(["Menlo", "Monaco", "Courier New", "monospace"])
        _console_font.setPointSize(10)
        self.ffmpeg_console.setFont(_console_font)
        self.ffmpeg_console.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        _lh = self.ffmpeg_console.fontMetrics().lineSpacing()
        self.ffmpeg_console.setFixedHeight(_lh * 3 + 12)
        _show = bool(settings_manager.get_settings().get("show_ffmpeg_console", False))
        self.ffmpeg_console.setVisible(_show)

        self._update_conversion_panel_visibility()
