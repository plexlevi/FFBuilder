#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
settings_manager.py — Alkalmazás-beállítások kezelése (FFBuilder core)
====================================================================
Beállítások mentése / betöltése JSON fájlba.

Publikus API:
    get_settings()  → dict
    save_settings(data: dict) → None
    get_output_suffix(template_suffix: str = "") → str | None
        None = számozás mód (a hívó fél kezeli)
"""

import json
from pathlib import Path


_SETTINGS_PATH = (
    Path.home() / "Documents" / "FFBuilder" / "ffbuilder_settings.json"
)

_DEFAULTS: dict = {
    "output_naming_mode": "template",
    "custom_suffix": "_converted",
    "sound_on_success": True,
    "sound_on_error": False,
    "save_pane_sizes": True,
    "window_size": "961x766",
    "splitter_main_horizontal": "331,606",
    "splitter_main_vertical": "529,147",
    "splitter_files_metadata": "133,349",
    "splitter_templates_details": "253,72",
    "auto_apply_last_preset": False,
    "last_used_preset_name": "",
    "last_open_dir": "",
    "auto_check_updates": True,
    "skip_update_version": "",
    "conversion_queue_items": [],
    "auto_ebu_analysis": False
}

def _ensure_settings_file() -> None:
    """Create the Documents settings file from defaults if it does not exist yet."""
    if _SETTINGS_PATH.exists():
        return
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(
        json.dumps(_DEFAULTS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_settings() -> dict:
    """Betölti a beállításokat; hiányzó kulcsokhoz visszaadja az alapértéket."""
    try:
        if _SETTINGS_PATH.exists():
            data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {**_DEFAULTS, **data}
        else:
            _ensure_settings_file()
    except Exception:
        pass
    return dict(_DEFAULTS)


def save_settings(data: dict) -> None:
    """Elmenti a beállításokat JSON fájlba (merge az aktuális értékekkel)."""
    current = get_settings()
    merged = {**current, **data}
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_output_suffix(template_suffix: str = "") -> str | None:
    """
    Visszaadja a kimeneti fájlnévhez hozzáfűzendő utótagot.

    Visszatérési érték:
        str  — a suffix (pl. "_h264", "_converted")
        None — számozás mód; a hívó fél felelős a számozás kezeléséért
    """
    settings = get_settings()
    mode = settings.get("output_naming_mode", "template")
    if mode == "template":
        return template_suffix
    if mode == "custom":
        return settings.get("custom_suffix", "_converted")
    return None
