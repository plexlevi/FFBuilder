"""UI widget lookup and signal wiring extracted from MainWindow."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QApplication,
    QAbstractScrollArea,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTreeWidget,
)

from app.gui_qt.main_window_parts import _CategoryDropFilter, _SplitterHandleAnimator


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

        for _spl in (
            self.main_h_splitter,
            self.main_v_splitter,
            self.files_meta_splitter,
            self.templates_details_splitter,
            self.cat_template_splitter,
        ):
            for _i in range(1, _spl.count()):
                _SplitterHandleAnimator(_spl.handle(_i))

        self.command_preview = self._w(QPlainTextEdit, "commandPreviewTextEdit")
        self.copy_command_button = self._w(QPushButton, "copyCommandButton")
        self.run_command_button = self._w(QPushButton, "runCommandButton")
        self.run_command_button.setDefault(False)
        self.run_command_button.setAutoDefault(False)
        self._apply_accent_styles()
        self.clear_command_button = self._w(QPushButton, "clearCommandButton")
        self.run_progress = self._w(QProgressBar, "statusRunProgressBar")
        self.browse_files_button.clicked.connect(self._on_browse_files)
        self.clear_files_button.clicked.connect(self._on_clear_files)
        self.files_list_widget.currentRowChanged.connect(self._on_file_selected)
        self.files_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files_list_widget.customContextMenuRequested.connect(self._show_file_context_menu)

        self.metadata_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.metadata_tree.customContextMenuRequested.connect(self._show_metadata_context_menu)
        self.settings_button.clicked.connect(self._open_settings)

        self.output_format_combo.currentIndexChanged.connect(self._on_output_format_changed)
        self.output_path_line.textChanged.connect(self._refresh_command)
        self.browse_output_button.clicked.connect(self._on_browse_output)

        self.templates_list.currentRowChanged.connect(self._on_template_selected)
        self.templates_list.currentRowChanged.connect(lambda _: self._apply_template())
        self.categories_list.currentRowChanged.connect(self._on_category_selected)
        self.categories_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.categories_list.customContextMenuRequested.connect(self._show_category_context_menu)
        self.new_template_button.clicked.connect(self._new_template)

        self.visual_editor_button = self._w(QPushButton, "visualEditorButton")
        self.visual_editor_button.clicked.connect(self._open_visual_editor)
        self._ve_dialog: QDialog | None = None

        self.builder_tabs.currentChanged.connect(lambda _idx: self._refresh_command())
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
