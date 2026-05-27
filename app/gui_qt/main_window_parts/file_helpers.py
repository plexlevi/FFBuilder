"""File selection, metadata formatting and file-list mutation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.shared.i18n import trs


def default_file_info_save_path(input_path: str) -> str:
    cleaned = (input_path or "").strip()
    if not cleaned:
        return "file_info.txt"

    p = Path(cleaned)
    return str(p.parent / f"{p.stem}_info.txt")


def build_metadata_rows(
    info: dict[str, Any],
    meta_fields: list[tuple[str, str]],
    loudness_keys: set[str],
) -> list[tuple[str, str]]:
    is_loading = bool(info.get("__loading__"))
    rows: list[tuple[str, str]] = []
    for label, key in meta_fields:
        value = str(info.get(key, "—"))
        if is_loading and key in loudness_keys and value in {"—", "unknown", ""}:
            value = trs("Analysis in progress...")
        rows.append((trs(label), value))
    return rows


def format_file_info_text(info: dict[str, Any], meta_fields: list[tuple[str, str]], loudness_keys: set[str]) -> str:
    lines: list[str] = []
    for label, value in build_metadata_rows(info, meta_fields, loudness_keys):
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


def resolve_current_file_info_text(
    current_file_info: dict[str, Any],
    meta_fields: list[tuple[str, str]],
    loudness_keys: set[str],
) -> dict[str, Any]:
    if not current_file_info:
        return {
            "text": None,
            "error_title": trs("No file"),
            "error_text": trs("Select a file first."),
        }
    return {
        "text": format_file_info_text(current_file_info, meta_fields, loudness_keys),
        "error_title": None,
        "error_text": None,
    }


def resolve_audio_analysis_request(
    current_file_info: dict[str, Any],
    ffmpeg_bin: str | None,
    ffprobe_bin: str | None,
) -> dict[str, Any]:
    if not current_file_info:
        return {"path": None, "error_title": trs("No file"), "error_text": trs("Select a file first.")}

    path = str(current_file_info.get("path", "") or "")
    if not path:
        return {"path": None, "error_title": trs("No file"), "error_text": trs("Select a file first.")}

    if not ffmpeg_bin or not ffprobe_bin:
        return {
            "path": None,
            "error_title": trs("FFmpeg missing"),
            "error_text": trs("FFmpeg and ffprobe are required for audio analysis."),
        }

    return {"path": path, "error_title": None, "error_text": None}


def resolve_selected_file_for_open(files: list[dict[str, Any]], idx: int) -> dict[str, Any]:
    if idx < 0 or idx >= len(files):
        return {"path": None, "error_title": trs("No file"), "error_text": trs("Select a file first.")}

    path = str(files[idx].get("path", "") or "").strip()
    if not path:
        return {
            "path": None,
            "error_title": trs("No file"),
            "error_text": trs("The selected item has no associated path."),
        }

    file_path = Path(path)
    if not file_path.exists():
        return {
            "path": None,
            "error_title": trs("File missing"),
            "error_text": trs("File not found:\n{var}").replace("{var}", path),
        }

    return {"path": str(file_path), "error_title": None, "error_text": None}


def resolve_file_rows_for_deletion(
    selected_rows: list[int],
    current_row: int,
    file_count: int,
) -> list[int]:
    rows = sorted(set(selected_rows), reverse=True)
    if not rows:
        rows = [current_row]
    return [r for r in rows if 0 <= r < file_count]


def delete_files_by_rows(files: list[dict[str, Any]], rows: list[int]) -> dict[str, Any]:
    if not rows:
        return {"removed_paths": [], "new_index": None, "has_files": bool(files)}

    first_row = min(rows)
    removed_paths: list[str] = []
    for idx in rows:
        removed = files.pop(idx)
        removed_path = str(removed.get("path", "") or "")
        if removed_path:
            removed_paths.append(removed_path)

    if not files:
        return {"removed_paths": removed_paths, "new_index": None, "has_files": False}

    new_index = min(first_row, len(files) - 1)
    return {"removed_paths": removed_paths, "new_index": new_index, "has_files": True}


def remove_paths_from_loudness_state(
    pending_loudness_paths: set[str],
    loudness_progress: dict[str, float],
    removed_paths: list[str],
) -> None:
    for removed_path in removed_paths:
        pending_loudness_paths.discard(removed_path)
        loudness_progress.pop(removed_path, None)


def resolve_selected_file_info(files: list[dict[str, Any]], idx: int) -> dict[str, Any] | None:
    if idx < 0 or idx >= len(files):
        return None
    return files[idx]
