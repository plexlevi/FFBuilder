"""Conversion history log — writes to ~/Documents/FFBuilder/conversions.log (JSONL)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_LOG_PATH = Path.home() / "Documents" / "FFBuilder" / "conversions.log"


def append_entry(input_path: str, output_path: str, status: str, exit_code: int, console_output: str = "") -> None:
    """Append one conversion record to the log file."""
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "input": input_path,
        "output": output_path,
        "status": status,
        "exit_code": exit_code,
        "console_output": console_output if len(console_output) <= 200_000 else console_output[-200_000:],
    }
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_entries() -> list[dict]:
    """Return all entries in oldest-first order."""
    if not _LOG_PATH.exists():
        return []
    entries: list[dict] = []
    with _LOG_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def delete_entries(indices: list[int]) -> None:
    """Delete entries by their 0-based (oldest-first) indices."""
    entries = read_entries()
    for idx in sorted(set(indices), reverse=True):
        if 0 <= idx < len(entries):
            entries.pop(idx)
    _write_entries(entries)


def clear_all() -> None:
    """Delete the entire log file."""
    if _LOG_PATH.exists():
        _LOG_PATH.unlink()


def _write_entries(entries: list[dict]) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
