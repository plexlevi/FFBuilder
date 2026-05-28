"""UI-only helper behaviors used by the main window."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QListWidget, QWidget


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


class _SplitterHandleAnimator(QObject):
    """Fades a splitter handle colour on hover via QPainter (bypasses QSS)."""

    _INTERVAL_MS = 16
    _DURATION_MS = 200.0
    _COLOR = QColor(74, 144, 217)

    def __init__(self, handle: QWidget) -> None:
        super().__init__(handle)
        self._handle = handle
        self._alpha: float = 0.0
        self._start: float = 0.0
        self._target: float = 0.0
        self._elapsed: float = 0.0

        handle.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        handle.installEventFilter(self)

        self._timer = QTimer(self)
        self._timer.setInterval(self._INTERVAL_MS)
        self._timer.timeout.connect(self._step)

    def _fade(self, target: float) -> None:
        self._start = self._alpha
        self._target = target
        self._elapsed = 0.0
        if not self._timer.isActive():
            self._timer.start()

    def _step(self) -> None:
        self._elapsed += self._INTERVAL_MS
        t = min(self._elapsed / self._DURATION_MS, 1.0)
        t = 2 * t * t if t < 0.5 else 1.0 - (-2 * t + 2) ** 2 / 2
        self._alpha = self._start + (self._target - self._start) * t
        self._handle.update()
        if self._elapsed >= self._DURATION_MS:
            self._alpha = self._target
            self._timer.stop()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj is self._handle:
            t = event.type()
            if t == QEvent.Type.Show:
                # Re-apply WA_Hover when the widget becomes visible.
                # Needed for handles inside non-active tabs at startup:
                # WA_Hover set on a hidden widget may not register with the
                # native macOS tracking layer until the widget is shown.
                self._handle.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            elif t in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
                self._fade(255.0)
            elif t in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
                self._fade(0.0)
            elif t == QEvent.Type.Paint:
                color = QColor(self._COLOR)
                color.setAlpha(int(self._alpha))
                painter = QPainter(self._handle)
                painter.fillRect(self._handle.rect(), color)
                painter.end()
                return True
        return False
