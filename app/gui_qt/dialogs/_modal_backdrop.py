#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Shared modal-backdrop helper for dialogs that close on outside click."""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtCore import (
    QEasingCurve, QEvent, QEventLoop, QPropertyAnimation, QRectF, Qt, Signal,
    Property,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRegion, QTransform
from PySide6.QtWidgets import QDialog, QPushButton, QWidget

from app.shared.i18n import trs

_CORNER_RADIUS = 12
_FADE_IN_MS = 180
_FADE_OUT_MS = 140
_DIALOG_MARGIN = 32  # px gap between backdrop edge and dialog on each side
_CLOSE_BTN_SIZE = 24
_CLOSE_BTN_MARGIN = 10


class _RoundCloseButton(QPushButton):
    """Always-round close button with custom paint (style-independent)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("X", parent)
        self.setFixedSize(_CLOSE_BTN_SIZE, _CLOSE_BTN_SIZE)
        self.setDefault(False)
        self.setAutoDefault(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(trs("Close"))
        self._hovered = False
        self._pressed = False

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._pressed:
            fill = QColor(180, 45, 45, 215)
            border = QColor(255, 190, 190, 190)
            text = QColor(255, 255, 255)
        elif self._hovered:
            fill = QColor(220, 70, 70, 185)
            border = QColor(255, 190, 190, 175)
            text = QColor(255, 255, 255)
        else:
            fill = QColor(80, 80, 80, 90)
            border = QColor(200, 200, 200, 95)
            text = QColor(245, 247, 252, 235)

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(border)
        painter.setBrush(fill)
        painter.drawEllipse(rect)

        font = painter.font()
        font.setBold(True)
        font.setPointSize(11)
        painter.setFont(font)
        painter.setPen(text)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "X")


class _DialogCloseButtonBinder(QObject):
    """Keep the top-right close button pinned on dialog resize/show."""

    def __init__(self, dialog: QDialog, button: QPushButton) -> None:
        super().__init__(dialog)
        self._dialog = dialog
        self._button = button

    def _reposition(self) -> None:
        x = self._dialog.width() - _CLOSE_BTN_SIZE - _CLOSE_BTN_MARGIN
        y = _CLOSE_BTN_MARGIN
        self._button.move(max(0, x), max(0, y))
        self._button.raise_()

    def eventFilter(self, watched, event) -> bool:
        if watched is self._dialog and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.LayoutRequest,
        }:
            self._reposition()
        return False


def _attach_top_right_close(dialog: QDialog) -> None:
    """Attach a conventional top-right X close button to embedded dialogs."""
    existing = dialog.findChild(QPushButton, "_modalBackdropCloseButton")
    if existing is not None:
        return

    btn = _RoundCloseButton(dialog)
    btn.setObjectName("_modalBackdropCloseButton")
    btn.clicked.connect(dialog.reject)

    binder = _DialogCloseButtonBinder(dialog, btn)
    dialog.installEventFilter(binder)
    dialog.setProperty("_closeButtonBinder", binder)
    binder._reposition()


class ModalBackdrop(QWidget):
    """Semi-transparent overlay that fills the parent window.

    Emits *dismissed* when the user clicks anywhere on the backdrop,
    allowing the owning dialog to reject itself.
    """

    dismissed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)
        self._alpha = 0          # animated 0 -> 150 (fill alpha, no QGraphicsEffect)
        self._anim: QPropertyAnimation | None = None
        self._dialog: QDialog | None = None
        self.raise_()
        self.show()

    # -- Animatable property -------------------------------------------------
    def _get_alpha(self) -> int:
        return self._alpha

    def _set_alpha(self, value: int) -> None:
        self._alpha = value
        self.update()

    backdrop_alpha = Property(int, _get_alpha, _set_alpha)

    # -- Painting ------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, self._alpha))

    def mousePressEvent(self, _event) -> None:
        self.dismissed.emit()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Resize and watched is self.parent():
            self.setGeometry(watched.rect())
            self._refit_dialog()
        return False

    # -- Dialog sizing -------------------------------------------------------
    def _refit_dialog(self) -> None:
        """Center the hosted dialog within the backdrop, constraining to available space."""
        if self._dialog is None:
            return
        max_w = self.width() - 2 * _DIALOG_MARGIN
        max_h = self.height() - 2 * _DIALOG_MARGIN
        new_w = max(self._dialog.minimumWidth(), min(self._dialog.width(), max_w))
        new_h = max(self._dialog.minimumHeight(), min(self._dialog.height(), max_h))
        if new_w != self._dialog.width() or new_h != self._dialog.height():
            self._dialog.resize(new_w, new_h)
        x = (self.width() - self._dialog.width()) // 2
        y = (self.height() - self._dialog.height()) // 2
        self._dialog.move(x, y)
        apply_rounded_mask(self._dialog)

    # -- Fade helpers --------------------------------------------------------
    def fade_in(self) -> None:
        self._animate(0, 150, _FADE_IN_MS, QEasingCurve.Type.OutCubic)

    def fade_out(self) -> QPropertyAnimation:
        return self._animate(150, 0, _FADE_OUT_MS, QEasingCurve.Type.InCubic)

    def _animate(
        self, start: int, end: int, duration: int, easing: QEasingCurve.Type
    ) -> QPropertyAnimation:
        if self._anim is not None:
            self._anim.stop()
        anim = QPropertyAnimation(self, b"backdrop_alpha", self)
        anim.setDuration(duration)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(easing)
        self._anim = anim
        anim.start()
        return anim

    def cleanup(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            parent.removeEventFilter(self)
        self.close()
        self.deleteLater()


def apply_rounded_mask(widget: QWidget) -> None:
    """Clip widget painting to a rounded rectangle."""
    path = QPainterPath()
    path.addRoundedRect(QRectF(widget.rect()), _CORNER_RADIUS, _CORNER_RADIUS)
    region = QRegion(path.toFillPolygon(QTransform()).toPolygon())
    widget.setMask(region)


def exec_with_backdrop(dialog: QDialog) -> int:
    """Run *dialog* embedded in a backdrop overlay, blocking until it closes.

    The dialog is reparented as a plain child widget of the backdrop so it is
    never a draggable top-level window. The backdrop fades in/out; the dialog
    content is rendered normally (no QGraphicsEffect, matplotlib-safe).
    """
    parent_widget = dialog.parent()
    backdrop: ModalBackdrop | None = None

    if isinstance(parent_widget, QWidget):
        backdrop = ModalBackdrop(parent_widget)
        # Reparent as a plain embedded widget - not a draggable window
        dialog.setParent(backdrop, Qt.WindowType.Widget)
        backdrop.dismissed.connect(dialog.reject)
        _attach_top_right_close(dialog)

    loop = QEventLoop()

    if backdrop is not None:
        def _on_finished() -> None:
            fade = backdrop.fade_out()
            fade.finished.connect(loop.quit)
        dialog.finished.connect(_on_finished)
    else:
        dialog.finished.connect(loop.quit)

    dialog.show()

    if backdrop is not None:
        backdrop._dialog = dialog
        backdrop._refit_dialog()
        dialog.raise_()
        backdrop.fade_in()

    loop.exec()

    if backdrop is not None:
        backdrop.cleanup()

    return dialog.result()
