"""UI widget lookup and signal wiring extracted from MainWindow."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QAbstractScrollArea,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QToolButton,
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
        """Create the first tab with files, command preview and output inside it."""
        self.conversion_tab = QWidget()
        self.conversion_tab.setObjectName("conversionTab")
        conversion_layout = QVBoxLayout(self.conversion_tab)
        # At least ~3 mm breathing room around the tab content.
        content_margin = 10
        conversion_layout.setContentsMargins(
            content_margin, content_margin, content_margin, content_margin
        )
        conversion_layout.setSpacing(8)

        self.conversion_v_splitter = QSplitter(Qt.Orientation.Vertical, self.conversion_tab)
        self.conversion_v_splitter.setObjectName("conversionVerticalSplitter")
        conversion_layout.addWidget(self.conversion_v_splitter)

        # Top: file + metadata pane.
        self._ui.leftPaneWidget.setParent(self.conversion_tab)
        self.conversion_v_splitter.addWidget(self._ui.leftPaneWidget)
        left_layout = self._ui.leftPaneWidget.layout()
        if left_layout is not None:
            left_layout.setContentsMargins(0, 0, 0, 0)
            left_layout.setSpacing(8)

        # Bottom: command preview, output settings and the run/status bar.
        # These are intentionally inside the tab so they share its frame.
        self._ui.bottomPreviewWidget.setParent(self.conversion_tab)
        self.conversion_v_splitter.addWidget(self._ui.bottomPreviewWidget)
        bottom_layout = self._ui.bottomPreviewWidget.layout()
        if bottom_layout is not None:
            bottom_layout.setContentsMargins(0, 0, 0, 0)
            bottom_layout.setSpacing(8)
        self.conversion_v_splitter.setSizes([420, 300])

        # Compact hierarchical preset menu in the file header row.
        self.preset_button = QToolButton(self._ui.leftPaneWidget)
        self.preset_button.setObjectName("presetButton")
        self.preset_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.preset_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.preset_button.setMinimumWidth(180)
        self.preset_button.setMaximumWidth(320)
        self.preset_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.preset_button.setText(trs("Preset"))
        self.preset_button.setToolTip(trs("Choose a preset"))
        self.preset_menu = QMenu(self.preset_button)
        self.preset_menu.triggered.connect(self._on_preset_menu_triggered)
        self.preset_button.setMenu(self.preset_menu)
        self.presets_label = QLabel(trs("Presets"), self._ui.leftPaneWidget)
        self.presets_label.setProperty("_i18n_text", "Presets")
        self._ui.filesHeaderLayout.addWidget(self.presets_label)
        self._ui.filesHeaderLayout.addWidget(self.preset_button)

        # Output settings belong below the command preview.
        self._ui.verticalLayout_5.removeWidget(self._ui.outputGroupBox)
        self._ui.outputGroupBox.setParent(self._ui.bottomPreviewWidget)
        self._ui.outputGroupBox.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self._ui.gridLayout.setColumnStretch(1, 1)
        self._ui.outputFormatComboBox.setMinimumWidth(110)
        self._ui.formatDescriptionLabel.setMinimumWidth(150)
        self._ui.outputFileLabelContainer.setMinimumWidth(0)
        self._ui.formatLabelContainer.setMinimumWidth(0)
        self._ui.outputFileLabelContainer.hide()
        self._ui.formatLabelContainer.hide()
        self._ui.outputPathLineEdit.setToolTip(trs("Output file"))
        self._ui.outputFormatComboBox.setToolTip(trs("Format"))
        self._ui.verticalLayout_8.addWidget(self._ui.outputGroupBox)

        # The run/status bar and the optional FFmpeg console also belong
        # inside the Conversion tab frame.
        self._ui.verticalLayout_2.removeWidget(self._ui.ffmpegConsoleTextEdit)
        self._ui.ffmpegConsoleTextEdit.setParent(self._ui.bottomPreviewWidget)
        self._ui.verticalLayout_8.addWidget(self._ui.ffmpegConsoleTextEdit)

        self._ui.statusbar.removeWidget(self._ui.statusBarContentWidget)
        self._ui.statusBarContentWidget.setParent(self._ui.bottomPreviewWidget)
        status_layout = self._ui.statusBarContentWidget.layout()
        if status_layout is not None:
            # Keep the status text on the same visual line as the content
            # inside the output/command boxes above.
            status_layout.setContentsMargins(10, 0, 0, 0)
            status_layout.setSpacing(8)
        self._ui.verticalLayout_8.addWidget(self._ui.statusBarContentWidget)
        self._ui.statusBarContentWidget.show()
        self._ui.statusbar.setVisible(False)

        self.builder_tabs.insertTab(0, self.conversion_tab, trs("Conversion"))
        self.builder_tabs.setCurrentIndex(0)

        # File metadata should be readable; the template list can be a bit smaller.
        template_font = QFont("Tuffy", 12)
        self.categories_list.setFont(template_font)
        self.templates_list.setFont(template_font)
        self.files_list_widget.setFont(QFont("Tuffy", 12))
        self.metadata_tree.setFont(QFont("Tuffy", 12))
        self.files_meta_splitter.setSizes([200, 320])

    def _update_conversion_panel_visibility(self, index: int | None = None) -> None:
        """Keep the optional console hidden outside the Conversion tab."""
        self._apply_console_visibility()

    def _wire_widgets(self) -> None:
        self.hardware_status_label = self._w(QLabel, "hardwareStatusLabel")
        self.settings_button = self._w(QPushButton, "settingsButton")
        self.browse_files_button = self._w(QPushButton, "browseFilesButton")
        self.clear_files_button = self._w(QPushButton, "clearFilesButton")
        self.files_list_widget = self._w(QListWidget, "filesListWidget")
        self.metadata_tree = self._w(QTreeWidget, "metadataTreeWidget")
        # Metadata is meant to read as plain content: no inner frame, and it
        # should span the same width as the widgets above and below it.
        self.metadata_tree.setFrameShape(QFrame.Shape.NoFrame)
        self.metadata_tree.setColumnCount(4)
        self.metadata_tree.setHeaderLabels(
            [trs("Field"), trs("Value"), trs("Field"), trs("Value")]
        )
        self._ui.verticalLayout_4.setContentsMargins(0, 0, 0, 0)
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
            self.conversion_v_splitter,
            self.files_meta_splitter,
            self.templates_details_splitter,
            self.cat_template_splitter,
        ):
            self._splitter_dots.extend(_install_splitter_dots(_spl))

        self.command_preview = self._w(QPlainTextEdit, "commandPreviewTextEdit")
        self.command_preview.textChanged.connect(self._on_command_text_edited)
        self.command_preview.setContextMenuPolicy(Qt.CustomContextMenu)
        self.command_preview.customContextMenuRequested.connect(self._show_command_context_menu)

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

        # The per-command buttons are no longer needed in a separate row.
        # Copy/Clear live in the command context menu; the visual editor moves
        # next to the Default state button.
        self._ui.horizontalLayout_4.removeWidget(self.visual_editor_button)
        self.preview_header_layout.insertWidget(2, self.visual_editor_button)
        self.copy_command_button.hide()
        self.clear_command_button.hide()
        self._ui.verticalLayout_8.removeItem(self._ui.horizontalLayout_4)

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
        self.conversion_v_splitter.splitterMoved.connect(self._on_splitter_changed)
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
