#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
template_repository.py — FFmpeg sablon-kezelő (logika, GUI-mentes)
===================================================================
Sablonok kategóriánként (alkönyvtáranként) tárolva.

Könyvtárszerkezet:
    ~/Documents/FFBuilder/Templates/
        Videó/
            basic_mp4.json
            ...
        Audió/
            mp3.json
            ...
        DAW/
            daw.json
        Általános/        ← régebbi lapos sablonok migrációs célhelye

Publikus API:
    mgr = TemplateManager()
    mgr.templates                           → list[dict]  (lapos, globális)
    mgr.categories()                        → list[str]
    mgr.templates_in_category(cat)          → list[tuple[int, dict]]
    mgr.add(name, desc, cmd, ..., category) → int  (globális index)
    mgr.update(idx, name, desc, cmd)        → None
    mgr.delete(indices)                     → None
    mgr.move(from_idx, to_idx)              → None
    mgr.add_category(name)                  → bool
    mgr.rename_category(old, new)           → bool
    mgr.delete_category(name)               → bool
    mgr.move_to_category(idx, cat)          → None
    mgr.export_xml(indices, filepath)       → None
    mgr.suggested_export_name(indices)      → str
"""

from __future__ import annotations

import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Útvonalak
# ---------------------------------------------------------------------------

_USER_DIR    = Path.home() / "Documents" / "FFBuilder" / "Templates"
_DEFAULT_DIR = Path(__file__).parent / "default_templates"
_GENERAL_CAT = "Általános"

# ---------------------------------------------------------------------------
# Belső segédfüggvények
# ---------------------------------------------------------------------------

def _sanitize(name: str) -> str:
    """Fájlnév-biztos szöveg a sablon nevéből (max 40 kar)."""
    s = name.lower()
    s = re.sub(r"[^\w]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:40] or "template"


def _sanitize_dir(name: str) -> str:
    """Könyvtárnév-biztos szöveg (macOS + Windows kompatibilis)."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()
    return s or "Kategória"


def _next_filepath(directory: Path, name: str, exclude: Path | None = None) -> Path:
    """Ütközésmentes fájlnév számozott suffix-szel."""
    base = _sanitize(name)
    candidate = directory / f"{base}.json"
    i = 2
    while candidate.exists() and candidate != exclude:
        candidate = directory / f"{base}_{i}.json"
        i += 1
    return candidate


# ---------------------------------------------------------------------------
# TemplateManager
# ---------------------------------------------------------------------------

class TemplateManager:
    """
    Sablonok kezelése kategóriánként (alkönyvtáranként).

    Minden template dict tartalmaz egy belső `_category` mezőt (nem kerül
    a JSON fájlba), amely az alkönyvtár nevével egyezik meg.
    """

    def __init__(self):
        _USER_DIR.mkdir(parents=True, exist_ok=True)
        self._user_dir    = _USER_DIR
        self._default_dir = _DEFAULT_DIR
        self._files:     list[Path] = []
        self._templates: list[dict] = []
        self._load()

    # ------------------------------------------------------------------ properties

    @property
    def templates(self) -> list[dict]:
        """Lapos lista az összes sablonról (globális indexelés)."""
        return list(self._templates)

    # ------------------------------------------------------------------ category API

    def categories(self) -> list[str]:
        """Kategórianevek ábécé sorrendben (csak amelyekben van sablon, + üres mappák)."""
        # Sablonokból
        seen: set[str] = set()
        for t in self._templates:
            seen.add(t.get("_category", _GENERAL_CAT))
        # Üres alkönyvtárak is szerepelnek
        for d in self._user_dir.iterdir():
            if d.is_dir():
                seen.add(d.name)
        return sorted(seen)

    def templates_in_category(self, category: str) -> list[tuple[int, dict]]:
        """Adott kategória sablonjai: [(globális_index, template_dict), ...]."""
        return [
            (i, t) for i, t in enumerate(self._templates)
            if t.get("_category", _GENERAL_CAT) == category
        ]

    def add_category(self, name: str) -> bool:
        """Új üres kategória (alkönyvtár) létrehozása. True ha sikeres."""
        cat_dir = self._user_dir / _sanitize_dir(name)
        if cat_dir.exists():
            return False
        try:
            cat_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False

    def rename_category(self, old_name: str, new_name: str) -> bool:
        """Kategória átnevezése. True ha sikeres."""
        old_dir = self._user_dir / _sanitize_dir(old_name)
        new_dir = self._user_dir / _sanitize_dir(new_name)
        if not old_dir.exists() or new_dir.exists():
            return False
        try:
            old_dir.rename(new_dir)
        except Exception:
            return False
        # Memória frissítése
        for t in self._templates:
            if t.get("_category") == old_name:
                t["_category"] = new_name
        for i, f in enumerate(self._files):
            if f.parent == old_dir:
                self._files[i] = new_dir / f.name
        return True

    def delete_category(self, name: str) -> bool:
        """Üres kategória törlése. True ha sikeres."""
        cat_dir = self._user_dir / _sanitize_dir(name)
        if not cat_dir.exists():
            return False
        if list(cat_dir.glob("*.json")):
            return False  # nem üres
        try:
            cat_dir.rmdir()
            return True
        except Exception:
            return False

    def copy_to_category(self, idx: int, new_category: str) -> int:
        """Sablon másolása más kategóriába. Visszaadja az új globális indexet."""
        src = self._templates[idx]
        return self.add(
            src["name"],
            src.get("desc", ""),
            src.get("cmd", ""),
            src.get("output_suffix", ""),
            src.get("output_extension", ""),
            category=new_category,
        )

    def move_to_category(self, idx: int, new_category: str) -> None:
        """Sablon áthelyezése más kategóriába (fájl mozgatás + memória frissítés)."""
        new_cat_dir = self._user_dir / _sanitize_dir(new_category)
        new_cat_dir.mkdir(exist_ok=True)
        old_path = self._files[idx]
        new_path = _next_filepath(new_cat_dir, self._templates[idx]["name"])
        try:
            old_path.rename(new_path)
        except Exception:
            return
        self._files[idx] = new_path
        self._templates[idx]["_category"] = new_category

    # ------------------------------------------------------------------ CRUD

    def add(
        self,
        name: str,
        desc: str,
        cmd: str,
        output_suffix: str = "",
        output_extension: str = "",
        category: str = _GENERAL_CAT,
    ) -> int:
        """Új sablon hozzáadása. Visszaadja a globális indexet."""
        cat_dir = self._user_dir / _sanitize_dir(category)
        cat_dir.mkdir(exist_ok=True)
        path = _next_filepath(cat_dir, name)
        data = {
            "name": name,
            "desc": desc,
            "cmd": cmd,
            "output_suffix": output_suffix,
            "output_extension": output_extension,
            "order": len(self._templates),
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        data["_category"] = category
        self._files.append(path)
        self._templates.append(data)
        return len(self._templates) - 1

    def update(
        self,
        idx: int,
        name: str,
        desc: str,
        cmd: str,
        output_suffix: str = "",
        output_extension: str = "",
    ) -> None:
        """Sablon módosítása."""
        current_order = int(self._templates[idx].get("order", idx))
        cat = self._templates[idx].get("_category", _GENERAL_CAT)
        data = {
            "name": name,
            "desc": desc,
            "cmd": cmd,
            "output_suffix": output_suffix,
            "output_extension": output_extension,
            "order": current_order,
        }
        self._files[idx].write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        data["_category"] = cat
        self._templates[idx] = data

    def delete(self, indices: list[int]) -> None:
        """Sablonok törlése (fájl törlés + lista frissítés)."""
        for i in sorted(indices, reverse=True):
            try:
                self._files[i].unlink(missing_ok=True)
            except Exception:
                pass
            del self._files[i]
            del self._templates[i]
        self._persist_order()

    def move(self, from_idx: int, to_idx: int) -> None:
        """Sablon átrendezése (drag-and-drop)."""
        if from_idx == to_idx:
            return
        if not (0 <= from_idx < len(self._templates) and 0 <= to_idx < len(self._templates)):
            return
        file_item = self._files.pop(from_idx)
        tmpl_item = self._templates.pop(from_idx)
        self._files.insert(to_idx, file_item)
        self._templates.insert(to_idx, tmpl_item)
        self._persist_order()

    # ------------------------------------------------------------------ export

    def export_xml(self, indices: list[int], filepath: str) -> None:
        """Kijelölt sablonok exportálása XML fájlba."""
        root_el = ET.Element("ffmpeg_templates")
        for el in indices:
            t = self._templates[el]
            te = ET.SubElement(root_el, "template")
            ET.SubElement(te, "name").text = t["name"]
            ET.SubElement(te, "desc").text = t["desc"]
            ET.SubElement(te, "cmd").text  = t["cmd"]
            if t.get("output_suffix"):
                ET.SubElement(te, "output_suffix").text = t["output_suffix"]
            if t.get("output_extension"):
                ET.SubElement(te, "output_extension").text = t["output_extension"]
        tree = ET.ElementTree(root_el)
        ET.indent(tree, space="  ")
        tree.write(filepath, encoding="utf-8", xml_declaration=True)

    def suggested_export_name(self, indices: list[int]) -> str:
        """Javasolt fájlnév az exporthoz (kiterjesztés nélkül)."""
        if len(indices) == 1:
            return _sanitize(self._templates[indices[0]]["name"])
        return "ffmpeg_templates"

    # ------------------------------------------------------------------ load / seed / migrate

    def _load(self) -> None:
        # 1. Migráció: régi lapos .json fájlok → Általános/
        flat_files = [f for f in self._user_dir.iterdir()
                      if f.is_file() and f.suffix == ".json"]
        if flat_files:
            gen_dir = self._user_dir / _sanitize_dir(_GENERAL_CAT)
            gen_dir.mkdir(exist_ok=True)
            for f in flat_files:
                dest = gen_dir / f.name
                if dest.exists():
                    dest = _next_filepath(gen_dir, f.stem)
                try:
                    f.rename(dest)
                except Exception:
                    pass

        # 2. Ha még nincs semmi → alapértelmezett sablonok seedelése
        all_json = list(self._user_dir.rglob("*.json"))
        if not all_json:
            self._seed_from_defaults()
            all_json = list(self._user_dir.rglob("*.json"))

        # 3. Betöltés alkönyvtárakból
        entries: list[tuple[Path, dict, str, int, int]] = []
        for idx, f in enumerate(sorted(all_json)):
            try:
                rel_parts = f.relative_to(self._user_dir).parts
            except ValueError:
                continue
            if len(rel_parts) < 2:
                continue  # root szintű fájl (nem kellene előfordulni a migráció után)
            category = rel_parts[0]  # alkönyvtár neve = kategória neve

            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if not (isinstance(data, dict) and "name" in data):
                    continue
                raw_order = data.get("order")
                if isinstance(raw_order, int):
                    order = raw_order
                elif isinstance(raw_order, str) and raw_order.isdigit():
                    order = int(raw_order)
                else:
                    order = 100_000 + idx
                normalized = {
                    "name":             data["name"],
                    "desc":             data.get("desc", ""),
                    "cmd":              data.get("cmd", ""),
                    "output_suffix":    data.get("output_suffix", ""),
                    "output_extension": data.get("output_extension", ""),
                    "order":            order,
                    "_category":        category,
                }
                entries.append((f, normalized, category, order, idx))
            except Exception:
                pass

        # Rendezés: kategória ábécé sorrendben, azon belül order szerint
        entries.sort(key=lambda e: (e[2], e[3], e[4]))

        self._files = []
        self._templates = []
        for new_order, (f, data, _cat, _order, _idx) in enumerate(entries):
            data["order"] = new_order
            to_save = {k: v for k, v in data.items() if not k.startswith("_")}
            try:
                f.write_text(json.dumps(to_save, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            self._files.append(f)
            self._templates.append(data)

    def _persist_order(self) -> None:
        """Az aktuális listasorrend alapján frissíti az order mezőket."""
        for idx, f in enumerate(self._files):
            t = self._templates[idx]
            t["order"] = idx
            to_save = {k: v for k, v in t.items() if not k.startswith("_")}
            try:
                f.write_text(json.dumps(to_save, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

    def _seed_from_defaults(self) -> None:
        """Alapértelmezett sablonok másolása a forrás almappa-struktúrával."""
        if not self._default_dir.exists():
            return
        for src in sorted(self._default_dir.rglob("*.json")):
            try:
                cat = src.parent.name  # almappa neve = kategória neve
                cat_dir = self._user_dir / cat
                cat_dir.mkdir(exist_ok=True)
                dst = cat_dir / src.name
                if not dst.exists():
                    shutil.copy2(src, dst)
            except Exception:
                pass
