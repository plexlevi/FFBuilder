#!/usr/bin/env python 
# -*- coding: utf-8 -*- 
"""Simple JSON-based localization helper."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QComboBox, QDialogButtonBox, QMessageBox, QTabWidget, QTreeWidget, QWidget

from app.shared import settings as settings_manager

_LOCALES_DIR = Path(__file__).resolve().parents[2] / "assets" / "locales"
_FALLBACK_LANG = "en"
_CATALOG_CACHE: dict[str, dict[str, str]] = {}
_EVENT_FILTER: QObject | None = None
_QMESSAGEBOX_PATCHED = False
_QMESSAGEBOX_ORIGINALS: dict[str, object] = {}


def normalize_language(lang: str | None) -> str:
    raw = str(lang or "").strip().lower()
    if not raw:
        return _FALLBACK_LANG

    aliases = {
        "hu_hu": "hu",
        "en_us": "en",
        "en_gb": "en",
    }
    return aliases.get(raw, raw)


def get_language() -> str:
    settings = settings_manager.get_settings()
    user_set = bool(settings.get("language_user_set", False))
    lang = normalize_language(settings.get("language", _FALLBACK_LANG))

    # Migrate legacy configs: before i18n settings UI, language could be 
    # persisted as Hungarian by default. Keep English as true default until 
    # the user explicitly selects a language. 
    if not user_set and lang == "hu":
        settings_manager.save_settings({"language": _FALLBACK_LANG})
        lang = _FALLBACK_LANG

    return lang or _FALLBACK_LANG


def set_language(lang: str) -> None:
    settings_manager.save_settings(
        {
            "language": normalize_language(lang),
            "language_user_set": True,
        }
    )


def _is_language_catalog(stem: str) -> bool:
    if stem.startswith("source_") or stem.startswith("param_descriptions_"):
        return False
    if len(stem) == 2 and stem.isalpha():
        return True
    if len(stem) == 5 and stem[2] in ("_", "-") and stem[:2].isalpha() and stem[3:].isalpha():
        return True
    return False


def available_languages() -> list[str]:
    if not _LOCALES_DIR.exists():
        return [_FALLBACK_LANG]
    langs = sorted(
        path.stem
        for path in _LOCALES_DIR.glob("*.json")
        if path.is_file() and _is_language_catalog(path.stem)
    )
    return langs or [_FALLBACK_LANG]


def _load_catalog(lang: str) -> dict[str, str]:
    lang = normalize_language(lang)
    cached = _CATALOG_CACHE.get(lang)
    if cached is not None:
        return cached

    path = _LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        _CATALOG_CACHE[lang] = {}
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    catalog = {str(k): str(v) for k, v in payload.items() if isinstance(k, str)}
    _CATALOG_CACHE[lang] = catalog
    return catalog


def trs(text: str, *, lang: str | None = None) -> str:
    """Translate a source UI text by looking it up directly in the language catalog."""
    source = str(text or "")
    if not source:
        return source

    chosen_lang = normalize_language(lang) if lang else get_language()
    translation = _load_catalog(chosen_lang).get(source)
    if translation is None and chosen_lang != _FALLBACK_LANG:
        translation = _load_catalog(_FALLBACK_LANG).get(source)
    return translation if translation is not None else source


def tr(key: str, default: str | None = None, *, lang: str | None = None) -> str:
    """Alias for trs(); kept for backwards compatibility."""
    return trs(key, lang=lang) if default is None else trs(default, lang=lang)


def _translate_prop(
    widget: QObject,
    prop_key: str,
    getter,
    setter,
    *,
    lang: str,
) -> None:
    """Translate one widget property, storing the original source text on first call."""
    stored_key = f"_i18n_{prop_key}"
    source = widget.property(stored_key)
    if not source:
        try:
            source = getter()
        except Exception:
            source = ""
        if source:
            widget.setProperty(stored_key, source)
    if not source:
        return
    try:
        setter(trs(source, lang=lang))
    except Exception:
        pass


def _translate_widget_props(widget: QWidget, *, lang: str) -> None:
    """Translate all translatable properties of one widget (no recursion)."""
    if hasattr(widget, "windowTitle") and hasattr(widget, "setWindowTitle"):
        _translate_prop(widget, "windowTitle", widget.windowTitle, widget.setWindowTitle, lang=lang)

    if hasattr(widget, "text") and hasattr(widget, "setText"):
        template = widget.property("i18n_template")
        if template:
            # Dynamic label: stored template + args, re-translated on every language change
            args = widget.property("i18n_args") or []
            text = trs(str(template), lang=lang)
            for arg in args:
                text = text.replace("{var}", str(arg), 1)
            try:
                widget.setText(text)
            except Exception:
                pass
        else:
            _translate_prop(widget, "text", widget.text, widget.setText, lang=lang)

    if hasattr(widget, "title") and hasattr(widget, "setTitle"):
        _translate_prop(widget, "groupTitle", widget.title, widget.setTitle, lang=lang)

    if hasattr(widget, "toolTip") and hasattr(widget, "setToolTip"):
        _translate_prop(widget, "toolTip", widget.toolTip, widget.setToolTip, lang=lang)

    if hasattr(widget, "placeholderText") and hasattr(widget, "setPlaceholderText"):
        _translate_prop(widget, "placeholder", widget.placeholderText, widget.setPlaceholderText, lang=lang)

    if isinstance(widget, QTabWidget):
        for idx in range(widget.count()):
            _translate_prop(
                widget, f"tab_{idx}",
                lambda i=idx: widget.tabText(i),
                lambda t, i=idx: widget.setTabText(i, t),
                lang=lang,
            )

    if isinstance(widget, QTreeWidget):
        header = widget.headerItem()
        if header is not None:
            for col in range(header.columnCount()):
                _translate_prop(
                    widget, f"hdr_{col}",
                    lambda c=col: header.text(c),
                    lambda t, c=col: header.setText(c, t),
                    lang=lang,
                )

    if isinstance(widget, QComboBox):
        for idx in range(widget.count()):
            _translate_prop(
                widget, f"combo_{idx}",
                lambda i=idx: widget.itemText(i),
                lambda t, i=idx: widget.setItemText(i, t),
                lang=lang,
            )

    if isinstance(widget, QDialogButtonBox):
        for btn in widget.buttons():
            _translate_prop(btn, "text", btn.text, btn.setText, lang=lang)


def localize_widget_tree(widget: QWidget, *, lang: str | None = None) -> None:
    """Apply source-text localization to a widget and all its descendants (flat iteration)."""
    if widget is None:
        return
    chosen_lang = normalize_language(lang) if lang else get_language()
    _translate_widget_props(widget, lang=chosen_lang)
    for child in widget.findChildren(QWidget):
        _translate_widget_props(child, lang=chosen_lang)


class _I18nEventFilter(QObject):
    def eventFilter(self, watched, event):  # type: ignore[override]
        if isinstance(watched, QWidget) and event.type() == QEvent.Type.Show:
            localize_widget_tree(watched)
        return False


def install_i18n(app: QApplication) -> None:
    """Install global Qt event filter to localize showable widgets/dialogs."""
    global _EVENT_FILTER
    if _EVENT_FILTER is None:
        _EVENT_FILTER = _I18nEventFilter(app)
        app.installEventFilter(_EVENT_FILTER)
    _patch_qmessagebox()


def apply_language_to_app(lang: str | None = None) -> None:
    """Apply current/selected language to all currently opened top-level widgets."""
    chosen_lang = normalize_language(lang) if lang else get_language()
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        if isinstance(widget, QWidget):
            localize_widget_tree(widget, lang=chosen_lang)


def _patch_qmessagebox() -> None:
    global _QMESSAGEBOX_PATCHED
    if _QMESSAGEBOX_PATCHED:
        return

    def _wrap(name: str):
        original = getattr(QMessageBox, name)
        _QMESSAGEBOX_ORIGINALS[name] = original

        def _wrapped(*args, **kwargs):
            args_list = list(args)
            if len(args_list) >= 3:
                args_list[1] = trs(str(args_list[1] or ""))
                args_list[2] = trs(str(args_list[2] or ""))
            if "title" in kwargs:
                kwargs["title"] = trs(str(kwargs.get("title") or ""))
            if "text" in kwargs:
                kwargs["text"] = trs(str(kwargs.get("text") or ""))
            return original(*tuple(args_list), **kwargs)

        setattr(QMessageBox, name, staticmethod(_wrapped))

    for method in ("information", "warning", "critical", "question", "about"):
        _wrap(method)

    _QMESSAGEBOX_PATCHED = True
