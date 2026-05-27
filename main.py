#!/usr/bin/env python 
# -*- coding: utf-8 -*- 
"""Run the FFBuilder GUI (Qt/PySide6)."""
import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QMessageBox

# Support direct execution: `python main.py` 
if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from app.gui_qt.main_window import MainWindow
from app.gui_qt.dialogs.ffmpeg_installer_dialog import run_ffmpeg_installer_dialog
from app.services.ffmpeg.manager import find_binaries
from app.shared.i18n import install_i18n, trs
from app.shared.version import APP_NAME, APP_VERSION
from app.shared.utils.theme import is_dark_mode, init_accent



def _check_ffmpeg_available() -> bool:
    ffmpeg, ffprobe = find_binaries()
    return bool(ffmpeg and ffprobe)


def _load_app_stylesheet() -> str:
    """Load common and theme-specific QSS files."""
    styles_dir = Path(__file__).resolve().parent / "assets" / "styles"
    chunks: list[str] = []
    for name in ("common.qss", "dark.qss" if is_dark_mode() else "light.qss"):
        path = styles_dir / name
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def main() -> int:
    app = QApplication(sys.argv)
    install_i18n(app)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    # Read the macOS accent colour before switching to Fusion style. 
    init_accent(app.palette().color(QPalette.ColorRole.Highlight))
    app.setStyle("fusion")

    # Register the custom font BEFORE building the stylesheet so the 
    # QSS engine already knows about it when setStyleSheet() is called. 
    font_family: str | None = None
    font_path = Path(__file__).resolve().parent / "assets" / "Tuffy-Regular.ttf"
    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            font_family = families[0]

    # Build stylesheet; prepend a universal font-family rule when available 
    # so QSS wins over the platform style's implicit font choices. 
    stylesheet = _load_app_stylesheet()
    if font_family:
        stylesheet = f'* {{ font-family: "{font_family}"; }}\n' + stylesheet
    app.setStyleSheet(stylesheet)

    # Also set as the Qt application-level default font. 
    if font_family:
        tuffy = QFont(font_family)
        tuffy.setPointSize(app.font().pointSize())
        app.setFont(tuffy)

    window = MainWindow()
    window.show()

    if not _check_ffmpeg_available():
        result = run_ffmpeg_installer_dialog(window)
        window.refresh_binary_paths(result.get("ffmpeg"), result.get("ffprobe"))
        if not (result.get("ffmpeg") and result.get("ffprobe")):
            QMessageBox.warning(
                window,
                trs("FFmpeg missing"),
                trs(
                    "Cannot find ffmpeg/ffprobe binaries.\n\n"
                    "The application can start, but conversion will not work until you install them."
                ),
            )

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
