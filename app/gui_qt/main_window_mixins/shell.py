"""Application shell behavior: updates, theming, layout persistence, and app-level events."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QMessageBox

from app.gui_qt.main_window_parts import _UpdateCheckWorker, _UpdateInstallWorker
from app.services.ffmpeg.manager import find_binaries
from app.shared import settings as settings_manager
from app.shared.utils.theme import get_accent, init_accent, invalidate_cache, is_dark_mode
from app.shared.version import APP_VERSION, GITHUB_RELEASES_URL, GITHUB_REPO

_ROOT_DIR = Path(__file__).resolve().parents[3]


class ShellMixin:
    def _prewarm_imports(self) -> None:
        try:
            import app.gui_qt.dialogs.audio_analysis_dialog  # noqa: F401
        except Exception:
            pass

    def _maybe_check_for_updates(self) -> None:
        settings = settings_manager.get_settings()
        if not settings.get("auto_check_updates", True):
            return
        if self._update_check_in_progress:
            return

        self._update_check_in_progress = True
        worker = _UpdateCheckWorker(GITHUB_REPO, APP_VERSION)
        worker.signals.finished.connect(self._on_update_check_finished)
        self._thread_pool.start(worker)

    def _on_update_check_finished(self, payload: dict) -> None:
        self._update_check_in_progress = False
        if not payload.get("ok"):
            if getattr(self, "_update_check_retries_left", 0) > 0:
                self._update_check_retries_left -= 1
                QTimer.singleShot(30_000, self._maybe_check_for_updates)
            return
        if not payload.get("update_available"):
            return

        latest_version = str(payload.get("latest_version", "")).strip()
        if not latest_version:
            return

        settings = settings_manager.get_settings()
        skipped = str(settings.get("skip_update_version", "")).strip()
        if skipped == latest_version:
            return

        html_url = str(payload.get("html_url", "")).strip() or GITHUB_RELEASES_URL
        dmg_url = str(payload.get("dmg_asset_url", "")).strip()
        dmg_name = str(payload.get("dmg_asset_name", "")).strip()

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("Frissítés elérhető")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        msg.setOpenExternalLinks(True)
        text = (
            f"<b>Új verzió érhető el: v{latest_version}</b><br>"
            f"Jelenlegi verzió: v{APP_VERSION}<br><br>"
            f"<a href=\"{html_url}\">Megnyitás GitHubon</a><br><br>"
            "Mit szeretnél tenni?"
        )
        msg.setText(text)

        install_btn = None
        if dmg_url and sys.platform == "darwin":
            install_btn = msg.addButton("Automatikus telepítés", QMessageBox.ButtonRole.AcceptRole)
            _ah, _ar, _ag, _ab = get_accent()
            _accent = QColor(_ah)
            _darker = _accent.darker(120)
            _lighter = _accent.lighter(115)
            install_btn.setStyleSheet(
                "QPushButton {"
                f" background-color: {_accent.name()};"
                " color: #ffffff;"
                f" border: 1px solid {_darker.name()};"
                " border-radius: 6px;"
                " font-weight: 600;"
                " padding: 6px 12px;"
                "}"
                f"QPushButton:hover {{ background-color: {_lighter.name()}; }}"
                f"QPushButton:pressed {{ background-color: {_darker.name()}; }}"
            )
        later_btn = msg.addButton("Később", QMessageBox.ButtonRole.RejectRole)
        skip_btn = msg.addButton("Verzió kihagyása", QMessageBox.ButtonRole.DestructiveRole)
        msg.setDefaultButton(install_btn or later_btn)
        msg.exec()

        clicked = msg.clickedButton()
        if install_btn is not None and clicked is install_btn:
            settings_manager.save_settings({"skip_update_version": ""})
            self._start_update_install(dmg_url, dmg_name)
            return
        if clicked is skip_btn:
            settings_manager.save_settings({"skip_update_version": latest_version})
            self._set_status(f"ℹ️ v{latest_version} frissítés elrejtve", 3500)
            return
        if clicked is later_btn:
            self._set_status(f"ℹ️ Új verzió: v{latest_version}", 3500)

    def _start_update_install(self, dmg_url: str, dmg_name: str) -> None:
        if self._update_install_in_progress:
            return
        self._update_install_in_progress = True
        self._set_status("⬇️ Frissítés letöltése és telepítése...", 0)
        worker = _UpdateInstallWorker(dmg_url, dmg_name)
        worker.signals.finished.connect(self._on_update_install_finished)
        self._thread_pool.start(worker)

    def _on_update_install_finished(self, result: dict) -> None:
        self._update_install_in_progress = False
        if not result.get("ok"):
            err = str(result.get("error", "Ismeretlen hiba"))
            self._set_status("❌ Frissítés telepítése sikertelen", 5000)
            QMessageBox.warning(self, "Frissítés hiba", err)
            return

        app_path = str(result.get("app_path", "")).strip()
        self._set_status("✅ Frissítés telepítve", 6000)
        answer = QMessageBox.question(
            self,
            "Frissítés telepítve",
            "A frissítés telepítve lett. Szeretnéd most újraindítani az alkalmazást?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        if app_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(app_path))
        QApplication.instance().quit()

    def refresh_binary_paths(self, ffmpeg: str | None = None, ffprobe: str | None = None) -> None:
        """Refresh cached ffmpeg/ffprobe paths after runtime install changes."""
        if ffmpeg and ffprobe:
            self._ffmpeg_bin, self._ffprobe_bin = ffmpeg, ffprobe
        else:
            self._ffmpeg_bin, self._ffprobe_bin = find_binaries(refresh=True)
        self._update_hardware_status()

    def _apply_theme_palette(self) -> None:
        styles_dir = _ROOT_DIR / "assets" / "styles"
        common_qss = styles_dir / "common.qss"
        themed_qss = styles_dir / ("dark.qss" if is_dark_mode() else "light.qss")

        style_chunks: list[str] = []
        for style_file in (common_qss, themed_qss):
            if style_file.exists():
                style_chunks.append(style_file.read_text(encoding="utf-8"))

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet("\n".join(style_chunks))
        else:
            self.setStyleSheet("\n".join(style_chunks))

    def _apply_accent_styles(self) -> None:
        _ah, _ar, _ag, _ab = get_accent()
        _accent = QColor(_ah)
        _darker = _accent.darker(120)
        _lighter = _accent.lighter(115)
        self.run_command_button.setStyleSheet(
            f"QPushButton {{ background: {_accent.name()}; color: #ffffff;"
            f" border: 1px solid {_darker.name()}; border-radius: 6px;"
            f" font-weight: 600; min-width: 88px; padding: 4px 8px; }}"
            f" QPushButton:hover {{ background: {_lighter.name()}; }}"
            f" QPushButton:pressed {{ background: {_darker.name()}; }}"
        )

    def _apply_platform_icons(self) -> None:
        icon_dir = _ROOT_DIR / "assets" / "icons" / ("dark" if is_dark_mode() else "light")

        def _load_icon(file_name: str) -> QIcon:
            path = icon_dir / file_name
            if not path.exists():
                return QIcon()
            return QIcon(str(path))

        app_icon = _load_icon("app.svg")
        if app_icon.isNull():
            app_icon = QIcon(str(_ROOT_DIR / "assets" / "icons" / "app.svg"))
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

    def _on_system_theme_changed(self, *_args) -> None:
        app = QApplication.instance()
        if app is not None:
            init_accent(app.palette().color(QPalette.ColorRole.Highlight))
        invalidate_cache()
        self._apply_theme_palette()
        self._apply_platform_icons()
        self._apply_accent_styles()

    def eventFilter(self, watched, event):
        event_type = event.type()
        if watched is QApplication.instance() and event_type in {
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.ThemeChange,
        }:
            QTimer.singleShot(0, self._on_system_theme_changed)

        if watched is self:
            if event_type == QEvent.Resize:
                if settings_manager.get_settings().get("save_pane_sizes", True):
                    self._layout_save_timer.start(180)
            elif event_type == QEvent.Close:
                self._save_layout_settings()
                self._save_queue_state()
            elif event_type == QEvent.DragEnter:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
            elif event_type == QEvent.Drop:
                urls = event.mimeData().urls()
                paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
                if paths:
                    self._load_files(paths)
        return super().eventFilter(watched, event)

    def _on_splitter_changed(self, _pos: int, _index: int) -> None:
        if settings_manager.get_settings().get("save_pane_sizes", True):
            self._layout_save_timer.start(120)

    def _apply_saved_layout(self) -> None:
        settings = settings_manager.get_settings()
        size = str(settings.get("window_size", "1140x760"))
        if "x" in size:
            try:
                w, h = size.split("x", 1)
                self.resize(int(w), int(h))
            except Exception:
                self.resize(1140, 760)

        if not settings.get("save_pane_sizes", True):
            return

        def _parse_sizes(text: str, fallback: list[int]) -> list[int]:
            try:
                vals = [int(part.strip()) for part in str(text).split(",") if part.strip()]
                if len(vals) >= 2:
                    return vals[:2]
            except Exception:
                pass
            return fallback

        h_sizes = _parse_sizes(settings.get("splitter_main_horizontal", "320,820"), [320, 820])
        v_sizes = _parse_sizes(settings.get("splitter_main_vertical", "560,260"), [560, 260])
        fm_sizes = _parse_sizes(settings.get("splitter_files_metadata", "300,240"), [300, 240])
        td_sizes = _parse_sizes(settings.get("splitter_templates_details", "260,260"), [260, 260])
        self.main_h_splitter.setSizes(h_sizes)
        self.main_v_splitter.setSizes(v_sizes)
        self.files_meta_splitter.setSizes(fm_sizes)
        self.templates_details_splitter.setSizes(td_sizes)

    def _save_layout_settings(self) -> None:
        settings = settings_manager.get_settings()
        if not settings.get("save_pane_sizes", True):
            return

        h_sizes = self.main_h_splitter.sizes()
        v_sizes = self.main_v_splitter.sizes()
        fm_sizes = self.files_meta_splitter.sizes()
        td_sizes = self.templates_details_splitter.sizes()
        settings_manager.save_settings(
            {
                "window_size": f"{self.width()}x{self.height()}",
                "splitter_main_horizontal": ",".join(str(v) for v in h_sizes[:2]),
                "splitter_main_vertical": ",".join(str(v) for v in v_sizes[:2]),
                "splitter_files_metadata": ",".join(str(v) for v in fm_sizes[:2]),
                "splitter_templates_details": ",".join(str(v) for v in td_sizes[:2]),
            }
        )
