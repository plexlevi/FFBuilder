"""UI-only helper behaviors used by the main window."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QListWidget, QSplitter, QWidget

from app.shared.utils.theme import is_dark_mode


def resolve_notification_sound_path(root_dir: Path, kind: str, settings: dict[str, Any]) -> str | None:
    if kind == "success" and not settings.get("sound_on_success", True):
        return None
    if kind == "error" and not settings.get("sound_on_error", True):
        return None

    sound_name = "success.wav" if kind == "success" else "fail.wav"
    sound_path = root_dir / "assets" / "sounds" / sound_name
    return str(sound_path)


class _CategoryDropFilter(QObject):
    """
    Event filter a categories_list.viewport()-re szerelve.
    macOS column-view drag viselkedés hover-delay committal.

    Fontos: setCurrentItem hívások blockSignals(True) alatt futnak, hogy
    _on_category_selected NE töltse újra a templates_list-et drag közben.
    Így a Drop eseménynél a forrás sor és kategória helyes marad.
    """

    _HOVER_MS: int = 600   # ms hover egy új soron, mielőtt az válik céllá
    _SNAP: int = 10        # px: bővített találati zóna item felett/alatt
    _EDGE_ZONE: int = 44   # px a viewport szélétől: auto-scroll zóna
    _EDGE_STEP: int = 14   # px / auto-scroll tick

    def __init__(
        self,
        categories_list: QListWidget,
        templates_list: QListWidget,
        on_drop_fn,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._cat = categories_list
        self._tmpl = templates_list
        self._on_drop = on_drop_fn

        self._active_target = None   # commitált cél item
        self._pending_item = None    # jelölt (egér alatti, nem commitált)
        self._dragged_row: int = -1  # templates_list sor, rögzítve drag induláskor
        self._original_cat_item = None   # categories_list kijelölés drag előtt

        # Hover-delay timer
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(self._HOVER_MS)
        self._hover_timer.timeout.connect(self._commit_hover)

        # Auto-scroll timer
        self._scroll_dir = 0
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(35)
        self._scroll_timer.timeout.connect(self._do_scroll)

        categories_list.setAcceptDrops(True)
        categories_list.viewport().setAcceptDrops(True)
        categories_list.viewport().installEventFilter(self)

    def _commit_hover(self) -> None:
        """Hover timer tüzelt: pending item lesz az aktív cél."""
        if self._pending_item is not None:
            self._active_target = self._pending_item
            self._pending_item = None
            self._cat.blockSignals(True)
            self._cat.setCurrentItem(self._active_target)
            self._cat.blockSignals(False)

    def _do_scroll(self) -> None:
        bar = self._cat.verticalScrollBar()
        bar.setValue(bar.value() + self._scroll_dir * self._EDGE_STEP)

    def _stop_scroll(self) -> None:
        self._scroll_timer.stop()
        self._scroll_dir = 0

    def _restore_original_selection(self) -> None:
        """Drag előtti kategória-kijelölés visszaállítása jelzés nélkül."""
        if self._original_cat_item is not None:
            self._cat.blockSignals(True)
            self._cat.setCurrentItem(self._original_cat_item)
            self._cat.blockSignals(False)
            self._original_cat_item = None

    def _item_at_forgiving(self, pos):
        """Háromrétegű hit test: pontos -> bővített rect -> legközelebbi Y."""
        item = self._cat.itemAt(pos)
        if item:
            return item
        for i in range(self._cat.count()):
            it = self._cat.item(i)
            rect = self._cat.visualItemRect(it)
            if rect.adjusted(0, -self._SNAP, 0, self._SNAP).contains(pos):
                return it
        if not self._cat.viewport().rect().contains(pos):
            return None
        best, best_dist = None, float("inf")
        for i in range(self._cat.count()):
            it = self._cat.item(i)
            rect = self._cat.visualItemRect(it)
            dist = abs(pos.y() - rect.center().y())
            if dist < best_dist:
                best_dist, best = dist, it
        return best

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        try:
            if obj is not self._cat.viewport():
                return False
        except RuntimeError:
            return False
        t = event.type()

        if t == QEvent.Type.DragEnter:
            if event.source() is self._tmpl:
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
                self._dragged_row = self._tmpl.currentRow()
                self._original_cat_item = self._cat.currentItem()
                if self._active_target is None:
                    pos = event.position().toPoint()
                    item = self._item_at_forgiving(pos)
                    if item is not None:
                        self._active_target = item
                        self._cat.blockSignals(True)
                        self._cat.setCurrentItem(item)
                        self._cat.blockSignals(False)
                return True

        elif t == QEvent.Type.DragMove:
            if event.source() is self._tmpl:
                pos = event.position().toPoint()
                vh = self._cat.viewport().height()

                if pos.y() < self._EDGE_ZONE:
                    self._scroll_dir = -1
                    if not self._scroll_timer.isActive():
                        self._scroll_timer.start()
                elif pos.y() > vh - self._EDGE_ZONE:
                    self._scroll_dir = 1
                    if not self._scroll_timer.isActive():
                        self._scroll_timer.start()
                else:
                    self._stop_scroll()

                item = self._item_at_forgiving(pos)

                if item is None:
                    self._hover_timer.stop()
                    self._pending_item = None
                elif item is self._active_target:
                    self._hover_timer.stop()
                    self._pending_item = None
                elif item is not self._pending_item:
                    self._pending_item = item
                    self._hover_timer.start()

                if self._active_target is not None or item is not None:
                    event.setDropAction(Qt.DropAction.CopyAction)
                    event.accept()
                else:
                    event.ignore()
                return True

        elif t == QEvent.Type.DragLeave:
            self._stop_scroll()
            self._hover_timer.stop()
            self._pending_item = None
            self._active_target = None
            self._restore_original_selection()
            self._dragged_row = -1

        elif t == QEvent.Type.Drop:
            self._stop_scroll()
            self._hover_timer.stop()
            if event.source() is self._tmpl:
                target = self._active_target
                if target is None:
                    target = self._item_at_forgiving(event.position().toPoint())

                self._restore_original_selection()

                local_row = self._dragged_row
                self._active_target = None
                self._pending_item = None
                self._dragged_row = -1

                if target is not None and local_row >= 0:
                    is_copy = bool(
                        QGuiApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier
                    )
                    event.setDropAction(Qt.DropAction.CopyAction)
                    event.accept()
                    self._on_drop(local_row, target.text(), is_copy)
                    return True
                event.ignore()
                return True

        return False


class _SplitterGripDots(QWidget):
    """Paints 4 grip dots on a QSplitterHandle. No animation, no hover effect."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self.resize(parent.size())
        self.raise_()
        # Keep dots sized when the handle resizes
        parent.installEventFilter(self)

    def eventFilter(self, obj: QObject, event) -> bool:  # type: ignore[override]
        try:
            if event.type() == QEvent.Type.Resize:
                self.resize(obj.size())
                self.raise_()
        except RuntimeError:
            pass
        return False

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        dot_color = QColor(180, 180, 185) if is_dark_mode() else QColor(50, 50, 55)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(dot_color)
        n, d, gap = 4, 2, 3  # 4 dots, 2 px diameter, 3 px gap
        if w <= h:  # vertical handle — dots stacked vertically
            total = n * d + (n - 1) * gap
            x0 = (w - d) // 2
            y0 = (h - total) // 2
            for i in range(n):
                p.drawEllipse(x0, y0 + i * (d + gap), d, d)
        else:  # horizontal handle — dots arranged horizontally
            total = n * d + (n - 1) * gap
            x0 = (w - total) // 2
            y0 = (h - d) // 2
            for i in range(n):
                p.drawEllipse(x0 + i * (d + gap), y0, d, d)
        p.end()


def _install_splitter_dots(splitter: QSplitter) -> list[_SplitterGripDots]:
    """Attach grip-dot overlays to every handle of *splitter*. Returns them so
    the caller can keep references (prevents premature garbage collection)."""
    dots: list[_SplitterGripDots] = []
    for i in range(1, splitter.count()):
        handle = splitter.handle(i)
        # Suppress Fusion's own grip marks by setting a transparent stylesheet
        handle.setStyleSheet("background-color: transparent;")
        dots.append(_SplitterGripDots(handle))
    return dots
