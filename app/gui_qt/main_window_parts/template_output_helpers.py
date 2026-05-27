"""Template and output-path related helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QLineEdit

from app.domain import cmd_macros


def resolve_template_by_index(templates: list[dict[str, Any]], idx: int | None) -> dict[str, Any] | None:
    if idx is None or idx < 0 or idx >= len(templates):
        return None
    return templates[idx]


def template_output_suffix(template: dict[str, Any]) -> str:
    return str(template.get("output_suffix", "") or "")


def template_output_extension(template: dict[str, Any]) -> str:
    return str(template.get("output_extension", "") or "").strip().lstrip(".").lower()


def expand_template_command(
    template: dict[str, Any],
    input_path: str,
    output_path: str,
    fallback_fmt: str,
    ffprobe_bin: str,
) -> str:
    return cmd_macros.expand_all(
        str(template.get("cmd", "") or ""),
        input_path=input_path,
        output_path=output_path,
        fallback_fmt=fallback_fmt,
        ffprobe_bin=ffprobe_bin,
    )


def format_output_description(desc: Any) -> str:
    if isinstance(desc, str) and "—" in desc:
        return desc.split("—", 1)[1].strip()
    return str(desc or "")


def normalized_output_format(value: str | None, fallback: str = "mp4") -> str:
    cleaned = (value or "").strip()
    return cleaned or fallback


def update_output_path_extension(current_output: str, fmt: str) -> str:
    cleaned = (current_output or "").strip()
    if not cleaned:
        return ""
    current_path = Path(cleaned)
    return str(current_path.with_suffix(f".{fmt}"))


def set_line_edit_text_at_start(line_edit: QLineEdit, text: str) -> None:
    line_edit.blockSignals(True)
    line_edit.setText(text)
    line_edit.setCursorPosition(0)
    line_edit.blockSignals(False)


def compute_output_path_with_suffix(input_path: str, fmt: str, suffix: str | None) -> str:
    p = Path(input_path)

    if suffix is None:
        candidate = p.parent / f"{p.stem}.{fmt}"
        if not candidate.exists():
            return str(candidate)
        idx = 1
        while True:
            numbered = p.parent / f"{p.stem}_{idx:03d}.{fmt}"
            if not numbered.exists():
                return str(numbered)
            idx += 1

    return str(p.parent / f"{p.stem}{suffix}.{fmt}")
