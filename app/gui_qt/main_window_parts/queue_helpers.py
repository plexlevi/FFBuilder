"""Queue item models and queue-flow helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.shared.i18n import trs


@dataclass
class _ConversionQueueItem:
    queue_id: int
    label: str
    input_path: str
    output_path: str
    command: str
    duration_seconds: float = 0.0
    status: str = "Waiting"
    progress: float = 0.0
    exit_code: int | None = None


def apply_queue_item_finish_state(
    queue_item: _ConversionQueueItem,
    exit_code: int,
    user_stopped: bool,
) -> dict[str, Any]:
    queue_item.exit_code = exit_code
    if exit_code == 0:
        queue_item.status = "Done"
        queue_item.progress = 1.0
        return {
            "status_text": trs("✅ Done: {var}").replace("{var}", queue_item.label),
            "timeout_ms": 3000,
            "play_sound": None,
            "start_next_queue": True,
        }

    if user_stopped:
        queue_item.status = "Stopped"
        return {
            "status_text": trs("⛔ Queue stopped"),
            "timeout_ms": 4000,
            "play_sound": None,
            "start_next_queue": False,
        }

    queue_item.status = f"Error ({exit_code})"
    queue_item.progress = max(0.0, min(1.0, queue_item.progress))
    return {
        "status_text": trs("❌ Error in queue: {var}").replace("{var}", queue_item.label),
        "timeout_ms": 5000,
        "play_sound": "error",
        "start_next_queue": True,
    }


def apply_queue_item_progress(queue_item: _ConversionQueueItem, pct: float) -> None:
    queue_item.progress = max(0.0, min(1.0, pct / 100.0))


def get_next_waiting_queue_item(queue_items: Iterable[_ConversionQueueItem]) -> _ConversionQueueItem | None:
    return next((item for item in queue_items if item.status == "Waiting"), None)


def queue_has_error_items(queue_items: Iterable[_ConversionQueueItem]) -> bool:
    return any(item.status.startswith("Error") for item in queue_items)


def apply_invalid_queue_item_state(queue_item: _ConversionQueueItem, validation_error: str) -> dict[str, Any]:
    queue_item.status = "Invalid command"
    queue_item.exit_code = -1
    queue_item.progress = 0.0
    return {
        "status_text": trs("⚠️ Queue item skipped: {var} ({var})").replace("{var}", queue_item.label, 1).replace("{var}", validation_error, 1),
        "timeout_ms": 7000,
    }
