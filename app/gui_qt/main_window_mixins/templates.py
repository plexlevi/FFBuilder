"""Template/category UI and data-flow behavior extracted from MainWindow."""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMenu, QMessageBox

from app.domain.ffmpeg_params import CONTAINER_FORMATS
from app.gui_qt.dialogs.template_editor_dialog import TemplateEditorDialog
from app.shared import settings as settings_manager


class TemplateCategoryMixin:
    def _populate_output_formats(self) -> None:
        self.output_format_combo.clear()
        for ext, desc in CONTAINER_FORMATS:
            self.output_format_combo.addItem(ext, desc)
        self.output_format_combo.setCurrentText("mp4")
        self._on_output_format_changed()

    def _current_category(self) -> str | None:
        """Az aktuálisan kiválasztott kategória neve, vagy None."""
        row = self.categories_list.currentRow()
        cats = self._template_manager.categories()
        if 0 <= row < len(cats):
            return cats[row]
        return None

    def _load_templates(self) -> None:
        cats = self._template_manager.categories()

        self.categories_list.blockSignals(True)
        self.categories_list.clear()
        for cat in cats:
            self.categories_list.addItem(cat)
        self.categories_list.blockSignals(False)

        if not cats:
            self.templates_list.clear()
            self._current_template_idx = None
            return

        settings = settings_manager.get_settings()
        last_name = ""
        if settings.get("auto_apply_last_preset", True):
            last_name = (settings.get("last_used_preset_name", "") or "").strip()

        target_cat_row = 0
        target_tmpl_row = 0
        if last_name:
            for g_idx, t in enumerate(self._template_manager.templates):
                if t.get("name") == last_name:
                    found_cat = t.get("_category", "Általános")
                    if found_cat in cats:
                        target_cat_row = cats.index(found_cat)
                        for local_row, (gi, _) in enumerate(
                            self._template_manager.templates_in_category(found_cat)
                        ):
                            if gi == g_idx:
                                target_tmpl_row = local_row
                                break
                    break

        self.categories_list.setCurrentRow(target_cat_row)
        if self.templates_list.count() > target_tmpl_row:
            self.templates_list.setCurrentRow(target_tmpl_row)
        elif self.templates_list.count() > 0:
            self.templates_list.setCurrentRow(0)
        if settings.get("auto_apply_last_preset", True):
            self._apply_template()

    def _reload_templates(self, select_cat: str | None = None, select_tmpl_row: int | None = None) -> None:
        """Lista újratöltése szerkesztés / törlés / áthelyezés után."""
        cats = self._template_manager.categories()
        prev_cat = select_cat or self._current_category()

        self.categories_list.blockSignals(True)
        self.categories_list.clear()
        for cat in cats:
            self.categories_list.addItem(cat)
        self.categories_list.blockSignals(False)

        if not cats:
            self.templates_list.clear()
            self._current_template_idx = None
            self.template_desc_label.setText("Válassz egy sablont.")
            return

        cat_row = 0
        if prev_cat and prev_cat in cats:
            cat_row = cats.index(prev_cat)
        self.categories_list.setCurrentRow(cat_row)

        if select_tmpl_row is not None and select_tmpl_row < self.templates_list.count():
            self.templates_list.setCurrentRow(select_tmpl_row)

    def _on_category_selected(self, row: int) -> None:
        cats = self._template_manager.categories()
        if row < 0 or row >= len(cats):
            self.templates_list.blockSignals(True)
            self.templates_list.clear()
            self.templates_list.blockSignals(False)
            self._current_template_idx = None
            self.template_desc_label.setText("Válassz egy sablont.")
            return
        cat = cats[row]
        cat_templates = self._template_manager.templates_in_category(cat)
        self.templates_list.blockSignals(True)
        self.templates_list.clear()
        for _, t in cat_templates:
            self.templates_list.addItem(t["name"])
        self.templates_list.blockSignals(False)
        if self.templates_list.count() > 0:
            self.templates_list.setCurrentRow(0)
        else:
            self._current_template_idx = None
            self.template_desc_label.setText("Válassz egy sablont.")

    def _on_template_selected(self, local_row: int) -> None:
        cat = self._current_category()
        if local_row < 0 or cat is None:
            self._current_template_idx = None
            self.template_desc_label.setText("Válassz egy sablont.")
            return
        cat_templates = self._template_manager.templates_in_category(cat)
        if local_row >= len(cat_templates):
            return
        global_idx, template = cat_templates[local_row]
        self._current_template_idx = global_idx
        self.template_desc_label.setText(template.get("desc", ""))
        self._refresh_output_path_from_input()
        self._refresh_command()

    def _new_template(self) -> None:
        cat = self._current_category() or "Általános"
        dlg = TemplateEditorDialog(parent=self)
        if not dlg.exec():
            return
        data = dlg.values()
        idx = self._template_manager.add(
            data["name"], data["desc"], data["cmd"],
            data.get("output_suffix", ""), data.get("output_extension", ""),
            category=cat,
        )
        cat_templates = self._template_manager.templates_in_category(cat)
        local_row = next((r for r, (gi, _) in enumerate(cat_templates) if gi == idx), 0)
        self._reload_templates(select_cat=cat, select_tmpl_row=local_row)

    def _on_template_rows_moved(self, _parent, start: int, end: int, _dest_parent, dest_row: int) -> None:
        if self._applying_template_move:
            return
        if start != end:
            return
        if dest_row == start or dest_row == start + 1:
            return

        cat = self._current_category()
        if cat is None:
            return
        cat_templates = self._template_manager.templates_in_category(cat)
        if start >= len(cat_templates):
            return

        global_from = cat_templates[start][0]
        to_local = dest_row if dest_row < start else dest_row - 1
        if to_local < 0 or to_local >= len(cat_templates):
            return
        global_to = cat_templates[to_local][0]

        self._template_manager.move(global_from, global_to)
        self._applying_template_move = True
        try:
            self._reload_templates(select_cat=cat, select_tmpl_row=to_local)
        finally:
            self._applying_template_move = False

    def _show_template_context_menu(self, pos) -> None:
        row = self.templates_list.indexAt(pos).row()
        if row >= 0 and not self.templates_list.item(row).isSelected():
            self.templates_list.clearSelection()
            self.templates_list.setCurrentRow(row)
            self.templates_list.item(row).setSelected(True)

        menu = QMenu(self.templates_list)
        selected_rows = sorted({idx.row() for idx in self.templates_list.selectedIndexes()})

        add_action = menu.addAction("Új sablon")
        menu.addSeparator()

        edit_action = menu.addAction("Szerkesztés")
        edit_action.setEnabled(len(selected_rows) == 1)

        duplicate_action = menu.addAction("Duplikálás")
        duplicate_action.setEnabled(len(selected_rows) == 1)

        move_menu = menu.addMenu("Áthelyezés mappába...")
        cats = self._template_manager.categories()
        current_cat = self._current_category()
        move_actions: dict = {}
        for cat in cats:
            if cat != current_cat:
                a = move_menu.addAction(cat)
                move_actions[a] = cat
        move_menu.setEnabled(bool(move_actions) and len(selected_rows) == 1)

        export_action = menu.addAction("Exportálás")
        menu.addSeparator()
        delete_action = menu.addAction("Törlés")
        action = menu.exec(self.templates_list.mapToGlobal(pos))
        if action == edit_action:
            self._edit_template()
        elif action == duplicate_action:
            self._duplicate_template()
        elif action == delete_action:
            self._delete_template()
        elif action == export_action:
            self._export_template()
        elif action == add_action:
            self._new_template()
        elif action in move_actions:
            self._move_template_to_category(move_actions[action])

    def _duplicate_template(self) -> None:
        selected_rows = sorted({idx.row() for idx in self.templates_list.selectedIndexes()})
        if len(selected_rows) != 1:
            return

        local_row = selected_rows[0]
        cat = self._current_category()
        if cat is None:
            return

        cat_templates = self._template_manager.templates_in_category(cat)
        if local_row >= len(cat_templates):
            return

        _global_idx, current = cat_templates[local_row]
        base_name = str(current.get("name", "")).strip() or "Új sablon"
        copy_name = f"{base_name} (másolat)"

        new_idx = self._template_manager.add(
            copy_name,
            str(current.get("desc", "")),
            str(current.get("cmd", "")),
            str(current.get("output_suffix", "")),
            str(current.get("output_extension", "")),
            category=cat,
        )

        cat_templates = self._template_manager.templates_in_category(cat)
        new_local_row = next((r for r, (gi, _) in enumerate(cat_templates) if gi == new_idx), local_row)
        self._reload_templates(select_cat=cat, select_tmpl_row=new_local_row)
        self._set_status(f"Sablon duplikálva: {copy_name}", 2500)

    def _edit_template(self) -> None:
        selected_rows = sorted({idx.row() for idx in self.templates_list.selectedIndexes()})
        if len(selected_rows) != 1:
            return
        local_row = selected_rows[0]
        cat = self._current_category()
        if cat is None:
            return
        cat_templates = self._template_manager.templates_in_category(cat)
        if local_row >= len(cat_templates):
            return
        global_idx, current = cat_templates[local_row]
        dlg = TemplateEditorDialog(template=current, parent=self)
        if not dlg.exec():
            return
        data = dlg.values()
        self._template_manager.update(
            global_idx, data["name"], data["desc"], data["cmd"],
            data.get("output_suffix", ""), data.get("output_extension", ""),
        )
        self._reload_templates(select_cat=cat, select_tmpl_row=local_row)
        if self._current_template_idx == global_idx:
            self._refresh_command()

    def _delete_template(self) -> None:
        selected_rows = sorted({idx.row() for idx in self.templates_list.selectedIndexes()})
        if not selected_rows:
            return
        cat = self._current_category()
        if cat is None:
            return
        cat_templates = self._template_manager.templates_in_category(cat)
        global_indices = [cat_templates[r][0] for r in selected_rows if r < len(cat_templates)]
        if not global_indices:
            return
        names = [self._template_manager.templates[gi].get("name", "") for gi in global_indices]
        if len(names) == 1:
            prompt = f"Biztosan törlöd ezt a sablont?\n\n{names[0]}"
        else:
            prompt = f"Biztosan törlöd a kijelölt {len(names)} sablont?"
        ok = QMessageBox.question(self, "Törlés", prompt)
        if ok != QMessageBox.Yes:
            return
        self._template_manager.delete(global_indices)
        last_used = (settings_manager.get_settings().get("last_used_preset_name", "") or "").strip()
        if last_used and last_used in names:
            settings_manager.save_settings({"last_used_preset_name": ""})
        self._reload_templates(select_cat=cat)

    def _export_template(self) -> None:
        selected_rows = sorted({idx.row() for idx in self.templates_list.selectedIndexes()})
        if not selected_rows:
            return
        cat = self._current_category()
        if cat is None:
            return
        cat_templates = self._template_manager.templates_in_category(cat)
        global_indices = [cat_templates[r][0] for r in selected_rows if r < len(cat_templates)]
        if not global_indices:
            return
        initial = self._template_manager.suggested_export_name(global_indices) + ".xml"
        path, _ = QFileDialog.getSaveFileName(self, "Sablon export", initial, "XML files (*.xml)")
        if not path:
            return
        self._template_manager.export_xml(global_indices, path)

    def _move_template_to_category(self, target_cat: str) -> None:
        selected_rows = sorted({idx.row() for idx in self.templates_list.selectedIndexes()})
        if len(selected_rows) != 1:
            return
        local_row = selected_rows[0]
        cat = self._current_category()
        if cat is None:
            return
        cat_templates = self._template_manager.templates_in_category(cat)
        if local_row >= len(cat_templates):
            return
        global_idx = cat_templates[local_row][0]
        self._template_manager.move_to_category(global_idx, target_cat)
        self._reload_templates(select_cat=cat)

    def _on_template_dropped_on_category(self, local_row: int, target_cat: str, copy: bool) -> None:
        """Callback: sablon húzva a kategórialistára (move vagy Alt=copy)."""
        cat = self._current_category()
        if cat is None:
            return
        if target_cat == cat and not copy:
            return
        cat_templates = self._template_manager.templates_in_category(cat)
        if local_row < 0 or local_row >= len(cat_templates):
            return
        global_idx = cat_templates[local_row][0]
        if copy:
            self._template_manager.copy_to_category(global_idx, target_cat)
            self._reload_templates(select_cat=cat)
        else:
            self._template_manager.move_to_category(global_idx, target_cat)
            self._reload_templates(select_cat=cat)

    def _show_category_context_menu(self, pos) -> None:
        row = self.categories_list.indexAt(pos).row()
        if row >= 0:
            self.categories_list.setCurrentRow(row)
        cats = self._template_manager.categories()

        menu = QMenu(self.categories_list)
        new_action = menu.addAction("Új mappa")
        rename_action = menu.addAction("Átnevezés")
        rename_action.setEnabled(row >= 0)
        delete_action = menu.addAction("Törlés")
        delete_action.setEnabled(row >= 0)
        action = menu.exec(self.categories_list.mapToGlobal(pos))

        if action == new_action:
            self._new_category()
        elif action == rename_action and row >= 0:
            self._rename_category(cats[row])
        elif action == delete_action and row >= 0:
            self._delete_category(cats[row])

    def _new_category(self) -> None:
        name, ok = QInputDialog.getText(self, "Új mappa", "Mappa neve:")
        if not ok or not name.strip():
            return
        if not self._template_manager.add_category(name.strip()):
            QMessageBox.warning(self, "Hiba", "Ez a mappa már létezik.")
            return
        self._reload_templates(select_cat=name.strip())

    def _rename_category(self, old_name: str) -> None:
        new_name, ok = QInputDialog.getText(self, "Átnevezés", "Új név:", text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        if not self._template_manager.rename_category(old_name, new_name.strip()):
            QMessageBox.warning(self, "Hiba", "Átnevezés sikertelen (esetleg már létezik ilyen nevű mappa).")
            return
        self._reload_templates(select_cat=new_name.strip())

    def _delete_category(self, name: str) -> None:
        cat_templates = self._template_manager.templates_in_category(name)
        if cat_templates:
            QMessageBox.warning(
                self, "Nem üres mappa",
                f'A „{name}” mappa {len(cat_templates)} sablont tartalmaz.\n'
                "Előbb helyezd át vagy töröld a sablonokat.",
            )
            return
        reply = QMessageBox.question(self, "Mappa törlése", f'Biztosan törlöd a „{name}” mappát?')
        if reply != QMessageBox.Yes:
            return
        if not self._template_manager.delete_category(name):
            QMessageBox.warning(self, "Hiba", "Törlés sikertelen.")
            return
        self._reload_templates()
